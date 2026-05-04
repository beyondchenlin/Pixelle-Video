from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from api.asset_bible_responses import (
    asset_bible_response_payload,
    build_asset_bible_response,
    safe_response_validation_detail,
)
from api.schemas.asset_bible import (
    AssetBibleDraftRequest,
    AssetBibleListResponse,
    AssetBibleResponse,
    PromptPlanApplyRequest,
    PromptPlanApplyResponse,
    PromptPlanProjectionPreviewRequest,
    PromptPlanProjectionPreviewResponse,
    SceneCastDraftRequest,
    SceneCastListResponse,
    SceneCastResponse,
)
from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.asset_bible_import_metadata import (
    mark_imported_asset_bible_customized,
)
from pixelle_video.services.asset_prompt_plan_apply import (
    AssetPromptPlanApplyService,
    PromptPlanApplyDependencyError,
    PromptPlanApplyNotFoundError,
    PromptPlanApplyRepositoryIdentityError,
    PromptPlanApplyValidationError,
)
from pixelle_video.services.asset_prompt_plan_composer import (
    AssetBibleNotFoundError,
    AssetPromptPlanComposerService,
    ProjectionDependencyError,
    PromptPlanNotFoundError,
    PromptPlanProjectionValidationError,
    RepositoryIdentityError,
    SceneCastNotFoundError,
)
from pixelle_video.services.scene_casting import (
    SceneCastValidationError,
    validate_scene_cast,
)
from pixelle_video.services.stale_write_integration import (
    StaleAwareAssetBibleWriteService,
    StaleAwarePromptPlanWriteService,
    StaleWriteDependencyNotFoundError,
    StaleWriteIntegrationError,
)

router = APIRouter(prefix="/projects", tags=["Asset Bible"])


