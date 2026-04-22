import json

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
from web.components.storyboard_preview import build_storyboard_preview_snapshot_identity


def _neutral_world() -> dict[str, object]:
    return {
        "preset_id": "neutral_knowledge_storyboard",
        "supported_modes": ("theme_mapping", "concept_explainer"),
        "forced_mode": None,
        "conservative_fallback_mode": "concept_explainer",
        "default_shot_preset_ids": ("balanced_explainer",),
    }


def _max_consecutive_run_length(shot_types: list[str]) -> int:
    max_run = 0
    current = None
    run_length = 0

    for shot_type in shot_types:
        if shot_type == current:
            run_length += 1
        else:
            current = shot_type
            run_length = 1
        max_run = max(max_run, run_length)

    return max_run


def _snapshot_identity_for_frames(frames: list[FramePlan | dict[str, object]]) -> str:
    serialized_frames: list[dict[str, object]] = []
    for frame in frames:
        if isinstance(frame, FramePlan):
            serialized_frames.append(frame.to_prompt_dict())
        else:
            serialized_frames.append(dict(frame))
    return build_storyboard_preview_snapshot_identity({"frames": serialized_frames})


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


def test_resolve_shot_preset_falls_back_to_balanced_explainer_when_no_world_default_matches():
    resolved = resolve_shot_preset(
        requested_preset_id=None,
        scene_count=5,
        world_preset_default_ids=("detail_focus",),
        available_presets={
            "detail_focus": {"supported_scene_count": (3, 4)},
            "balanced_explainer": {"supported_scene_count": (3, 4, 5, 6), "override_policy": "adaptive"},
        },
    )

    assert resolved.preset_id == "balanced_explainer"
    assert resolved.selection_source == "fallback_substituted"
    assert resolved.fallback_reason == "no world default shot preset supported the requested scene count"


def test_resolve_shot_preset_rejects_unsupported_explicit_scene_count():
    with pytest.raises(ValueError, match="does not support the requested scene count"):
        resolve_shot_preset(
            requested_preset_id="detail_focus",
            scene_count=5,
            world_preset_default_ids=(),
            available_presets={
                "detail_focus": {"supported_scene_count": (3, 4)},
            },
        )


def test_repair_frame_plan_shots_breaks_four_consecutive_identical_medium_shots():
    plans = [
        FramePlan(scene_id="1", shot_type="medium_shot", shot_purpose="context", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="medium_shot", shot_purpose="explain", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="medium_shot", shot_purpose="detail", prompt_intent="c"),
        FramePlan(scene_id="4", shot_type="medium_shot", shot_purpose="summary", prompt_intent="d"),
    ]

    repaired = repair_frame_plan_shots(
        frame_plans=plans,
        shot_rules={"max_consecutive_same": 2},
    )

    assert _max_consecutive_run_length([plan.shot_type for plan in repaired]) <= 2
    assert any(plan.frame_source == "repair_adjusted" for plan in repaired)


def test_repair_frame_plan_shots_breaks_four_consecutive_close_up_frames():
    plans = [
        FramePlan(scene_id="1", shot_type="close_up", shot_purpose="a", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="close_up", shot_purpose="b", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="close_up", shot_purpose="c", prompt_intent="c"),
        FramePlan(scene_id="4", shot_type="close_up", shot_purpose="d", prompt_intent="d"),
    ]

    repaired = repair_frame_plan_shots(
        frame_plans=plans,
        shot_rules={"max_consecutive_same": 2},
    )

    assert _max_consecutive_run_length([plan.shot_type for plan in repaired]) <= 2
    assert any(plan.frame_source == "repair_adjusted" for plan in repaired)


def test_repair_frame_plan_shots_avoids_merging_into_adjacent_close_up_frames():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", shot_purpose="lead", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="close_up", shot_purpose="x", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="close_up", shot_purpose="y", prompt_intent="c"),
        FramePlan(scene_id="4", shot_type="close_up", shot_purpose="z", prompt_intent="d"),
        FramePlan(scene_id="5", shot_type="close_up", shot_purpose="tail", prompt_intent="e"),
        FramePlan(scene_id="6", shot_type="wide_shot", shot_purpose="outro", prompt_intent="f"),
    ]

    repaired = repair_frame_plan_shots(
        frame_plans=plans,
        shot_rules={"max_consecutive_same": 2},
    )

    assert _max_consecutive_run_length([plan.shot_type for plan in repaired]) <= 2
    assert any(plan.frame_source == "repair_adjusted" for plan in repaired)


