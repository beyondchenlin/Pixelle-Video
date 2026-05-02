from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.text_rendering_preview import (
    TextRenderingPreviewFrameRequest as TextRenderingPreviewFrameAPIRequest,
)
from api.schemas.text_rendering_preview import TextRenderingPreviewFrameResponse
from pixelle_video.models.template_text_style_presets import TEMPLATE_TEXT_STYLE_PRESETS
from pixelle_video.services.text_rendering_preview import (
    TextRenderingPreviewFrameRequest,
    TextRenderingPreviewFrameRequestError,
    TextRenderingPreviewFrameService,
)
from pixelle_video.repositories.artifacts import ArtifactObjectStore

router = APIRouter(prefix="/text-rendering", tags=["Text Rendering"])


def _validated_preview_template_id(template_id: str) -> str:
    raw_template_id = str(template_id)
    if (
        not raw_template_id
        or raw_template_id.strip() != raw_template_id
        or "/" in raw_template_id
        or "\\" in raw_template_id
        or "." in raw_template_id
        or ":" in raw_template_id
        or raw_template_id not in TEMPLATE_TEXT_STYLE_PRESETS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported text rendering preview template_id",
        )
    return raw_template_id


def _get_artifact_object_store(request: Request) -> ArtifactObjectStore:
    object_store = getattr(request.app.state, "artifact_object_store", None)
    if object_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artifact object store is not configured",
        )
    return object_store


@router.post(
    "/preview-frame",
    response_model=TextRenderingPreviewFrameResponse,
)
async def render_text_rendering_preview_frame(
    http_request: Request,
    request: TextRenderingPreviewFrameAPIRequest,
) -> TextRenderingPreviewFrameResponse:
    template_id = _validated_preview_template_id(request.template_id)
    object_store = _get_artifact_object_store(http_request)
    service = TextRenderingPreviewFrameService(object_store=object_store)
    try:
        result = await service.render_preview_frame(
            TextRenderingPreviewFrameRequest(
                workspace_id=request.workspace_id,
                template_id=template_id,
                title_text=request.title_text,
                caption_text=request.caption_text,
                text_rendering=request.text_rendering.model_dump(exclude_none=True),
                canvas_width=request.canvas_width,
                canvas_height=request.canvas_height,
                media_width=request.media_width,
                media_height=request.media_height,
                media_placement=request.media_placement.model_dump(),
                render_backend=request.render_backend,
                fps=request.fps,
                preview_media_storage_key=request.preview_media_storage_key,
            )
        )
    except TextRenderingPreviewFrameRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TextRenderingPreviewFrameResponse(
        storage_key=result.storage_key,
        url=result.url,
    )
