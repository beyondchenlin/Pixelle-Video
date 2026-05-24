from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pixelle_video.models.llm_interaction_trace import LLMTraceContext, LLMTraceRecordingError
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.llm_service import LLMService


class MovieReview(BaseModel):
    title: str
    rating: int


class FakeRawPayloadStore:
    def __init__(self):
        self.payloads = []

    async def put_json(self, workspace_id, payload):
        key = f"raw-payloads/{workspace_id}/{len(self.payloads) + 1:032x}.json"
        self.payloads.append(
            {
                "workspace_id": workspace_id,
                "storage_key": key,
                "payload": dict(payload),
            }
        )
        return key


class FakeTraceRepository:
    def __init__(self):
        self.appended = []

    async def append_llm_interaction(self, workspace_id, trace):
        self.appended.append(
            {
                "workspace_id": workspace_id,
                "trace": dict(trace),
            }
        )
        return dict(trace)


class RaisingRawPayloadStore:
    async def put_json(self, workspace_id, payload):
        raise RuntimeError("raw payload store unavailable")


class Usage:
    prompt_tokens = 7
    completion_tokens = 5
    total_tokens = 12


class CreateRecorder:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ParseRecorder:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response


def _fake_client(*, base_url, content="", usage=None, create_exception=None):
    response = (
        create_exception
        if create_exception is not None
        else SimpleNamespace(
            usage=usage,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content)
                )
            ],
        )
    )
    create_recorder = CreateRecorder(response)
    return (
        SimpleNamespace(
            base_url=base_url,
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_recorder.create)
            ),
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=None)
                )
            ),
        ),
        create_recorder,
    )


def _fake_native_client(*, base_url, message, usage=None):
    response = SimpleNamespace(
        usage=usage,
        choices=[
            SimpleNamespace(
                message=message,
            )
        ],
    )
    parse_recorder = ParseRecorder(response)
    return (
        SimpleNamespace(
            base_url=base_url,
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=None)
            ),
            beta=SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(parse=parse_recorder.parse)
                )
            ),
        ),
        parse_recorder,
    )


def _recorder(trace_id):
    raw_store = FakeRawPayloadStore()
    trace_repository = FakeTraceRepository()
    return (
        LLMInteractionRecorder(
            trace_repository=trace_repository,
            raw_payload_store=raw_store,
            trace_id_factory=lambda: trace_id,
        ),
        raw_store,
        trace_repository,
    )


@pytest.mark.asyncio
async def test_llm_service_records_successful_text_calls_at_gateway(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="plain answer",
        usage=Usage(),
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_text_success")

    result = await service(
        prompt="Explain atomic habits",
        model="deepseek-chat",
        trace_context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_123",
            operation="script_generation",
            stage="stage1a",
        ),
        trace_recorder=recorder,
    )

    assert result == "plain answer"
    assert len(raw_store.payloads) == 2
    assert raw_store.payloads[0]["payload"]["messages"] == [
        {"role": "user", "content": "Explain atomic habits"}
    ]
    assert raw_store.payloads[1]["payload"]["content"] == "plain answer"
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_text_success"
    assert stored_trace["status"] == "success"
    assert stored_trace["request_payload_key"] == raw_store.payloads[0]["storage_key"]
    assert stored_trace["response_payload_key"] == raw_store.payloads[1]["storage_key"]
    assert stored_trace["elapsed_ms"] >= 0
    assert stored_trace["token_usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 5,
        "total_tokens": 12,
    }
    assert "Explain atomic habits" in stored_trace["request_preview"]
    assert "plain answer" in stored_trace["response_preview"]
    assert stored_trace["request_preview"]
    assert stored_trace["response_preview"]


