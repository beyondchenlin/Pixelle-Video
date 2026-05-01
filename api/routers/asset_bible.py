from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.asset_bible import (
    AssetBibleDraftRequest,
    AssetBibleResponse,
    SceneCastDraftRequest,
    SceneCastResponse,
)
from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.scene_casting import (
    SceneCastValidationError,
    validate_scene_cast,
)

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


@router.post(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts",
    response_model=SceneCastResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scene_cast_draft(
    project_id: str,
    asset_bible_id: str,
    payload: SceneCastDraftRequest,
    request: Request,
) -> SceneCastResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    repository = _get_asset_bible_repository(request)
    asset_bible = await _load_asset_bible_for_scene_cast(
        repository,
        workspace_id=payload.workspace_id,
        asset_bible_id=asset_bible_id,
    )
    scene_cast = _request_to_scene_cast_model(
        payload,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    _validate_scene_cast_for_api(scene_cast, asset_bible)
    saved = await repository.save_scene_cast(
        payload.workspace_id,
        scene_cast.to_dict(),
    )
    return SceneCastResponse(
        scene_cast=_scene_cast_response(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            asset_bible=asset_bible,
        )
    )


@router.get(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}",
    response_model=SceneCastResponse,
)
async def load_scene_cast_draft(
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    workspace_id: str,
    request: Request,
) -> SceneCastResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_id("scene_cast_id", scene_cast_id)
    workspace_id = _validate_public_id("workspace_id", workspace_id)
    repository = _get_asset_bible_repository(request)
    asset_bible = await _load_asset_bible_for_scene_cast(
        repository,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
    )
    loaded = await repository.load_scene_cast(workspace_id, scene_cast_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="scene cast draft was not found")
    return SceneCastResponse(
        scene_cast=_scene_cast_response(
            loaded,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            asset_bible=asset_bible,
            scene_cast_id=scene_cast_id,
        )
    )


@router.put(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}",
    response_model=SceneCastResponse,
)
async def update_scene_cast_draft(
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    payload: SceneCastDraftRequest,
    request: Request,
) -> SceneCastResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_id("scene_cast_id", scene_cast_id)
    if payload.scene_cast_id != scene_cast_id:
        raise HTTPException(
            status_code=422,
            detail="payload scene_cast_id must match route scene_cast_id",
        )
    repository = _get_asset_bible_repository(request)
    asset_bible = await _load_asset_bible_for_scene_cast(
        repository,
        workspace_id=payload.workspace_id,
        asset_bible_id=asset_bible_id,
    )
    scene_cast = _request_to_scene_cast_model(
        payload,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    _validate_scene_cast_for_api(scene_cast, asset_bible)
    saved = await repository.save_scene_cast(
        payload.workspace_id,
        scene_cast.to_dict(),
    )
    return SceneCastResponse(
        scene_cast=_scene_cast_response(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            asset_bible=asset_bible,
            scene_cast_id=scene_cast_id,
        )
    )


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


def _request_to_scene_cast_model(
    payload: SceneCastDraftRequest,
    *,
    project_id: str,
    asset_bible_id: str,
) -> SceneCast:
    try:
        return payload.to_model(
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _load_asset_bible_for_scene_cast(
    repository,
    *,
    workspace_id: str,
    asset_bible_id: str,
) -> AssetBible:
    loaded = await repository.load_asset_bible(workspace_id, asset_bible_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="asset bible draft was not found")
    try:
        return AssetBible.from_dict(loaded)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _validate_scene_cast_for_api(scene_cast: SceneCast, asset_bible: AssetBible) -> None:
    try:
        validate_scene_cast(scene_cast, asset_bible)
    except SceneCastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _asset_bible_response(payload: Mapping[str, Any], *, project_id: str) -> dict[str, Any]:
    asset_bible = AssetBible.from_dict(payload)
    if asset_bible.project_id != project_id:
        raise HTTPException(status_code=502, detail="asset bible project does not match request")
    return asset_bible.to_dict()


def _scene_cast_response(
    payload: Mapping[str, Any],
    *,
    project_id: str,
    asset_bible_id: str,
    asset_bible: AssetBible | None = None,
    scene_cast_id: str | None = None,
) -> dict[str, Any]:
    scene_cast = SceneCast.from_dict(payload)
    if scene_cast.project_id != project_id:
        raise HTTPException(status_code=502, detail="scene cast project does not match request")
    if scene_cast.asset_bible_id != asset_bible_id:
        raise HTTPException(status_code=502, detail="scene cast asset bible does not match request")
    if scene_cast_id is not None and scene_cast.scene_cast_id != scene_cast_id:
        raise HTTPException(status_code=502, detail="scene cast ID does not match request")
    if asset_bible is not None:
        _validate_scene_cast_for_api(scene_cast, asset_bible)
    return scene_cast.to_dict()


def _validate_public_id(field_name: str, value: str) -> str:
    try:
        return validate_public_reference_id(field_name, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
