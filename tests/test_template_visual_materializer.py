from pathlib import Path

import pytest

from pixelle_video.models.template_visual_asset import TemplateVisualAsset
from pixelle_video.services.template_visual_materializer import (
    TemplateVisualMaterializer,
    resolve_template_body_text,
)


def test_resolve_template_body_text_defaults_to_caption_renderer():
    assert resolve_template_body_text("Template body", "caption_renderer") == ""
    assert resolve_template_body_text("Template body", "none") == ""
    assert resolve_template_body_text("Template body", "template_body") == "Template body"
    assert resolve_template_body_text("Template body", "explicit_both") == "Template body"


def test_template_visual_asset_is_immutable():
    asset = TemplateVisualAsset(
        path="frames/frame.png",
        frame_index=0,
        template_id="image_default",
        template_path="templates/1080x1920/image_default.html",
        width=1080,
        height=1920,
        media_path="raw.png",
        text_policy="caption_renderer",
    )

    with pytest.raises(Exception):
        asset.path = "frames/other.png"


@pytest.mark.asyncio
async def test_template_visual_materializer_rejects_invalid_policy_before_loading_template(
    monkeypatch,
    tmp_path,
):
    def fail_if_constructed(_template_path):
        raise AssertionError("generator should not be constructed")

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        fail_if_constructed,
    )

    with pytest.raises(ValueError, match="Invalid template text policy"):
        await TemplateVisualMaterializer().materialize_frame(
            title="Demo",
            template_body_text="Template body",
            media_path=None,
            frame_index=0,
            template_path="missing.html",
            template_id="image_default",
            output_path=tmp_path / "frame.png",
            text_policy="unsafe",
        )


@pytest.mark.asyncio
async def test_template_visual_materializer_rejects_reserved_template_params(
    monkeypatch,
    tmp_path,
):
    def fail_if_constructed(_template_path):
        raise AssertionError("generator should not be constructed")

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        fail_if_constructed,
    )

    with pytest.raises(ValueError, match="reserved template parameter"):
        await TemplateVisualMaterializer().materialize_frame(
            title="Demo",
            template_body_text="Template body",
            media_path="raw.png",
            frame_index=0,
            template_path="templates/1080x1920/image_default.html",
            template_id="image_default",
            output_path=tmp_path / "frame.png",
            text_policy="caption_renderer",
            template_params={"text": "bypass caption renderer"},
        )


@pytest.mark.asyncio
async def test_template_visual_materializer_renders_html_with_text_policy(tmp_path, monkeypatch):
    calls = {}

    class FakeGenerator:
        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            calls["template_path"] = template_path
            calls["canvas_width"] = canvas_width
            calls["canvas_height"] = canvas_height
            self.width = canvas_width or 1080
            self.height = canvas_height or 1920

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
        template_body_text="Template body",
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


@pytest.mark.asyncio
async def test_template_visual_materializer_forwards_canvas_dimensions(
    tmp_path,
    monkeypatch,
):
    calls = {}

    class FakeGenerator:
        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            calls["template_path"] = template_path
            calls["canvas_width"] = canvas_width
            calls["canvas_height"] = canvas_height
            self.width = canvas_width or 1080
            self.height = canvas_height or 1920

        async def generate_frame(self, *, title, text, image, ext, output_path):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    result = await TemplateVisualMaterializer().materialize_frame(
        title="Demo",
        template_body_text="Template body",
        media_path="raw.png",
        frame_index=0,
        template_path="templates/1080x1920/image_default.html",
        template_id="image_default",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        canvas_width=1280,
        canvas_height=720,
    )

    assert calls["canvas_width"] == 1280
    assert calls["canvas_height"] == 720
    assert (result.width, result.height) == (1280, 720)
