import itertools

import pytest

from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.schema import (
    PixelleVideoConfig,
    StoryboardShotPresetItemConfig,
    StoryboardWorldPresetItemConfig,
)
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
    dual_mode = next(item for item in library["items"] if item["preset_id"] == "dual_mode_storyboard")

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


def test_storyboard_shot_preset_schema_preserves_numeric_repair_rule():
    config = PixelleVideoConfig()

    model_dump = config.storyboard.shot_preset_library.model_dump()
    balanced = next(item for item in model_dump["items"] if item["preset_id"] == "balanced_explainer")
    detail_focus = next(item for item in model_dump["items"] if item["preset_id"] == "detail_focus")

    assert balanced["max_consecutive_same"] == 2
    assert detail_focus["max_consecutive_same"] == 1


def test_storyboard_world_preset_schema_preserves_localization_metadata():
    config = PixelleVideoConfig()

    model_dump = config.storyboard.world_preset_library.model_dump()
    neutral = next(item for item in model_dump["items"] if item["preset_id"] == "neutral_knowledge_storyboard")

    assert neutral["display_name_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.name"
    assert neutral["description_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.description"


@pytest.mark.parametrize(
    ("preset_id", "display_name_key", "description_key"),
    [
        (
            "angry_birds_three_kingdoms",
            "storyboard.preset.world.angry_birds_three_kingdoms.name",
            "storyboard.preset.world.angry_birds_three_kingdoms.description",
        ),
        (
            "angry_birds_knowledge_classroom",
            "storyboard.preset.world.angry_birds_knowledge_classroom.name",
            "storyboard.preset.world.angry_birds_knowledge_classroom.description",
        ),
        (
            "angry_birds_history_classroom",
            "storyboard.preset.world.angry_birds_history_classroom.name",
            "storyboard.preset.world.angry_birds_history_classroom.description",
        ),
    ],
)
def test_task2_world_presets_preserve_localization_metadata_after_bootstrap(
    preset_id, display_name_key, description_key
):
    config = PixelleVideoConfig()

    model_dump = config.storyboard.world_preset_library.model_dump()
    preset = next(item for item in model_dump["items"] if item["preset_id"] == preset_id)

    assert preset["display_name_key"] == display_name_key
    assert preset["description_key"] == description_key


def test_storyboard_shot_preset_schema_preserves_localization_metadata():
    config = PixelleVideoConfig()

    model_dump = config.storyboard.shot_preset_library.model_dump()
    balanced = next(item for item in model_dump["items"] if item["preset_id"] == "balanced_explainer")

    assert balanced["display_name_key"] == "storyboard.preset.shot.balanced_explainer.name"
    assert balanced["description_key"] == "storyboard.preset.shot.balanced_explainer.description"


@pytest.mark.parametrize(
    ("preset_id", "display_name_key", "description_key"),
    [
        (
            "opening_world_building",
            "storyboard.preset.shot.opening_world_building.name",
            "storyboard.preset.shot.opening_world_building.description",
        ),
        (
            "character_relationship",
            "storyboard.preset.shot.character_relationship.name",
            "storyboard.preset.shot.character_relationship.description",
        ),
        (
            "classroom_demo",
            "storyboard.preset.shot.classroom_demo.name",
            "storyboard.preset.shot.classroom_demo.description",
        ),
    ],
)
def test_task2_shot_presets_preserve_localization_metadata_after_bootstrap(
    preset_id, display_name_key, description_key
):
    config = PixelleVideoConfig()

    model_dump = config.storyboard.shot_preset_library.model_dump()
    preset = next(item for item in model_dump["items"] if item["preset_id"] == preset_id)

    assert preset["display_name_key"] == display_name_key
    assert preset["description_key"] == description_key


def test_builtin_world_preset_library_contains_expanded_catalog():
    library = build_builtin_world_preset_library_dict()
    preset_ids = [item["preset_id"] for item in library["items"]]

    assert preset_ids == [
        "neutral_knowledge_storyboard",
        "dual_mode_storyboard",
        "angry_birds_three_kingdoms",
        "angry_birds_knowledge_classroom",
        "angry_birds_history_classroom",
    ]


def test_builtin_shot_preset_library_contains_expanded_catalog():
    library = build_builtin_shot_preset_library_dict()
    preset_ids = [item["preset_id"] for item in library["items"]]

    assert preset_ids == [
        "balanced_explainer",
        "detail_focus",
        "opening_world_building",
        "character_relationship",
        "classroom_demo",
    ]


def test_angry_birds_three_kingdoms_uses_theme_mapping_with_expected_cast_and_shots():
    library = build_builtin_world_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "angry_birds_three_kingdoms")

    assert preset["supported_modes"] == ["theme_mapping"]
    assert preset["forced_mode"] == "theme_mapping"
    assert preset["conservative_fallback_mode"] == "theme_mapping"
    assert preset["default_shot_preset_ids"] == [
        "character_relationship",
        "opening_world_building",
        "balanced_explainer",
    ]
    assert preset["cast_slots"] == [
        {
            "slot_id": "shu_leader",
            "semantic_role": "shu_leader",
            "visual_anchor": "warm-toned leader bird",
            "prop_anchor": "banner or oath scroll",
            "personality_anchor": "benevolent and steady",
            "theme_mapping_rule": "map Shu leadership figures into this slot",
            "reuse_priority": 95,
        },
        {
            "slot_id": "wei_leader",
            "semantic_role": "wei_leader",
            "visual_anchor": "cool-toned command bird",
            "prop_anchor": "command tablet or banner",
            "personality_anchor": "strategic and forceful",
            "theme_mapping_rule": "map Wei leadership figures into this slot",
            "reuse_priority": 94,
        },
        {
            "slot_id": "strategist",
            "semantic_role": "strategist",
            "visual_anchor": "clever adviser bird",
            "prop_anchor": "war map or fan",
            "personality_anchor": "calm and analytical",
            "theme_mapping_rule": "map tacticians and planners into this slot",
            "reuse_priority": 92,
        },
        {
            "slot_id": "warrior_support",
            "semantic_role": "warrior_support",
            "visual_anchor": "strong support bird",
            "prop_anchor": "weapon prop or shield marker",
            "personality_anchor": "loyal and energetic",
            "theme_mapping_rule": "map martial support roles into this slot",
            "reuse_priority": 88,
        },
        {
            "slot_id": "learner_observer",
            "semantic_role": "learner_observer",
            "visual_anchor": "curious observer bird",
            "prop_anchor": "notes or study card",
            "personality_anchor": "curious and attentive",
            "theme_mapping_rule": "use as the audience-surrogate learner slot",
            "reuse_priority": 80,
        },
    ]


def test_angry_birds_knowledge_classroom_uses_expected_mode_shots_and_cast_slots():
    library = build_builtin_world_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "angry_birds_knowledge_classroom")

    assert preset["supported_modes"] == ["concept_explainer"]
    assert preset["forced_mode"] == "concept_explainer"
    assert preset["conservative_fallback_mode"] == "concept_explainer"
    assert preset["default_shot_preset_ids"] == [
        "classroom_demo",
        "balanced_explainer",
        "detail_focus",
    ]
    assert preset["cast_slots"] == [
        {
            "slot_id": "host_explainer",
            "semantic_role": "host_explainer",
            "visual_anchor": "confident presenter bird",
            "prop_anchor": "board pointer or diagram card",
            "personality_anchor": "clear and friendly",
            "theme_mapping_rule": "keep the main explainer stable across concept topics",
            "reuse_priority": 96,
        },
        {
            "slot_id": "learner_support",
            "semantic_role": "learner_support",
            "visual_anchor": "engaged learner bird",
            "prop_anchor": "notebook or label card",
            "personality_anchor": "curious and receptive",
            "theme_mapping_rule": "support teaching beats with reaction and comparison framing",
            "reuse_priority": 84,
        },
        {
            "slot_id": "demo_assistant",
            "semantic_role": "demo_assistant",
            "visual_anchor": "helper bird near props",
            "prop_anchor": "sample object or experiment prop",
            "personality_anchor": "helpful and practical",
            "theme_mapping_rule": "support demonstrations and staged comparisons",
            "reuse_priority": 78,
        },
    ]


