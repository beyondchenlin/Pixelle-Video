from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    LLMTraceStatus,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder


class FakeRawPayloadStore:
    def __init__(self):
        self.payloads = []

    async def put_json(self, workspace_id, payload):
        index = len(self.payloads) + 1
        storage_key = f"raw-payloads/{workspace_id}/{index:032x}.json"
        self.payloads.append(
            {
                "workspace_id": workspace_id,
                "storage_key": storage_key,
                "payload": dict(payload),
            }
        )
        return storage_key


class FakeTraceRepository:
    def __init__(self):
        self.appended = []

    async def append_llm_interaction(self, workspace_id, trace):
        stored = dict(trace)
        self.appended.append(
            {
                "workspace_id": workspace_id,
                "trace": stored,
            }
        )
        return stored


async def test_recorder_persists_raw_payloads_to_object_store_and_trace_refs_to_repository():
    raw_store = FakeRawPayloadStore()
    trace_repository = FakeTraceRepository()
    recorder = LLMInteractionRecorder(
        trace_repository=trace_repository,
        raw_payload_store=raw_store,
        trace_id_factory=lambda: "trace_0001",
    )

    trace = await recorder.record_interaction(
        context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_123",
            operation="image_prompt_generation",
            stage="stage1a",
            frame_id="frame_0001",
        ),
        provider="openai-compatible",
        model="qwen-plus",
        request_payload={"messages": [{"role": "user", "content": "make image prompt"}]},
        response_payload={"choices": [{"message": {"content": "warm scene"}}]},
        status=LLMTraceStatus.SUCCESS,
        elapsed_ms=321,
        token_usage={"prompt_tokens": 12, "completion_tokens": 8},
    )

    assert [payload["workspace_id"] for payload in raw_store.payloads] == [
        "workspace_1",
        "workspace_1",
    ]
    assert raw_store.payloads[0]["payload"] == {
        "messages": [{"role": "user", "content": "make image prompt"}]
    }
    assert raw_store.payloads[1]["payload"] == {
        "choices": [{"message": {"content": "warm scene"}}]
    }

    assert trace_repository.appended == [
        {
            "workspace_id": "workspace_1",
            "trace": trace.to_dict(),
        }
    ]
    stored_trace = trace_repository.appended[0]["trace"]
    assert stored_trace["trace_id"] == "trace_0001"
    assert stored_trace["request_payload_key"] == raw_store.payloads[0]["storage_key"]
    assert stored_trace["response_payload_key"] == raw_store.payloads[1]["storage_key"]
    assert "request_payload" not in stored_trace
    assert "response_payload" not in stored_trace


async def test_recorder_supports_failure_before_response_payload_exists():
    raw_store = FakeRawPayloadStore()
    trace_repository = FakeTraceRepository()
    recorder = LLMInteractionRecorder(
        trace_repository=trace_repository,
        raw_payload_store=raw_store,
        trace_id_factory=lambda: "trace_error",
    )

    trace = await recorder.record_interaction(
        context=LLMTraceContext(
            workspace_id="workspace_2",
            task_id="task_456",
            operation="storyboard_planning",
        ),
        provider="openai-compatible",
        model="qwen-plus",
        request_payload={"messages": [{"role": "user", "content": "make storyboard"}]},
        response_payload=None,
        status=LLMTraceStatus.ERROR,
        parse_error="timeout before response",
    )

    assert len(raw_store.payloads) == 1
    assert trace.response_payload_key is None
    assert trace.response_sha256 is None
    assert trace.response_preview is None
    assert trace_repository.appended[0]["workspace_id"] == "workspace_2"
    assert trace_repository.appended[0]["trace"]["status"] == "error"
    assert trace_repository.appended[0]["trace"]["parse_error"] == "timeout before response"
