from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    LLMTraceRecordingError,
)
from pixelle_video.models.llm_response import (
    LLMEmptyResponseError,
    LLMProviderRequestError,
    LLMResponseShapeError,
)
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


def _fake_client(
    *,
    base_url,
    content="",
    usage=None,
    create_exception=None,
    choices=None,
):
    response = (
        create_exception
        if create_exception is not None
        else SimpleNamespace(
            usage=usage,
            choices=(
                [SimpleNamespace(message=SimpleNamespace(content=content))]
                if choices is None
                else choices
            ),
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
    fake_client, create_recorder = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="plain answer",
        usage=Usage(),
    )
    create_recorder.response.provider_metadata = {
        "client_secret_value": "provider-response-secret"
    }
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
    assert raw_store.payloads[1]["payload"]["response"]["provider_metadata"] == {
        "client_secret_value": "[REDACTED]"
    }
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
async def test_llm_service_records_and_sanitizes_client_initialization_failure(monkeypatch):
    service = LLMService({})

    async def fail_settings(**kwargs):
        raise RuntimeError(
            "api_key=provider-secret https://user:password@provider.example/v1"
        )

    monkeypatch.setattr(service, "_client_settings", fail_settings)
    recorder, raw_store, trace_repository = _recorder("trace_client_init_error")

    with pytest.raises(LLMProviderRequestError) as captured:
        await service(
            prompt="hello",
            model="deepseek-chat",
            base_url="https://provider.example/v1",
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="script_generation",
            ),
            trace_recorder=recorder,
        )

    assert "provider-secret" not in str(captured.value)
    assert "user:password" not in str(captured.value)
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["status"] == "error"
    assert "provider-secret" not in stored_trace["error_message"]
    assert "user:password" not in stored_trace["error_message"]
    assert len(raw_store.payloads) == 1


@pytest.mark.asyncio
async def test_llm_service_fails_closed_when_mandatory_trace_persistence_fails(monkeypatch):
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

    with pytest.raises(LLMTraceRecordingError, match="mandatory LLM interaction trace"):
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
@pytest.mark.parametrize(
    ("choices", "content", "error_type", "reason"),
    [
        ([], "unused", LLMEmptyResponseError, "choices_empty"),
        (None, None, LLMEmptyResponseError, "content_missing"),
        (None, "   \n", LLMEmptyResponseError, "content_blank"),
        (
            [SimpleNamespace(message=SimpleNamespace(content=[{"type": "text"}]))],
            "unused",
            LLMResponseShapeError,
            "content_type_invalid",
        ),
    ],
)
async def test_llm_service_rejects_invalid_text_response_contracts_and_records_trace(
    monkeypatch,
    choices,
    content,
    error_type,
    reason,
):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content=content,
        choices=choices,
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder(f"trace_{reason}")

    with pytest.raises(error_type) as exc_info:
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

        assert exc_info.value.reason == reason
        assert len(raw_store.payloads) == 2
        stored_trace = trace_repository.appended[0]["trace"]
        assert stored_trace["status"] == "error"
        assert stored_trace["error_message"]
        assert stored_trace["response_payload_key"] == raw_store.payloads[1]["storage_key"]


@pytest.mark.asyncio
async def test_llm_service_rejects_empty_dict_response_instead_of_fabricating_success(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content=None,
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, _, trace_repository = _recorder("trace_empty_dict")

    with pytest.raises(LLMEmptyResponseError) as exc_info:
        await service(
            prompt="Return an object",
            model="deepseek-chat",
            response_type=dict,
            trace_context=LLMTraceContext(
                workspace_id="workspace_1",
                task_id="task_123",
                operation="object_generation",
                stage="stage1a",
            ),
            trace_recorder=recorder,
        )

    assert exc_info.value.reason == "content_missing"
    assert trace_repository.appended[0]["trace"]["status"] == "error"


@pytest.mark.asyncio
async def test_llm_service_redacts_sensitive_extra_parameters_from_trace_only(monkeypatch):
    fake_client, create_recorder = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="plain answer",
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, _ = _recorder("trace_redacted_headers")

    await service(
        prompt="Explain atomic habits",
        model="deepseek-chat",
        extra_headers={
            "Authorization": "Bearer provider-secret",
            "X-API-Key": "provider-key",
            "nested": {"client_secret": "oauth-secret"},
        },
        trace_context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_123",
            operation="script_generation",
            stage="stage1a",
        ),
        trace_recorder=recorder,
    )

    assert create_recorder.calls[0]["extra_headers"] == {
        "Authorization": "Bearer provider-secret",
        "X-API-Key": "provider-key",
        "nested": {"client_secret": "oauth-secret"},
    }
    assert raw_store.payloads[0]["payload"]["extra_parameters"]["extra_headers"] == {
        "Authorization": "[REDACTED]",
        "X-API-Key": "[REDACTED]",
        "nested": {"client_secret": "[REDACTED]"},
    }


@pytest.mark.asyncio
async def test_llm_service_sanitizes_provider_errors_before_trace_and_reraise(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        create_exception=RuntimeError(
            'authorization=Bearer super-secret api_key=provider-secret '
            'client_secret="oauth secret with spaces"'
        ),
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, _, trace_repository = _recorder("trace_sanitized_error")

    with pytest.raises(LLMProviderRequestError) as exc_info:
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

    assert "super-secret" not in str(exc_info.value)
    assert "provider-secret" not in str(exc_info.value)
    assert "oauth secret with spaces" not in str(exc_info.value)
    trace_error = trace_repository.appended[0]["trace"]["error_message"]
    assert "super-secret" not in trace_error
    assert "provider-secret" not in trace_error
    assert "oauth secret with spaces" not in trace_error


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
async def test_llm_service_records_structured_validation_failures_at_gateway(monkeypatch):
    fake_client, _ = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content='{"title":"Schema drift"}',
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    recorder, raw_store, trace_repository = _recorder("trace_validation_failure")

    with pytest.raises(ValidationError):
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
    assert raw_store.payloads[1]["payload"]["content"] == '{"title":"Schema drift"}'
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_validation_failure"
    assert stored_trace["status"] == "validation_error"
    assert "rating" in stored_trace["parse_error"]
    assert stored_trace["validation_errors"] == [
        {
            "field": "rating",
            "message": "Field required",
            "type": "missing",
        }
    ]
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
