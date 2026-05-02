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
