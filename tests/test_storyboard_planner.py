import json

import pytest

import pixelle_video.services.storyboard_planner as storyboard_planner_module
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_planning import (
    FramePlan,
    StoryboardPlanningFrameResponse,
    StoryboardPlanningResponse,
)
from pixelle_video.prompts.storyboard_planning import (
    build_storyboard_planning_prompt,
    parse_storyboard_frames,
)
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


def test_resolve_shot_preset_allows_large_storyboards_to_extend_explicit_preset():
    resolved = resolve_shot_preset(
        requested_preset_id="detail_focus",
        scene_count=25,
        world_preset_default_ids=(),
        available_presets={
            "detail_focus": {"supported_scene_count": (3, 4), "override_policy": "adaptive"},
        },
    )

    assert resolved.preset_id == "detail_focus"
    assert resolved.selection_source == "user_selected"
    assert resolved.fallback_reason == "large storyboard extends shot preset beyond nominal scene counts"


def test_resolve_shot_preset_allows_large_storyboards_to_extend_world_default():
    resolved = resolve_shot_preset(
        requested_preset_id=None,
        scene_count=25,
        world_preset_default_ids=("detail_focus",),
        available_presets={
            "detail_focus": {"supported_scene_count": (3, 4), "override_policy": "adaptive"},
            "balanced_explainer": {"supported_scene_count": (3, 4, 5, 6, 7), "override_policy": "adaptive"},
        },
    )

    assert resolved.preset_id == "detail_focus"
    assert resolved.selection_source == "auto_selected"
    assert resolved.fallback_reason == "large storyboard extends shot preset beyond nominal scene counts"


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


def test_plan_identity_anchor_only_override_validates_without_mutating_frame_plan():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")
    ]
    prompt_contexts = PromptContextEnvelope(
        plan_context={
            "plan_id": "plan_abc",
            "plan_revision": 1,
            "source_digest": "a" * 64,
        },
        frame_contexts=[{"frame_id": "frame_0001"}],
    )

    overridden = apply_frame_overrides(
        frame_plans=plans,
        frame_overrides=[
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": [
                    "mandatory_anchor_area_ratio",
                    "mandatory_anchor_action_verb",
                ],
                "mandatory_anchor_area_ratio": 0.8,
                "mandatory_anchor_action_verb": "holds",
                "override_source": "user_preview",
            }
        ],
        prompt_contexts=prompt_contexts,
    )

    assert overridden == plans


def test_plan_identity_anchor_override_rejects_invalid_area_ratio():
    plans = [
        FramePlan(scene_id="1", shot_type="wide_shot", prompt_intent="opening")
    ]
    prompt_contexts = PromptContextEnvelope(
        plan_context={
            "plan_id": "plan_abc",
            "plan_revision": 1,
            "source_digest": "a" * 64,
        },
        frame_contexts=[{"frame_id": "frame_0001"}],
    )

    with pytest.raises(ValueError, match="area ratio"):
        apply_frame_overrides(
            frame_plans=plans,
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["mandatory_anchor_area_ratio"],
                    "mandatory_anchor_area_ratio": 1.1,
                    "override_source": "user_preview",
                }
            ],
            prompt_contexts=prompt_contexts,
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