def test_repair_frame_plan_shots_respects_locked_shot_type():
    plans = [
        FramePlan(scene_id="1", shot_type="close_up", shot_purpose="a", prompt_intent="a"),
        FramePlan(scene_id="2", shot_type="close_up", shot_purpose="b", prompt_intent="b"),
        FramePlan(scene_id="3", shot_type="close_up", shot_purpose="c", prompt_intent="c"),
        FramePlan(scene_id="4", shot_type="close_up", shot_purpose="d", prompt_intent="d"),
    ]

    overridden = apply_frame_overrides(
        frame_plans=plans,
        frame_overrides=[
            {
                "scene_id": "3",
                "snapshot_identity": _snapshot_identity_for_frames(plans),
                "locked_fields": ["shot_type"],
                "shot_type": "close_up",
                "override_source": "user_preview",
            }
        ],
    )

    repaired = repair_frame_plan_shots(
        frame_plans=overridden,
        shot_rules={"max_consecutive_same": 2},
    )

    assert repaired[2].shot_type == "close_up"
    assert "shot_type" in repaired[2].locked_fields
    assert repaired[2].frame_source == "user_edited"
    assert _max_consecutive_run_length([plan.shot_type for plan in repaired]) <= 2


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
                "snapshot_identity": _snapshot_identity_for_frames(plans),
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


def test_apply_frame_overrides_preserves_prior_locks_across_repeated_overrides():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", focus_detail="orig", prompt_intent="opening"),
    ]
    snapshot_identity = _snapshot_identity_for_frames(plans)

    overridden = apply_frame_overrides(
        frame_plans=plans,
        frame_overrides=[
            {
                "scene_id": "1",
                "snapshot_identity": snapshot_identity,
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
                "override_source": "user_preview",
            },
            {
                "scene_id": "1",
                "snapshot_identity": snapshot_identity,
                "locked_fields": ["focus_detail"],
                "focus_detail": "user focus note",
                "override_source": "user_preview",
            },
        ],
    )

    assert overridden[0].shot_type == "medium_shot"
    assert overridden[0].focus_detail == "user focus note"
    assert overridden[0].locked_fields == ("shot_type", "focus_detail")
    assert overridden[0].override_source == "user_preview"
    assert overridden[0].frame_source == "user_edited"


