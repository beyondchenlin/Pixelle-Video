from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.storyboard_preset_library import (
    build_builtin_shot_preset_library_dict,
    build_builtin_world_preset_library_dict,
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
