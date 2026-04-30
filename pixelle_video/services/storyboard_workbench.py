from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from os import PathLike
from typing import Any
from uuid import uuid4

from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.generation_event import GenerationEvent, GenerationEventAction
from pixelle_video.models.storyboard_workbench import (
    StoryboardFrameWorkbenchState,
    mark_frame_stale_after_prompt_plan_change,
    mark_frame_stale_after_selected_image_change,
)
from pixelle_video.repositories.artifacts import ArtifactObjectStore, ArtifactRepository
from pixelle_video.repositories.prompt_plans import PromptPlanRepository
from pixelle_video.repositories.trace import TraceRepository
from pixelle_video.services.generation_coordinator import build_generation_fingerprint


class StoryboardWorkbenchError(ValueError):
    """Base error for storyboard workbench service contract violations."""


class ArtifactVersionNotFoundError(StoryboardWorkbenchError):
    """Raised when a requested image version is not a candidate of the artifact."""


class FrameImageLockedError(StoryboardWorkbenchError):
    """Raised when a locked frame image would be replaced without an explicit override."""


class UnsafeArtifactUrlError(StoryboardWorkbenchError):
    """Raised when an object-store adapter returns a local path-like URL."""


@dataclass(frozen=True)
class FrameImageRegenerationTaskRequest:
    generation_fingerprint: str
    request_params: Mapping[str, Any]


@dataclass(frozen=True)
class FrameImageRegenerationResult:
    workbench_state: StoryboardFrameWorkbenchState
    artifact_version: ArtifactVersion


@dataclass(frozen=True)
class StoryboardImageCandidate:
    artifact_id: str
    version_id: str
    frame_id: str
    prompt_plan_id: str
    storage_key: str
    status: str
    provider: str | None = None
    url: str | None = None
    width: int | None = None
    height: int | None = None
    trace_event_id: str | None = None
    created_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_artifact_version(
        cls,
        version: ArtifactVersion,
        *,
        url: str | None,
    ) -> "StoryboardImageCandidate":
        return cls(
            artifact_id=version.artifact_id,
            version_id=version.version_id,
            frame_id=version.frame_id,
            prompt_plan_id=version.source_prompt_plan_id,
            storage_key=version.storage_key,
            status=version.status.value,
            provider=version.provider,
            url=url,
            width=version.width,
            height=version.height,
            trace_event_id=version.trace_event_id,
            created_at=version.created_at,
            metadata=version.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "version_id": self.version_id,
            "frame_id": self.frame_id,
            "prompt_plan_id": self.prompt_plan_id,
            "storage_key": self.storage_key,
            "status": self.status,
            "provider": self.provider,
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "trace_event_id": self.trace_event_id,
            "created_at": self.created_at,
            "metadata": _json_safe_copy(self.metadata),
        }


