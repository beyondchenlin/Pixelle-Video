import pytest

from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
    project_canvas_box_to_template,
    resolve_media_placement,
)


def test_media_placement_defaults_to_center_offsets():
    placement = MediaPlacement()

    assert placement.basis == "canvas"
    assert placement.fit == "contain"
    assert placement.scale_percent == 100
    assert placement.offset_x == 0
    assert placement.offset_y == 0
    assert placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


@pytest.mark.parametrize("scale", [9, 101])
def test_media_placement_rejects_scale_outside_allowed_range(scale):
    with pytest.raises(ValueError, match="scale_percent"):
        MediaPlacement(scale_percent=scale)


@pytest.mark.parametrize("scale", [80.5, float("nan"), float("inf"), True])
def test_media_placement_rejects_non_integral_or_non_finite_scale(scale):
    with pytest.raises(ValueError, match="scale_percent"):
        MediaPlacement(scale_percent=scale)


@pytest.mark.parametrize("offset_name", ["offset_x", "offset_y"])
@pytest.mark.parametrize("offset", [1.5, float("nan"), float("inf"), True])
def test_media_placement_rejects_non_integral_or_non_finite_offsets(offset_name, offset):
    with pytest.raises(ValueError, match=offset_name):
        MediaPlacement(**{offset_name: offset})


def test_resolve_media_placement_accepts_dict_and_none():
    assert resolve_media_placement(None) == MediaPlacement()
    assert resolve_media_placement(
        {"scale_percent": 100, "offset_x": 40, "offset_y": -20}
    ) == MediaPlacement(
        scale_percent=100,
        offset_x=40,
        offset_y=-20,
    )


@pytest.mark.parametrize(
    ("source", "scale", "expected"),
    [
        ((1280, 720), 100, (1280, 720, 0, 0)),
        ((1280, 720), 80, (1024, 576, 128, 72)),
        ((1024, 1024), 100, (720, 720, 280, 0)),
        ((1024, 1024), 80, (576, 576, 352, 72)),
        ((720, 1280), 100, (405, 720, 438, 0)),
        ((720, 1280), 80, (324, 576, 478, 72)),
    ],
)
def test_contain_geometry_uses_final_canvas(source, scale, expected):
    box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=source[0],
        media_source_height=source[1],
        placement=MediaPlacement(scale_percent=scale),
    )

    assert (round(box.width), round(box.height), round(box.left), round(box.top)) == expected


def test_center_offsets_move_position_without_changing_size():
    center = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80),
    )
    moved = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, offset_x=64, offset_y=-32),
    )

    assert moved.width == pytest.approx(center.width)
    assert moved.height == pytest.approx(center.height)
    assert moved.left == pytest.approx(416)
    assert moved.top == pytest.approx(40)


@pytest.mark.parametrize(
    ("anchor", "expected_left", "expected_top"),
    [
        ("top_left", 0, 0),
        ("top", 352, 0),
        ("top_right", 704, 0),
        ("left", 0, 72),
        ("center", 352, 72),
        ("right", 704, 72),
        ("bottom_left", 0, 144),
        ("bottom", 352, 144),
        ("bottom_right", 704, 144),
    ],
)
def test_legacy_anchor_input_positions_without_changing_size(anchor, expected_left, expected_top):
    box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement={"scale_percent": 80, "anchor": anchor},
    )

    assert box.width == pytest.approx(576)
    assert box.height == pytest.approx(576)
    assert box.left == pytest.approx(expected_left)
    assert box.top == pytest.approx(expected_top)


def test_legacy_anchor_is_not_serialized_as_new_output():
    placement = resolve_media_placement({"scale_percent": 80, "anchor": "bottom_right"})

    assert placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "offset_x": 0,
        "offset_y": 0,
    }


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "wide"])
def test_calculate_media_box_rejects_non_finite_dimensions(bad_value):
    with pytest.raises(ValueError, match="canvas_width"):
        calculate_media_box(
            canvas_width=bad_value,
            canvas_height=720,
            media_source_width=1280,
            media_source_height=720,
            placement=MediaPlacement(),
        )


def test_canvas_box_projects_into_template_coordinates_for_same_aspect_resize():
    canvas_box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1280,
        media_source_height=720,
        placement=MediaPlacement(scale_percent=80),
    )

    template_box = project_canvas_box_to_template(
        canvas_box,
        canvas_width=1280,
        canvas_height=720,
        template_width=1920,
        template_height=1080,
        canvas_fit="contain",
    )

    assert template_box.width == pytest.approx(1536)
    assert template_box.height == pytest.approx(864)
    assert template_box.left == pytest.approx(192)
    assert template_box.top == pytest.approx(108)


def test_projection_rejects_template_canvas_aspect_mismatch():
    canvas_box = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1280,
        media_source_height=720,
        placement=MediaPlacement(),
    )

    with pytest.raises(ValueError, match="aspect ratio"):
        project_canvas_box_to_template(
            canvas_box,
            canvas_width=1280,
            canvas_height=720,
            template_width=1080,
            template_height=1920,
            canvas_fit="contain",
        )
