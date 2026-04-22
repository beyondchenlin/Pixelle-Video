from datetime import datetime

import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.history_manager import HistoryManager
from pixelle_video.services.persistence import PersistenceService


def _build_planning_snapshot() -> dict:
    return {
        "world_preset_id": "neutral_knowledge_storyboard",
        "effective_final_shot_preset": "balanced_explainer",
        "resolved_content_mode": "concept_explainer",
        "selected_consistency_strength": "strong",
        "resolved_role_strategy": "stable_explainer_cast",
        "selected_role_locking_strength": "strong",
        "selected_shot_strategy": "strict",
        "frames": [
            {
                "shot_type": "medium_shot",
                "shot_purpose": "context",
                "frame_source": "planner_generated",
            }
        ],
    }


@pytest.mark.asyncio
async def test_storyboard_persistence_round_trip_preserves_planning_snapshot_and_fields(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    planning_snapshot = _build_planning_snapshot()
    storyboard = Storyboard(
        title="Planning Snapshot Storyboard",
        config=StoryboardConfig(
            task_id="task-1",
            media_width=1024,
            media_height=1024,
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            content_mode="concept_explainer",
            consistency_strength="strong",
            role_strategy="stable_explainer_cast",
            role_locking_strength="strong",
            shot_strategy="strict",
        ),
        frames=[
            StoryboardFrame(
                index=0,
                narration="scene one",
                image_prompt="styled prompt",
                shot_type="medium_shot",
                shot_purpose="context",
                frame_source="planner_generated",
            )
        ],
        planning_snapshot=planning_snapshot,
    )

    await persistence.save_storyboard("task-1", storyboard)

    loaded = await persistence.load_storyboard("task-1")

    assert loaded is not None
    assert loaded.planning_snapshot == planning_snapshot
    assert loaded.config.world_preset_id == "neutral_knowledge_storyboard"
    assert loaded.config.shot_preset_id == "balanced_explainer"
    assert loaded.config.content_mode == "concept_explainer"
    assert loaded.config.consistency_strength == "strong"
    assert loaded.config.role_strategy == "stable_explainer_cast"
    assert loaded.config.role_locking_strength == "strong"
    assert loaded.config.shot_strategy == "strict"
    assert loaded.frames[0].shot_type == "medium_shot"
    assert loaded.frames[0].shot_purpose == "context"
    assert loaded.frames[0].frame_source == "planner_generated"


@pytest.mark.asyncio
async def test_history_manager_task_detail_includes_storyboard_planning_snapshot(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    history = HistoryManager(persistence)
    planning_snapshot = _build_planning_snapshot()
    storyboard = Storyboard(
        title="History Snapshot Storyboard",
        config=StoryboardConfig(
            task_id="task-2",
            media_width=1024,
            media_height=1024,
            world_preset_id="neutral_knowledge_storyboard",
        ),
        frames=[
            StoryboardFrame(
                index=0,
                narration="scene one",
                image_prompt="styled prompt",
                shot_type="medium_shot",
                shot_purpose="context",
                frame_source="planner_generated",
            )
        ],
        planning_snapshot=planning_snapshot,
    )

    await persistence.save_task_metadata(
        "task-2",
        {
            "created_at": datetime.now(),
            "status": "completed",
            "input": {"text": "scene one"},
            "result": {"video_path": "output/final.mp4"},
            "config": {},
        },
    )
    await persistence.save_storyboard("task-2", storyboard)

    detail = await history.get_task_detail("task-2")

    assert detail is not None
    assert detail["storyboard"].planning_snapshot == planning_snapshot
    assert detail["planning_snapshot"] == planning_snapshot
