import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from pixelle_video.config import config_manager
from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    LLMTraceRecordingError,
    LLMTraceRequiredError,
)
from pixelle_video.models.llm_response import LLMResponseContractError
from pixelle_video.services.vision_llm_service import VisionLLMService


def _data_url() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 255, 255)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )


class _FakeClient:
    def __init__(self):
        self.base_url = "https://example.test/v1"
        self.completions = _FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class _FailingCompletions:
    async def create(self, **kwargs):
        raise RuntimeError(
            "provider echoed payload data:image/png;base64,AAAA "
            "/home/user/secret.png C:\\Users\\ai\\secret.png"
        )


class _FailingClient:
    def __init__(self):
        self.base_url = "https://example.test/v1"
        self.completions = _FailingCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


class _FakeRecorder:
    def __init__(self):
        self.records = []

    async def record_interaction(self, **kwargs):
        self.records.append(kwargs)


class _FailingRecorder:
    async def record_interaction(self, **kwargs):
        raise OSError("trace store unavailable")


def _trace_context() -> LLMTraceContext:
    return LLMTraceContext(
        workspace_id="workspace",
        task_id="task",
        operation="reference_image_vision",
    )


@pytest.mark.asyncio
async def test_vision_llm_service_records_redacted_trace(monkeypatch):
    service = VisionLLMService({"force_supports_vision": True})
    client = _FakeClient()
    monkeypatch.setattr(service, "_create_client", lambda **kwargs: client)
    recorder = _FakeRecorder()
    data_url = _data_url()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请返回 JSON"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    content = await service.chat(
        messages=messages,
        model="qwen-vl-max",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        trace_context=_trace_context(),
        trace_recorder=recorder,
    )

    assert content == '{"ok": true}'
    assert client.completions.calls[0]["messages"] == messages
    recorded_request = recorder.records[0]["request_payload"]
    request_json = json.dumps(recorded_request, ensure_ascii=False)
    assert "base64," not in request_json
    assert "data:image" not in request_json
    assert "<redacted:data-url>" in request_json
    assert "sha256" in request_json
    assert recorder.records[0]["status"] == "success"
    assert recorder.records[0]["provider"] == "https://example.test"


@pytest.mark.asyncio
async def test_vision_llm_service_redacts_provider_error_trace(monkeypatch):
    service = VisionLLMService({"force_supports_vision": True})
    monkeypatch.setattr(service, "_create_client", lambda **kwargs: _FailingClient())
    recorder = _FakeRecorder()

    with pytest.raises(RuntimeError):
        await service.chat(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请返回 JSON"},
                        {"type": "image_url", "image_url": {"url": _data_url()}},
                    ],
                }
            ],
            model="qwen-vl-max",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            trace_context=_trace_context(),
            trace_recorder=recorder,
        )

    assert recorder.records[0]["status"] == "error"
    error_message = recorder.records[0]["error_message"]
    assert "base64," not in error_message
    assert "data:image" not in error_message
    assert "/home/user" not in error_message
    assert "C:\\" not in error_message
    assert "<redacted:data-url>" in error_message
    assert "<redacted:absolute-path>" in error_message


@pytest.mark.asyncio
async def test_vision_llm_service_rejects_empty_provider_response_and_records_error(monkeypatch):
    service = VisionLLMService({"force_supports_vision": True})
    client = _FakeClient()

    async def empty_response(**kwargs):
        return SimpleNamespace(choices=[], usage=None)

    monkeypatch.setattr(client.completions, "create", empty_response)
    monkeypatch.setattr(service, "_create_client", lambda **kwargs: client)
    recorder = _FakeRecorder()

    with pytest.raises(LLMResponseContractError):
        await service.chat(
            messages=[{"role": "user", "content": "describe"}],
            model="qwen-vl-max",
            trace_context=_trace_context(),
            trace_recorder=recorder,
        )

    assert len(recorder.records) == 1
    assert recorder.records[0]["status"] == "error"
    assert recorder.records[0]["response_payload"]["content"] is None


@pytest.mark.asyncio
async def test_vision_llm_service_trace_failure_is_fail_closed(monkeypatch):
    service = VisionLLMService({"force_supports_vision": True})
    monkeypatch.setattr(service, "_create_client", lambda **kwargs: _FakeClient())

    with pytest.raises(LLMTraceRecordingError):
        await service.chat(
            messages=[{"role": "user", "content": "describe"}],
            model="qwen-vl-max",
            trace_context=_trace_context(),
            trace_recorder=_FailingRecorder(),
        )


@pytest.mark.asyncio
async def test_vision_llm_service_reuses_client_and_redacts_sensitive_extras(monkeypatch):
    service = VisionLLMService({"force_supports_vision": True})
    client = _FakeClient()
    create_calls = 0

    def create_client(**kwargs):
        nonlocal create_calls
        create_calls += 1
        return client

    monkeypatch.setattr(service, "_create_client", create_client)
    recorder = _FakeRecorder()
    extra_headers = {
        "Authorization": "Bearer wire-secret",
        "nested": {
            "api_key": "nested-secret",
            "client_secret": "oauth-secret",
        },
    }
    for _ in range(2):
        await service.chat(
            messages=[{"role": "user", "content": "describe"}],
            model="qwen-vl-max",
            trace_context=_trace_context(),
            trace_recorder=recorder,
            extra_headers=extra_headers,
        )

    assert create_calls == 1
    assert client.completions.calls[0]["extra_headers"] is extra_headers
    traced_extras = recorder.records[0]["request_payload"]["extra_parameters"]
    assert traced_extras["extra_headers"]["Authorization"] == "[REDACTED]"
    assert traced_extras["extra_headers"]["nested"]["api_key"] == "[REDACTED]"
    assert traced_extras["extra_headers"]["nested"]["client_secret"] == "[REDACTED]"

    await service.aclose()
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_vision_llm_service_requires_trace_objects():
    service = VisionLLMService({"force_supports_vision": True})

    with pytest.raises(LLMTraceRequiredError):
        await service.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="qwen-vl-max",
        )


@pytest.mark.asyncio
async def test_vision_llm_service_rejects_unknown_text_model():
    service = VisionLLMService()

    with pytest.raises(ValueError, match="does not support image messages"):
        await service.chat(
            messages=[{"role": "user", "content": "hello"}],
            model="deepseek-chat",
            trace_context=_trace_context(),
            trace_recorder=_FakeRecorder(),
        )


def test_constructor_config_overrides_global_vision_config(monkeypatch):
    def fake_get(key, default=None):
        if key == "vision_llm":
            return {
                "model": "deepseek-chat",
                "force_supports_vision": None,
                "temperature": 0.9,
            }
        return default

    monkeypatch.setattr(config_manager, "get", fake_get)

    service = VisionLLMService(
        {
            "model": "qwen-vl-max",
            "force_supports_vision": True,
        }
    )

    resolved = service._get_vision_config()
    assert resolved["model"] == "qwen-vl-max"
    assert resolved["force_supports_vision"] is True
    assert resolved["temperature"] == 0.9
