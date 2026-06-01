import pytest

from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_STYLE_ID,
    DEFAULT_OVERLAY_STYLE_ID,
    DEFAULT_TITLE_STYLE_ID,
    TextStyleProfile,
    build_default_text_style_profiles,
    normalize_hex_color,
)


def test_text_style_profile_round_trips_with_normalized_colors():
    profile = TextStyleProfile(
        id="caption-default",
        name="Caption Default",
        font_size=68,
        primary_color="#ffff00",
        stroke_color="#000000",
        background_color="#111111",
        shadow_color="#222222",
        background_opacity=0.35,
        margin_y=120,
    )

    restored = TextStyleProfile.from_dict(profile.to_dict())

    assert restored == TextStyleProfile(
        id="caption-default",
        name="Caption Default",
        font_size=68,
        primary_color="#FFFF00",
        stroke_color="#000000",
        background_color="#111111",
        shadow_color="#222222",
        background_opacity=0.35,
        margin_y=120,
    )


def test_normalize_hex_color_accepts_none_and_rejects_invalid_values():
    assert normalize_hex_color(None) is None

    with pytest.raises(ValueError, match="hex color"):
        normalize_hex_color("yellow")


def test_text_style_profile_rejects_invalid_opacity():
    with pytest.raises(ValueError, match="background_opacity"):
        TextStyleProfile(id="bad", name="Bad", background_opacity=1.5)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"id": ""}, "id"),
        ({"font_size": 0}, "font_size"),
        ({"stroke_width": -1}, "stroke_width"),
        ({"shadow_blur": -1}, "shadow_blur"),
        ({"margin_x": -1}, "margin"),
        ({"position": "middle"}, "position"),
        ({"alignment": "justify"}, "alignment"),
        ({"scale_basis_width": 0}, "scale basis"),
        ({"scale_basis_height": 0}, "scale basis"),
    ],
)
def test_text_style_profile_rejects_invalid_contract_values(kwargs, message):
    payload = {"id": "style", "name": "Style"}
    payload.update(kwargs)
    with pytest.raises(ValueError, match=message):
        TextStyleProfile(**payload)


def test_text_style_profile_scale_for_canvas_clamps_canvas_dimensions():
    profile = TextStyleProfile(id="style", name="Style")

    assert profile.scale_for_canvas(540, 960) == 1.0
    assert profile.scale_for_canvas(0, 0) == 1.0


def test_text_style_profile_scales_only_when_scale_basis_is_explicit():
    profile = TextStyleProfile(
        id="style",
        name="Style",
        scale_basis_width=1080,
        scale_basis_height=1920,
    )

    assert profile.scale_for_canvas(540, 960) == 0.5
    assert profile.scale_for_canvas(0, 0) == min(1 / 1080, 1 / 1920)


def test_default_text_style_profiles_include_caption_title_and_overlay_defaults():
    profiles = build_default_text_style_profiles(template_id="image_landscape_minimal")

    assert [profile.id for profile in profiles] == [
        DEFAULT_CAPTION_STYLE_ID,
        DEFAULT_TITLE_STYLE_ID,
        DEFAULT_OVERLAY_STYLE_ID,
    ]
    assert profiles[0].position == "bottom"
    assert profiles[0].font_size == 36
    assert profiles[0].font_weight == 500
    assert profiles[0].primary_color == "#000000"
    assert profiles[0].stroke_width == 0
    assert profiles[0].shadow_color is None
    assert profiles[0].shadow_blur == 0
    title = profiles[1]
    assert title.name == "Title Default"
    assert title.position == "top_left"
    assert title.font_size == 55
    assert title.primary_color == "#000000"
    assert title.stroke_width == 0
    assert title.shadow_color is None
    assert title.shadow_blur == 0
    assert title.background_color == "#FFFFFF"
    assert title.background_opacity == 0.0
    assert profiles[2].name == "Overlay Default"
    assert profiles[2].font_size == 76
    assert profiles[2].primary_color == "#FFFFFF"
    assert profiles[2].stroke_width == 2
    assert profiles[2].position == "center"
    assert profiles[2].margin_y == 80


def test_default_title_background_opacity_is_zero_for_all_system_template_presets():
    for template_id in (
        "image_default",
        "image_life_insights_light",
        "image_landscape_full",
        "image_landscape_minimal",
    ):
        title_profile = build_default_text_style_profiles(template_id=template_id)[1]
        assert title_profile.background_opacity == 0.0


def test_default_text_style_profiles_apply_scale_basis_to_all_profiles():
    profiles = build_default_text_style_profiles(
        template_id="image_default",
        canvas_width=1080,
        canvas_height=1920,
    )

    assert [profile.scale_basis_width for profile in profiles] == [1080, 1080, 1080]
    assert [profile.scale_basis_height for profile in profiles] == [1920, 1920, 1920]


def test_text_style_profile_from_dict_preserves_defaults_for_missing_fields():
    profile = TextStyleProfile.from_dict({"id": "minimal", "name": "Minimal"})

    assert profile.version == "text_style_profile.v1"
    assert profile.font_family == "Noto Sans CJK SC"
    assert profile.font_size == 36
    assert profile.font_weight == 500
    assert profile.primary_color == "#000000"
    assert profile.stroke_color == "#000000"
    assert profile.stroke_width == 0
    assert profile.shadow_color is None
    assert profile.shadow_blur == 0
