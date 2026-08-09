import json
from pathlib import Path
from types import SimpleNamespace

from pixelle_video.models.size_contract import (
    DEFAULT_MEDIA_RESOLUTION_PRESET,
    DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION,
    STANDARD_VIDEO_SIZE_PRESETS,
)
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


def test_template_picker_entries_filter_orientation_convention_and_duplicates():
    def template(name: str, orientation: str, path: str):
        return SimpleNamespace(
            template_path=path,
            display_info=SimpleNamespace(
                name=name,
                orientation=orientation,
                width=1080,
                height=1920,
            ),
        )

    first = template("image_default", "portrait", "templates/portrait.html")
    duplicate = template("image_duplicate", "portrait", "templates/portrait.html")
    wrong_orientation = template("image_landscape", "landscape", "templates/landscape.html")
    wrong_convention = template("legacy_template", "portrait", "templates/legacy.html")

    entries = style_config._compatible_template_picker_entries(
        {
            "first": [first, wrong_orientation],
            "second": [duplicate, wrong_convention],
        },
        orientation="portrait",
    )

    assert entries == [first]
    assert style_config._template_picker_label(first) == "image_default · 1080×1920"


def test_template_picker_preserves_custom_layered_template_label():
    assert (
        style_config._template_picker_option_label(
            "data/templates/customer/custom_scene.html",
            {},
        )
        == "custom_scene"
    )


def test_template_picker_callback_updates_selection_and_clears_layered_identity(monkeypatch):
    session_state = {
        "template_picker": "templates/portrait/image_default.html",
        "selected_template": "data/templates/customer/custom_scene.html",
        "layered_template_selected_spec_identity": {
            "template_id": "user:custom",
            "template_name": "Custom",
            "template_type": "image",
        },
    }
    monkeypatch.setattr(
        style_config,
        "st",
        SimpleNamespace(session_state=session_state),
    )

    style_config._apply_template_picker_selection("template_picker")

    assert session_state["selected_template"] == "templates/portrait/image_default.html"
    assert "layered_template_selected_spec_identity" not in session_state


def test_template_picker_preview_does_not_read_assets_before_user_action(monkeypatch):
    fake_st = SimpleNamespace(button=lambda *_args, **_kwargs: False)
    monkeypatch.setattr(style_config, "st", fake_st)

    def unexpected_preview_lookup(*_args, **_kwargs):
        raise AssertionError("preview lookup must be user initiated")

    monkeypatch.setattr(
        style_config,
        "get_template_preview_path",
        unexpected_preview_lookup,
    )

    style_config._render_template_picker_preview_on_demand(
        "templates/portrait/image_default.html",
        "image_default",
        current_lang="zh_CN",
        picker_key="template_picker",
    )


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

    assert fake_st.media_resolution_default == DEFAULT_MEDIA_RESOLUTION_PRESET
    assert contract.media_orientation == "landscape"
    assert contract.media_resolution_preset == DEFAULT_MEDIA_RESOLUTION_PRESET


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

    expected_preset = DEFAULT_VIDEO_RESOLUTION_PRESETS_BY_ORIENTATION["portrait"]
    expected_size = STANDARD_VIDEO_SIZE_PRESETS["portrait"][expected_preset].as_tuple()
    assert fake_st.video_resolution_default == expected_preset
    assert contract.video_resolution_preset == expected_preset
    assert (contract.canvas_width, contract.canvas_height) == expected_size


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
