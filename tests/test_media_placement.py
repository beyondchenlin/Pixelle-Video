import pytest

from pixelle_video.models.media_placement import (
    MediaPlacement,
    calculate_media_box,
    project_canvas_box_to_template,
    resolve_media_placement,
)


def test_media_placement_defaults_to_canvas_contain_80_center():
    placement = MediaPlacement()

    assert placement.basis == "canvas"
    assert placement.fit == "contain"
    assert placement.scale_percent == 80
    assert placement.anchor == "center"
    assert placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 80,
        "anchor": "center",
    }


@pytest.mark.parametrize("scale", [9, 101])
def test_media_placement_rejects_scale_outside_allowed_range(scale):
    with pytest.raises(ValueError, match="scale_percent"):
        MediaPlacement(scale_percent=scale)


@pytest.mark.parametrize("anchor", ["middle", "top-middle", ""])
def test_media_placement_rejects_unknown_anchor(anchor):
    with pytest.raises(ValueError, match="anchor"):
        MediaPlacement(anchor=anchor)


def test_resolve_media_placement_accepts_dict_and_none():
    assert resolve_media_placement(None) == MediaPlacement()
    assert resolve_media_placement({"scale_percent": 100, "anchor": "right"}) == MediaPlacement(
        scale_percent=100,
        anchor="right",
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


def test_anchor_right_bottom_moves_position_without_changing_size():
    center = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, anchor="center"),
    )
    bottom_right = calculate_media_box(
        canvas_width=1280,
        canvas_height=720,
        media_source_width=1024,
        media_source_height=1024,
        placement=MediaPlacement(scale_percent=80, anchor="bottom_right"),
    )

    assert bottom_right.width == pytest.approx(center.width)
    assert bottom_right.height == pytest.approx(center.height)
    assert bottom_right.left == pytest.approx(704)
    assert bottom_right.top == pytest.approx(144)


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
