from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_workbench import (
    FrameLockPolicy,
    FrameStaleFlag,
    StoryboardFrameWorkbenchState,
    mark_frame_stale_after_prompt_plan_change,
    mark_frame_stale_after_selected_image_change,
)
from pixelle_video.services.persistence import PersistenceService


def test_workbench_state_round_trips_lightweight_references():
    state = StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        selected_image_artifact_id="artifact_frame_0001_image",
        selected_image_version_id="artifact_version_002",
        candidate_image_version_ids=("artifact_version_001", "artifact_version_002"),
        lock_policy=FrameLockPolicy.LOCKED_ARTIFACT,
        stale_flags=(FrameStaleFlag.VIDEO_SEGMENT,),
        last_generation_job_id="job_image_regen_001",
    )

    payload = state.to_dict()

    assert StoryboardFrameWorkbenchState.from_dict(payload) == state
    assert payload == {
        "frame_id": "frame_0001",
        "prompt_plan_id": "prompt_plan_001",
        "selected_image_artifact_id": "artifact_frame_0001_image",
        "selected_image_version_id": "artifact_version_002",
        "candidate_image_version_ids": ["artifact_version_001", "artifact_version_002"],
        "lock_policy": "locked_artifact",
        "stale_flags": ["video_segment"],
        "last_generation_job_id": "job_image_regen_001",
    }
    assert "local_path" not in payload
    assert "image_path" not in payload
    with pytest.raises(FrozenInstanceError):
        state.selected_image_version_id = "artifact_version_003"


def test_workbench_state_rejects_duplicate_candidate_versions():
    with pytest.raises(ValueError, match="candidate_image_version_ids"):
        StoryboardFrameWorkbenchState(
            frame_id="frame_0001",
            candidate_image_version_ids=("artifact_version_001", "artifact_version_001"),
        )


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("frame_id", r"D:\demo1\Pixelle\output\frame.png"),
        ("prompt_plan_id", "/tmp/prompt_plan_001"),
        ("selected_image_version_id", "../artifact_version_001"),
        ("last_generation_job_id", "file:///tmp/job.json"),
    ],
)
def test_workbench_state_rejects_local_path_like_ids(field_name, value):
    kwargs = {"frame_id": "frame_0001", field_name: value}

    with pytest.raises(ValueError, match=field_name):
        StoryboardFrameWorkbenchState(**kwargs)


def test_workbench_lock_and_stale_helpers_return_new_state_without_duplicates():
    state = StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        lock_policy="locked_artifact",
        stale_flags=(FrameStaleFlag.VIDEO_SEGMENT,),
    )

    after_prompt_change = mark_frame_stale_after_prompt_plan_change(state)
    after_selection_change = mark_frame_stale_after_selected_image_change(after_prompt_change)

    assert state.stale_flags == (FrameStaleFlag.VIDEO_SEGMENT,)
    assert state.is_image_artifact_locked is True
    assert state.can_auto_replace_selected_image is False
    assert after_prompt_change.stale_flags == (
        FrameStaleFlag.VIDEO_SEGMENT,
        FrameStaleFlag.IMAGE_ARTIFACT,
        FrameStaleFlag.FINAL_VIDEO,
    )
    assert after_selection_change.stale_flags == (
        FrameStaleFlag.VIDEO_SEGMENT,
        FrameStaleFlag.IMAGE_ARTIFACT,
        FrameStaleFlag.FINAL_VIDEO,
    )


@pytest.mark.asyncio
async def test_storyboard_persistence_round_trips_workbench_state(tmp_path):
    service = PersistenceService(output_dir=str(tmp_path))
    workbench_state = StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        selected_image_artifact_id="artifact_frame_0001_image",
        selected_image_version_id="artifact_version_002",
        candidate_image_version_ids=("artifact_version_001", "artifact_version_002"),
        stale_flags=(FrameStaleFlag.IMAGE_ARTIFACT,),
    )
    storyboard = Storyboard(
        title="Workbench Storyboard",
        config=StoryboardConfig(
            task_id="task-1",
            media_width=768,
            media_height=768,
            canvas_width=1280,
            canvas_height=720,
        ),
        frames=[
            StoryboardFrame(
                index=0,
                narration="scene one",
                image_prompt="prompt",
                workbench_state=workbench_state,
            )
        ],
    )

    await service.save_storyboard("task-1", storyboard)
    restored = await service.load_storyboard("task-1")

    assert restored is not None
    assert restored.frames[0].workbench_state == workbench_state


def test_historical_frame_without_workbench_state_still_loads():
    service = PersistenceService(output_dir="output")

    frame = service._dict_to_frame(
        {
            "index": 0,
            "narration": "scene one",
            "image_prompt": "prompt",
        }
    )

    assert frame.workbench_state is None


def test_storyboard_frame_accepts_mapping_workbench_state_payload():
    frame = StoryboardFrame(
        index=0,
        narration="scene one",
        image_prompt="prompt",
        workbench_state=MappingProxyType(
            {
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "selected_image_version_id": "artifact_version_001",
            }
        ),
    )

    assert frame.workbench_state == StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        selected_image_version_id="artifact_version_001",
    )
