import pytest

from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.storyboard_preset_library import (
    build_builtin_shot_preset_library_dict,
    build_builtin_world_preset_library_dict,
    lookup_world_preset,
)


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
    assert 5 in balanced["supported_scene_count"]


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


def test_lookup_world_preset_raises_for_invalid_requested_or_default_ids():
    library = build_builtin_world_preset_library_dict()

    with pytest.raises(ValueError, match="unknown world preset id: missing_preset"):
        lookup_world_preset(library, "missing_preset")

    invalid_default_library = dict(library, default_world_preset_id="missing_default")
    with pytest.raises(ValueError, match="unknown world preset id: missing_default"):
        lookup_world_preset(invalid_default_library)


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
