"""Progress event bridge for registry-backed generation tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from api.tasks.models import TaskProgress
from api.tasks.store import LostTaskLeaseError
from pixelle_video.models.progress import ProgressEvent

PROGRESS_EVENT_FALLBACK_MESSAGES = {
    "synthesizing_audio": "Generating audio...",
    "preparing_render_manifest": "Preparing render manifest...",
    "rendering_hyperframes": "Rendering with HyperFrames...",
    "rendering_ffmpeg_manifest": "Rendering with FFmpeg...",
    "concatenating": "Concatenating video...",
    "completed": "Completed",
}


def progress_event_to_task_progress(event: ProgressEvent) -> TaskProgress:
    extra: dict[str, Any] = {}
    if event.frame_current is not None:
        extra["frame_current"] = event.frame_current
    if event.frame_total is not None:
        extra["frame_total"] = event.frame_total
    if event.step is not None:
        extra["step"] = event.step
    if event.action is not None:
        extra["action"] = event.action
    if event.extra_info is not None:
        extra["extra_info"] = str(event.extra_info)

    event_type = str(event.event_type)
    return TaskProgress(
        current=int(event.frame_current or 0),
        total=int(event.frame_total or 0),
        percentage=round(float(event.progress) * 100, 2),
        message=PROGRESS_EVENT_FALLBACK_MESSAGES.get(
            event_type,
            event_type.replace("_", " "),
        ),
        event_type=event_type,
        extra=extra,
    )


class TaskProgressSink:
    """Writes pipeline progress to the registry with the current execution lease."""

    def __init__(
        self,
        *,
        registry,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> None:
        self.registry = registry
        self.task_id = task_id
        self.owner_id = owner_id
        self.lease_token = lease_token
        self._tasks: set[asyncio.Task] = set()
        self._completed_tasks: list[asyncio.Task] = []

    def emit(self, event: ProgressEvent) -> None:
        task = asyncio.create_task(self._write(event))
        self._tasks.add(task)
        task.add_done_callback(self._track_completed)

    def _track_completed(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        self._completed_tasks.append(task)

    async def _write(self, event: ProgressEvent) -> None:
        try:
            await self.registry.update_progress(
                task_id=self.task_id,
                progress=progress_event_to_task_progress(event),
                owner_id=self.owner_id,
                lease_token=self.lease_token,
            )
        except LostTaskLeaseError:
            logger.warning(f"Task {self.task_id} lease was lost before progress could be recorded")

    async def drain(self) -> None:
        if not self._tasks and not self._completed_tasks:
            return
        tasks = [*self._completed_tasks, *self._tasks]
        self._completed_tasks.clear()
        await asyncio.gather(*tasks)
