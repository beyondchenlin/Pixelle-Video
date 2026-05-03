from pathlib import Path

import pytest

from pixelle_video.models.template_parameters import RESERVED_TEMPLATE_PARAM_NAMES
from pixelle_video.models.template_visual_asset import TemplateVisualAsset
from pixelle_video.services.template_visual_materializer import (
    TemplateVisualMaterializer,
    resolve_template_body_text,
)


def _layered_template_spec_payload(**overrides):
    payload = {
        "version": "layered_template.v1",
        "template_id": "user:portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [],
        "metadata": {"source_kind": "user"},
    }
    payload.update(overrides)
    return payload


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
@pytest.mark.parametrize("param_name", sorted(RESERVED_TEMPLATE_PARAM_NAMES))
async def test_template_visual_materializer_rejects_reserved_template_params(
    monkeypatch,
    tmp_path,
    param_name,
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
            template_params={param_name: "bypass runtime field"},
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

        async def generate_frame(self, *, title, text, image, ext, output_path, **kwargs):
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
    assert calls["ext"] == {
        "index": 1,
        "media_layout_mode": "template",
        "accent": "#fff",
    }


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

        async def generate_frame(self, *, title, text, image, ext, output_path, **kwargs):
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


@pytest.mark.asyncio
async def test_template_visual_materializer_uses_layered_template_html_adapter(
    tmp_path,
    monkeypatch,
):
    calls = {}

    def fail_if_legacy_constructed(*_args, **_kwargs):
        raise AssertionError("legacy HTMLFrameGenerator must not render layered specs")

    class FakeLayeredTemplateHTMLFrameAdapter:
        async def render_frame(
            self,
            *,
            spec,
            output_path,
            title_text,
            caption_text,
            text_rendering,
            media_path,
        ):
            calls["spec"] = spec.to_dict()
            calls["title_text"] = title_text
            calls["caption_text"] = caption_text
            calls["text_rendering"] = dict(text_rendering)
            calls["media_path"] = media_path
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        fail_if_legacy_constructed,
    )
    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.LayeredTemplateHTMLFrameAdapter",
        FakeLayeredTemplateHTMLFrameAdapter,
    )

    result = await TemplateVisualMaterializer().materialize_frame(
        title="Runtime Title",
        template_body_text="Runtime Caption",
        media_path="raw.png",
        frame_index=2,
        template_path="templates/1080x1920/image_default.html",
        template_id="legacy-image-default",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        caption_text="Runtime Caption",
        text_rendering={"title_style": {"font_size": 88}},
        layered_template_spec=_layered_template_spec_payload(),
    )

    assert result.path == str(tmp_path / "frame.png")
    assert (result.width, result.height) == (720, 1280)
    assert result.template_id == "user:portrait_news"
    assert result.template_path == "layered_template:user:portrait_news"
    assert result.media_path == "raw.png"
    assert result.text_policy == "caption_renderer"
    assert result.diagnostics["layered_template_id"] == "user:portrait_news"
    assert result.diagnostics["layered_template_canvas"] == "720x1280"
    assert calls["title_text"] == "Runtime Title"
    assert calls["caption_text"] == "Runtime Caption"
    assert calls["media_path"] == "raw.png"
    assert calls["text_rendering"] == {"title_style": {"font_size": 88}}


@pytest.mark.asyncio
async def test_template_visual_materializer_forwards_media_layout_mode(
    tmp_path,
    monkeypatch,
):
    calls = {}

    class FakeGenerator:
        width = 1280
        height = 720

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            calls["template_path"] = template_path

        async def generate_frame(self, *, title, text, image, ext, output_path, **kwargs):
            calls["ext"] = dict(ext)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    await TemplateVisualMaterializer().materialize_frame(
        title="Demo",
        template_body_text="Template body",
        media_path="raw.png",
        frame_index=0,
        template_path="templates/1920x1080/image_landscape_minimal.html",
        template_id="image_landscape_minimal",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        media_layout_mode="canvas",
    )

    assert calls["ext"]["media_layout_mode"] == "canvas"


@pytest.mark.asyncio
async def test_template_visual_materializer_forwards_typed_media_placement(
    tmp_path,
    monkeypatch,
):
    calls = {}

    class FakeGenerator:
        width = 1280
        height = 720

        def __init__(self, template_path, canvas_width=None, canvas_height=None):
            calls["canvas"] = (canvas_width, canvas_height)

        async def generate_frame(
            self,
            *,
            title,
            text,
            image,
            ext,
            output_path,
            media_placement,
            media_type,
            media_width,
            media_height,
        ):
            calls["media_placement"] = media_placement.to_dict()
            calls["media_type"] = media_type
            calls["media_size"] = (media_width, media_height)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"png")
            return output_path

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        FakeGenerator,
    )

    await TemplateVisualMaterializer().materialize_frame(
        title="Demo",
        template_body_text="Template body",
        media_path="raw.png",
        media_type="image",
        frame_index=0,
        template_path="templates/1920x1080/image_landscape_minimal.html",
        template_id="image_landscape_minimal",
        output_path=tmp_path / "frame.png",
        text_policy="caption_renderer",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        media_placement={"scale_percent": 90, "anchor": "right"},
    )

    assert calls["canvas"] == (1280, 720)
    assert calls["media_placement"]["scale_percent"] == 90
    assert calls["media_placement"]["offset_x"] == 0
    assert calls["media_placement"]["offset_y"] == 0
    assert calls["media_type"] == "image"
    assert calls["media_size"] == (768, 768)