@router.get(
    "/{project_id}/asset-bible",
    response_model=AssetBibleListResponse,
)
async def list_asset_bible_drafts(
    project_id: str,
    workspace_id: str,
    request: Request,
) -> AssetBibleListResponse:
    project_id = _validate_public_id("project_id", project_id)
    workspace_id = _validate_public_id("workspace_id", workspace_id)
    repository = _get_asset_bible_repository(request)
    loaded = await repository.list_asset_bibles(workspace_id, project_id)
    return _build_asset_bible_list_response(
        asset_bibles=[
            _asset_bible_response(item, project_id=project_id)
            for item in loaded
        ]
    )


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
    service = _build_stale_asset_write_service(request)
    if service is None:
        saved = await repository.save_asset_bible(
            payload.workspace_id,
            asset_bible.to_dict(),
        )
    else:
        try:
            result = await service.save_asset_bible(payload.workspace_id, asset_bible)
        except StaleWriteIntegrationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        saved = result.saved_payload
    return _build_asset_bible_response(
        asset_bible=_asset_bible_response(
            saved,
            project_id=project_id,
            asset_bible_id=payload.asset_bible_id,
        )
    )


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
    return _build_asset_bible_response(
        asset_bible=_asset_bible_response(
            loaded,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    )


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
    service = _build_stale_asset_write_service(request)
    existing = await repository.load_asset_bible(payload.workspace_id, asset_bible_id)
    asset_bible = _asset_bible_from_payload(
        mark_imported_asset_bible_customized(
            asset_bible.to_dict(),
            existing,
        )
    )
    if service is None:
        saved = await repository.save_asset_bible(
            payload.workspace_id,
            asset_bible.to_dict(),
        )
    else:
        try:
            result = await service.save_asset_bible(payload.workspace_id, asset_bible)
        except StaleWriteIntegrationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        saved = result.saved_payload
    return _build_asset_bible_response(
        asset_bible=_asset_bible_response(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
    )


@router.get(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts",
    response_model=SceneCastListResponse,
)
async def list_scene_cast_drafts(
    project_id: str,
    asset_bible_id: str,
    workspace_id: str,
    request: Request,
) -> SceneCastListResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    workspace_id = _validate_public_id("workspace_id", workspace_id)
    repository = _get_asset_bible_repository(request)
    asset_bible = await _load_asset_bible_for_scene_cast(
        repository,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
    )
    loaded = await repository.list_scene_casts(
        workspace_id,
        project_id,
        asset_bible_id,
    )
    return _build_scene_cast_list_response(
        scene_casts=[
            _scene_cast_response(
                item,
                project_id=project_id,
                asset_bible_id=asset_bible_id,
                asset_bible=asset_bible,
            )
            for item in loaded
        ]
    )


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
    service = _build_stale_asset_write_service(request)
    if service is None:
        saved = await repository.save_scene_cast(
            payload.workspace_id,
            scene_cast.to_dict(),
        )
    else:
        try:
            result = await service.save_scene_cast(payload.workspace_id, scene_cast)
        except StaleWriteDependencyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StaleWriteIntegrationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        saved = result.saved_payload
    return _build_scene_cast_response(
        scene_cast=_scene_cast_response(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            asset_bible=asset_bible,
            scene_cast_id=payload.scene_cast_id,
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
    return _build_scene_cast_response(
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
    service = _build_stale_asset_write_service(request)
    if service is None:
        saved = await repository.save_scene_cast(
            payload.workspace_id,
            scene_cast.to_dict(),
        )
    else:
        try:
            result = await service.save_scene_cast(payload.workspace_id, scene_cast)
        except StaleWriteDependencyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StaleWriteIntegrationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        saved = result.saved_payload
    return _build_scene_cast_response(
        scene_cast=_scene_cast_response(
            saved,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            asset_bible=asset_bible,
            scene_cast_id=scene_cast_id,
        )
    )


@router.post(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-projection",
    response_model=PromptPlanProjectionPreviewResponse,
)
async def preview_prompt_plan_projection(
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    payload: PromptPlanProjectionPreviewRequest,
    request: Request,
) -> PromptPlanProjectionPreviewResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_id("scene_cast_id", scene_cast_id)
    service = AssetPromptPlanComposerService(
        asset_bible_repository=_get_asset_bible_repository(request),
        prompt_plan_repository=_get_prompt_plan_repository(request),
    )
    try:
        preview = await service.preview_prompt_plan_projection(
            workspace_id=payload.workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=payload.storyboard_plan_id,
            frame_id=payload.frame_id,
        )
    except (AssetBibleNotFoundError, SceneCastNotFoundError, PromptPlanNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromptPlanProjectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryIdentityError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ProjectionDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return PromptPlanProjectionPreviewResponse(projection=preview.to_dict())
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_projection_response_validation_detail(exc),
        ) from exc


@router.post(
    "/{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-apply",
    response_model=PromptPlanApplyResponse,
)
async def apply_scene_cast_to_prompt_plan(
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    payload: PromptPlanApplyRequest,
    request: Request,
) -> PromptPlanApplyResponse:
    project_id = _validate_public_id("project_id", project_id)
    asset_bible_id = _validate_public_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_id("scene_cast_id", scene_cast_id)
    service = AssetPromptPlanApplyService(
        asset_bible_repository=_get_asset_bible_repository(request),
        prompt_plan_repository=_get_prompt_plan_repository(request),
        stale_prompt_plan_writer=_build_stale_prompt_plan_write_service(request),
    )
    try:
        application = await service.apply_scene_cast_to_prompt_plan_bundle(
            workspace_id=payload.workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=payload.storyboard_plan_id,
            frame_id=payload.frame_id,
            actor_id=payload.actor_id,
        )
    except PromptPlanApplyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PromptPlanApplyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PromptPlanApplyRepositoryIdentityError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PromptPlanApplyDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return PromptPlanApplyResponse(application=application.to_dict())
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(
                exc,
                response_name="prompt plan apply response",
                default_field_path="application",
            ),
        ) from exc


def _get_asset_bible_repository(request: Request):
    repository = getattr(request.app.state, "asset_bible_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="asset bible repository is not configured",
        )
    return repository


def _get_prompt_plan_repository(request: Request):
    repository = getattr(request.app.state, "prompt_plan_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail="prompt plan repository is not configured",
        )
    return repository


def _get_dependency_edge_repository(request: Request):
    return getattr(request.app.state, "dependency_edge_repository", None)


def _get_stale_mark_repository(request: Request):
    return getattr(request.app.state, "stale_mark_repository", None)


def _build_stale_asset_write_service(request: Request) -> StaleAwareAssetBibleWriteService | None:
    edge_repository = _get_dependency_edge_repository(request)
    stale_repository = _get_stale_mark_repository(request)
    if edge_repository is None and stale_repository is None:
        return None
    if edge_repository is None or stale_repository is None:
        raise HTTPException(
            status_code=503,
            detail="stale write repositories are not fully configured",
        )
    return StaleAwareAssetBibleWriteService(
        asset_bible_repository=_get_asset_bible_repository(request),
        edge_repository=edge_repository,
        stale_repository=stale_repository,
    )


def _build_stale_prompt_plan_write_service(request: Request) -> StaleAwarePromptPlanWriteService:
    edge_repository = _get_dependency_edge_repository(request)
    stale_repository = _get_stale_mark_repository(request)
    if edge_repository is None or stale_repository is None:
        raise HTTPException(
            status_code=503,
            detail="stale write repositories are not fully configured",
        )
    return StaleAwarePromptPlanWriteService(
        prompt_plan_repository=_get_prompt_plan_repository(request),
        asset_bible_repository=_get_asset_bible_repository(request),
        edge_repository=edge_repository,
        stale_repository=stale_repository,
    )


def _build_asset_bible_response(*, asset_bible: dict[str, Any]) -> AssetBibleResponse:
    return build_asset_bible_response(asset_bible=asset_bible)


def _build_asset_bible_list_response(
    *,
    asset_bibles: list[dict[str, Any]],
) -> AssetBibleListResponse:
    try:
        return AssetBibleListResponse(asset_bibles=asset_bibles)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(exc, response_name="asset bible list response"),
        ) from exc


def _build_scene_cast_response(*, scene_cast: dict[str, Any]) -> SceneCastResponse:
    try:
        return SceneCastResponse(scene_cast=scene_cast)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(exc, response_name="scene cast response"),
        ) from exc


def _build_scene_cast_list_response(
    *,
    scene_casts: list[dict[str, Any]],
) -> SceneCastListResponse:
    try:
        return SceneCastListResponse(scene_casts=scene_casts)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(exc, response_name="scene cast list response"),
        ) from exc


def _request_to_model(payload: AssetBibleDraftRequest, *, project_id: str) -> AssetBible:
    try:
        return payload.to_model(project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _asset_bible_from_payload(payload: Mapping[str, Any]) -> AssetBible:
    try:
        return AssetBible.from_dict(payload)
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


def _asset_bible_response(
    payload: Mapping[str, Any],
    *,
    project_id: str,
    asset_bible_id: str | None = None,
) -> dict[str, Any]:
    return asset_bible_response_payload(
        payload,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )


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


def _safe_projection_response_validation_detail(exc: ValidationError) -> str:
    return _safe_response_validation_detail(
        exc,
        response_name="prompt plan projection response",
        default_field_path="projection",
    )


def _safe_response_validation_detail(
    exc: ValidationError,
    *,
    response_name: str,
    default_field_path: str | None = None,
) -> str:
    return safe_response_validation_detail(
        exc,
        response_name=response_name,
        default_field_path=default_field_path,
    )


__all__ = ["router"]
