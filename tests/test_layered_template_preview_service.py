from pathlib import Path

import pytest

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.services.layered_template_service import (
    LAYERED_TEMPLATE_PREVIEW_ARTIFACT_KIND,
    LayeredTemplatePreviewFrameRequest,
    LayeredTemplateService,
    layered_template_preview_frame_fingerprint,
)


class FakeArtifactObjectStore:
    def __init__(self) -> None:
        self.uploads = []

    async def put_file(self, workspace_id, source_path, metadata=None):
        source_path = Path(source_path)
        assert source_path.is_file()
        self.uploads.append(
            {
                "workspace_id": workspace_id,
                "source_path": source_path,
                "metadata": dict(metadata or {}),
            }
        )
        return StoredArtifactFile(
            storage_key="artifacts/demo/layered-preview.png",
            url="/api/files/artifacts/demo/layered-preview.png",
        )


class FakeRenderer:
    def __init__(self) -> None:
        self.calls = []

    async def render_preview_frame(self, *, html, output_path, width, height):
        self.calls.append(
            {
                "html": html,
                "output_path": Path(output_path),
                "width": width,
                "height": height,
            }
        )
        Path(output_path).write_bytes(b"png")
        return output_path


def _preview_spec() -> LayeredTemplateSpec:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id="demo",
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="bg",
                type="background",
                name="Background",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="color", ref="#F6F1E8"),
                style={"background_color": "#F6F1E8"},
            ),
            TemplateLayer(
                id="title",
                type="text",
                name="Title",
                rect=RectSpec(x=96, y=120, width=888, height=220),
                z_index=20,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=None,
                style={},
                role="title",
            ),
        ),
        metadata={},
    )


def test_render_preview_html_orders_layers_and_escapes_text():
    html = LayeredTemplateService().render_preview_html(
        spec=_preview_spec(),
        title_text="<b>Title</b>",
        caption_text="Caption",
        text_rendering={"title_style": {"font_size": 88, "primary_color": "#2C3E50"}},
    )

    assert html.index('data-layer-id="bg"') < html.index('data-layer-id="title"')
    assert "&lt;b&gt;Title&lt;/b&gt;" in html
    assert "<script" not in html
    assert "position:absolute" in html


def test_render_preview_html_skips_disabled_layers():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="hidden-bg",
                type="background",
                name="Hidden background",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                enabled=False,
                source=LayerSourceSpec(kind="color", ref="#FF0000"),
                style={"background_color": "#FF0000"},
            ),
            TemplateLayer(
                id="visible-title",
                type="text",
                name="Visible title",
                rect=RectSpec(x=96, y=120, width=888, height=220),
                z_index=20,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=None,
                style={"text_content": "Visible"},
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Runtime Title",
        caption_text="Runtime Caption",
        text_rendering={},
    )

    assert 'data-layer-id="hidden-bg"' not in html
    assert "#FF0000" not in html
    assert 'data-layer-id="visible-title"' in html
    assert "Visible" in html


def test_render_preview_html_prefers_layer_text_content_over_runtime_title():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="custom-title",
                type="text",
                name="Custom Title",
                rect=RectSpec(x=96, y=120, width=888, height=220),
                z_index=20,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=None,
                style={"text_content": "图层内文案"},
                role=None,
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Runtime Title",
        caption_text="Runtime Caption",
        text_rendering={},
    )

    assert "图层内文案" in html
    assert "Runtime Title" not in html


def test_render_preview_html_uses_text_layer_style_without_global_text_rendering():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="custom-text",
                type="text",
                name="Custom Text",
                rect=RectSpec(x=96, y=120, width=888, height=220),
                z_index=20,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=None,
                style={
                    "text_content": "Independent text",
                    "font_family": "SimHei",
                    "font_size": 54,
                    "primary_color": "#112233",
                    "background_color": "#F8FAFC",
                    "alignment": "right",
                },
                role=None,
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Runtime Title",
        caption_text="Runtime Caption",
        text_rendering={},
    )

    assert "Independent text" in html
    assert "font-family:SimHei;" in html
    assert "font-size:54px;" in html
    assert "color:#112233;" in html
    assert "background:#F8FAFC;" in html
    assert "text-align:right;justify-content:flex-end;" in html
    assert "Runtime Title" not in html
    assert "Runtime Caption" not in html


