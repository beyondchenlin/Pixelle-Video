from api.schemas.text_rendering import TextRenderingRequest
from pixelle_video.services.text_rendering_orchestrator import TextRenderingOrchestrator


def test_text_style_request_serializes_as_partial_override():
    request = TextRenderingRequest.model_validate(
        {
            "caption_style": {"font_size": 72, "font_file": "fonts/simhei.ttf"},
            "overlay_style": {},
        }
    )

    payload = request.model_dump(exclude_none=True)

    assert payload["caption_style"] == {
        "font_file": "fonts/simhei.ttf",
        "font_size": 72,
    }
    assert payload["overlay_style"] == {}


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