def test_angry_birds_history_classroom_uses_mode_specific_cast_slot_mapping():
    library = build_builtin_world_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "angry_birds_history_classroom")

    assert "cast_slots_by_mode" in preset
    assert preset["default_shot_preset_ids"] == [
        "opening_world_building",
        "balanced_explainer",
        "character_relationship",
    ]
    assert set(preset["cast_slots_by_mode"].keys()) == {"theme_mapping", "concept_explainer"}
    assert preset["cast_slots_by_mode"]["theme_mapping"] == [
        {
            "slot_id": "history_figure_lead",
            "semantic_role": "history_figure_lead",
            "visual_anchor": "mapped history lead bird",
            "prop_anchor": "timeline marker or emblem",
            "personality_anchor": "grounded and recognizable",
            "theme_mapping_rule": "map named historical figures into this lead slot",
            "reuse_priority": 90,
        },
        {
            "slot_id": "era_context_support",
            "semantic_role": "era_context_support",
            "visual_anchor": "era context support bird",
            "prop_anchor": "map or era card",
            "personality_anchor": "contextual and explanatory",
            "theme_mapping_rule": "carry factions, periods, or comparison context",
            "reuse_priority": 82,
        },
        {
            "slot_id": "narrator_moderator",
            "semantic_role": "narrator_moderator",
            "visual_anchor": "teaching moderator bird",
            "prop_anchor": "pointer or podium",
            "personality_anchor": "measured and helpful",
            "theme_mapping_rule": "stabilize narration through topic shifts",
            "reuse_priority": 85,
        },
    ]
    assert preset["cast_slots_by_mode"]["concept_explainer"] == [
        {
            "slot_id": "history_host",
            "semantic_role": "history_host",
            "visual_anchor": "history lecturer bird",
            "prop_anchor": "timeline board or podium",
            "personality_anchor": "clear and welcoming",
            "theme_mapping_rule": "anchor history explainer lessons with a stable host",
            "reuse_priority": 92,
        },
        {
            "slot_id": "timeline_support",
            "semantic_role": "timeline_support",
            "visual_anchor": "timeline guide bird",
            "prop_anchor": "timeline marker or era card",
            "personality_anchor": "organized and contextual",
            "theme_mapping_rule": "support chronology, sequence, and era transitions in history lessons",
            "reuse_priority": 80,
        },
        {
            "slot_id": "student_observer",
            "semantic_role": "student_observer",
            "visual_anchor": "learner observer bird",
            "prop_anchor": "notes or question card",
            "personality_anchor": "curious and focused",
            "theme_mapping_rule": "provide audience viewpoint for history concept beats",
            "reuse_priority": 76,
        },
    ]


