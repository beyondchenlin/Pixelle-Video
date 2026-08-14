from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from api.tasks.models import TaskProgress, TaskStatus, TaskType


@dataclass(frozen=True)
class VideoGenerationTaskSubmission:
    task_id: str
    created: bool
    reused_reason: str | None = None


@dataclass(frozen=True)
class VideoGenerationTaskSnapshot:
    task_id: str
    status: TaskStatus
    progress: TaskProgress | None
    result: dict[str, Any] | None
    video_path: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


@runtime_checkable
class VideoGenerationTaskSubmitter(Protocol):
    async def reserve_video_generation(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> VideoGenerationTaskSubmission: ...

    async def get_video_generation_task(
        self,
        task_id: str,
    ) -> VideoGenerationTaskSnapshot | None: ...

    async def cancel_video_generation(self, task_id: str) -> bool: ...


class TaskManagerVideoGenerationTaskSubmitter:
    """Narrow video-task facade that never exposes stored request parameters."""

    def __init__(self, task_manager: Any) -> None:
        self.task_manager = task_manager

    async def reserve_video_generation(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> VideoGenerationTaskSubmission:
        if not await self.task_manager.can_execute_task_type(TaskType.VIDEO_GENERATION):
            raise RuntimeError("video generation execution is not configured")
        outcome = await self.task_manager.reserve_or_reuse_generation_task(
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint=generation_fingerprint,
            request_params=dict(request_params),
        )
        return VideoGenerationTaskSubmission(
            task_id=outcome.task.task_id,
            created=outcome.created,
            reused_reason=outcome.reused_reason,
        )

    async def get_video_generation_task(
        self,
        task_id: str,
    ) -> VideoGenerationTaskSnapshot | None:
        task = await self.task_manager.get_task(task_id)
        if task is None or task.task_type != TaskType.VIDEO_GENERATION:
            return None
        result = deepcopy(task.result) if isinstance(task.result, dict) else None
        video_path = None
        storage_key = result.get("storage_key") if result else None
        artifact_store = getattr(self.task_manager.registry, "artifact_store", None)
        resolve_local_path = getattr(artifact_store, "resolve_local_path", None)
        if resolve_local_path is not None:
            resolved = resolve_local_path(storage_key)
            video_path = str(resolved) if resolved is not None else None
        return VideoGenerationTaskSnapshot(
            task_id=task.task_id,
            status=task.status,
            progress=task.progress,
            result=result,
            video_path=video_path,
            created_at=task.created_at.isoformat(),
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
        )

    async def cancel_video_generation(self, task_id: str) -> bool:
        return await self.task_manager.cancel_task(task_id)


__all__ = [
    "TaskManagerVideoGenerationTaskSubmitter",
    "VideoGenerationTaskSnapshot",
    "VideoGenerationTaskSubmission",
    "VideoGenerationTaskSubmitter",
]
