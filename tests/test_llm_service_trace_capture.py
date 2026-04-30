from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
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


class CreateRecorder:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.response


def _fake_client(*, base_url, content):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content)
            )
        ]
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
    assert trace_repository.appended[0]["trace"]["trace_id"] == "trace_text_success"
    assert trace_repository.appended[0]["trace"]["status"] == "success"
    assert trace_repository.appended[0]["trace"]["request_payload_key"] == (
        raw_store.payloads[0]["storage_key"]
    )
    assert trace_repository.appended[0]["trace"]["response_payload_key"] == (
        raw_store.payloads[1]["storage_key"]
    )


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