def test_parse_storyboard_frames_converts_comma_separated_string_to_list():
    plans = parse_storyboard_frames(
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
              "secondary_subjects": "元素1, 元素2",
              "world_elements": "世界元素1, 世界元素2",
              "continuity_anchors": "锚点1, 锚点2",
              "focus_detail": "detail",
              "prompt_intent": "intent",
              "locked_fields": "锁定字段1, 锁定字段2",
              "override_source": "user_preview",
              "frame_source": "planner_generated",
              "replan_scope": "local",
              "planner_version": "1.0"
            }
          ]
        }
        """
    )
    assert len(plans) == 1
    frame = plans[0]
    assert frame.secondary_subjects == ("元素1", "元素2")
    assert frame.world_elements == ("世界元素1", "世界元素2")
    assert frame.continuity_anchors == ("锚点1", "锚点2")
    assert frame.locked_fields == ("锁定字段1", "锁定字段2")


def test_parse_storyboard_frames_raises_when_field_types_are_invalid():
    with pytest.raises(ValueError, match="list items must be strings"):
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
                  "secondary_subjects": ["valid", 123],
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


def test_parse_storyboard_frames_normalizes_numeric_scene_id_to_string():
    plans = parse_storyboard_frames(
        """
        {
          "frames": [
            {
              "scene_id": 1,
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
              "override_source": null,
              "frame_source": "planner_generated",
              "replan_scope": "local",
              "planner_version": "1.0"
            }
          ]
        }
        """
    )

    assert [plan.scene_id for plan in plans] == ["1"]


def test_build_storyboard_planning_prompt_instructs_string_scene_ids():
    prompt = json.loads(
        build_storyboard_planning_prompt(
            narrations=["intro"],
            world_preset=_neutral_world(),
            shot_preset={"preset_id": "balanced_explainer"},
            resolved_mode="concept_explainer",
            consistency_strength="standard",
        )
    )

    frame_schema = prompt["required_output"]["$defs"]["StoryboardPlanningFrameResponse"]
    assert frame_schema["properties"]["scene_id"]["type"] == "string"
    assert "quoted string" in frame_schema["properties"]["scene_id"]["description"].lower()
    assert any("never a number" in instruction for instruction in prompt["instructions"])


def test_build_storyboard_planning_prompt_can_use_absolute_scene_ids_for_batches():
    prompt = json.loads(
        build_storyboard_planning_prompt(
            narrations=["middle", "ending"],
            world_preset=_neutral_world(),
            shot_preset={"preset_id": "balanced_explainer"},
            resolved_mode="concept_explainer",
            consistency_strength="standard",
            scene_id_start=12,
        )
    )

    assert prompt["narration_items"] == [
        {"scene_id": "12", "text": "middle"},
        {"scene_id": "13", "text": "ending"},
    ]
    assert any("narration_items" in instruction for instruction in prompt["instructions"])


def test_build_storyboard_planning_prompt_uses_frame_source_inputs_with_prompt_contexts():
    prompt = json.loads(
        build_storyboard_planning_prompt(
            narrations=["intro"],
            prompt_contexts=PromptContextEnvelope(
                plan_context={"plan_source_text": "Full connected source text."},
                frame_contexts=[
                    {
                        "frame_source_text": "intro",
                        "visual_goal": "Introduce the topic.",
                        "prompt_intent": "Open with continuity.",
                    }
                ],
            ),
            world_preset=_neutral_world(),
            shot_preset={"preset_id": "balanced_explainer"},
            resolved_mode="concept_explainer",
            consistency_strength="standard",
        )
    )

    assert prompt["frame_source_texts"] == ["intro"]
    assert prompt["frame_source_items"] == [{"scene_id": "1", "text": "intro"}]
    assert "narrations" not in prompt
    assert "narration_items" not in prompt
    assert any("frame_source_items" in instruction for instruction in prompt["instructions"])


def test_build_storyboard_planning_prompt_can_request_chinese_output():
    prompt = json.loads(
        build_storyboard_planning_prompt(
            narrations=["intro"],
            world_preset=_neutral_world(),
            shot_preset={"preset_id": "balanced_explainer"},
            resolved_mode="concept_explainer",
            consistency_strength="standard",
            prompt_language="zh_CN",
        )
    )

    assert prompt["prompt_language"] == "zh_CN"
    assert any("in Chinese" in instruction for instruction in prompt["instructions"])


@pytest.mark.asyncio
async def test_plan_storyboard_batch_normalizes_numeric_scene_ids_from_llm():
    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            return """
            {
              "frames": [
                {
                  "scene_id": 1,
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
                  "scene_id": 2,
                  "narration_fragment": "middle",
                  "knowledge_goal": "goal 2",
                  "shot_type": "medium_shot",
                  "shot_purpose": "summary",
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
        narrations=["intro", "middle"],
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
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
                    "supported_scene_count": [2],
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
        content_mode="concept_explainer",
        llm_service=FakeLLM(),
    )

    assert [frame.scene_id for frame in result.frames] == ["1", "2"]


@pytest.mark.asyncio
async def test_plan_storyboard_batch_plans_large_storyboards_in_chunks():
    captured_prompts: list[dict[str, object]] = []
    captured_max_tokens: list[int] = []

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            payload = json.loads(prompt)
            captured_prompts.append(payload)
            captured_max_tokens.append(kwargs["max_tokens"])
            frames = []
            for item in payload["narration_items"]:
                frames.append(
                    {
                        "scene_id": item["scene_id"],
                        "narration_fragment": item["text"],
                        "knowledge_goal": f"goal {item['scene_id']}",
                        "shot_type": "medium_shot",
                        "shot_purpose": "explain",
                        "primary_subject": "subject",
                        "secondary_subjects": [],
                        "world_elements": ["board"],
                        "continuity_anchors": [],
                        "focus_detail": "detail",
                        "prompt_intent": "intent",
                        "locked_fields": [],
                        "override_source": None,
                        "frame_source": "planner_generated",
                        "replan_scope": "local",
                        "planner_version": "1.0",
                    }
                )
            return json.dumps({"frames": frames})

    narrations = [f"scene {index}" for index in range(1, 26)]
    result = await plan_storyboard_batch(
        llm_service=FakeLLM(),
        narrations=narrations,
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
                    "supported_scene_count": list(range(1, 101)),
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
        shot_preset_id="balanced_explainer",
        content_mode="concept_explainer",
        role_strategy="auto",
        classifier_result={"mode": "concept_explainer", "confidence": 0.91},
    )

    assert len(captured_prompts) == 3
    assert [len(prompt["narration_items"]) for prompt in captured_prompts] == [10, 10, 5]
    assert [prompt["narration_items"][0]["scene_id"] for prompt in captured_prompts] == ["1", "11", "21"]
    assert all(max_tokens >= 2400 for max_tokens in captured_max_tokens)
    assert [frame.scene_id for frame in result.frames] == [str(index) for index in range(1, 26)]
    assert result.planning_snapshot["planning_batch_count"] == 3


def test_parse_storyboard_frames_accepts_markdown_fenced_json():
    plans = parse_storyboard_frames(
        """
        ```json
        {
          "frames": []
        }
        ```
        """
    )

    assert plans == []


@pytest.mark.parametrize(
    "raw_response",
    [
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
def test_parse_storyboard_frames_rejects_non_json_wrappers(raw_response: str):
    with pytest.raises(ValueError, match="JSON payload"):
        parse_storyboard_frames(raw_response)


def test_parse_storyboard_frames_rejects_missing_frames_key():
    with pytest.raises(ValueError, match="include a frames array"):
        parse_storyboard_frames('{"not_frames": []}')


@pytest.mark.asyncio
async def test_plan_storyboard_batch_runs_prompt_parse_override_repair_and_snapshot(monkeypatch):
    captured_prompts: list[str] = []
    captured_kwargs: list[dict[str, object]] = []
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
            captured_kwargs.append(dict(kwargs))
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
    assert captured_kwargs[0]["response_type"] is StoryboardPlanningResponse
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
async def test_plan_storyboard_batch_includes_frame_aware_prompt_contexts_in_llm_prompt():
    captured_prompts = []
    planner_frames = [
        {
            "scene_id": "1",
            "narration_fragment": "First idea narration.",
            "knowledge_goal": "goal 1",
            "shot_type": "medium_shot",
            "shot_purpose": "context",
            "primary_subject": "subject 1",
            "secondary_subjects": [],
            "world_elements": ["board"],
            "continuity_anchors": ["shared anchor"],
            "focus_detail": "detail 1",
            "prompt_intent": "intent 1",
            "locked_fields": [],
            "override_source": None,
            "frame_source": "planner_generated",
            "replan_scope": "local",
            "planner_version": "1.0",
        }
    ]

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            captured_prompts.append(prompt)
            return json.dumps({"frames": planner_frames})

    await plan_storyboard_batch(
        llm_service=FakeLLM(),
        narrations=["First idea narration."],
        prompt_contexts=[
            {
                "plan_source_text": "Full script with connected ideas.",
                "frame_source_text": "First idea in the connected script.",
                "visual_goal": "Show the first idea as part of the whole story.",
                "prompt_intent": "Keep continuity with the complete script.",
            }
        ],
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
                    "supported_scene_count": [1],
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
    )

    assert captured_prompts
    assert "prompt_contexts" in captured_prompts[0]
    assert "Full script with connected ideas." in captured_prompts[0]
    assert "Show the first idea as part of the whole story." in captured_prompts[0]


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


@pytest.mark.asyncio
async def test_plan_storyboard_batch_accepts_structured_response_instance(monkeypatch):
    monkeypatch.setattr(
        storyboard_planner_module,
        "parse_storyboard_frames",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("text parser should not run")),
    )

    captured_response_type: list[object] = []

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            captured_response_type.append(kwargs.get("response_type"))
            return StoryboardPlanningResponse(
                frames=[
                    StoryboardPlanningFrameResponse(
                        scene_id="1",
                        narration_fragment="intro",
                        knowledge_goal="goal 1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        primary_subject="subject 1",
                        secondary_subjects=[],
                        world_elements=["board"],
                        continuity_anchors=["anchor 1"],
                        focus_detail="detail 1",
                        prompt_intent="intent 1",
                        locked_fields=[],
                        override_source=None,
                        frame_source="planner_generated",
                        replan_scope="local",
                        planner_version="1.0",
                    )
                ]
            )

    result = await plan_storyboard_batch(
        llm_service=FakeLLM(),
        narrations=["first"],
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
                    "supported_scene_count": [1],
                    "override_policy": "adaptive",
                    "shot_distribution_rules": [],
                }
            ],
        },
        shot_preset_id="balanced_explainer",
        content_mode="concept_explainer",
        role_strategy="auto",
        classifier_result={"mode": "concept_explainer", "confidence": 0.91},
    )

    assert captured_response_type == [StoryboardPlanningResponse]
    assert [frame.scene_id for frame in result.frames] == ["1"]


