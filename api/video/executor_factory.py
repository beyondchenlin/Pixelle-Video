from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from loguru import logger

from api.tasks.artifacts import ArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.models import TaskType

REGISTRY_CONTROL_PARAM_NAMES = {"generation_fingerprint"}


def register_video_generation_executor(
    registry: TaskExecutorRegistry,
    *,
    core_provider: Callable[[], Any | Awaitable[Any]],
    artifact_store: ArtifactStore,
    core_releaser: Callable[[Any], None | Awaitable[None]] | None = None,
) -> TaskExecutorRegistry:
    async def _execute_video_generation_task(
        *,
        task_id: str,
        request_params: dict[str, Any],
        progress_dispatcher=None,
    ) -> dict[str, Any]:
        core = core_provider()
        if hasattr(core, "__await__"):
            core = await core
        task_failed = False
        try:
            params = dict(request_params)
            for name in REGISTRY_CONTROL_PARAM_NAMES:
                params.pop(name, None)
            params["api_task_id"] = task_id
            if progress_dispatcher is not None:
                params["progress_dispatcher"] = progress_dispatcher
            output_root = getattr(artifact_store, "output_root", None)
            if output_root is not None:
                params.setdefault("output_path", str(Path(output_root) / task_id / "final.mp4"))

            result = await core.generate_video(**params)
            persisted = await artifact_store.persist_video(
                task_id=task_id,
                source_path=Path(result.video_path),
                duration=float(getattr(result, "duration", 0.0) or 0.0),
            )
            storyboard = getattr(result, "storyboard", None)
            config = getattr(storyboard, "config", None)
            created_at = getattr(result, "created_at", None)
            persisted.update(
                {
                    "title": getattr(storyboard, "title", None),
                    "frame_count": len(getattr(storyboard, "frames", []) or []),
                    "canvas_width": getattr(config, "canvas_width", None),
                    "canvas_height": getattr(config, "canvas_height", None),
                    "frame_template": getattr(config, "frame_template", None),
                    "cover_path": getattr(result, "cover_path", None),
                    "created_at": (
                        created_at.isoformat()
                        if hasattr(created_at, "isoformat")
                        else str(created_at or "")
                    ),
                }
            )
            return persisted
        except BaseException:
            task_failed = True
            raise
        finally:
            if core_releaser is not None:
                try:
                    released = core_releaser(core)
                    if hasattr(released, "__await__"):
                        await released
                except BaseException:
                    if not task_failed:
                        raise
                    logger.exception("Video task core cleanup failed after task failure")

    registry.register(TaskType.VIDEO_GENERATION, _execute_video_generation_task)
    return registry


__all__ = ["register_video_generation_executor"]