def test_classroom_demo_shot_preset_prefers_medium_teaching_rhythm():
    library = build_builtin_shot_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "classroom_demo")
    config_preset = next(
        item
        for item in PixelleVideoConfig().storyboard.shot_preset_library.model_dump()["items"]
        if item["preset_id"] == "classroom_demo"
    )

    for item in (preset, config_preset):
        assert item["supported_scene_count"] == [3, 4, 5, 6]
        assert item["max_consecutive_same"] == 2
        assert item["shot_distribution_rules"] == [
            "favor medium teaching frames as the backbone of the lesson rhythm",
            "adapt close detail inserts around the core teaching cadence when needed",
        ]
        assert item["opening_rules"] == ["start with a readable teacher-and-demo setup"]
        assert item["closing_rules"] == ["end on the clearest demonstrated takeaway or recap beat"]
        assert item["transition_rules"] == [
            "cycle between medium teaching coverage and selective detail emphasis",
        ]
        assert item["purpose_bias"] == "medium-shot teaching rhythm bias for classroom demonstrations"
        assert item["override_policy"] == "adaptive"


def test_opening_world_building_shot_preset_requires_establishing_opening_and_gradual_tightening():
    library = build_builtin_shot_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "opening_world_building")
    config_preset = next(
        item
        for item in PixelleVideoConfig().storyboard.shot_preset_library.model_dump()["items"]
        if item["preset_id"] == "opening_world_building"
    )

    for item in (preset, config_preset):
        assert item["supported_scene_count"] == [4, 5, 6, 7]
        assert item["max_consecutive_same"] == 2
        assert item["shot_distribution_rules"] == [
            "favor wider establishing coverage early before tightening into teaching beats",
            "require at least one long/full establishing frame in the opening portion",
            "adapt shot distance based on scene count while keeping the world readable",
        ]
        assert item["opening_rules"] == [
            "open with a long/full establishing frame that makes world, cast, and spatial context immediately readable"
        ]
        assert item["closing_rules"] == ["close on a clear knowledge takeaway after the world has been established"]
        assert item["transition_rules"] == [
            "tighten coverage gradually with a wide -> medium -> detail progression as the lesson focus sharpens",
        ]
        assert item["purpose_bias"] == "world-establishing opening bias for teaching-first story setups"
        assert item["override_policy"] == "adaptive"


