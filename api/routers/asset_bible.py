from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.asset_bible import AssetBibleDraftRequest, AssetBibleResponse
from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.models.asset_bible import AssetBible

router = APIRouter(prefix="/projects", tags=["Asset Bible"])


@router.post(
    "/{project_id}/asset-bible",
    response_model=AssetBibleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset_bible_draft(
    project_id: str,
    payload: AssetBibleDraftRequest,
    request: Request,
) -> AssetBibleResponse:
    project_id = _validate_public_id("project_id", project_id)
    repository = _get_asset_bible_repository(request)
    asset_bible = _request_to_model(payload, project_id=project_id)
    saved = await repository.save_asset_bible(
        payload.workspace_id,
        asset_bible.to_dict(),
    )
    return AssetBibleResponse(asset_bible=_asset_bible_response(saved, project_id=project_id))


@router.get(
    "/{project_id}/asset-bible/{asset_bible_id}",
    response_model=AssetBibleResponse,
)
async def load_asset_bible_draft(
    project_id: str,
    asset_bible_id: str,
    workspace_id: str,
    request: Request,
) -> AssetBibleResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    workspace_id = _validate_public_id("workspace_id", workspace_id)
    repository = _get_asset_bible_repository(request)
    loaded = await repository.load_asset_bible(workspace_id, asset_bible_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="asset bible draft was not found")
    return AssetBibleResponse(asset_bible=_asset_bible_response(loaded, project_id=project_id))


@router.put(
    "/{project_id}/asset-bible/{asset_bible_id}",
    response_model=AssetBibleResponse,
)
async def update_asset_bible_draft(
    project_id: str,
    asset_bible_id: str,
    payload: AssetBibleDraftRequest,
    request: Request,
) -> AssetBibleResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    if payload.asset_bible_id != asset_bible_id:
        raise HTTPException(
            status_code=422,
            detail="payload asset_bible_id must match route asset_bible_id",
        )
    repository = _get_asset_bible_repository(request)
    asset_bible = _request_to_model(payload, project_id=project_id)
    saved = await repository.save_asset_bible(
        payload.workspace_id,
        asset_bible.to_dict(),
    )
    return AssetBibleResponse(asset_bible=_asset_bible_response(saved, project_id=project_id))


def _get_asset_bible_repository(request: Request):
    repository = getattr(request.app.state, "asset_bible_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="asset bible repository is not configured",
        )
    return repository


def _request_to_model(payload: AssetBibleDraftRequest, *, project_id: str) -> AssetBible:
    try:
        return payload.to_model(project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _asset_bible_response(payload: Mapping[str, Any], *, project_id: str) -> dict[str, Any]:
    asset_bible = AssetBible.from_dict(payload)
    if asset_bible.project_id != project_id:
        raise HTTPException(status_code=502, detail="asset bible project does not match request")
    return asset_bible.to_dict()


def _validate_public_id(field_name: str, value: str) -> str:
    try:
        return validate_public_reference_id(field_name, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
