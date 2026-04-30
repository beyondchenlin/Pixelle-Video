from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.llm_interaction_trace import (
    LLMInteractionTrace,
    LLMTraceContext,
    LLMTraceStatus,
)


def test_trace_context_is_semantic_and_immutable():
    context = LLMTraceContext(
        workspace_id="workspace_1",
        task_id="task_123",
        operation="storyboard_planning",
        stage="stage1a",
        frame_id="frame_0001",
        metadata={"prompt_plan_id": "plan_123", "tags": ["storyboard", "image"]},
    )

    assert context.to_dict() == {
        "workspace_id": "workspace_1",
        "task_id": "task_123",
        "operation": "storyboard_planning",
        "stage": "stage1a",
        "frame_id": "frame_0001",
        "metadata": {
            "prompt_plan_id": "plan_123",
            "tags": ["storyboard", "image"],
        },
    }

    with pytest.raises(FrozenInstanceError):
        context.task_id = "changed"
    with pytest.raises(TypeError):
        context.metadata["prompt_plan_id"] = "changed"


def test_trace_stores_payload_refs_hashes_and_safe_previews_only():
    trace = LLMInteractionTrace.create(
        trace_id="trace_123",
        context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_123",
            operation="image_prompt_generation",
            stage="stage1a",
        ),
        provider="openai-compatible",
        model="qwen-plus",
        request_payload_key="raw-payloads/workspace_1/request.json",
        response_payload_key="raw-payloads/workspace_1/response.json",
        request_payload={
            "messages": [
                {
                    "role": "user",
                    "content": "A" * 500,
                }
            ],
            "api_key": "must-not-be-treated-as-special-inline-data",
        },
        response_payload={
            "choices": [
                {
                    "message": {
                        "content": "B" * 500,
                    }
                }
            ]
        },
        status=LLMTraceStatus.SUCCESS,
        elapsed_ms=153,
        token_usage={"prompt_tokens": 10, "completion_tokens": 20},
        error_message="",
    )

    payload = trace.to_dict()

    assert payload["request_payload_key"] == "raw-payloads/workspace_1/request.json"
    assert payload["response_payload_key"] == "raw-payloads/workspace_1/response.json"
    assert len(payload["request_sha256"]) == 64
    assert len(payload["response_sha256"]) == 64
    assert len(payload["request_preview"]) <= 240
    assert len(payload["response_preview"]) <= 240
    assert "request_payload" not in payload
    assert "response_payload" not in payload
    assert "messages" not in payload
    assert "choices" not in payload
    assert payload["status"] == "success"
    assert payload["elapsed_ms"] == 153
    assert payload["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 20}
    assert payload["error_message"] == ""


def test_trace_round_trips_parse_and_validation_errors():
    trace = LLMInteractionTrace.create(
        trace_id="trace_parse_error",
        context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_456",
            operation="storyboard_planning",
        ),
        provider="openai-compatible",
        model="qwen-plus",
        request_payload_key="raw-payloads/workspace_1/request.json",
        response_payload_key="raw-payloads/workspace_1/response.json",
        request_payload={"prompt": "make storyboard"},
        response_payload={"content": "{not json"},
        status=LLMTraceStatus.PARSE_ERROR,
        parse_error="JSONDecodeError: expected object",
        error_message="",
        validation_errors=[
            {
                "field": "frames",
                "message": "frames must not be empty",
            }
        ],
    )

    restored = LLMInteractionTrace.from_dict(trace.to_dict())

    assert restored == trace
    assert restored.status is LLMTraceStatus.PARSE_ERROR
    assert restored.parse_error == "JSONDecodeError: expected object"
    assert restored.error_message == ""
    assert restored.validation_errors == (
        {
            "field": "frames",
            "message": "frames must not be empty",
        },
    )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("workspace_id", {"workspace_id": "", "task_id": "task", "operation": "op"}),
        ("task_id", {"workspace_id": "workspace", "task_id": " ", "operation": "op"}),
        ("operation", {"workspace_id": "workspace", "task_id": "task", "operation": ""}),
    ],
)
def test_trace_context_rejects_missing_required_semantics(field_name, kwargs):
    with pytest.raises(ValueError, match=field_name):
        LLMTraceContext(**kwargs)


def test_trace_round_trips_non_parse_error_message():
    trace = LLMInteractionTrace.create(
        trace_id="trace_provider_error",
        context=LLMTraceContext(
            workspace_id="workspace_1",
            task_id="task_789",
            operation="script_generation",
        ),
        provider="openai-compatible",
        model="qwen-plus",
        request_payload_key="raw-payloads/workspace_1/request.json",
        request_payload={"prompt": "make script"},
        response_payload=None,
        status=LLMTraceStatus.ERROR,
        error_message="provider timeout",
    )

    restored = LLMInteractionTrace.from_dict(trace.to_dict())

    assert restored.status is LLMTraceStatus.ERROR
    assert restored.parse_error == ""
    assert restored.error_message == "provider timeout"
    assert restored.response_payload_key is None
