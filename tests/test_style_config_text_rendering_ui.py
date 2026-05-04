from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.schemas.text_rendering import TextRenderingRequest


class _TextStyleFakeUI:
    def __init__(self):
        self.session_state = {}
        self.text_inputs = []
        self.selectboxes = []

    def text_input(self, label, value="", **kwargs):
        self.text_inputs.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def number_input(self, _label, value=0, **kwargs):
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def color_picker(self, _label, value="#000000", **kwargs):
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def selectbox(self, _label, options, index=0, **kwargs):
        self.selectboxes.append(
            {"label": _label, "options": list(options), "index": index, **kwargs}
        )
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return options[index]


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _WidgetDefaultRecordingUI:
    def __init__(self):
        self.session_state = {
            "caption_style_font_family": "SimHei",
            "caption_style_font_size": 42,
            "caption_style_primary_color": "#2C3E50",
            "image_text_suppress_embedded_text": True,
            "image_text_positive_prompt": "avoid embedded text",
            "text_layer_enabled": False,
        }
        self.checkbox_calls = []
        self.text_area_calls = []
        self.text_input_calls = []
        self.number_input_calls = []
        self.color_picker_calls = []
        self.tabs_calls = []
        self.button_calls = []
        self.image_calls = []
        self.caption_calls = []
        self.error_calls = []

    def expander(self, *_args, **_kwargs):
        return _NoopContext()

    def container(self, *_args, **_kwargs):
        return _NoopContext()

    def tabs(self, labels):
        self.tabs_calls.append(list(labels))
        return [_NoopContext() for _label in labels]

    def markdown(self, *_args, **_kwargs):
        return None

    def caption(self, message):
        self.caption_calls.append(message)

    def image(self, url, **kwargs):
        self.image_calls.append({"url": url, **kwargs})

    def error(self, message):
        self.error_calls.append(message)

    def button(self, _label, **kwargs):
        self.button_calls.append({"label": _label, **kwargs})
        return bool(self.session_state.get(kwargs.get("key"), False))

    def checkbox(self, _label, **kwargs):
        self.checkbox_calls.append(kwargs)
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return kwargs.get("value", False)

    def text_area(self, _label, **kwargs):
        self.text_area_calls.append(kwargs)
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return kwargs.get("value", "")

    def text_input(self, _label, **kwargs):
        self.text_input_calls.append({"label": _label, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return kwargs.get("value", "")

    def number_input(self, _label, **kwargs):
        self.number_input_calls.append(kwargs)
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return kwargs.get("value", 0)

    def color_picker(self, _label, **kwargs):
        self.color_picker_calls.append(kwargs)
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return kwargs.get("value", "#000000")

    def selectbox(self, _label, options, **kwargs):
        index = kwargs.get("index", 0)
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return list(options)[index]

    def radio(self, _label, options, **kwargs):
        index = kwargs.get("index", 0)
        return list(options)[index]


def test_text_rendering_request_accepts_caption_style_and_forbids_unknown_fields():
    request = TextRenderingRequest.model_validate(
        {
            "overlay": {"enabled": True, "renderer_targets": ["ass"]},
            "caption_style": {
                "font_size": 72,
                "primary_color": "#FFFF00",
                "stroke_color": "#000000",
                "stroke_width": 4,
            },
        }
    )

    assert request.caption_style.font_size == 72
    assert request.caption_style.primary_color == "#FFFF00"

    title_request = TextRenderingRequest.model_validate(
        {
            "title_style": {
                "font_size": 96,
                "position": "top_left",
                "background_opacity": 0.8,
            }
        }
    )
    assert title_request.title_style.font_size == 96
    assert title_request.title_style.position == "top_left"
    assert title_request.title_style.background_opacity == 0.8

    overlay_request = TextRenderingRequest.model_validate(
        {
            "overlay_style": {
                "font_size": 88,
                "position": "center",
                "max_chars_per_line": 14,
            }
        }
    )
    assert overlay_request.overlay_style.font_size == 88
    assert overlay_request.overlay_style.position == "center"
    assert overlay_request.overlay_style.max_chars_per_line == 14

    with pytest.raises(ValidationError):
        TextRenderingRequest.model_validate(
            {
                "caption_style": {
                    "font_size": 72,
                    "unknown_style_field": "unexpected",
                }
            }
        )


def test_text_rendering_controls_reject_preview_only_context(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls

    fake_ui = _WidgetDefaultRecordingUI()
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    with pytest.raises(TypeError):
        render_text_rendering_controls(
            "hyperframes",
            ui=fake_ui,
            translate=lambda key: key,
            canvas_width=1080,
        )


def test_build_text_rendering_payload_keeps_caption_style_when_overlay_disabled():
    from web.components.text_rendering_config import build_text_rendering_payload

    payload = build_text_rendering_payload(
        caption_style={
            "font_size": 72,
            "primary_color": "#FFFF00",
            "stroke_color": "#000000",
            "stroke_width": 4,
            "position": "bottom",
            "margin_y": 120,
        },
        overlay_policy=None,
        suppress_embedded_text=True,
        positive_prompt="avoid embedded text",
    )

    assert payload["caption_style"]["font_size"] == 72
    assert payload["caption_style"]["primary_color"] == "#FFFF00"
    assert payload["overlay"] == {"enabled": False}
    assert payload["image_text"] == {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid embedded text",
    }


def test_build_text_rendering_payload_keeps_overlay_style_when_overlay_disabled():
    from web.components.text_rendering_config import build_text_rendering_payload

    payload = build_text_rendering_payload(
        caption_style=None,
        overlay_policy=None,
        overlay_style={
            "font_size": 88,
            "position": "center",
        },
        suppress_embedded_text=False,
        positive_prompt="",
    )

    assert payload["overlay"] == {"enabled": False}
    assert payload["overlay_style"] == {
        "font_size": 88,
        "position": "center",
    }


def test_build_text_rendering_payload_keeps_title_style_and_drops_preview_demo_fields():
    from web.components.text_rendering_config import build_text_rendering_payload

    payload = build_text_rendering_payload(
        caption_style={
            "font_size": 42,
            "preview_caption_text": "演示字幕",
            "preview_media_ref": "artifacts/demo.png",
        },
        title_style={
            "font_family": " Noto Sans CJK SC ",
            "font_size": 96,
            "background_opacity": 0.8,
            "preview_title_text": "演示标题",
            "preview_caption_text": "演示字幕",
            "preview_media_ref": "artifacts/demo.png",
        },
        overlay_policy=None,
        suppress_embedded_text=False,
        positive_prompt="",
    )

    assert payload["title_style"] == {
        "font_family": "Noto Sans CJK SC",
        "font_size": 96,
        "background_opacity": 0.8,
    }
    assert payload["caption_style"] == {"font_size": 42}
    assert "preview_title_text" not in payload["title_style"]
    assert "preview_caption_text" not in payload["title_style"]
    assert "preview_media_ref" not in payload["title_style"]


def test_caption_style_ui_defaults_match_template_dark_text():
    from web.components.text_rendering_config import CAPTION_STYLE_DEFAULTS, OVERLAY_STYLE_DEFAULTS

    assert CAPTION_STYLE_DEFAULTS["font_size"] == 42
    assert CAPTION_STYLE_DEFAULTS["primary_color"] == "#2C3E50"
    assert CAPTION_STYLE_DEFAULTS["stroke_width"] == 0
    assert OVERLAY_STYLE_DEFAULTS["font_size"] == 76
    assert OVERLAY_STYLE_DEFAULTS["primary_color"] == "#FFFFFF"
    assert OVERLAY_STYLE_DEFAULTS["stroke_width"] == 2


def test_text_style_font_family_control_explains_font_directory(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()

    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    assert fake_ui.text_inputs[0]["label"] == "translated:caption_style.font_family"
    assert fake_ui.text_inputs[0]["help"] == "translated:caption_style.font_family_help"


def test_discover_font_families_reads_project_font_directories(tmp_path):
    from web.components.text_rendering_config import discover_font_families

    fonts_dir = tmp_path / "fonts"
    ignored_dir = tmp_path / "ignored"
    nested_dir = fonts_dir / "nested"
    nested_dir.mkdir(parents=True)
    ignored_dir.mkdir()
    (fonts_dir / "PixelleDemoFont.ttf").write_bytes(b"not a real font")
    (nested_dir / "FZZhengHeiS-EB-GB.TTF").write_bytes(b"not a real font")
    (ignored_dir / "ignored.ttf").write_bytes(b"not a real font")

    assert discover_font_families(candidate_dirs=(fonts_dir,)) == [
        "FZZhengHeiS-EB-GB",
        "PixelleDemoFont",
    ]


def test_discover_font_families_includes_ttc_files(tmp_path):
    from web.components.text_rendering_config import discover_font_families

    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "STHeitiMedium.ttc").write_bytes(b"not a real font")

    assert discover_font_families(candidate_dirs=(fonts_dir,)) == ["STHeitiMedium"]


def test_discover_font_options_keeps_distinct_files_with_same_family(monkeypatch, tmp_path):
    from pixelle_video.services import font_discovery

    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    simhei_ttf = fonts_dir / "simhei.ttf"
    stheiti_ttc = fonts_dir / "STHeitiMedium.ttc"
    simhei_ttf.write_bytes(b"not a real font")
    stheiti_ttc.write_bytes(b"not a real font")
    monkeypatch.setattr(
        font_discovery,
        "font_family_from_file",
        lambda _path: "SimHei",
    )

    options = font_discovery.discover_font_options(candidate_dirs=(fonts_dir,))

    assert [(option.family, option.path.name) for option in options] == [
        ("SimHei", "simhei.ttf"),
        ("SimHei", "STHeitiMedium.ttc"),
    ]


def test_text_style_font_family_control_uses_dropdown_when_fonts_exist(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    fake_ui.session_state = {"caption_style_font_family": "SimHei"}
    monkeypatch.setattr(
        text_rendering_config,
        "discover_font_options",
        lambda *_args: [
            SimpleNamespace(family="FZCuHeiSongS-B-GB", path=Path("fonts/fzchsjt.ttf")),
            SimpleNamespace(family="SimHei", path=Path("fonts/simhei.ttf")),
        ],
        raising=False,
    )

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    font_select = fake_ui.selectboxes[0]
    assert fake_ui.text_inputs == []
    assert font_select["label"] == "translated:caption_style.font_family"
    assert font_select["options"] == [
        "FZCuHeiSongS-B-GB (fzchsjt.ttf)",
        "SimHei (simhei.ttf)",
    ]
    assert font_select["index"] == 1
    assert font_select["help"] == "translated:caption_style.font_family_help"
    assert style["font_family"] == "SimHei"
    assert style["font_file"] == "fonts/simhei.ttf"


def test_text_style_font_family_dropdown_uses_first_local_font_when_default_missing(
    monkeypatch,
):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    monkeypatch.setattr(
        text_rendering_config,
        "discover_font_options",
        lambda *_args: [
            SimpleNamespace(family="FZCuHeiSongS-B-GB", path=Path("fonts/fzchsjt.ttf")),
            SimpleNamespace(family="SimHei", path=Path("fonts/simhei.ttf")),
        ],
        raising=False,
    )

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    font_select = fake_ui.selectboxes[0]
    assert font_select["options"] == [
        "FZCuHeiSongS-B-GB (fzchsjt.ttf)",
        "SimHei (simhei.ttf)",
    ]
    assert font_select["index"] == 0
    assert style["font_family"] == "FZCuHeiSongS-B-GB"
    assert style["font_file"] == "fonts/fzchsjt.ttf"
    assert fake_ui.session_state["caption_style_font_family"] == "FZCuHeiSongS-B-GB"


def test_text_style_font_family_dropdown_disambiguates_duplicate_family_files(
    monkeypatch,
):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    fake_ui.session_state = {"caption_style_font_family": "SimHei"}
    monkeypatch.setattr(
        text_rendering_config,
        "discover_font_options",
        lambda *_args: [
            SimpleNamespace(family="SimHei", path=Path("fonts/simhei.ttf")),
            SimpleNamespace(family="SimHei", path=Path("fonts/STHeitiMedium.ttc")),
        ],
        raising=False,
    )

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    font_select = fake_ui.selectboxes[0]
    assert font_select["options"] == [
        "SimHei (simhei.ttf)",
        "SimHei (STHeitiMedium.ttc)",
    ]
    assert font_select["index"] == 0
    assert style["font_family"] == "SimHei"
    assert style["font_file"] == "fonts/simhei.ttf"


def test_text_style_font_family_dropdown_preserves_duplicate_family_by_font_file(
    monkeypatch,
):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    fake_ui.session_state = {
        "caption_style_font_family": "SimHei",
        "caption_style_font_file": "fonts/STHeitiMedium.ttc",
    }
    monkeypatch.setattr(
        text_rendering_config,
        "discover_font_options",
        lambda *_args: [
            SimpleNamespace(family="SimHei", path=Path("fonts/simhei.ttf")),
            SimpleNamespace(family="SimHei", path=Path("fonts/STHeitiMedium.ttc")),
        ],
        raising=False,
    )

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    font_select = fake_ui.selectboxes[0]
    assert font_select["index"] == 1
    assert style["font_family"] == "SimHei"
    assert style["font_file"] == "fonts/STHeitiMedium.ttc"


def test_caption_style_control_migrates_legacy_hollow_caption_defaults(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    fake_ui.session_state = {
        "caption_style_font_size": 64,
        "caption_style_primary_color": "#FFFFFF",
        "caption_style_stroke_width": 2,
    }
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    assert style["font_size"] == 42
    assert style["primary_color"] == "#2C3E50"
    assert style["stroke_width"] == 0
    assert fake_ui.session_state["caption_style_font_size"] == 42
    assert fake_ui.session_state["caption_style_primary_color"] == "#2C3E50"
    assert fake_ui.session_state["caption_style_stroke_width"] == 0


def test_text_rendering_controls_omit_widget_defaults_for_existing_session_keys(
    monkeypatch,
):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls

    fake_ui = _WidgetDefaultRecordingUI()
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    payload = render_text_rendering_controls(
        "legacy",
        ui=fake_ui,
        translate=lambda key: key,
    )

    checkbox_by_key = {call["key"]: call for call in fake_ui.checkbox_calls}
    text_area_by_key = {call["key"]: call for call in fake_ui.text_area_calls}
    text_input_by_key = {call["key"]: call for call in fake_ui.text_input_calls}
    number_input_by_key = {call["key"]: call for call in fake_ui.number_input_calls}
    color_picker_by_key = {call["key"]: call for call in fake_ui.color_picker_calls}

    assert "value" not in checkbox_by_key["image_text_suppress_embedded_text"]
    assert "value" not in text_area_by_key["image_text_positive_prompt"]
    assert "value" not in text_input_by_key["caption_style_font_family"]
    assert "value" not in number_input_by_key["caption_style_font_size"]
    assert "value" not in color_picker_by_key["caption_style_primary_color"]
    assert payload["image_text"] == {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid embedded text",
    }


def test_text_rendering_controls_render_caption_and_title_tabs(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls

    fake_ui = _WidgetDefaultRecordingUI()
    fake_ui.session_state.update(
        {
            "title_style_font_size": 76,
            "title_style_primary_color": "#171410",
            "title_style_background_opacity": 0.88,
            "title_style_position": "top_left",
            "title_style_alignment": "right",
            "title_style_margin_x": 110,
            "title_style_margin_y": 92,
            "title_style_max_width_ratio": 0.44,
        }
    )
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    payload = render_text_rendering_controls(
        "hyperframes",
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
        template_id="image_landscape_minimal",
    )

    assert fake_ui.tabs_calls == [
        ["translated:caption_style.tab", "translated:title_style.tab"]
    ]
    text_input_by_key = {call["key"]: call for call in fake_ui.text_input_calls}
    assert text_input_by_key["caption_style_font_family"]["label"] == (
        "translated:caption_style.font_family"
    )
    assert text_input_by_key["title_style_font_family"]["label"] == (
        "translated:title_style.font_family"
    )
    assert payload["title_style"]["font_size"] == 76
    assert payload["title_style"]["position"] == "top_left"
    assert payload["title_style"]["alignment"] == "right"
    assert payload["title_style"]["margin_x"] == 110
    assert payload["title_style"]["margin_y"] == 92
    assert payload["title_style"]["max_width_ratio"] == 0.44


def test_title_style_control_migrates_historical_template_background_defaults(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls

    fake_ui = _WidgetDefaultRecordingUI()
    fake_ui.session_state.update(
        {
            "title_style_background_opacity": 0.88,
        }
    )
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    payload = render_text_rendering_controls(
        "hyperframes",
        ui=fake_ui,
        translate=lambda key: key,
        template_id="image_landscape_minimal",
    )

    assert payload["title_style"]["background_opacity"] == 0.0
    assert fake_ui.session_state["title_style_background_opacity"] == 0.0


def test_text_style_controls_return_full_layout_fields(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import (
        CAPTION_STYLE_DEFAULTS,
        _render_text_style_controls,
    )

    fake_ui = _TextStyleFakeUI()
    fake_ui.session_state = {
        "caption_style_position": "bottom_right",
        "caption_style_alignment": "right",
        "caption_style_margin_x": 44,
        "caption_style_margin_y": 56,
        "caption_style_max_width_ratio": 0.4,
    }
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    style = _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    assert style["position"] == "bottom_right"
    assert style["alignment"] == "right"
    assert style["margin_x"] == 44
    assert style["margin_y"] == 56
    assert style["max_width_ratio"] == 0.4


def test_text_rendering_preview_helper_remains_separate_from_text_controls(monkeypatch):
    from web.components import text_rendering_config
    from web.components.text_rendering_config import render_text_rendering_controls
    from web.components.text_rendering_preview import build_text_rendering_preview_spec

    fake_ui = _WidgetDefaultRecordingUI()
    fake_ui.session_state.update(
        {
            "text_rendering_generate_real_preview": True,
            "api_base_url": "http://localhost:8000/api",
            "workspace_id": "ws",
            "title_style_font_size": 76,
        }
    )
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])

    payload = render_text_rendering_controls(
        "hyperframes",
        ui=fake_ui,
        translate=lambda key, **kwargs: key,
        template_id="image_default",
    )

    preview_spec = build_text_rendering_preview_spec(
        template_id="image_default",
        render_backend="hyperframes",
        canvas_width=1080,
        canvas_height=1920,
        media_width=900,
        media_height=1200,
        media_placement={"anchor": "center"},
        preview_media_ref="artifacts/ws/source.png",
        title_text="Preview title",
        caption_text="Preview caption",
        title_style=payload["title_style"],
        caption_style=payload["caption_style"],
    )

    assert fake_ui.button_calls == []
    assert fake_ui.image_calls == []
    assert preview_spec.template_id == "image_default"
    assert preview_spec.preview_media_ref == "artifacts/ws/source.png"
    assert "text_rendering_real_preview_frame" not in payload
    assert "preview_media_url" not in payload


def test_render_style_config_passes_only_text_contract_to_text_controls(
    monkeypatch,
):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
        }
    )
    captured = {}

    def fake_render_text_rendering_controls(render_backend, **kwargs):
        captured["render_backend"] = render_backend
        captured.update(kwargs)
        return {"overlay": {"enabled": False}}

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config,
        "render_text_rendering_controls",
        fake_render_text_rendering_controls,
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [{"display_name": "Image Default", "key": "selfhost/image.json"}]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(
        _FakeVideo(),
        storyboard_default_enabled=True,
        content_context={
            "title": "Runtime Title",
            "text": "\nRuntime caption line\nsecond line",
        },
    )

    assert result["text_rendering"] == {"overlay": {"enabled": False}}
    assert captured["render_backend"] == "hyperframes"
    assert captured == {
        "render_backend": "hyperframes",
        "ui": fake_st,
        "translate": style_config.tr,
        "template_id": "image_default",
    }


def test_standard_pipeline_passes_content_context_to_style_config(monkeypatch):
    from web.pipelines import standard as standard_pipeline

    captured = {}

    class _FakeColumn(_NoopContext):
        pass

    def fake_render_style_config(
        pixelle_video,
        storyboard_default_enabled=False,
        storyboard_prompt_language="zh_CN",
        content_context=None,
    ):
        captured["content_context"] = content_context
        captured["storyboard_prompt_language"] = storyboard_prompt_language
        return {"style": "ok"}

    def fake_render_content_input(*, pixelle_video=None):
        captured["content_input_pixelle_video"] = pixelle_video
        return {
            "title": "上下文标题",
            "text": "第一行字幕\n第二行",
            "storyboard_prompt_language": "en_US",
        }

    monkeypatch.setattr(
        standard_pipeline.st,
        "columns",
        lambda _sizes: [_FakeColumn(), _FakeColumn(), _FakeColumn()],
    )
    monkeypatch.setattr(
        standard_pipeline,
        "render_content_input",
        lambda: {
            "title": "上下文标题",
            "text": "第一行字幕\n第二行",
            "storyboard_prompt_language": "en_US",
        },
    )
    monkeypatch.setattr(
        standard_pipeline,
        "render_content_input",
        fake_render_content_input,
    )
    monkeypatch.setattr(standard_pipeline, "render_bgm_section", lambda **_kwargs: {})
    monkeypatch.setattr(standard_pipeline, "render_version_info", lambda: None)
    monkeypatch.setattr(standard_pipeline, "render_style_config", fake_render_style_config)
    monkeypatch.setattr(standard_pipeline, "render_quick_create_flow_diagram", lambda: None)
    monkeypatch.setattr(
        standard_pipeline,
        "render_output_preview",
        lambda _pixelle_video, _video_params: None,
    )

    pixelle_video = object()
    standard_pipeline.StandardPipelineUI().render(pixelle_video)

    assert captured["content_input_pixelle_video"] is pixelle_video
    assert captured["storyboard_prompt_language"] == "en_US"
    assert captured["content_context"] == {
        "title": "上下文标题",
        "text": "第一行字幕\n第二行",
        "storyboard_prompt_language": "en_US",
    }


def test_text_rendering_font_help_translation_keys_exist_in_supported_locales():
    import json

    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    required_keys = [
        "caption_style.font_family_help",
        "title_style.font_family_help",
        "overlay_style.font_family_help",
    ]

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
