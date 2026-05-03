from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from api.tasks.executors import TaskExecutorRegistry
from api.tasks.models import TaskType
from api.workbench.frame_image_regeneration import execute_frame_image_regeneration


def register_storyboard_workbench_executors(
    registry: TaskExecutorRegistry,
    *,
    core_provider: Callable[[], Any | Awaitable[Any]],
) -> TaskExecutorRegistry:
    async def _execute_frame_image_regeneration_task(
        *,
        task_id: str,
        request_params: dict[str, Any],
        progress_dispatcher=None,
    ) -> dict[str, Any]:
        core = core_provider()
        if hasattr(core, "__await__"):
            core = await core
        return await execute_frame_image_regeneration(
            core=core,
            task_id=task_id,
            request_params=request_params,
            progress_dispatcher=progress_dispatcher,
        )

    registry.register(
        TaskType.FRAME_IMAGE_REGENERATION,
        _execute_frame_image_regeneration_task,
    )
    return registry


__all__ = ["register_storyboard_workbench_executors"]
