from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from api.schemas.stale_dependencies import (
    TargetStaleSummaryApiResponse,
    UpstreamDownstreamApiResponse,
)
from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.services.stale_dependency_read_model import (
    StaleDependencyReadRepositoryNotConfiguredError,
    StaleDependencyReadService,
)

router = APIRouter(prefix="/projects", tags=["Stale Dependencies"])


@router.get(
    "/{project_id}/stale/targets/{target_type}/{target_id}",
    response_model=TargetStaleSummaryApiResponse,
)
async def get_target_stale_summary(
    project_id: str,
    target_type: str,
    target_id: str,
    workspace_id: str,
    request: Request,
) -> TargetStaleSummaryApiResponse:
    _validate_public_ids(
        project_id=project_id,
        workspace_id=workspace_id,
        target_type=target_type,
        target_id=target_id,
    )
    service = _build_read_service(request)
    try:
        summary = await service.get_target_summary(
            workspace_id=workspace_id,
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
        )
    except StaleDependencyReadRepositoryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _target_response(summary.to_dict())


@router.get(
    "/{project_id}/stale/upstream/{upstream_type}/{upstream_id}/downstream",
    response_model=UpstreamDownstreamApiResponse,
)
async def get_upstream_downstream_summary(
    project_id: str,
    upstream_type: str,
    upstream_id: str,
    workspace_id: str,
    request: Request,
) -> UpstreamDownstreamApiResponse:
    _validate_public_ids(
        project_id=project_id,
        workspace_id=workspace_id,
        upstream_type=upstream_type,
        upstream_id=upstream_id,
    )
    service = _build_read_service(request)
    try:
        summary = await service.get_downstream_summary(
            workspace_id=workspace_id,
            project_id=project_id,
            upstream_type=upstream_type,
            upstream_id=upstream_id,
        )
    except StaleDependencyReadRepositoryNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _downstream_response(summary.to_dict())


def _build_read_service(request: Request) -> StaleDependencyReadService:
    return StaleDependencyReadService(
        edge_repository=getattr(request.app.state, "dependency_edge_repository", None),
        stale_repository=getattr(request.app.state, "stale_mark_repository", None),
    )


def _target_response(summary: dict[str, object]) -> TargetStaleSummaryApiResponse:
    try:
        return TargetStaleSummaryApiResponse(stale_summary=summary)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(exc, response_name="stale target summary"),
        ) from exc


def _downstream_response(summary: dict[str, object]) -> UpstreamDownstreamApiResponse:
    try:
        return UpstreamDownstreamApiResponse(downstream=summary)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=_safe_response_validation_detail(exc, response_name="stale downstream summary"),
        ) from exc


def _validate_public_ids(**values: str) -> None:
    for field_name, value in values.items():
        try:
            validate_public_reference_id(field_name, value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _safe_response_validation_detail(exc: ValidationError, *, response_name: str) -> str:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = first_error.get("loc") or ()
    field_path = ".".join(str(item) for item in location) or "response"
    return f"{response_name} is invalid: {field_path}"


__all__ = ["router"]
