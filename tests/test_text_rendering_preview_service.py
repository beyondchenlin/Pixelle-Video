from pathlib import Path

import pytest

from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.services.text_rendering_preview import (
    TextRenderingPreviewFrameRequest,
    TextRenderingPreviewFrameService,
    preview_frame_fingerprint,
)


class FakeArtifactObjectStore:
    def __init__(self) -> None:
        self.uploads = []
        self.urls = {
            "artifacts/demo/source.png": "https://cdn.example.test/source.png",
        }

    async def put_file(self, workspace_id, source_path, metadata=None):
        self.uploads.append(
            {
                "workspace_id": workspace_id,
                "source_path": Path(source_path),
                "metadata": dict(metadata or {}),
            }
        )
        return StoredArtifactFile(
            storage_key="artifacts/demo/rendered.png",
            url="https://cdn.example.test/rendered.png",
        )

    async def get_file_url(self, storage_key, options=None):
        return self.urls[storage_key]

    async def exists(self, storage_key):
        return storage_key in self.urls


class FakeRenderer:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.calls = []

    async def render_preview_frame(self, *, request, build_result, preview_media_url):
        self.calls.append(
            {
                "request": request,
                "build_result": build_result,
                "preview_media_url": preview_media_url,
            }
        )
        self.output_path.write_bytes(b"png")
        return self.output_path


def _request(**overrides):
    payload = {
        "workspace_id": "demo",
        "template_id": "image_default",
        "title_text": "Preview title",
        "caption_text": "Preview caption",
        "text_rendering": {
            "title_style": {"font_size": 88, "primary_color": "#112233"},
            "caption_style": {"font_size": 42},
        },
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 900,
        "media_height": 1200,
        "media_placement": {"anchor": "center"},
        "preview_media_storage_key": "artifacts/demo/source.png",
        "preview_media_url": "file:///tmp/local-only.png",
    }
    payload.update(overrides)
    return TextRenderingPreviewFrameRequest(**payload)


@pytest.mark.asyncio
async def test_render_preview_frame_returns_only_artifact_key_url_and_fingerprint(tmp_path):
    renderer = FakeRenderer(tmp_path / "preview.png")
    object_store = FakeArtifactObjectStore()
    service = TextRenderingPreviewFrameService(
        object_store=object_store,
        renderer=renderer,
    )

    result = await service.render_preview_frame(_request())

    assert result.storage_key == "artifacts/demo/rendered.png"
    assert result.url == "https://cdn.example.test/rendered.png"
    assert result.fingerprint == preview_frame_fingerprint(_request())
    assert not hasattr(result, "local_path")
    assert object_store.uploads[0]["metadata"] == {
        "kind": "text_rendering_preview_frame",
        "fingerprint": result.fingerprint,
        "template_id": "image_default",
    }
    assert renderer.calls[0]["preview_media_url"] == "https://cdn.example.test/source.png"
    assert renderer.calls[0]["build_result"].title_style.font_size == 88


def test_preview_frame_fingerprint_excludes_local_preview_media_url():
    first = _request(preview_media_url="file:///tmp/a.png")
    second = _request(preview_media_url="file:///tmp/b.png")

    assert preview_frame_fingerprint(first) == preview_frame_fingerprint(second)
