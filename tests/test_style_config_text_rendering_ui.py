from pathlib import Path

import pytest
from pydantic import ValidationError

from api.schemas.text_rendering import TextRenderingRequest


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
