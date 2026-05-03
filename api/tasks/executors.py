from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from api.tasks.models import TaskType


@runtime_checkable
class TaskExecutor(Protocol):
    async def __call__(
        self,
        *,
        task_id: str,
        request_params: Mapping[str, Any],
        progress_dispatcher: Any | None = None,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class TaskExecutionCapability:
    can_execute: bool
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_execute": self.can_execute,
            "unavailable_reason": self.unavailable_reason,
        }


class TaskExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[TaskType, TaskExecutor] = {}

    def register(self, task_type: TaskType, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def supported_task_types(self) -> set[TaskType]:
        return set(self._executors)

    def can_execute(self, task_type: TaskType) -> TaskExecutionCapability:
        if task_type in self._executors:
            return TaskExecutionCapability(can_execute=True)
        return TaskExecutionCapability(
            can_execute=False,
            unavailable_reason="task executor is not registered",
        )

    async def execute(
        self,
        task_type: TaskType,
        *,
        task_id: str,
        request_params: Mapping[str, Any],
        progress_dispatcher: Any | None = None,
    ) -> dict[str, Any]:
        executor = self._executors.get(task_type)
        if executor is None:
            raise RuntimeError("task executor is not registered")
        result = await executor(
            task_id=task_id,
            request_params=request_params,
            progress_dispatcher=progress_dispatcher,
        )
        return dict(result)


@runtime_checkable
class WorkerCapabilityRegistry(Protocol):
    async def supports(self, task_type: TaskType) -> bool: ...


__all__ = [
    "TaskExecutionCapability",
    "TaskExecutor",
    "TaskExecutorRegistry",
    "WorkerCapabilityRegistry",
]
