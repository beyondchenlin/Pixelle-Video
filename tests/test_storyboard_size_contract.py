import pytest

from pixelle_video.models.media_placement import MediaPlacement
from pixelle_video.models.storyboard import StoryboardConfig


def test_storyboard_config_defaults_canvas_to_media_for_legacy_constructor():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert (config.canvas_width, config.canvas_height) == (1080, 1920)
    assert (config.media_width, config.media_height) == (1080, 1920)


def test_storyboard_config_preserves_distinct_canvas_and_media_sizes():
    config = StoryboardConfig(
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="1k",
        media_orientation="square",
        media_resolution_preset="768",
        sync_media_size_to_canvas=False,
    )

    assert (config.canvas_width, config.canvas_height) == (1280, 720)
    assert (config.media_width, config.media_height) == (768, 768)
    assert config.video_orientation == "landscape"
    assert config.video_resolution_preset == "1k"
    assert config.media_orientation == "square"
    assert config.media_resolution_preset == "768"
    assert config.sync_media_size_to_canvas is False


def test_storyboard_config_defaults_media_placement_independently_from_sync_flag():
    config = StoryboardConfig(
        media_width=768,
        media_height=768,
        canvas_width=1280,
        canvas_height=720,
        sync_media_size_to_canvas=True,
    )

    assert config.media_placement == MediaPlacement()
    assert config.media_placement.scale_percent == 100


def test_storyboard_config_accepts_media_placement_dict():
    config = StoryboardConfig(
        media_width=768,
        media_height=768,
        canvas_width=1280,
        canvas_height=720,
        media_placement={"scale_percent": 90, "anchor": "bottom_right"},
    )

    assert config.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "anchor": "bottom_right",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"canvas_width": 0, "canvas_height": 720},
        {"canvas_width": 1280, "canvas_height": 0},
        {"media_width": 0, "media_height": 768},
        {"media_width": 768, "media_height": 0},
    ],
)
def test_storyboard_config_rejects_non_positive_dimensions(kwargs):
    base = {"media_width": 768, "media_height": 768}
    base.update(kwargs)

    with pytest.raises(ValueError):
        StoryboardConfig(**base)
