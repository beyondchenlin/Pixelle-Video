from pathlib import Path
from types import SimpleNamespace

from web.components import style_config


def test_landscape_template_gallery_preview_assets_exist():
    preview_assets = [
        Path("docs/images/1920x1080/image_landscape_full.png"),
        Path("docs/images/1920x1080/image_landscape_full_en.png"),
        Path("docs/images/1920x1080/image_landscape_minimal.png"),
        Path("docs/images/1920x1080/image_landscape_minimal_en.png"),
    ]

    for preview_asset in preview_assets:
        assert preview_asset.exists(), f"missing template gallery preview: {preview_asset}"


def test_template_gallery_tab_label_uses_orientation_without_base_size():
    orientation_labels = {
        "portrait": "竖屏",
        "landscape": "横屏",
        "square": "方形",
    }

    labels = [
        style_config._build_template_gallery_tab_label(
            SimpleNamespace(orientation="portrait", width=1080, height=1920),
            orientation_labels,
        ),
        style_config._build_template_gallery_tab_label(
            SimpleNamespace(orientation="landscape", width=1920, height=1080),
            orientation_labels,
        ),
        style_config._build_template_gallery_tab_label(
            SimpleNamespace(orientation="square", width=1080, height=1080),
            orientation_labels,
        ),
    ]

    assert labels == ["竖屏", "横屏", "方形"]
    assert all("1080" not in label for label in labels)
    assert all("1920" not in label for label in labels)


def test_render_generation_size_controls_returns_independent_image_size(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "portrait",
                "video_resolution_preset": "2k",
                "media_orientation": "landscape",
                "media_resolution_preset": "4k",
                "sync_media_size_to_canvas": False,
            }
            self.info_messages = []

        def segmented_control(self, _label, options, *, format_func, default, key):
            assert default in options
            return self.session_state[key]

        def toggle(self, _label, *, value, help, key):
            assert value is False
            assert help
            return self.session_state[key]

        def info(self, message):
            self.info_messages.append(message)

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    contract = style_config._render_generation_size_controls()

    assert (contract.canvas_width, contract.canvas_height) == (1080, 1920)
    assert (contract.media_width, contract.media_height) == (3840, 2160)
    assert contract.media_orientation == "landscape"
    assert contract.media_resolution_preset == "4k"


def test_render_generation_size_controls_syncs_image_size_to_canvas(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "4k",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": True,
            }

        def segmented_control(self, _label, options, *, format_func, default, key):
            assert default in options
            return self.session_state[key]

        def toggle(self, _label, *, value, help, key):
            assert value is True
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    contract = style_config._render_generation_size_controls()

    assert (contract.canvas_width, contract.canvas_height) == (3840, 2160)
    assert (contract.media_width, contract.media_height) == (3840, 2160)
    assert contract.sync_media_size_to_canvas is True
