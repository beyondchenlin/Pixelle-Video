from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.schemas.layered_template_preview import (
    LayeredTemplatePreviewFrameRequest,
    LayeredTemplatePreviewFrameResponse,
)
from pixelle_video.services.layered_template_service import LayeredTemplateService

router = APIRouter(prefix="/layered-templates", tags=["Layered Templates"])


@router.post("/preview-frame", response_model=LayeredTemplatePreviewFrameResponse)
async def render_layered_template_preview_frame(
    request: LayeredTemplatePreviewFrameRequest,
) -> LayeredTemplatePreviewFrameResponse:
    service = LayeredTemplateService()
    try:
        spec = request.spec.to_model()
        html = service.render_preview_html(
            spec=spec,
            title_text=request.title_text,
            caption_text=request.caption_text,
            text_rendering=request.text_rendering,
        )
        fingerprint = service.fingerprint(spec)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return LayeredTemplatePreviewFrameResponse(html=html, fingerprint=fingerprint)
