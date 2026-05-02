from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.layered_template_preview import (
    LayeredTemplatePreviewFrameRequest,
    LayeredTemplatePreviewFrameResponse,
)
from pixelle_video.repositories.artifacts import ArtifactObjectStore
from pixelle_video.services.layered_template_service import LayeredTemplateService

router = APIRouter(prefix="/layered-templates", tags=["Layered Templates"])


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
    response_model=LayeredTemplatePreviewFrameResponse,
)
async def render_layered_template_preview_frame(
    http_request: Request,
    request: LayeredTemplatePreviewFrameRequest,
) -> LayeredTemplatePreviewFrameResponse:
    object_store = _get_artifact_object_store(http_request)
    service = LayeredTemplateService(object_store=object_store)
    result = await service.render_preview_frame(request.to_service_request())
    return LayeredTemplatePreviewFrameResponse(
        storage_key=result.storage_key,
        url=result.url,
    )
