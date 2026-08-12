import pytest

from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.services.ass_style_builder import AssStyleBuilder, ass_color


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("#FFFFFF", "&H00FFFFFF"),
        ("#000000", "&H00000000"),
        ("#FFCC00", "&H0000CCFF"),
    ],
)
def test_ass_color_converts_hex_rgb_to_ass_bbggrr(source, expected):
    assert ass_color(source) == expected


@pytest.mark.parametrize("source", ["FFFFFF", "#FFF", "#FFFFFG", "#00000000", "blue"])
def test_ass_color_rejects_invalid_hex_values(source):
    with pytest.raises(ValueError, match="hex color"):
        ass_color(source)


@pytest.mark.parametrize("alpha", [-1, 256, 1.5, True, "1"])
def test_ass_color_rejects_invalid_alpha_values(alpha):
    with pytest.raises(ValueError, match="alpha"):
        ass_color("#FFFFFF", alpha=alpha)


def test_build_style_scales_font_outline_shadow_and_margins_for_canvas():
    profile = TextStyleProfile(
        id="caption",
        name="Caption",
        font_size=64,
        stroke_width=4,
        shadow_blur=0,
        margin_y=140,
        scale_basis_width=1080,
        scale_basis_height=1920,
    )

    style = AssStyleBuilder().build_style(
        "Scaled", profile, canvas_width=720, canvas_height=1280
    )

    assert style.startswith("Style: Scaled,Noto Sans SC,43,")
    assert ",3,0,2,53,53,93,1" in style


@pytest.mark.parametrize("name", ["Bad,Name", "Bad\rName", "Bad\nName"])
def test_build_style_rejects_style_names_that_break_ass_fields(name):
    profile = TextStyleProfile(id="style", name="Style")

    with pytest.raises(ValueError, match="style name"):
        AssStyleBuilder().build_style(
            name, profile, canvas_width=1080, canvas_height=1920
        )


@pytest.mark.parametrize("font_family", ["Bad,Font", "Bad\rFont", "Bad\nFont"])
def test_build_style_rejects_font_families_that_break_ass_fields(font_family):
    profile = TextStyleProfile(id="style", name="Style", font_family=font_family)

    with pytest.raises(ValueError, match="font family"):
        AssStyleBuilder().build_style(
            "Safe", profile, canvas_width=1080, canvas_height=1920
        )


@pytest.mark.parametrize(
    ("canvas_width", "canvas_height"),
    [
        (0, 1920),
        (1080, 0),
        (-1, 1920),
        (1080, -1),
    ],
)
def test_build_style_rejects_non_positive_canvas_dimensions(
    canvas_width, canvas_height
):
    profile = TextStyleProfile(id="style", name="Style")

    with pytest.raises(ValueError, match="canvas"):
        AssStyleBuilder().build_style(
            "Safe",
            profile,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )


def test_build_style_without_explicit_basis_keeps_resolved_pixel_values():
    profile = TextStyleProfile(id="style", name="Style", font_size=64)

    style = AssStyleBuilder().build_style(
        "Tiny", profile, canvas_width=1, canvas_height=1
    )

    assert style.startswith("Style: Tiny,Noto Sans SC,64,")


@pytest.mark.parametrize(
    ("canvas_width", "canvas_height"),
    [(1280, 720), (720, 1280), (1080, 1080)],
)
def test_build_style_without_basis_is_orientation_independent(
    canvas_width,
    canvas_height,
):
    profile = TextStyleProfile(id="style", name="Style", font_size=36)

    style = AssStyleBuilder().build_style(
        "Resolved",
        profile,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )

    assert style.startswith("Style: Resolved,Noto Sans SC,36,")


def test_build_style_projects_canonical_css_pixels_to_ass_font_units():
    profile = TextStyleProfile(id="style", name="Style", font_size=36)

    style = AssStyleBuilder().build_style(
        "Projected",
        profile,
        canvas_width=320,
        canvas_height=180,
        project_css_pixel_units=True,
    )

    assert style.startswith("Style: Projected,Noto Sans SC,54,")


@pytest.mark.parametrize(
    ("position", "alignment", "expected_alignment"),
    [
        ("top", "center", 8),
        ("center", "center", 5),
        ("top_left", "left", 7),
        ("top_right", "right", 9),
        ("bottom_left", "left", 1),
        ("bottom_right", "right", 3),
        ("lower_third", "center", 2),
    ],
)
def test_build_style_maps_platform_position_and_alignment_to_ass_alignment(
    position, alignment, expected_alignment
):
    profile = TextStyleProfile(
        id="style",
        name="Style",
        position=position,
        alignment=alignment,
    )

    style = AssStyleBuilder().build_style(
        "Mapped", profile, canvas_width=1080, canvas_height=1920
    )

    assert f",{expected_alignment},80,80,140,1" in style


@pytest.mark.parametrize(
    ("font_weight", "expected_bold"),
    [
        (599, 0),
        (600, 1),
    ],
)
def test_build_style_bold_flag_follows_font_weight(font_weight, expected_bold):
    profile = TextStyleProfile(
        id="weight",
        name="Weight",
        font_weight=font_weight,
    )

    style = AssStyleBuilder().build_style(
        "Weight", profile, canvas_width=1080, canvas_height=1920
    )

    assert f"&HFF000000,{expected_bold},0,1," in style
