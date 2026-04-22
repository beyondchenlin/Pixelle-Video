import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.prompts.storyboard_planning import parse_storyboard_frames
from pixelle_video.services.storyboard_consistency import (
    apply_frame_overrides,
    repair_frame_plan_shots,
)
from pixelle_video.services.storyboard_planner import (
    plan_storyboard_batch,
    resolve_content_mode,
    resolve_role_strategy,
    resolve_shot_preset,
)


def _neutral_world() -> dict[str, object]:
    return {
        "preset_id": "neutral_knowledge_storyboard",
        "supported_modes": ("theme_mapping", "concept_explainer"),
        "forced_mode": None,
        "conservative_fallback_mode": "concept_explainer",
        "default_shot_preset_ids": ("balanced_explainer",),
    }


def test_resolve_content_mode_prefers_forced_mode_over_classifier_result():
    resolved = resolve_content_mode(
        user_mode=None,
        classifier_result={"mode": "theme_mapping", "confidence": 0.95},
        world_preset={**_neutral_world(), "forced_mode": "concept_explainer"},
        default_threshold=0.7,
    )

    assert resolved.mode == "concept_explainer"
    assert resolved.selection_source == "forced_mode"


@pytest.mark.parametrize(
    ("resolved_mode", "role_strategy"),
    [
        ("theme_mapping", "stable_explainer_cast"),
        ("concept_explainer", "theme_mapping"),
    ],
)
def test_resolve_role_strategy_raises_on_mode_conflict(resolved_mode: str, role_strategy: str):
    with pytest.raises(ValueError, match="role strategy"):
        resolve_role_strategy(resolved_mode=resolved_mode, role_strategy=role_strategy)


def test_resolve_shot_preset_selects_first_world_default_supporting_scene_count():
    resolved = resolve_shot_preset(
        requested_preset_id=None,
        scene_count=5,
        world_preset_default_ids=("detail_focus", "balanced_explainer"),
        available_presets={
            "detail_focus": {"supported_scene_count": (3, 4)},
            "balanced_explainer": {"supported_scene_count": (5, 6)},
        },
    )

    assert resolved.preset_id == "balanced_explainer"


def test_resolve_shot_preset_raises_when_no_world_default_supports_scene_count():
    with pytest.raises(ValueError, match="no world default shot preset supports the requested scene count"):
        resolve_shot_preset(
            requested_preset_id=None,
            scene_count=5,
            world_preset_default_ids=("detail_focus",),
            available_presets={
                "detail_focus": {"supported_scene_count": (3, 4)},
            },
        )


def test_repair_frame_plan_shots_breaks_three_consecutive_identical_medium_shots():
    plans = [
        FramePlan(scene_id="1", shot_type="medium_shot", shot_purpose="context", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="medium_shot", shot_purpose="explain", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="medium_shot", shot_purpose="detail", prompt_intent="c"),
    ]

    repaired = repair_frame_plan_shots(
        frame_plans=plans,
        shot_rules={"max_consecutive_same": 2},
    )

    assert repaired[-1].shot_type == "close_up"
    assert repaired[-1].frame_source == "repair_adjusted"


def test_apply_frame_overrides_locks_requested_fields_and_keeps_override_source():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening"),
        FramePlan(scene_id="2", shot_type="medium_shot", prompt_intent="explain"),
    ]

    overridden = apply_frame_overrides(
        frame_plans=plans,
        frame_overrides=[
            {
                "scene_id": "2",
                "locked_fields": ["shot_type"],
                "shot_type": "close_up",
                "override_source": "user_preview",
            }
        ],
    )

    assert overridden[1].shot_type == "close_up"
    assert overridden[1].locked_fields == ("shot_type",)
    assert overridden[1].override_source == "user_preview"
    assert overridden[1].frame_source == "user_edited"


def test_parse_storyboard_frames_raises_when_required_fields_are_missing():
    with pytest.raises(ValueError, match="missing required storyboard frame field"):
        parse_storyboard_frames(
            """
            {
              "frames": [
                {
                  "scene_id": "1",
                  "narration_fragment": "intro",
                  "knowledge_goal": "goal",
                  "shot_type": "wide_shot",
                  "shot_purpose": "opening",
                  "primary_subject": "subject",
                  "secondary_subjects": [],
                  "world_elements": [],
                  "continuity_anchors": [],
                  "focus_detail": "detail",
                  "prompt_intent": "intent",
                  "locked_fields": [],
                  "override_source": "user_preview",
                  "frame_source": "planner_generated",
                  "replan_scope": "local"
                }
              ]
            }
            """
        )


