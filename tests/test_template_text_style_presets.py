import pytest

from pixelle_video.models.template_text_style_presets import (
    TEMPLATE_TEXT_STYLE_PRESETS,
    TemplateTextStylePreset,
    normalize_template_id,
    require_template_text_style_preset,
    resolve_template_text_style_preset,
)
from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


def test_template_text_style_presets_cover_phase1_title_templates():
    assert set(TEMPLATE_TEXT_STYLE_PRESETS) == {
        "image_default",
        "image_life_insights_light",
        "image_landscape_full",
        "image_landscape_minimal",
    }

    for template_id, preset in TEMPLATE_TEXT_STYLE_PRESETS.items():
        assert preset.template_id == template_id
        assert preset.title_style["id"] == DEFAULT_TITLE_STYLE_ID
        assert preset.title_region["x"] >= 0
        assert preset.title_region["y"] >= 0
        assert preset.title_region["width"] > 0
        assert preset.title_region["height"] > 0
        assert preset.caption_safe_area["width"] > 0
        assert preset.caption_safe_area["height"] > 0


def test_normalize_template_id_accepts_frame_template_paths():
    assert normalize_template_id("1080x1920/image_default.html") == "image_default"
    assert normalize_template_id("image_landscape_full") == "image_landscape_full"
    assert normalize_template_id(None) is None


def test_resolve_template_text_style_preset_returns_generic_for_missing_template():
    preset = resolve_template_text_style_preset("static_plain")

    assert isinstance(preset, TemplateTextStylePreset)
    assert preset.template_id == "generic"
    assert preset.title_style["id"] == DEFAULT_TITLE_STYLE_ID


def test_require_template_text_style_preset_fails_for_missing_title_region_preset():
    with pytest.raises(ValueError, match="title preset"):
        require_template_text_style_preset("static_plain")
