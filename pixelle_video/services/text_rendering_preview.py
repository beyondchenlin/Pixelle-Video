from __future__ import annotations

import hashlib
import inspect
import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from pixelle_video.models.render_package import CaptionCue, VisualClip
from pixelle_video.models.template_render_context import TemplateRenderContext
from pixelle_video.repositories.artifacts import ArtifactObjectStore
from pixelle_video.services.hyperframes_compiler import HyperFramesCompiler
from pixelle_video.services.text_rendering_orchestrator import (
    TextRenderingBuildResult,
    TextRenderingOrchestrator,
)

PREVIEW_ARTIFACT_KIND = "text_rendering_preview_frame"
_PREVIEW_MEDIA_FILENAME_PATTERN = re.compile(
    r"^[0-9A-Za-z][0-9A-Za-z_.-]*\.[A-Za-z0-9][A-Za-z0-9_-]*$"
)


class TextRenderingPreviewFrameRequestError(ValueError):
    """Raised when a preview-frame request violates the artifact-key contract."""


@dataclass(frozen=True)
class TextRenderingPreviewFrameRequest:
    workspace_id: str
    template_id: str
    title_text: str
    caption_text: str
    text_rendering: Mapping[str, Any]
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    media_placement: Mapping[str, Any] = field(default_factory=dict)
    render_backend: str | None = None
    fps: int = 30
    preview_media_storage_key: str | None = None


@dataclass(frozen=True)
class TextRenderingPreviewFrameResult:
    storage_key: str
    url: str | None
    fingerprint: str


class TextRenderingPreviewFrameRenderer(Protocol):
    def render_preview_frame(
        self,
        *,
        request: TextRenderingPreviewFrameRequest,
        build_result: TextRenderingBuildResult,
        preview_media_url: str | None,
        output_path: str | Path,
    ) -> str | Path:
        ...


def preview_frame_fingerprint(request: TextRenderingPreviewFrameRequest) -> str:
    payload = asdict(request)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class TextRenderingPreviewFrameService:
    def __init__(
        self,
        *,
        object_store: ArtifactObjectStore,
        renderer: TextRenderingPreviewFrameRenderer | None = None,
        orchestrator: TextRenderingOrchestrator | None = None,
    ) -> None:
        self.object_store = object_store
        self.renderer = renderer or HyperFramesCompiledPreviewFrameRenderer()
        self.orchestrator = orchestrator or TextRenderingOrchestrator()

    async def render_preview_frame(
        self,
        request: TextRenderingPreviewFrameRequest,
    ) -> TextRenderingPreviewFrameResult:
        fingerprint = preview_frame_fingerprint(request)
        build_result = self.orchestrator.build(
            text_rendering=dict(request.text_rendering),
            narrations=[request.caption_text],
            render_backend=request.render_backend,
            frame_count=1,
            task_id=f"text-rendering-preview-{fingerprint}",
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            template_id=request.template_id,
        )
        preview_media_url = await self._resolve_preview_media_url(request)
        with tempfile.TemporaryDirectory(prefix="text-rendering-preview-") as staging_dir:
            rendered_path = await self._render(
                request=request,
                build_result=build_result,
                preview_media_url=preview_media_url,
                output_path=Path(staging_dir) / "preview.png",
            )
            stored_file = await self.object_store.put_file(
                request.workspace_id,
                rendered_path,
                metadata={
                    "kind": PREVIEW_ARTIFACT_KIND,
                    "fingerprint": fingerprint,
                    "template_id": request.template_id,
                },
            )
        return TextRenderingPreviewFrameResult(
            storage_key=stored_file.storage_key,
            url=stored_file.url,
            fingerprint=fingerprint,
        )

    async def _resolve_preview_media_url(
        self,
        request: TextRenderingPreviewFrameRequest,
    ) -> str | None:
        if request.preview_media_storage_key:
            self._validate_preview_media_storage_key(
                request.workspace_id,
                request.preview_media_storage_key,
            )
            local_file_uri = await self._get_local_file_uri_if_supported(
                request.preview_media_storage_key
            )
            if local_file_uri is not None:
                return local_file_uri
            return await self.object_store.get_file_url(request.preview_media_storage_key)
        return None

    @staticmethod
    def _validate_preview_media_storage_key(workspace_id: str, storage_key: str) -> None:
        parts = storage_key.split("/")
        if (
            len(parts) != 3
            or parts[0] != "artifacts"
            or parts[1] != workspace_id
            or not _PREVIEW_MEDIA_FILENAME_PATTERN.fullmatch(parts[2])
        ):
            raise TextRenderingPreviewFrameRequestError(
                "preview_media_storage_key must belong to the request workspace"
            )

    async def _get_local_file_uri_if_supported(self, storage_key: str) -> str | None:
        get_local_file_uri = getattr(self.object_store, "get_local_file_uri", None)
        if get_local_file_uri is None:
            return None

        try:
            resolved_uri = get_local_file_uri(storage_key)
            if inspect.isawaitable(resolved_uri):
                resolved_uri = await resolved_uri
        except (FileNotFoundError, ValueError) as exc:
            raise TextRenderingPreviewFrameRequestError(str(exc)) from exc

        if not isinstance(resolved_uri, str) or not resolved_uri.strip():
            raise TextRenderingPreviewFrameRequestError("local artifact URI is invalid")
        return resolved_uri

    async def _render(
        self,
        *,
        request: TextRenderingPreviewFrameRequest,
        build_result: TextRenderingBuildResult,
        preview_media_url: str | None,
        output_path: Path,
    ) -> Path:
        rendered = self.renderer.render_preview_frame(
            request=request,
            build_result=build_result,
            preview_media_url=preview_media_url,
            output_path=output_path,
        )
        if inspect.isawaitable(rendered):
            rendered = await rendered
        return Path(rendered)


