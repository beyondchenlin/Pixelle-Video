from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    layered_template_fingerprint,
)
from pixelle_video.repositories.artifacts import ArtifactObjectStore
from pixelle_video.services.frame_html import HTMLDocumentFrameRenderer
from pixelle_video.services.layered_template_adapters.html_preview import (
    render_layered_template_preview_html,
)

LAYERED_TEMPLATE_PREVIEW_ARTIFACT_KIND = "layered_template_preview_frame"


@dataclass(frozen=True)
class LayeredTemplatePreviewFrameRequest:
    workspace_id: str
    spec: LayeredTemplateSpec
    title_text: str = ""
    caption_text: str = ""
    text_rendering: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LayeredTemplatePreviewFrameResult:
    storage_key: str
    url: str | None
    fingerprint: str


class LayeredTemplatePreviewFrameRenderer(Protocol):
    def render_preview_frame(
        self,
        *,
        html: str,
        output_path: str | Path,
        width: int,
        height: int,
    ) -> str | Path:
        ...


def layered_template_preview_frame_fingerprint(
    request: LayeredTemplatePreviewFrameRequest,
) -> str:
    payload = {
        "workspace_id": request.workspace_id,
        "spec": request.spec.to_dict(),
        "title_text": request.title_text,
        "caption_text": request.caption_text,
        "text_rendering": dict(request.text_rendering or {}),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class LayeredTemplateHTMLDocumentFrameRenderer:
    def __init__(self, renderer: HTMLDocumentFrameRenderer | None = None) -> None:
        self.renderer = renderer or HTMLDocumentFrameRenderer()

    async def render_preview_frame(
        self,
        *,
        html: str,
        output_path: str | Path,
        width: int,
        height: int,
    ) -> Path:
        rendered_path = await self.renderer.render_html_document(
            html=html,
            output_path=str(output_path),
            width=width,
            height=height,
        )
        return Path(rendered_path)


class LayeredTemplateService:
    def __init__(
        self,
        *,
        object_store: ArtifactObjectStore | None = None,
        renderer: LayeredTemplatePreviewFrameRenderer | None = None,
    ) -> None:
        self.object_store = object_store
        self.renderer = renderer or LayeredTemplateHTMLDocumentFrameRenderer()

    def render_preview_html(
        self,
        *,
        spec: LayeredTemplateSpec,
        title_text: str,
        caption_text: str,
        text_rendering: Mapping[str, Any] | None,
    ) -> str:
        return render_layered_template_preview_html(
            spec=spec,
            title_text=title_text,
            caption_text=caption_text,
            text_rendering=text_rendering or {},
            fingerprint=layered_template_fingerprint(spec),
        )

    async def render_preview_frame(
        self,
        request: LayeredTemplatePreviewFrameRequest,
    ) -> LayeredTemplatePreviewFrameResult:
        if self.object_store is None:
            raise RuntimeError("Artifact object store is not configured")
        fingerprint = layered_template_preview_frame_fingerprint(request)
        html = self.render_preview_html(
            spec=request.spec,
            title_text=request.title_text,
            caption_text=request.caption_text,
            text_rendering=request.text_rendering or {},
        )
        with tempfile.TemporaryDirectory(prefix="layered-template-preview-") as staging_dir:
            output_path = Path(staging_dir) / "preview.png"
            rendered_path = self.renderer.render_preview_frame(
                html=html,
                output_path=output_path,
                width=request.spec.canvas_width,
                height=request.spec.canvas_height,
            )
            if inspect.isawaitable(rendered_path):
                rendered_path = await rendered_path
            stored_file = await self.object_store.put_file(
                request.workspace_id,
                rendered_path,
                metadata={
                    "kind": LAYERED_TEMPLATE_PREVIEW_ARTIFACT_KIND,
                    "fingerprint": fingerprint,
                    "template_id": request.spec.template_id,
                },
            )
        return LayeredTemplatePreviewFrameResult(
            storage_key=stored_file.storage_key,
            url=stored_file.url,
            fingerprint=fingerprint,
        )
