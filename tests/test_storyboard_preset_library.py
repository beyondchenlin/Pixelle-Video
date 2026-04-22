import itertools

import pytest

from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.storyboard_preset_library import (
    build_builtin_shot_preset_library_dict,
    build_builtin_world_preset_library_dict,
    load_shot_preset_map,
    lookup_world_preset,
)
from pixelle_video.services.storyboard_planner import plan_storyboard_batch


def test_build_builtin_world_preset_library_dict_uses_neutral_knowledge_default():
    library = build_builtin_world_preset_library_dict()

    assert library["default_world_preset_id"] == "neutral_knowledge_storyboard"
    neutral = next(item for item in library["items"] if item["preset_id"] == "neutral_knowledge_storyboard")
    assert neutral["safe_default"] is True
    assert neutral["supported_modes"] == ["theme_mapping", "concept_explainer"]
    assert neutral["conservative_fallback_mode"] == "concept_explainer"
    assert neutral["default_shot_preset_ids"] == ["balanced_explainer", "detail_focus"]


def test_neutral_world_preset_has_mode_specific_cast_slots():
    library = build_builtin_world_preset_library_dict()
    neutral = next(item for item in library["items"] if item["preset_id"] == "neutral_knowledge_storyboard")

    assert set(neutral["cast_slots_by_mode"].keys()) == set(neutral["supported_modes"])


def test_dual_mode_world_preset_has_mode_aligned_cast_slots_and_fallback():
    library = build_builtin_world_preset_library_dict()
    dual_mode = next(item for item in library["items"] if item["preset_id"] != "neutral_knowledge_storyboard")

    assert set(dual_mode["cast_slots_by_mode"].keys()) == set(dual_mode["supported_modes"])
    assert dual_mode["conservative_fallback_mode"] in dual_mode["supported_modes"]


def test_build_builtin_shot_preset_library_dict_uses_balanced_explainer_default():
    library = build_builtin_shot_preset_library_dict()

    assert library["default_shot_preset_id"] == "balanced_explainer"
    balanced = next(item for item in library["items"] if item["preset_id"] == "balanced_explainer")
    assert balanced["override_policy"] == "adaptive"
    assert balanced["max_consecutive_same"] == 2
    assert 5 in balanced["supported_scene_count"]
    detail_focus = next(item for item in library["items"] if item["preset_id"] == "detail_focus")
    assert detail_focus["max_consecutive_same"] == 1


def test_pixelle_video_config_bootstraps_storyboard_libraries():
    config = PixelleVideoConfig()

    assert config.storyboard.world_preset_library.default_world_preset_id == "neutral_knowledge_storyboard"
    assert config.storyboard.shot_preset_library.default_shot_preset_id == "balanced_explainer"


def test_partial_storyboard_library_inputs_merge_builtin_defaults():
    config = PixelleVideoConfig.model_validate(
        {
            "storyboard": {
                "world_preset_library": {
                    "default_world_preset_id": "dual_mode_storyboard",
                },
                "shot_preset_library": {
                    "default_shot_preset_id": "detail_focus",
                },
            }
        }
    )

    assert config.storyboard.world_preset_library.default_world_preset_id == "dual_mode_storyboard"
    assert config.storyboard.shot_preset_library.default_shot_preset_id == "detail_focus"
    assert len(config.storyboard.world_preset_library.items) == len(build_builtin_world_preset_library_dict()["items"])
    assert len(config.storyboard.shot_preset_library.items) == len(build_builtin_shot_preset_library_dict()["items"])


def test_invalid_storyboard_default_world_preset_id_rejects_validation():
    with pytest.raises(ValueError, match="unknown default_world_preset_id: missing_world"):
        PixelleVideoConfig.model_validate(
            {
                "storyboard": {
                    "world_preset_library": {
                        "default_world_preset_id": "missing_world",
                    }
                }
            }
        )


def test_invalid_storyboard_default_shot_preset_id_rejects_validation():
    with pytest.raises(ValueError, match="unknown default_shot_preset_id: missing_shot"):
        PixelleVideoConfig.model_validate(
            {
                "storyboard": {
                    "shot_preset_library": {
                        "default_shot_preset_id": "missing_shot",
                    }
                }
            }
        )


def test_world_preset_reference_to_missing_shot_preset_rejects_validation():
    with pytest.raises(ValueError, match="references missing shot preset ids: missing_shot"):
        PixelleVideoConfig.model_validate(
            {
                "storyboard": {
                    "world_preset_library": {
                        "items": [
                            {
                                "preset_id": "neutral_knowledge_storyboard",
                                "default_shot_preset_ids": ["missing_shot"],
                            }
                        ]
                    }
                }
            }
        )