def test_render_preview_html_renders_media_layers_with_safe_sources():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            *base.layers,
            TemplateLayer(
                id="asset-image",
                type="image",
                name="Asset image",
                rect=RectSpec(x=128, y=420, width=824, height=620),
                z_index=10,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="asset", ref="artifacts/demo/source.png"),
                style={"object_fit": "contain"},
            ),
            TemplateLayer(
                id="generated",
                type="generated_media",
                name="Generated media",
                rect=RectSpec(x=128, y=1080, width=824, height=620),
                z_index=11,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="generated_media", ref="generated://primary"),
                style={},
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert 'data-layer-id="asset-image"' in html
    assert '<img class="pixelle-layer-media"' in html
    assert 'src="/api/files/artifacts/demo/source.png"' in html
    assert "object-fit:contain" in html
    assert 'data-layer-id="generated"' in html
    assert 'data-source-ref="generated://primary"' in html
    assert "pixelle-generated-media-placeholder" in html


def test_render_preview_html_renders_template_asset_keys_from_repository():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="repository-asset",
                type="image",
                name="Repository asset",
                rect=RectSpec(x=0, y=0, width=320, height=240),
                z_index=10,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="asset", ref="assets/layer_draft/logo.png"),
                style={},
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert 'src="/api/files/data/template_presets/assets/layer_draft/logo.png"' in html
    assert '<div class="pixelle-missing-media-placeholder">' not in html


def test_render_preview_html_renders_background_asset_layer():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="background-asset",
                type="background",
                name="Background asset",
                rect=RectSpec(x=0, y=0, width=1080, height=1920),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="asset", ref="assets/layer_draft/texture.jpg"),
                style={"background_color": "#112233"},
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert 'data-layer-id="background-asset"' in html
    assert 'src="/api/files/data/template_presets/assets/layer_draft/texture.jpg"' in html
    assert "background:#112233" in html


def test_render_preview_html_ignores_unsafe_style_values_and_source_urls():
    base = _preview_spec()
    spec = LayeredTemplateSpec(
        version=base.version,
        template_id=base.template_id,
        template_name=base.template_name,
        template_type=base.template_type,
        canvas_width=base.canvas_width,
        canvas_height=base.canvas_height,
        media_width=base.media_width,
        media_height=base.media_height,
        safe_area=base.safe_area,
        layers=(
            TemplateLayer(
                id="unsafe",
                type="image",
                name="Unsafe image",
                rect=RectSpec(x=0, y=0, width=100, height=100),
                z_index=0,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(kind="asset", ref="javascript:alert(1)"),
                style={
                    "background_color": "red;background-image:url(javascript:alert(2))",
                    "primary_color": "#123456",
                    "font_size": "not-a-number",
                    "object_fit": "cover;filter:url(javascript:alert(3))",
                },
            ),
        ),
        metadata=base.metadata,
    )

    html = LayeredTemplateService().render_preview_html(
        spec=spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
    )

    assert "javascript:" not in html
    assert "background-image" not in html
    assert "not-a-number" not in html
    assert "filter:" not in html
    assert "#123456" not in html
    assert '<img class="pixelle-layer-media"' not in html
    assert "pixelle-missing-media-placeholder" in html


@pytest.mark.asyncio
async def test_render_preview_frame_uploads_artifact_with_fingerprint():
    renderer = FakeRenderer()
    object_store = FakeArtifactObjectStore()
    service = LayeredTemplateService(object_store=object_store, renderer=renderer)
    request = LayeredTemplatePreviewFrameRequest(
        workspace_id="demo",
        spec=_preview_spec(),
        title_text="Title",
        caption_text="Caption",
        text_rendering={"title_style": {"font_size": 88}},
    )

    result = await service.render_preview_frame(request)

    fingerprint = layered_template_preview_frame_fingerprint(request)
    assert result.storage_key == "artifacts/demo/layered-preview.png"
    assert result.url == "/api/files/artifacts/demo/layered-preview.png"
    assert result.fingerprint == fingerprint
    assert renderer.calls[0]["width"] == 1080
    assert renderer.calls[0]["height"] == 1920
    assert object_store.uploads[0]["metadata"] == {
        "kind": LAYERED_TEMPLATE_PREVIEW_ARTIFACT_KIND,
        "fingerprint": fingerprint,
        "template_id": "demo",
    }
    assert not object_store.uploads[0]["source_path"].exists()
