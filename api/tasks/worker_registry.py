from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from api.tasks.models import TaskType, utc_now


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    supported_task_types: set[TaskType]
    heartbeat_at: datetime


@runtime_checkable
class WorkerRegistry(Protocol):
    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None: ...

    async def supports(
        self,
        task_type: TaskType,
        *,
        now: datetime | None = None,
    ) -> bool: ...


class InMemoryWorkerRegistry:
    def __init__(self, heartbeat_ttl_seconds: int = 60) -> None:
        self.heartbeat_ttl = timedelta(seconds=heartbeat_ttl_seconds)
        self._heartbeats: dict[str, WorkerHeartbeat] = {}
        self._lock = asyncio.Lock()

    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        async with self._lock:
            self._heartbeats[heartbeat.worker_id] = heartbeat

    async def supports(
        self,
        task_type: TaskType,
        *,
        now: datetime | None = None,
    ) -> bool:
        cutoff = (now or utc_now()) - self.heartbeat_ttl
        async with self._lock:
            return any(
                heartbeat.heartbeat_at >= cutoff
                and task_type in heartbeat.supported_task_types
                for heartbeat in self._heartbeats.values()
            )


__all__ = [
    "InMemoryWorkerRegistry",
    "WorkerHeartbeat",
    "WorkerRegistry",
]
