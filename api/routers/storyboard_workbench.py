from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas.storyboard_workbench import (
    RegenerateStoryboardFrameImageRequest,
    RegenerateStoryboardFrameImageResponse,
    SelectStoryboardImageRequest,
    SelectStoryboardImageResponse,
    StoryboardFrameWorkbenchStateResponse,
    StoryboardImageCandidateListResponse,
    StoryboardImageCandidateResponse,
    validate_public_reference_id,
)
from api.tasks.models import TaskType
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.services.storyboard_workbench import (
    ArtifactVersionNotFoundError,
    FrameImageLockedError,
    StoryboardImageCandidate,
    StoryboardWorkbenchError,
    UnsafeArtifactUrlError,
)

router = APIRouter(prefix="/storyboards", tags=["Storyboard Workbench"])


@router.get(
    "/{storyboard_id}/frames/{frame_id}/images",
    response_model=StoryboardImageCandidateListResponse,
)
async def list_frame_image_candidates(
    storyboard_id: str,
    frame_id: str,
    workspace_id: str,
    artifact_id: str,
    request: Request,
) -> StoryboardImageCandidateListResponse:
    _validate_public_ids(
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        artifact_id=artifact_id,
    )
    service = _get_storyboard_workbench_service(request)
    try:
        candidates = await service.list_image_candidates(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )
    except UnsafeArtifactUrlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return StoryboardImageCandidateListResponse(
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        artifact_id=artifact_id,
        candidates=[
            _candidate_response(candidate, expected_frame_id=frame_id)
            for candidate in candidates
        ],
    )


@router.post(
    "/{storyboard_id}/frames/{frame_id}/select-image",
    response_model=SelectStoryboardImageResponse,
)
async def select_frame_image_version(
    storyboard_id: str,
    frame_id: str,
    payload: SelectStoryboardImageRequest,
    request: Request,
) -> SelectStoryboardImageResponse:
    _validate_public_ids(
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )
    service = _get_storyboard_workbench_service(request)
    state_store = _get_storyboard_workbench_state_store(request)
    state = await _load_frame_state(
        state_store,
        workspace_id=payload.workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )

    try:
        updated_state = await service.select_image_version(
            workspace_id=payload.workspace_id,
            state=state,
            artifact_id=payload.artifact_id,
            version_id=payload.version_id,
            actor_id=payload.actor_id,
            allow_locked=payload.allow_locked,
        )
    except FrameImageLockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArtifactVersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StoryboardWorkbenchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _save_frame_state(
        state_store,
        workspace_id=payload.workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        state=updated_state,
    )
    return SelectStoryboardImageResponse(
        workspace_id=payload.workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        state=_state_response(updated_state),
    )


@router.post(
    "/{storyboard_id}/frames/{frame_id}/regenerate-image",
    response_model=RegenerateStoryboardFrameImageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_frame_image_regeneration(
    storyboard_id: str,
    frame_id: str,
    payload: RegenerateStoryboardFrameImageRequest,
    request: Request,
) -> RegenerateStoryboardFrameImageResponse:
    _validate_public_ids(
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )
    service = _get_storyboard_workbench_service(request)
    state_store = _get_storyboard_workbench_state_store(request)
    task_manager = _get_task_manager(request)
    state = await _load_frame_state(
        state_store,
        workspace_id=payload.workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
    )

    try:
        task_request = service.build_frame_image_regeneration_task_request(
            workspace_id=payload.workspace_id,
            storyboard_id=storyboard_id,
            state=state,
            artifact_id=payload.artifact_id,
            provider=payload.provider,
            model=payload.model,
        )
    except StoryboardWorkbenchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outcome = await task_manager.reserve_or_reuse_generation_task(
        task_type=TaskType.FRAME_IMAGE_REGENERATION,
        generation_fingerprint=task_request.generation_fingerprint,
        request_params=dict(task_request.request_params),
    )
    return RegenerateStoryboardFrameImageResponse(
        workspace_id=payload.workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        artifact_id=payload.artifact_id,
        task_id=outcome.task.task_id,
        task_type=outcome.task.task_type.value,
        created=outcome.created,
        reused_reason=outcome.reused_reason,
        generation_fingerprint=task_request.generation_fingerprint,
    )


def _get_storyboard_workbench_service(request: Request):
    service = getattr(request.app.state, "storyboard_workbench_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="storyboard workbench service is not configured",
        )
    return service


def _get_storyboard_workbench_state_store(request: Request):
    state_store = getattr(request.app.state, "storyboard_workbench_state_store", None)
    if state_store is None:
        raise HTTPException(
            status_code=503,
            detail="storyboard workbench state store is not configured",
        )
    return state_store


def _get_task_manager(request: Request):
    task_manager = getattr(request.app.state, "task_manager", None)
    if task_manager is None:
        raise HTTPException(status_code=503, detail="task manager is not configured")
    return task_manager


async def _load_frame_state(
    state_store,
    *,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
) -> StoryboardFrameWorkbenchState:
    payload = await state_store.load_frame_state(workspace_id, storyboard_id, frame_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="storyboard frame workbench state was not found")
    state = (
        payload
        if isinstance(payload, StoryboardFrameWorkbenchState)
        else StoryboardFrameWorkbenchState.from_dict(payload)
    )
    if state.frame_id != frame_id:
        raise HTTPException(status_code=502, detail="workbench state does not match requested frame")
    return state


async def _save_frame_state(
    state_store,
    *,
    workspace_id: str,
    storyboard_id: str,
    frame_id: str,
    state: StoryboardFrameWorkbenchState,
) -> None:
    await state_store.save_frame_state(
        workspace_id,
        storyboard_id,
        frame_id,
        state.to_dict(),
    )


def _candidate_response(
    candidate: StoryboardImageCandidate | Mapping[str, Any],
    *,
    expected_frame_id: str,
) -> StoryboardImageCandidateResponse:
    payload = candidate.to_dict() if isinstance(candidate, StoryboardImageCandidate) else dict(candidate)
    if payload.get("frame_id") != expected_frame_id:
        raise HTTPException(status_code=502, detail="candidate image does not match requested frame")
    return StoryboardImageCandidateResponse(**payload)


def _state_response(state: StoryboardFrameWorkbenchState) -> StoryboardFrameWorkbenchStateResponse:
    return StoryboardFrameWorkbenchStateResponse(**state.to_dict())


def _validate_public_ids(**values: str) -> None:
    for field_name, value in values.items():
        try:
            validate_public_reference_id(field_name, value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