class StoryboardWorkbenchService:
    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        object_store: ArtifactObjectStore,
        trace_repository: TraceRepository,
        prompt_plan_repository: PromptPlanRepository,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.object_store = object_store
        self.trace_repository = trace_repository
        self.prompt_plan_repository = prompt_plan_repository

    def build_frame_image_regeneration_task_request(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> FrameImageRegenerationTaskRequest:
        self._ensure_state_matches_artifact(state, artifact_id)
        prompt_plan_id = _require_state_prompt_plan_id(state)
        request_params = _drop_none_values(
            {
                "workspace_id": workspace_id,
                "storyboard_id": storyboard_id,
                "frame_id": state.frame_id,
                "prompt_plan_id": prompt_plan_id,
                "artifact_id": artifact_id,
                "selected_image_version_id": state.selected_image_version_id,
                "provider": provider,
                "model": model,
            }
        )
        generation_fingerprint = build_generation_fingerprint(
            text=f"{workspace_id}:{storyboard_id}:{state.frame_id}:{prompt_plan_id}:{artifact_id}",
            pipeline="storyboard_frame_image_regeneration",
            params=request_params,
        )
        return FrameImageRegenerationTaskRequest(
            generation_fingerprint=generation_fingerprint,
            request_params={
                **request_params,
                "generation_fingerprint": generation_fingerprint,
            },
        )

    async def list_image_candidates(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
    ) -> tuple[StoryboardImageCandidate, ...]:
        versions = await self._load_artifact_versions(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )
        candidates: list[StoryboardImageCandidate] = []
        for version in versions:
            url = await self.object_store.get_file_url(version.storage_key)
            candidates.append(
                StoryboardImageCandidate.from_artifact_version(
                    version,
                    url=_validate_access_url(url),
                )
            )
        return tuple(candidates)

    async def add_image_candidate_version(
        self,
        *,
        workspace_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        version_id: str,
        auto_select: bool = False,
    ) -> StoryboardFrameWorkbenchState:
        self._ensure_state_matches_artifact(state, artifact_id)
        await self._require_artifact_version(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            version_id=version_id,
        )
        candidate_state = replace(
            state,
            selected_image_artifact_id=state.selected_image_artifact_id or artifact_id,
            candidate_image_version_ids=_append_unique(
                state.candidate_image_version_ids,
                version_id,
            ),
        )
        if auto_select and candidate_state.can_auto_replace_selected_image:
            return await self.select_image_version(
                workspace_id=workspace_id,
                state=candidate_state,
                artifact_id=artifact_id,
                version_id=version_id,
                actor_id=None,
            )
        return candidate_state

    async def select_image_version(
        self,
        *,
        workspace_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
        allow_locked: bool = False,
    ) -> StoryboardFrameWorkbenchState:
        self._ensure_state_matches_artifact(state, artifact_id)
        if state.is_image_artifact_locked and not allow_locked:
            raise FrameImageLockedError("frame image artifact is locked")

        version = await self._require_artifact_version(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            version_id=version_id,
        )
        await self.artifact_repository.select_artifact_version(
            workspace_id,
            artifact_id,
            version_id,
        )

        selected_state = replace(
            state,
            selected_image_artifact_id=artifact_id,
            selected_image_version_id=version_id,
            candidate_image_version_ids=_append_unique(
                state.candidate_image_version_ids,
                version_id,
            ),
        )
        selected_state = mark_frame_stale_after_selected_image_change(selected_state)
        await self._append_generation_event(
            workspace_id=workspace_id,
            action=GenerationEventAction.SELECT,
            state=selected_state,
            artifact_id=artifact_id,
            artifact_version_id=version_id,
            storage_key=version.storage_key,
            metadata={"actor_id": actor_id} if actor_id else {},
        )
        return selected_state

    async def mark_prompt_plan_change_stale(
        self,
        *,
        workspace_id: str,
        state: StoryboardFrameWorkbenchState,
        reason: str,
    ) -> StoryboardFrameWorkbenchState:
        prompt_plan_id = _require_state_prompt_plan_id(state)
        artifact_id = _require_state_image_artifact_id(state)
        await self.prompt_plan_repository.mark_prompt_plan_stale(
            workspace_id,
            prompt_plan_id,
            {
                "frame_id": state.frame_id,
                "reason": reason,
            },
        )
        stale_state = mark_frame_stale_after_prompt_plan_change(state)
        await self._append_generation_event(
            workspace_id=workspace_id,
            action=GenerationEventAction.STALE_MARK,
            state=stale_state,
            artifact_id=artifact_id,
            artifact_version_id=stale_state.selected_image_version_id,
            stale_reason=reason,
            metadata={
                "stale_flags": [flag.value for flag in stale_state.stale_flags],
            },
        )
        return stale_state

    async def record_frame_image_regeneration_result(
        self,
        *,
        workspace_id: str,
        task_id: str,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        source_path: str | PathLike[str],
        provider: str | None = None,
        provider_metadata: Mapping[str, Any] | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> FrameImageRegenerationResult:
        self._ensure_state_matches_artifact(state, artifact_id)
        prompt_plan_id = _require_state_prompt_plan_id(state)
        stored_file = await self.object_store.put_file(
            workspace_id,
            source_path,
            metadata={
                "artifact_id": artifact_id,
                "frame_id": state.frame_id,
                "prompt_plan_id": prompt_plan_id,
                "task_id": task_id,
            },
        )
        event_id = f"generation_event_{uuid4().hex}"
        artifact_version = ArtifactVersion(
            version_id=f"artifact_version_{uuid4().hex}",
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            frame_id=state.frame_id,
            source_prompt_plan_id=prompt_plan_id,
            storage_key=stored_file.storage_key,
            status=ArtifactVersionStatus.CANDIDATE,
            provider=provider,
            provider_metadata=provider_metadata or {},
            width=width,
            height=height,
            trace_event_id=event_id,
            metadata={"source_task_id": task_id},
        )
        stored_version = await self.artifact_repository.create_artifact_version(
            workspace_id,
            artifact_id,
            artifact_version.to_dict(),
        )
        artifact_version = ArtifactVersion.from_dict(stored_version)
        updated_state = replace(
            state,
            selected_image_artifact_id=artifact_id,
            candidate_image_version_ids=_append_unique(
                state.candidate_image_version_ids,
                artifact_version.version_id,
            ),
            last_generation_job_id=task_id,
        )
        await self._append_generation_event(
            workspace_id=workspace_id,
            event_id=event_id,
            action=GenerationEventAction.REGENERATE,
            state=updated_state,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version.version_id,
            storage_key=artifact_version.storage_key,
            task_id=task_id,
            metadata={
                "provider": provider,
                "provider_metadata": _json_safe_copy(provider_metadata or {}),
                "candidate_image_version_ids": list(updated_state.candidate_image_version_ids),
            },
        )
        return FrameImageRegenerationResult(
            workbench_state=updated_state,
            artifact_version=artifact_version,
        )

    async def _load_artifact_versions(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
    ) -> tuple[ArtifactVersion, ...]:
        payloads = await self.artifact_repository.list_artifact_versions(
            workspace_id,
            artifact_id,
        )
        versions = tuple(ArtifactVersion.from_dict(payload) for payload in payloads)
        for version in versions:
            if version.workspace_id != workspace_id or version.artifact_id != artifact_id:
                raise ValueError("artifact version does not match requested artifact")
        return versions

    async def _require_artifact_version(
        self,
        *,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> ArtifactVersion:
        versions = await self._load_artifact_versions(
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )
        for version in versions:
            if version.version_id == version_id:
                return version
        raise ArtifactVersionNotFoundError("artifact version not found")

    async def _append_generation_event(
        self,
        *,
        workspace_id: str,
        event_id: str | None = None,
        action: GenerationEventAction,
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
        artifact_version_id: str | None = None,
        storage_key: str | None = None,
        task_id: str | None = None,
        stale_reason: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        event = GenerationEvent(
            event_id=event_id or f"generation_event_{uuid4().hex}",
            workspace_id=workspace_id,
            action=action,
            frame_id=state.frame_id,
            prompt_plan_id=_require_state_prompt_plan_id(state),
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            storage_key=storage_key,
            task_id=task_id,
            stale_reason=stale_reason,
            metadata=metadata or {},
        )
        await self.trace_repository.append_generation_event(
            workspace_id,
            event.to_dict(),
        )

    @staticmethod
    def _ensure_state_matches_artifact(
        state: StoryboardFrameWorkbenchState,
        artifact_id: str,
    ) -> None:
        if state.selected_image_artifact_id and state.selected_image_artifact_id != artifact_id:
            raise ValueError("state selected_image_artifact_id does not match artifact_id")


def _require_state_prompt_plan_id(state: StoryboardFrameWorkbenchState) -> str:
    if not state.prompt_plan_id:
        raise ValueError("workbench state must include prompt_plan_id")
    return state.prompt_plan_id


def _require_state_image_artifact_id(state: StoryboardFrameWorkbenchState) -> str:
    if not state.selected_image_artifact_id:
        raise ValueError("workbench state must include selected_image_artifact_id")
    return state.selected_image_artifact_id


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)


def _drop_none_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in values.items()
        if value is not None
    }


def _validate_access_url(url: str | None) -> str | None:
    if url is None:
        return None
    normalized = str(url).strip()
    if (
        normalized.lower().startswith("file:")
        or "\\" in normalized
        or normalized.startswith("/")
        or normalized.startswith("~")
        or normalized.startswith("../")
        or "/../" in normalized
        or _looks_like_windows_path(normalized)
    ):
        raise UnsafeArtifactUrlError("object-store URL must not be a local path")
    return normalized


def _looks_like_windows_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return value


__all__ = [
    "ArtifactVersionNotFoundError",
    "FrameImageLockedError",
    "FrameImageRegenerationResult",
    "FrameImageRegenerationTaskRequest",
    "StoryboardImageCandidate",
    "StoryboardWorkbenchError",
    "StoryboardWorkbenchService",
    "UnsafeArtifactUrlError",
]
