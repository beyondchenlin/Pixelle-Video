from fastapi import APIRouter

from api.config import api_config
from api.schemas.text_rendering_preview import (
    TextRenderingPreviewFrameRequest as TextRenderingPreviewFrameAPIRequest,
)
from api.schemas.text_rendering_preview import TextRenderingPreviewFrameResponse
from pixelle_video.services.text_rendering_preview import (
    TextRenderingPreviewFrameRequest,
    TextRenderingPreviewFrameService,
)
from pixelle_video.storage.artifact_object_store import FilesystemDevArtifactObjectStore

router = APIRouter(prefix="/text-rendering", tags=["Text Rendering"])


@router.post("/preview-frame", response_model=TextRenderingPreviewFrameResponse)
async def render_text_rendering_preview_frame(
    request: TextRenderingPreviewFrameAPIRequest,
) -> TextRenderingPreviewFrameResponse:
    object_store = FilesystemDevArtifactObjectStore(
        root=api_config.artifact_base_path,
        base_url=api_config.artifact_base_url,
    )
    service = TextRenderingPreviewFrameService(object_store=object_store)
    result = await service.render_preview_frame(
        TextRenderingPreviewFrameRequest(
            workspace_id=request.workspace_id,
            template_id=request.template_id,
            title_text=request.title_text,
            caption_text=request.caption_text,
            text_rendering=request.text_rendering.model_dump(exclude_none=True),
            canvas_width=request.canvas_width,
            canvas_height=request.canvas_height,
            media_width=request.media_width,
            media_height=request.media_height,
            media_placement=dict(request.media_placement),
            render_backend=request.render_backend,
            fps=request.fps,
            preview_media_storage_key=request.preview_media_storage_key,
            preview_media_url=request.preview_media_url,
        )
    )
    return TextRenderingPreviewFrameResponse(
        storage_key=result.storage_key,
        url=result.url,
        fingerprint=result.fingerprint,
    )
