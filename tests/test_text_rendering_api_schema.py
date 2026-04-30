import pytest
from pydantic import ValidationError

from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator


def test_text_style_request_serializes_as_partial_override():
    request = TextRenderingRequest.model_validate(
        {
            "caption_style": {"font_size": 72, "font_file": "fonts/simhei.ttf"},
            "title_style": {"font_size": 96, "background_opacity": 0.9},
            "overlay_style": {},
        }
    )

    payload = request.model_dump(exclude_none=True)

    assert payload["caption_style"] == {
        "font_file": "fonts/simhei.ttf",
        "font_size": 72,
    }
    assert payload["title_style"] == {
        "background_opacity": 0.9,
        "font_size": 96,
    }
    assert payload["overlay_style"] == {}


def test_text_rendering_request_accepts_title_style_with_caption_shape():
    request = TextRenderingRequest.model_validate(
        {
            "title_style": {
                "font_family": "Noto Sans CJK SC",
                "font_size": 88,
                "primary_color": "#112233",
                "stroke_color": "#FFFFFF",
                "stroke_width": 3,
                "background_color": "#000000",
                "background_opacity": 0.75,
                "position": "top_left",
                "alignment": "right",
                "margin_x": 44,
                "margin_y": 72,
                "max_width_ratio": 0.4,
                "max_chars_per_line": 9,
            }
        }
    )

    assert request.title_style is not None
    assert request.title_style.font_size == 88
    assert request.title_style.background_opacity == 0.75
    assert request.title_style.position == "top_left"
    assert request.title_style.alignment == "right"
    assert request.title_style.margin_x == 44
    assert request.title_style.margin_y == 72
    assert request.title_style.max_width_ratio == 0.4


def test_title_style_forbids_unknown_fields_like_caption_style():
    with pytest.raises(ValidationError):
        TextRenderingRequest.model_validate(
            {
                "title_style": {
                    "font_size": 88,
                    "title_shadow_preset": "private-template-field",
                }
            }
        )


def test_empty_api_text_style_overrides_keep_role_defaults():
    request = TextRenderingRequest.model_validate(
        {
            "caption_style": {},
            "overlay_style": {},
        }
    )
    payload = request.model_dump(exclude_none=True)

    result = TextRenderingOrchestrator().build(text_rendering=payload)

    assert result.caption_style.font_size == 42
    assert result.caption_style.primary_color == "#2C3E50"
    assert result.caption_style.stroke_width == 0
    assert result.overlay_style.font_size == 76
    assert result.overlay_style.primary_color == "#FFFFFF"
    assert result.overlay_style.stroke_width == 2
