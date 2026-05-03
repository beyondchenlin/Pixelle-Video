import json
from pathlib import Path
from types import SimpleNamespace

from web.components import style_config


def test_product_locales_do_not_expose_legacy_media_anchor_labels():
    locale_paths = [
        Path("web/i18n/locales/zh_CN.json"),
        Path("web/i18n/locales/en_US.json"),
    ]

    for locale_path in locale_paths:
        translations = json.loads(locale_path.read_text(encoding="utf-8"))["t"]

        assert "media_placement.anchor" not in translations
        assert "media_placement.summary" not in translations
        assert not any(key.startswith("media_placement.anchor.") for key in translations)
        assert "text_style.position.top_left" in translations


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
                "video_resolution_preset": "portrait_full_hd",
                "media_orientation": "landscape",
                "media_resolution_preset": "4k",
                "sync_media_size_to_canvas": False,
            }
            self.info_messages = []

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
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
    assert contract.video_resolution_preset == "portrait_full_hd"
    assert contract.media_orientation == "landscape"
    assert contract.media_resolution_preset == "4k"


def test_render_generation_size_controls_uses_standard_video_presets(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_full_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            }
            self.video_resolution_options = None

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            if key == "video_resolution_preset":
                self.video_resolution_options = list(options)
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
                assert value is False
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    style_config._render_generation_size_controls()

    assert fake_st.video_resolution_options == [
        "landscape_hd",
        "landscape_full_hd",
        "landscape_4k",
    ]


def test_render_generation_size_controls_uses_standard_video_labels(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_full_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            }
            self.video_labels = {}

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            if key == "video_resolution_preset":
                self.video_labels = {option: format_func(option) for option in options}
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
                assert value is False
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    translations = {
        "size.preset.landscape_hd": "HD landscape",
        "size.preset.landscape_full_hd": "Full HD landscape",
        "size.preset.landscape_4k": "4K landscape",
    }

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs)
        if kwargs
        else translations.get(key, key),
    )

    style_config._render_generation_size_controls()

    label = fake_st.video_labels["landscape_full_hd"]
    assert "1K" not in label
    assert "1920×720" not in label
    assert "1920x720" not in label
    assert "Full HD" in label
    assert ("1920×1080" in label) or ("1920x1080" in label)


def test_render_generation_size_controls_uses_valid_non_square_media_default(
    monkeypatch,
):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_hd",
                "media_orientation": "landscape",
                "media_resolution_preset": "landscape_hd",
                "sync_media_size_to_canvas": False,
            }
            self.media_resolution_default = None

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            if key == "media_resolution_preset":
                self.media_resolution_default = default or self.session_state[key]
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
                assert value is False
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    contract = style_config._render_generation_size_controls()

    assert fake_st.media_resolution_default == "1k"
    assert contract.media_orientation == "landscape"
    assert contract.media_resolution_preset == "1k"


def test_render_generation_size_controls_uses_orientation_video_default(
    monkeypatch,
):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "portrait",
                "video_resolution_preset": "landscape_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            }
            self.video_resolution_default = None

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            if key == "video_resolution_preset":
                self.video_resolution_default = default or self.session_state[key]
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
                assert value is False
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    contract = style_config._render_generation_size_controls()

    assert fake_st.video_resolution_default == "portrait_hd"
    assert contract.video_resolution_preset == "portrait_hd"
    assert (contract.canvas_width, contract.canvas_height) == (720, 1280)


def test_render_generation_size_controls_syncs_image_size_to_canvas(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_4k",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": True,
            }

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
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


def test_render_generation_size_controls_sets_default_media_placement(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_hd",
                "media_orientation": "landscape",
                "media_resolution_preset": "1k",
                "sync_media_size_to_canvas": False,
            }

        def segmented_control(self, _label, options, *, format_func, key, default=None):
            if default is not None:
                assert default in options
            return self.session_state[key]

        def toggle(self, _label, *, help, key, value=None):
            if value is not None:
                assert value is False
            assert help
            return self.session_state[key]

        def info(self, _message):
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    style_config._render_generation_size_controls()

    assert fake_st.session_state["media_placement_scale_percent"] == 100
    assert fake_st.session_state["media_placement_offset_x"] == 0
    assert fake_st.session_state["media_placement_offset_y"] == 0
    assert fake_st.session_state["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }


def test_render_generation_size_controls_omits_defaults_for_session_widgets(
    monkeypatch,
):
    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "video_orientation": "landscape",
                "video_resolution_preset": "landscape_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
                "media_placement_scale_percent": 100,
                "media_placement_offset_x": 0,
                "media_placement_offset_y": 0,
            }
            self.segmented_kwargs = {}
            self.toggle_kwargs = {}
            self.slider_kwargs = {}

        def segmented_control(self, _label, options, *, format_func, key, **kwargs):
            assert self.session_state[key] in options
            self.segmented_kwargs[key] = kwargs
            return self.session_state[key]

        def toggle(self, _label, *, help, key, **kwargs):
            assert help
            self.toggle_kwargs[key] = kwargs
            return self.session_state[key]

        def slider(self, _label, *, key, **kwargs):
            self.slider_kwargs[key] = kwargs
            return self.session_state[key]

        def info(self, _message):
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(
        style_config,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )

    style_config._render_generation_size_controls()

    assert all(
        "default" not in kwargs for kwargs in fake_st.segmented_kwargs.values()
    )
    assert "value" not in fake_st.toggle_kwargs["sync_media_size_to_canvas"]
    assert "value" not in fake_st.slider_kwargs["media_placement_scale_percent"]
    assert "value" not in fake_st.slider_kwargs["media_placement_offset_x"]
    assert "value" not in fake_st.slider_kwargs["media_placement_offset_y"]