def test_character_relationship_shot_preset_prefers_full_medium_alternation_and_limits_extreme_closeups():
    library = build_builtin_shot_preset_library_dict()
    preset = next(item for item in library["items"] if item["preset_id"] == "character_relationship")
    config_preset = next(
        item
        for item in PixelleVideoConfig().storyboard.shot_preset_library.model_dump()["items"]
        if item["preset_id"] == "character_relationship"
    )

    for item in (preset, config_preset):
        assert item["supported_scene_count"] == [3, 4, 5, 6, 7]
        assert item["max_consecutive_same"] == 2
        assert item["shot_distribution_rules"] == [
            "favor two-shots and readable groupings when relationships matter",
            "prefer full/medium alternation so relationship beats stay legible across scenes",
            "adapt framing to preserve comparison clarity across scene counts",
        ]
        assert item["opening_rules"] == ["open with relationship context that makes the key subjects readable together"]
        assert item["closing_rules"] == ["end on the clearest relationship takeaway or contrast beat"]
        assert item["transition_rules"] == [
            "prefer full/medium alternation over frequent/repeated extreme close-ups to preserve relationship readability",
        ]
        assert item["purpose_bias"] == "relationship readability bias for role, faction, and comparison-heavy topics"
        assert item["override_policy"] == "adaptive"


def test_partial_typed_storyboard_override_preserves_localization_metadata():
    config = PixelleVideoConfig.model_validate(
        {
            "storyboard": {
                "world_preset_library": {
                    "items": [
                        StoryboardWorldPresetItemConfig(
                            preset_id="neutral_knowledge_storyboard",
                            display_name="Neutral Knowledge Storyboard",
                            supported_modes=["theme_mapping", "concept_explainer"],
                            conservative_fallback_mode="concept_explainer",
                            cast_slots_by_mode={"theme_mapping": [], "concept_explainer": []},
                        )
                    ],
                },
                "shot_preset_library": {
                    "items": [
                        StoryboardShotPresetItemConfig(
                            preset_id="balanced_explainer",
                            display_name="Balanced Explainer",
                        )
                    ],
                },
            }
        }
    )

    world_item = next(
        item for item in config.storyboard.world_preset_library.model_dump()["items"]
        if item["preset_id"] == "neutral_knowledge_storyboard"
    )
    shot_item = next(
        item for item in config.storyboard.shot_preset_library.model_dump()["items"]
        if item["preset_id"] == "balanced_explainer"
    )

    assert world_item["display_name_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.name"
    assert world_item["description_key"] == "storyboard.preset.world.neutral_knowledge_storyboard.description"
    assert shot_item["display_name_key"] == "storyboard.preset.shot.balanced_explainer.name"
    assert shot_item["description_key"] == "storyboard.preset.shot.balanced_explainer.description"


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


def test_lookup_world_preset_returns_dual_mode_storyboard_for_explicit_preset_id():
    preset = lookup_world_preset(build_builtin_world_preset_library_dict(), "dual_mode_storyboard")

    assert preset["preset_id"] == "dual_mode_storyboard"
    assert preset["supported_modes"] == ["theme_mapping", "concept_explainer"]


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
    balanced = next(item for item in shot_library["items"] if item["preset_id"] == "balanced_explainer")
    assert balanced["max_consecutive_same"] == 2


@pytest.mark.asyncio
async def test_builtin_shot_preset_path_propagates_numeric_repair_rule(monkeypatch):
    from pixelle_video.services.storyboard_planner import config_manager as planner_config_manager

    monkeypatch.setattr(planner_config_manager, "config", PixelleVideoConfig())

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
