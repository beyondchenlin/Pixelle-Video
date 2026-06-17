# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api.config import api_config
from api.reference_image_upload_store import ReferenceImageUploadStore
from api.schemas.reference_image import ReferenceImageUploadResponse
from pixelle_video.services.resource_resolver import (
    ResourceIdInvalidError,
    ResourceNotFoundError,
    ResourceResolverError,
)

router = APIRouter(prefix="/reference-images", tags=["Reference Images"])


def _upload_store(request: Request) -> ReferenceImageUploadStore:
    store = getattr(request.app.state, "reference_image_upload_store", None)
    if store is None:
        store = ReferenceImageUploadStore(
            base_dir=api_config.reference_image_upload_base_path,
            max_upload_size_mb=api_config.reference_image_max_upload_size_mb,
        )
        request.app.state.reference_image_upload_store = store
    return store


def _require_reference_image_api_enabled() -> None:
    if not api_config.reference_image_api_enabled:
        raise HTTPException(
            status_code=404,
            detail="reference image API is disabled",
        )


def _resolver_http_exception(exc: ResourceResolverError) -> HTTPException:
    if isinstance(exc, ResourceIdInvalidError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ResourceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/uploads", response_model=ReferenceImageUploadResponse)
async def upload_reference_image(
    request: Request,
    file: UploadFile = File(...),
) -> ReferenceImageUploadResponse:
    """Upload a reference image and receive public upload/artifact IDs.

    This is a gray API. It stores the upload in a controlled API-local store and
    returns IDs that may be used in `VideoGenerateRequest.reference_image`.
    """

    _require_reference_image_api_enabled()
    try:
        record = await _upload_store(request).store_upload(file)
    except ResourceResolverError as exc:
        raise _resolver_http_exception(exc)
    return ReferenceImageUploadResponse(**record.to_response_dict())


@router.get("/uploads/{upload_id}", response_model=ReferenceImageUploadResponse)
async def get_reference_image_upload(
    request: Request,
    upload_id: str,
) -> ReferenceImageUploadResponse:
    _require_reference_image_api_enabled()
    try:
        record = _upload_store(request).resolve_upload_id(upload_id)
    except ResourceResolverError as exc:
        raise _resolver_http_exception(exc)
    return ReferenceImageUploadResponse(**record.to_response_dict())
