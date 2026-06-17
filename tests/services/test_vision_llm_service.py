import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from pixelle_video.models.llm_interaction_trace import LLMTraceContext, LLMTraceRequiredError
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


class _FakeRecorder:
    def __init__(self):
        self.records = []

    async def record_interaction(self, **kwargs):
        self.records.append(kwargs)


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
