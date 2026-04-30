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
        self.url_requests = []
        self.urls = {
            "artifacts/demo/source.png": "https://cdn.example.test/source.png",
            "artifacts/ws-a/source.png": "https://cdn.example.test/ws-a/source.png",
        }

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
            storage_key="artifacts/demo/rendered.png",
            url="https://cdn.example.test/rendered.png",
        )

    async def get_file_url(self, storage_key, options=None):
        self.url_requests.append(storage_key)
        return self.urls[storage_key]

    async def exists(self, storage_key):
        return storage_key in self.urls


class FakeRenderer:
    def __init__(self) -> None:
        self.calls = []

    async def render_preview_frame(self, *, request, build_result, preview_media_url, output_path):
        self.calls.append(
            {
                "request": request,
                "build_result": build_result,
                "preview_media_url": preview_media_url,
                "output_path": Path(output_path),
            }
        )
        Path(output_path).write_bytes(b"png")
        return output_path


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
    }
    payload.update(overrides)
    return TextRenderingPreviewFrameRequest(**payload)


@pytest.mark.asyncio
async def test_render_preview_frame_returns_only_artifact_key_url_and_fingerprint(tmp_path):
    renderer = FakeRenderer()
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
    assert not object_store.uploads[0]["source_path"].exists()


def test_preview_frame_request_rejects_public_url_and_template_params():
    with pytest.raises(TypeError):
        _request(preview_media_url="file:///tmp/a.png")
    with pytest.raises(TypeError):
        _request(template_params={"author": "leak"})


@pytest.mark.asyncio
async def test_preview_media_storage_key_must_match_workspace():
    object_store = FakeArtifactObjectStore()
    service = TextRenderingPreviewFrameService(
        object_store=object_store,
        renderer=FakeRenderer(),
    )

    with pytest.raises(ValueError, match="workspace"):
        await service.render_preview_frame(
            _request(
                workspace_id="ws-a",
                preview_media_storage_key="artifacts/ws-b/source.png",
            )
        )

    assert object_store.url_requests == []


class CapturingCompiler:
    def __init__(self) -> None:
        self.contexts = []

    def compile(self, *, project_dir, context):
        self.contexts.append(context)
        Path(project_dir).mkdir(parents=True, exist_ok=True)
        (Path(project_dir) / "index.html").write_text("<html></html>", encoding="utf-8")


@pytest.mark.asyncio
async def test_hyperframes_preview_context_uses_fixed_template_values(tmp_path, monkeypatch):
    from pixelle_video.services import text_rendering_preview as preview_module

    compiler = CapturingCompiler()

    async def fake_capture(self, html_path, output_path, *, width, height):
        Path(output_path).write_bytes(b"png")

    monkeypatch.setattr(
        preview_module.HyperFramesCompiledPreviewFrameRenderer,
        "_capture_screenshot",
        fake_capture,
    )
    renderer = preview_module.HyperFramesCompiledPreviewFrameRenderer(compiler=compiler)

    await renderer.render_preview_frame(
        request=_request(preview_media_storage_key=None),
        build_result=preview_module.TextRenderingOrchestrator().build(
            text_rendering={},
            template_id="image_default",
            canvas_width=1080,
            canvas_height=1920,
        ),
        preview_media_url=None,
        output_path=tmp_path / "preview.png",
    )

    context = compiler.contexts[0]
    assert context.author is None
    assert context.footer is None
    assert context.theme is None
    assert context.style_profile == "image_default"
    assert context.template_params == {}


@pytest.mark.asyncio
async def test_hyperframes_preview_renderer_cleans_temporary_project_dir(tmp_path, monkeypatch):
    from pixelle_video.services import text_rendering_preview as preview_module

    compiler = CapturingCompiler()
    work_root = tmp_path / "renderer-work"
    work_root.mkdir()

    async def fake_capture(self, html_path, output_path, *, width, height):
        Path(output_path).write_bytes(b"png")

    monkeypatch.setattr(
        preview_module.HyperFramesCompiledPreviewFrameRenderer,
        "_capture_screenshot",
        fake_capture,
    )
    renderer = preview_module.HyperFramesCompiledPreviewFrameRenderer(
        compiler=compiler,
        work_root=work_root,
    )
    output_path = tmp_path / "preview.png"

    await renderer.render_preview_frame(
        request=_request(preview_media_storage_key=None),
        build_result=preview_module.TextRenderingOrchestrator().build(
            text_rendering={},
            template_id="image_default",
            canvas_width=1080,
            canvas_height=1920,
        ),
        preview_media_url=None,
        output_path=output_path,
    )

    assert output_path.is_file()
    assert list(work_root.iterdir()) == []