@pytest.mark.asyncio
async def test_plan_storyboard_batch_passes_generation_world_profile_to_prompt(monkeypatch):
    captured = {}

    async def fake_llm_service(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return StoryboardPlanningResponse(
            frames=[
                StoryboardPlanningFrameResponse(
                    scene_id="1",
                    narration_fragment="从长乐门出发。",
                    knowledge_goal="建立正定古城入口认知",
                    shot_type="medium_shot",
                    shot_purpose="context",
                    primary_subject="长乐门",
                    secondary_subjects=[],
                    world_elements=["青砖城墙"],
                    continuity_anchors=["长乐门"],
                    focus_detail="清晨古城入口",
                    prompt_intent="建立古城漫游开篇",
                    locked_fields=[],
                    override_source=None,
                    frame_source="planner_generated",
                    replan_scope="local",
                    planner_version="1.0",
                )
            ]
        )

    result = await plan_storyboard_batch(
        llm_service=fake_llm_service,
        narrations=["从长乐门出发。"],
        generation_world_profile=ContentWorldProfile(
            summary="正定古城清晨漫游",
            story_constraints="不能替代长乐门",
            ip_integration_guidance="IP 作为陪伴式向导",
        ),
        world_preset_id="neutral_knowledge_storyboard",
    )

    assert "generation_world_profile" in captured["prompt"]
    assert "正定古城清晨漫游" in captured["prompt"]
    assert result.planning_snapshot["generation_world_profile"]["summary"] == "正定古城清晨漫游"


@pytest.mark.asyncio
async def test_plan_storyboard_batch_omits_empty_generation_world_profile(monkeypatch):
    captured = {}

    async def fake_llm_service(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return StoryboardPlanningResponse(
            frames=[
                StoryboardPlanningFrameResponse(
                    scene_id="1",
                    narration_fragment="从长乐门出发。",
                    knowledge_goal="建立正定古城入口认知",
                    shot_type="medium_shot",
                    shot_purpose="context",
                    primary_subject="长乐门",
                    secondary_subjects=[],
                    world_elements=["青砖城墙"],
                    continuity_anchors=["长乐门"],
                    focus_detail="清晨古城入口",
                    prompt_intent="建立古城漫游开篇",
                    locked_fields=[],
                    override_source=None,
                    frame_source="planner_generated",
                    replan_scope="local",
                    planner_version="1.0",
                )
            ]
        )

    result = await plan_storyboard_batch(
        llm_service=fake_llm_service,
        narrations=["从长乐门出发。"],
        generation_world_profile={},
        world_preset_id="neutral_knowledge_storyboard",
    )

    assert "generation_world_profile" not in captured["prompt"]
    assert "generation_world_profile" not in result.planning_snapshot
