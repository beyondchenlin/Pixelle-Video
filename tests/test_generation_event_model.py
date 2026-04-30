from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.generation_event import (
    GenerationEvent,
    GenerationEventAction,
)


def test_generation_event_round_trips_domain_ids_and_storage_key():
    event = GenerationEvent(
        event_id="generation_event_001",
        workspace_id="workspace_1",
        action=GenerationEventAction.GENERATE,
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        artifact_id="artifact_frame_001",
        artifact_version_id="artifact_version_001",
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_001.png",
        task_id="task_123",
        llm_trace_id="llm_trace_001",
        metadata={"provider": "comfyui"},
    )

    payload = event.to_dict()

    assert GenerationEvent.from_dict(payload) == event
    assert payload["action"] == "generate"
    assert payload["frame_id"] == "frame_0001"
    assert payload["prompt_plan_id"] == "prompt_plan_001"
    assert payload["artifact_version_id"] == "artifact_version_001"
    assert payload["storage_key"] == "artifacts/workspace_1/frame_0001/artifact_version_001.png"
    assert "local_path" not in payload
    with pytest.raises(FrozenInstanceError):
        event.action = GenerationEventAction.SELECT
    with pytest.raises(TypeError):
        event.metadata["provider"] = "changed"


@pytest.mark.parametrize(
    "action",
    [
        GenerationEventAction.FAIL,
        GenerationEventAction.SELECT,
        GenerationEventAction.REGENERATE,
        GenerationEventAction.STALE_MARK,
    ],
)
def test_generation_event_supports_stage1b_workbench_actions(action):
    event = GenerationEvent(
        event_id=f"generation_event_{action.value}",
        workspace_id="workspace_1",
        action=action,
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        artifact_id="artifact_frame_001",
        artifact_version_id="artifact_version_001",
        error_message="provider failed" if action is GenerationEventAction.FAIL else "",
        stale_reason="prompt_plan_changed" if action is GenerationEventAction.STALE_MARK else "",
    )

    restored = GenerationEvent.from_dict(event.to_dict())

    assert restored.action is action
    assert restored.frame_id == "frame_0001"
    if action is GenerationEventAction.FAIL:
        assert restored.error_message == "provider failed"
    if action is GenerationEventAction.STALE_MARK:
        assert restored.stale_reason == "prompt_plan_changed"


@pytest.mark.parametrize(
    "storage_key",
    [
        r"D:\demo1\Pixelle\output\frame.png",
        "/tmp/pixelle/frame.png",
        "../output/frame.png",
        "artifacts\\workspace_1\\frame.png",
        "file:///tmp/frame.png",
    ],
)
def test_generation_event_rejects_local_or_path_escape_storage_keys(storage_key):
    with pytest.raises(ValueError, match="storage_key"):
        GenerationEvent(
            event_id="generation_event_001",
            workspace_id="workspace_1",
            action=GenerationEventAction.GENERATE,
            frame_id="frame_0001",
            prompt_plan_id="prompt_plan_001",
            artifact_id="artifact_frame_001",
            storage_key=storage_key,
        )
