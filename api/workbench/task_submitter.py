from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from api.tasks.models import TaskType


@dataclass(frozen=True)
class StoryboardWorkbenchTaskSubmission:
    task_id: str
    task_type: str
    created: bool
    reused_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "created": self.created,
            "reused_reason": self.reused_reason,
        }


@dataclass(frozen=True)
class StoryboardWorkbenchCapabilities:
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_regenerate_frame_image": self.can_regenerate_frame_image,
            "regenerate_unavailable_reason": self.regenerate_unavailable_reason,
        }


@runtime_checkable
class StoryboardWorkbenchTaskSubmitter(Protocol):
    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities: ...

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission: ...


class TaskManagerStoryboardWorkbenchTaskSubmitter:
    def __init__(self, task_manager: Any) -> None:
        self.task_manager = task_manager

    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
        can_execute_task_type = getattr(self.task_manager, "can_execute_task_type", None)
        can_execute = (
            bool(await can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION))
            if can_execute_task_type is not None
            else False
        )
        if not can_execute:
            return StoryboardWorkbenchCapabilities(
                can_regenerate_frame_image=False,
                regenerate_unavailable_reason=(
                    "frame image regeneration execution is not configured"
                ),
            )
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=True,
            regenerate_unavailable_reason=None,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission:
        capabilities = await self.get_capabilities()
        if not capabilities.can_regenerate_frame_image:
            raise RuntimeError(
                capabilities.regenerate_unavailable_reason
                or "frame image regeneration execution is not configured"
            )
        outcome = await self.task_manager.reserve_or_reuse_generation_task(
            task_type=TaskType.FRAME_IMAGE_REGENERATION,
            generation_fingerprint=generation_fingerprint,
            request_params=dict(request_params),
        )
        return StoryboardWorkbenchTaskSubmission(
            task_id=outcome.task.task_id,
            task_type=outcome.task.task_type.value,
            created=outcome.created,
            reused_reason=outcome.reused_reason,
        )


class NoopStoryboardWorkbenchTaskSubmitter:
    def __init__(self, reason: str = "task submitter is not configured") -> None:
        self.reason = reason

    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=False,
            regenerate_unavailable_reason=self.reason,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission:
        raise RuntimeError(self.reason)


async def get_storyboard_workbench_capabilities(
    submitter: StoryboardWorkbenchTaskSubmitter | None,
) -> StoryboardWorkbenchCapabilities:
    if submitter is None:
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=False,
            regenerate_unavailable_reason="task submitter is not configured",
        )
    return await submitter.get_capabilities()


__all__ = [
    "NoopStoryboardWorkbenchTaskSubmitter",
    "StoryboardWorkbenchCapabilities",
    "StoryboardWorkbenchTaskSubmission",
    "StoryboardWorkbenchTaskSubmitter",
    "TaskManagerStoryboardWorkbenchTaskSubmitter",
    "get_storyboard_workbench_capabilities",
]