def test_apply_frame_overrides_rejects_missing_scene_id():
    plans = [FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")]

    with pytest.raises(ValueError, match="scene_id must be a non-empty string"):
        apply_frame_overrides(
            frame_plans=plans,
            frame_overrides=[
                {
                    "snapshot_identity": _snapshot_identity_for_frames(plans),
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                    "override_source": "user_preview",
                }
            ],
        )


def test_apply_frame_overrides_rejects_unknown_scene_id():
    plans = [FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")]

    with pytest.raises(ValueError, match="does not match any frame plan"):
        apply_frame_overrides(
            frame_plans=plans,
            frame_overrides=[
                {
                    "scene_id": "2",
                    "snapshot_identity": _snapshot_identity_for_frames(plans),
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                    "override_source": "user_preview",
                }
            ],
        )


@pytest.mark.parametrize(
    ("override_payload", "match"),
    [
        (
            {
                "scene_id": "1",
                "locked_fields": ["shot_type"],
                "frame_source": "planner_generated",
                "override_source": "user_preview",
            },
            "unsupported frame override field",
        ),
        (
            {
                "scene_id": "1",
                "locked_fields": ["shot_type"],
                "focus_detail": "not allowed unless locked",
                "override_source": "user_preview",
            },
            "must be listed in locked_fields",
        ),
    ],
)
def test_apply_frame_overrides_rejects_invalid_override_attempts(
    override_payload: dict[str, object],
    match: str,
):
    plans = [FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")]
    override_payload = dict(override_payload)
    override_payload["snapshot_identity"] = _snapshot_identity_for_frames(plans)

    with pytest.raises(ValueError, match=match):
        apply_frame_overrides(frame_plans=plans, frame_overrides=[override_payload])


def test_apply_frame_overrides_rejects_snapshot_identity_mismatch():
    plans = [FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")]

    with pytest.raises(ValueError, match="snapshot_identity"):
        apply_frame_overrides(
            frame_plans=plans,
            frame_overrides=[
                {
                    "scene_id": "1",
                    "snapshot_identity": "snapshot:stale",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                    "override_source": "user_preview",
                }
            ],
        )


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


def test_parse_storyboard_frames_raises_when_field_types_are_invalid():
    with pytest.raises(ValueError, match="secondary_subjects must be a list or tuple of strings"):
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
                  "secondary_subjects": "not-a-list",
                  "world_elements": [],
                  "continuity_anchors": [],
                  "focus_detail": "detail",
                  "prompt_intent": "intent",
                  "locked_fields": [],
                  "override_source": "user_preview",
                  "frame_source": "planner_generated",
                  "replan_scope": "local",
                  "planner_version": "1.0"
                }
              ]
            }
            """
        )


@pytest.mark.parametrize(
    "raw_response",
    [
        """
        ```json
        {
          "frames": []
        }
        ```
        """,
        """
        Here is the plan:
        {"frames": []}
        """,
        """
        {"frames": []}
        trailing prose
        """,
    ],
)
def test_parse_storyboard_frames_rejects_wrapped_or_trailing_text(raw_response: str):
    with pytest.raises(ValueError, match="raw JSON only"):
        parse_storyboard_frames(raw_response)


def test_parse_storyboard_frames_rejects_missing_frames_key():
    with pytest.raises(ValueError, match="include a frames array"):
        parse_storyboard_frames('{"not_frames": []}')


@pytest.mark.asyncio
async def test_plan_storyboard_batch_runs_prompt_parse_override_repair_and_snapshot(monkeypatch):
    captured_prompts: list[str] = []
    planner_frames = [
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
            "override_source": None,
            "frame_source": "planner_generated",
            "replan_scope": "local",
            "planner_version": "1.0",
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
            "override_source": None,
            "frame_source": "planner_generated",
            "replan_scope": "local",
            "planner_version": "1.0",
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
            "override_source": None,
            "frame_source": "planner_generated",
            "replan_scope": "local",
            "planner_version": "1.0",
        },
    ]
    raw_planner_response = json.dumps({"frames": planner_frames})

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            captured_prompts.append(prompt)
            return raw_planner_response

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
                "snapshot_identity": _snapshot_identity_for_frames(planner_frames),
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


@pytest.mark.asyncio
async def test_plan_storyboard_batch_respects_preset_max_consecutive_same(monkeypatch):
    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            return """
            {
              "frames": [
                {
                  "scene_id": "1",
                  "narration_fragment": "first",
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
                  "narration_fragment": "second",
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
                }
              ]
            }
            """

    result = await plan_storyboard_batch(
        llm_service=FakeLLM(),
        narrations=["first", "second"],
        world_preset_library={
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [
                {
                    "preset_id": "neutral_knowledge_storyboard",
                    "supported_modes": ["theme_mapping", "concept_explainer"],
                    "default_shot_preset_ids": ["strict_alternating"],
                    "conservative_fallback_mode": "concept_explainer",
                }
            ],
        },
        shot_preset_library={
            "default_shot_preset_id": "strict_alternating",
            "items": [
                {
                    "preset_id": "strict_alternating",
                    "supported_scene_count": [2],
                    "max_consecutive_same": 1,
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
        shot_preset_id="strict_alternating",
        content_mode="concept_explainer",
        role_strategy="auto",
        classifier_result={"mode": "concept_explainer", "confidence": 0.91},
    )

    assert result.resolved_shot_preset.max_consecutive_same == 1
    assert result.planning_snapshot["resolved_shot_preset_details"]["max_consecutive_same"] == 1
    assert _max_consecutive_run_length([plan.shot_type for plan in result.frames]) <= 1