def test_malformed_storyboard_library_item_without_preset_id_rejects_validation():
    with pytest.raises(ValueError, match="malformed storyboard preset item: missing preset_id"):
        PixelleVideoConfig.model_validate(
            {
                "storyboard": {
                    "world_preset_library": {
                        "items": [
                            {
                                "display_name": "Broken preset",
                            }
                        ]
                    }
                }
            }
        )


@pytest.mark.parametrize(
    ("world_item", "error_message"),
    [
        (
            {
                "preset_id": "custom_world",
                "display_name": "Custom World",
                "supported_modes": ["concept_explainer"],
                "conservative_fallback_mode": "theme_mapping",
            },
            "conservative_fallback_mode must be one of supported_modes",
        ),
        (
            {
                "preset_id": "custom_world",
                "display_name": "Custom World",
                "supported_modes": ["concept_explainer"],
                "forced_mode": "theme_mapping",
            },
            "forced_mode must be one of supported_modes",
        ),
        (
            {
                "preset_id": "custom_world",
                "display_name": "Custom World",
                "supported_modes": ["theme_mapping", "concept_explainer"],
                "conservative_fallback_mode": "concept_explainer",
                "cast_slots_by_mode": {
                    "theme_mapping": [],
                    "unsupported_mode": [],
                },
            },
            "cast_slots_by_mode contains unsupported modes",
        ),
        (
            {
                "preset_id": "custom_world",
                "display_name": "Custom World",
                "supported_modes": ["theme_mapping", "concept_explainer"],
                "conservative_fallback_mode": "concept_explainer",
                "cast_slots_by_mode": {
                    "theme_mapping": [],
                },
            },
            "cast_slots_by_mode must cover all supported modes",
        ),
    ],
)
def test_invalid_custom_world_preset_combinations_reject_validation(world_item, error_message):
    with pytest.raises(ValueError, match=error_message):
        PixelleVideoConfig.model_validate(
            {
                "storyboard": {
                    "world_preset_library": {
                        "items": [world_item],
                    }
                }
            }
        )


def test_lookup_world_preset_raises_for_invalid_requested_or_default_ids():
    library = build_builtin_world_preset_library_dict()

    with pytest.raises(ValueError, match="unknown world preset id: missing_preset"):
        lookup_world_preset(library, "missing_preset")

    invalid_default_library = dict(library, default_world_preset_id="missing_default")
    with pytest.raises(ValueError, match="unknown world preset id: missing_default"):
        lookup_world_preset(invalid_default_library)


def test_load_shot_preset_map_rejects_items_missing_preset_id():
    with pytest.raises(ValueError, match="malformed storyboard shot preset item: missing preset_id"):
        load_shot_preset_map({"items": [{"display_name": "Broken shot"}]})


def test_config_manager_exposes_storyboard_library_getters():
    manager = object.__new__(ConfigManager)
    manager.config_path = None
    manager.config = PixelleVideoConfig()

    world_library = manager.get_storyboard_world_preset_library()
    shot_library = manager.get_storyboard_shot_preset_library()

    assert world_library["default_world_preset_id"] == "neutral_knowledge_storyboard"
    assert shot_library["default_shot_preset_id"] == "balanced_explainer"
    assert world_library["items"]
    assert shot_library["items"]


@pytest.mark.asyncio
async def test_builtin_shot_preset_path_propagates_numeric_repair_rule(monkeypatch):
    monkeypatch.setattr(
        "pixelle_video.services.storyboard_planner.config_manager.get_storyboard_shot_preset_library",
        lambda: build_builtin_shot_preset_library_dict(),
    )
    monkeypatch.setattr(
        "pixelle_video.services.storyboard_planner.config_manager.get_storyboard_world_preset_library",
        lambda: build_builtin_world_preset_library_dict(),
    )

    class FakeLLM:
        async def __call__(self, *, prompt: str, **kwargs):
            return """
            {
              "frames": [
                {
                  "scene_id": "1",
                  "narration_fragment": "intro",
                  "knowledge_goal": "goal 1",
                  "shot_type": "close_up",
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
                  "shot_type": "close_up",
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
                  "shot_type": "close_up",
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
        shot_preset_id="detail_focus",
        content_mode="concept_explainer",
        role_strategy="auto",
        classifier_result={"mode": "concept_explainer", "confidence": 0.95},
    )

    assert result.resolved_shot_preset.preset_id == "detail_focus"
    assert result.resolved_shot_preset.max_consecutive_same == 1
    assert result.planning_snapshot["resolved_shot_preset_details"]["max_consecutive_same"] == 1
    assert result.planning_snapshot["resolved_shot_preset_details"]["selection_source"] == "user_selected"
    assert max(
        len(list(group))
        for _, group in itertools.groupby([frame.shot_type for frame in result.frames])
    ) <= 1
