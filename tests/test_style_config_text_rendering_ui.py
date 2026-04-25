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
        return value

    def number_input(self, _label, value=0, **_kwargs):
        return value

    def color_picker(self, _label, value="#000000", **_kwargs):
        return value

    def selectbox(self, _label, options, index=0, **_kwargs):
        self.selectboxes.append(
            {"label": _label, "options": list(options), "index": index, **_kwargs}
        )
        return options[index]


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


def test_text_rendering_controls_live_in_focused_component():
    component = Path("web/components/text_rendering_config.py")
    style_config = Path("web/components/style_config.py")

    assert component.exists()
    assert "render_text_rendering_controls" in component.read_text(encoding="utf-8")
    assert "caption_style" in component.read_text(encoding="utf-8")
    assert "def render_text_rendering_controls" not in style_config.read_text(encoding="utf-8")


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
    assert font_select["options"] == ["FZCuHeiSongS-B-GB", "SimHei"]
    assert font_select["index"] == 1
    assert font_select["help"] == "translated:caption_style.font_family_help"
    assert style["font_family"] == "SimHei"
    assert style["font_file"] == "fonts/simhei.ttf"


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


def test_text_rendering_font_help_translation_keys_exist_in_supported_locales():
    import json

    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    required_keys = [
        "caption_style.font_family_help",
        "overlay_style.font_family_help",
    ]

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