class HyperFramesCompiledPreviewFrameRenderer:
    """Compile a one-frame HyperFrames project and capture the first frame."""

    def __init__(
        self,
        *,
        compiler: HyperFramesCompiler | None = None,
        work_root: str | Path | None = None,
    ) -> None:
        self.compiler = compiler or HyperFramesCompiler()
        self.work_root = Path(work_root) if work_root is not None else None

    async def render_preview_frame(
        self,
        *,
        request: TextRenderingPreviewFrameRequest,
        build_result: TextRenderingBuildResult,
        preview_media_url: str | None,
        output_path: str | Path,
    ) -> Path:
        with tempfile.TemporaryDirectory(
            prefix="text-rendering-preview-render-",
            dir=str(self.work_root) if self.work_root is not None else None,
        ) as work_dir:
            project_dir = Path(work_dir) / "hyperframes"
            project_dir.mkdir(parents=True, exist_ok=True)
            self.compiler.compile(
                project_dir=project_dir,
                context=self._build_context(
                    request=request,
                    build_result=build_result,
                    preview_media_url=preview_media_url,
                ),
            )
            resolved_output_path = Path(output_path)
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            await self._capture_screenshot(
                project_dir / "index.html",
                resolved_output_path,
                width=request.canvas_width,
                height=request.canvas_height,
            )
            return resolved_output_path

    def _build_context(
        self,
        *,
        request: TextRenderingPreviewFrameRequest,
        build_result: TextRenderingBuildResult,
        preview_media_url: str | None,
    ) -> TemplateRenderContext:
        visuals = []
        if preview_media_url:
            visuals.append(
                VisualClip(
                    id="preview-media",
                    frame_index=0,
                    start=0.0,
                    end=1.0,
                    media_path=preview_media_url,
                    media_type="image",
                )
            )
        return TemplateRenderContext(
            template_id=request.template_id,
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            media_width=request.media_width,
            media_height=request.media_height,
            media_placement=dict(request.media_placement),
            duration=1.0,
            fps=request.fps,
            title=request.title_text,
            author=None,
            footer=None,
            theme=None,
            style_profile=request.template_id,
            template_params={},
            visuals=visuals,
            captions=[
                CaptionCue(
                    id="preview-caption",
                    text=request.caption_text,
                    start=0.0,
                    end=1.0,
                    frame_indices=[0],
                    style_profile=build_result.caption_settings.style_profile,
                )
            ],
            text_style_profiles=list(build_result.text_style_profiles),
            title_style_profile=build_result.title_style,
        )

    async def _capture_screenshot(
        self,
        html_path: Path,
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for real text rendering preview frames."
            ) from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_viewport_size({"width": int(width), "height": int(height)})
                await page.goto(html_path.resolve().as_uri())
                await page.screenshot(path=str(output_path), full_page=True)
            finally:
                await browser.close()
