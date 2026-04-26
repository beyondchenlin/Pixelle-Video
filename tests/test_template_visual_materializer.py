from pathlib import Path

import pytest

from pixelle_video.services.template_visual_materializer import (
    TemplateVisualMaterializer,
    resolve_template_body_text,
)


def test_resolve_template_body_text_defaults_to_caption_renderer():
    assert resolve_template_body_text("Narration", "caption_renderer") == ""
    assert resolve_template_body_text("Narration", "none") == ""
    assert resolve_template_body_text("Narration", "template_body") == "Narration"
    assert resolve_template_body_text("Narration", "explicit_both") == "Narration"


@pytest.mark.asyncio
async def test_template_visual_materializer_renders_html_with_text_policy(tmp_path, monkeypatch):
    calls = {}

    class FakeGenerator:
        width = 1080
        height = 1920

        def __init__(self, template_path):
            calls["template_path"] = template_path

        async def generate_frame(self, *, title, text, image, ext, output_path):
            calls["title"] = title
            calls["text"] = text
            calls["image"] = image
            calls["ext"] = dict(ext)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    materializer = TemplateVisualMaterializer()
    result = await materializer.materialize_frame(
        title="Demo",
        narration="Narration",
        media_path="raw.png",
        frame_index=0,
        template_path="templates/1080x1920/image_default.html",
        template_id="image_default",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        template_params={"accent": "#fff"},
    )

    assert result.path == str(tmp_path / "frame.png")
    assert result.text_policy == "caption_renderer"
    assert calls["text"] == ""
    assert calls["ext"] == {"index": 1, "accent": "#fff"}
