from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas.text_rendering import TextRenderingRequest


class _TextStyleFakeUI:
    session_state = {}

    def __init__(self):
        self.text_inputs = []

    def text_input(self, label, value="", **kwargs):
        self.text_inputs.append({"label": label, "value": value, **kwargs})
        return value

    def number_input(self, _label, value=0, **_kwargs):
        return value

    def color_picker(self, _label, value="#000000", **_kwargs):
        return value

    def selectbox(self, _label, options, index=0, **_kwargs):
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


def test_text_style_font_family_control_explains_font_directory():
    from web.components.text_rendering_config import CAPTION_STYLE_DEFAULTS, _render_text_style_controls

    fake_ui = _TextStyleFakeUI()

    _render_text_style_controls(
        "caption_style",
        CAPTION_STYLE_DEFAULTS,
        ui=fake_ui,
        translate=lambda key: f"translated:{key}",
    )

    assert fake_ui.text_inputs[0]["label"] == "translated:caption_style.font_family"
    assert fake_ui.text_inputs[0]["help"] == "translated:caption_style.font_family_help"


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