@pytest.mark.asyncio
async def test_llm_service_propagates_trace_recorder_failure_after_provider_success(monkeypatch):
    fake_client, create_recorder = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="plain answer",
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    trace_recorder = LLMInteractionRecorder(
        trace_repository=FakeTraceRepository(),
        raw_payload_store=RaisingRawPayloadStore(),
        trace_id_factory=lambda: "trace_store_failure",
    )

    with pytest.raises(LLMTraceRecordingError, match="Failed to record LLM interaction trace") as exc_info:
        await service(
            prompt="Explain atomic habits",
            model="deepseek-chat",
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="script_generation",
                stage="stage1a",
            ),
            trace_recorder=trace_recorder,
        )

    assert len(create_recorder.calls) == 1
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "raw payload store unavailable" in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_llm_service_rejects_untraced_generation_calls_before_provider_request(monkeypatch):
    service = LLMService({})
    provider_requests = []

    def fail_if_client_created(**_):
        provider_requests.append("client-created")
        raise AssertionError("provider client should not be created")

    monkeypatch.setattr(service, "_create_client", fail_if_client_created)

    with pytest.raises(
        ValueError,
        match="LLM trace_context and trace_recorder are required for generation calls",
    ):
        await service(prompt="Explain atomic habits", model="deepseek-chat")

    assert provider_requests == []


@pytest.mark.asyncio
async def test_llm_service_records_structured_parse_failures_at_gateway(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="{not valid json",
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_parse_failure")

    with pytest.raises(ValueError, match="Failed to parse LLM response"):
        await service(
            prompt="Review a movie",
            model="deepseek-chat",
            response_type=MovieReview,
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="movie_review",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert len(raw_store.payloads) == 2
    assert raw_store.payloads[1]["payload"]["content"] == "{not valid json"
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_parse_failure"
    assert stored_trace["status"] == "parse_error"
    assert "Failed to parse LLM response" in stored_trace["parse_error"]
    assert stored_trace["response_payload_key"] == raw_store.payloads[1]["storage_key"]


@pytest.mark.asyncio
async def test_llm_service_records_provider_failures_before_reraising(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        create_exception=RuntimeError("provider timeout"),
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_provider_failure")

    with pytest.raises(RuntimeError, match="provider timeout"):
        await service(
            prompt="Explain atomic habits",
            model="deepseek-chat",
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="script_generation",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert len(raw_store.payloads) == 1
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_provider_failure"
    assert stored_trace["status"] == "error"
    assert stored_trace["parse_error"] == ""
    assert "provider timeout" in stored_trace["error_message"]
    assert stored_trace["response_payload_key"] is None
    assert stored_trace["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_llm_service_records_prompt_schema_json_mode_provider_failures(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        create_exception=RuntimeError("json mode gateway timeout"),
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_json_mode_failure")

    with pytest.raises(RuntimeError, match="json mode gateway timeout"):
        await service(
            prompt="Review a movie",
            model="deepseek-chat",
            response_type=MovieReview,
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="movie_review",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert len(raw_store.payloads) == 1
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_json_mode_failure"
    assert stored_trace["status"] == "error"
    assert stored_trace["parse_error"] == ""
    assert "json mode gateway timeout" in stored_trace["error_message"]
    assert stored_trace["request_payload_key"] == raw_store.payloads[0]["storage_key"]
    assert raw_store.payloads[0]["payload"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_llm_service_records_native_structured_refusals_before_reraising(monkeypatch):
    message = SimpleNamespace(content="", parsed=None, refusal="policy refusal")
    fake_client, _ = _fake_native_client(
        base_url="https://api.openai.com/v1",
        message=message,
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_native_refusal")

    with pytest.raises(ValueError, match="Structured output request refused"):
        await service(
            prompt="Review a movie",
            model="gpt-4o",
            response_type=MovieReview,
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="movie_review",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert len(raw_store.payloads) == 2
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_native_refusal"
    assert stored_trace["status"] == "error"
    assert stored_trace["parse_error"] == ""
    assert "policy refusal" in stored_trace["error_message"]
    assert stored_trace["response_payload_key"] == raw_store.payloads[1]["storage_key"]


@pytest.mark.asyncio
async def test_llm_service_records_native_structured_empty_content_failures(monkeypatch):
    message = SimpleNamespace(content="", parsed=None, refusal=None)
    fake_client, _ = _fake_native_client(
        base_url="https://api.openai.com/v1",
        message=message,
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_native_empty")

    with pytest.raises(ValueError, match="did not include parsed content"):
        await service(
            prompt="Review a movie",
            model="gpt-4o",
            response_type=MovieReview,
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="movie_review",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert len(raw_store.payloads) == 2
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_native_empty"
    assert stored_trace["status"] == "error"
    assert stored_trace["parse_error"] == ""
    assert "did not include parsed content" in stored_trace["error_message"]