@pytest.mark.asyncio
async def test_plan_storyboard_batch_runs_prompt_parse_override_repair_and_snapshot(monkeypatch):
    captured_prompts: list[str] = []

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            captured_prompts.append(prompt)
            return """
            {
              "frames": [
                {
                  "scene_id": "1",
                  "narration_fragment": "intro",
                  "knowledge_goal": "goal 1",
                  "shot_type": "medium_shot",
                  "shot_purpose": "context",
                  "primary_subject": "subject 1",
                  "secondary_subjects": [],
                  "world_elements": ["board"],
                  "continuity_anchors": ["anchor 1"],
                  "focus_detail": "detail 1",
                  "prompt_intent": "intent 1",
                  "locked_fields": [],
                  "override_source": null,
                  "frame_source": "planner_generated",
                  "replan_scope": "local",
                  "planner_version": "1.0"
                },
                {
                  "scene_id": "2",
                  "narration_fragment": "middle",
                  "knowledge_goal": "goal 2",
                  "shot_type": "medium_shot",
                  "shot_purpose": "explain",
                  "primary_subject": "subject 2",
                  "secondary_subjects": [],
                  "world_elements": ["board"],
                  "continuity_anchors": ["anchor 2"],
                  "focus_detail": "detail 2",
                  "prompt_intent": "intent 2",
                  "locked_fields": [],
                  "override_source": null,
                  "frame_source": "planner_generated",
                  "replan_scope": "local",
                  "planner_version": "1.0"
                },
                {
                  "scene_id": "3",
                  "narration_fragment": "ending",
                  "knowledge_goal": "goal 3",
                  "shot_type": "medium_shot",
                  "shot_purpose": "summary",
                  "primary_subject": "subject 3",
                  "secondary_subjects": [],
                  "world_elements": ["board"],
                  "continuity_anchors": ["anchor 3"],
                  "focus_detail": "detail 3",
                  "prompt_intent": "intent 3",
                  "locked_fields": [],
                  "override_source": null,
                  "frame_source": "planner_generated",
                  "replan_scope": "local",
                  "planner_version": "1.0"
                }
              ]
            }
            """

    result = await plan_storyboard_batch(
        llm_service=FakeLLM(),
        narrations=["first", "second", "third"],
        world_preset_library={
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [
                {
                    "preset_id": "neutral_knowledge_storyboard",
                    "supported_modes": ["theme_mapping", "concept_explainer"],
                    "default_shot_preset_ids": ["balanced_explainer"],
                    "conservative_fallback_mode": "concept_explainer",
                }
            ],
        },
        shot_preset_library={
            "default_shot_preset_id": "balanced_explainer",
            "items": [
                {
                    "preset_id": "balanced_explainer",
                    "supported_scene_count": [3],
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
        shot_preset_id="balanced_explainer",
        content_mode="concept_explainer",
        role_strategy="auto",
        frame_overrides=[
            {
                "scene_id": "2",
                "locked_fields": ["focus_detail"],
                "focus_detail": "user focus note",
                "override_source": "user_preview",
            }
        ],
        classifier_result={"mode": "concept_explainer", "confidence": 0.91},
    )

    assert captured_prompts
    assert '"task": "plan_storyboard_frames"' in captured_prompts[0]
    assert result.planning_snapshot["requested_shot_preset_id"] == "balanced_explainer"
    assert result.planning_snapshot["effective_final_shot_preset"] == "balanced_explainer"
    assert result.planning_snapshot["resolved_content_mode"] == "concept_explainer"
    assert result.planning_snapshot["resolved_mode_selection_source"] == "user_selected"
    assert result.planning_snapshot["frame_overrides"][0]["override_source"] == "user_preview"
    assert result.frames[1].focus_detail == "user focus note"
    assert result.frames[1].frame_source == "user_edited"
    assert result.frames[2].shot_type == "close_up"
    assert result.frames[2].frame_source == "repair_adjusted"
