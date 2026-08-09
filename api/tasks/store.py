"""Task storage contracts and in-memory implementation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Protocol

from api.tasks.models import (
    TASK_STATUS_TRANSITION_SOURCES,
    TERMINAL_TASK_STATUSES,
    ArtifactStatus,
    Task,
    TaskProgress,
    TaskStatus,
    TaskType,
    utc_now,
)


class TaskStoreError(RuntimeError):
    """Base error for task storage failures."""


class TaskAlreadyExistsError(TaskStoreError):
    """Raised when a task id already exists."""


class TaskNotFoundError(TaskStoreError):
    """Raised when a task id cannot be found."""


class LostTaskLeaseError(TaskStoreError):
    """Raised when a stale owner or lease token attempts to write state."""


class InvalidTaskTransitionError(TaskStoreError):
    """Raised when persisted task state would move backward or resurrect."""


class TaskStore(Protocol):
    async def create_task(self, task: Task) -> Task:
        raise NotImplementedError

    async def get_task(self, task_id: str) -> Task | None:
        raise NotImplementedError

    async def find_reusable_by_fingerprint(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        active_statuses: set[TaskStatus],
        completed_after: datetime | None,
    ) -> Task | None:
        raise NotImplementedError

    async def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        owner_id: str | None = None,
        lease_token: str | None = None,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
        artifact_status: ArtifactStatus | None = None,
    ) -> None:
        raise NotImplementedError

    async def update_progress(
        self,
        *,
        task_id: str,
        progress: TaskProgress,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def claim_next_pending(
        self,
        *,
        owner_id: str,
        lease_token: str,
        task_types: set[TaskType] | None = None,
    ) -> Task | None:
        raise NotImplementedError

    async def list_running_tasks(
        self,
        *,
        task_types: set[TaskType] | None = None,
        limit: int = 100,
    ) -> list[Task]:
        raise NotImplementedError

    async def claim_running_task(
        self,
        *,
        task_id: str,
        owner_id: str,
        lease_token: str,
        expected_owner_id: str | None,
        expected_lease_token: str | None,
    ) -> Task | None:
        raise NotImplementedError

    async def list_tasks(
        self,
        status: TaskStatus | None,
        limit: int,
        offset: int = 0,
    ) -> list[Task]:
        raise NotImplementedError

    async def count_tasks(self, status: TaskStatus | None) -> int:
        raise NotImplementedError

    async def cancel_task(self, task_id: str) -> bool:
        raise NotImplementedError


class InMemoryTaskStore:
    """Process-local TaskStore implementation for development and unit tests."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task: Task) -> Task:
        async with self._lock:
            if task.task_id in self._tasks:
                raise TaskAlreadyExistsError(task.task_id)

            now = utc_now()
            task_copy = task.model_copy(deep=True)
            task_copy.created_at = task_copy.created_at or now
            task_copy.updated_at = now
            if task_copy.generation_fingerprint is None and task_copy.request_params:
                task_copy.generation_fingerprint = task_copy.request_params.get(
                    "generation_fingerprint"
                )
            self._tasks[task_copy.task_id] = task_copy
            return self._clone(task_copy)

    async def get_task(self, task_id: str) -> Task | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            return self._clone(task) if task is not None else None

    async def find_reusable_by_fingerprint(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        active_statuses: set[TaskStatus],
        completed_after: datetime | None,
    ) -> Task | None:
        async with self._lock:
            matches = [
                task
                for task in self._tasks.values()
                if task.task_type == task_type and task.generation_fingerprint == fingerprint
            ]

            active = [task for task in matches if task.status in active_statuses]
            if active:
                active.sort(key=lambda task: task.created_at, reverse=True)
                return self._clone(active[0])

            completed = [
                task
                for task in matches
                if task.status == TaskStatus.COMPLETED
                and task.completed_at is not None
                and (completed_after is None or task.completed_at >= completed_after)
            ]
            if not completed:
                return None

            completed.sort(key=lambda task: task.completed_at or task.created_at, reverse=True)
            return self._clone(completed[0])

    async def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        owner_id: str | None = None,
        lease_token: str | None = None,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
        artifact_status: ArtifactStatus | None = None,
    ) -> None:
        async with self._lock:
            task = self._require_task(task_id)
            self._assert_expected_lease(
                task,
                expected_owner_id=expected_owner_id,
                expected_lease_token=expected_lease_token,
            )

            if task.status not in TASK_STATUS_TRANSITION_SOURCES[status]:
                raise InvalidTaskTransitionError(
                    f"task {task_id} cannot transition from {task.status.value} to {status.value}"
                )

            task.status = status
            if owner_id is not None:
                task.owner_id = owner_id
            if lease_token is not None:
                task.lease_token = lease_token
            if started_at is not None:
                task.started_at = started_at
            if completed_at is not None:
                task.completed_at = completed_at
            if error is not None:
                task.error = error
            if result is not None:
                task.result = result
            if artifact_status is not None:
                task.artifact_status = artifact_status
            if status in TERMINAL_TASK_STATUSES:
                task.lease_token = None
                task.completed_at = completed_at or task.completed_at or utc_now()
            task.updated_at = utc_now()

    async def update_progress(
        self,
        *,
        task_id: str,
        progress: TaskProgress,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None:
        async with self._lock:
            task = self._require_task(task_id)
            self._assert_expected_lease(
                task,
                expected_owner_id=expected_owner_id,
                expected_lease_token=expected_lease_token,
            )
            if task.status != TaskStatus.RUNNING:
                raise InvalidTaskTransitionError(
                    f"task {task_id} progress cannot change while {task.status.value}"
                )
            task.progress = progress.model_copy(deep=True)
            task.updated_at = utc_now()

    async def claim_next_pending(
        self,
        *,
        owner_id: str,
        lease_token: str,
        task_types: set[TaskType] | None = None,
    ) -> Task | None:
        async with self._lock:
            pending = [
                task
                for task in self._tasks.values()
                if task.status == TaskStatus.PENDING
                and (task_types is None or task.task_type in task_types)
            ]
            if not pending:
                return None

            pending.sort(key=lambda task: task.created_at)
            task = pending[0]
            now = utc_now()
            task.status = TaskStatus.RUNNING
            task.owner_id = owner_id
            task.lease_token = lease_token
            task.started_at = task.started_at or now
            task.updated_at = now
            return self._clone(task)

    async def list_running_tasks(
        self,
        *,
        task_types: set[TaskType] | None = None,
        limit: int = 100,
    ) -> list[Task]:
        async with self._lock:
            running = [
                task
                for task in self._tasks.values()
                if task.status == TaskStatus.RUNNING
                and (task_types is None or task.task_type in task_types)
            ]
            running.sort(key=lambda task: task.updated_at)
            return [self._clone(task) for task in running[:limit]]

    async def claim_running_task(
        self,
        *,
        task_id: str,
        owner_id: str,
        lease_token: str,
        expected_owner_id: str | None,
        expected_lease_token: str | None,
    ) -> Task | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.RUNNING:
                return None
            self._assert_expected_lease(
                task,
                expected_owner_id=expected_owner_id,
                expected_lease_token=expected_lease_token,
            )
            now = utc_now()
            task.owner_id = owner_id
            task.lease_token = lease_token
            task.started_at = task.started_at or now
            task.updated_at = now
            return self._clone(task)

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        async with self._lock:
            tasks = list(self._tasks.values())
            if status is not None:
                tasks = [task for task in tasks if task.status == status]
            tasks.sort(key=lambda task: (task.created_at, task.task_id), reverse=True)
            return [self._clone(task) for task in tasks[offset : offset + limit]]

    async def count_tasks(self, status: TaskStatus | None = None) -> int:
        async with self._lock:
            if status is None:
                return len(self._tasks)
            return sum(1 for task in self._tasks.values() if task.status == status)

    async def cancel_task(self, task_id: str) -> bool:
        return await self.cancel_task_if_owned(task_id)

    async def cancel_task_if_owned(
        self,
        task_id: str,
        *,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        require_lease_match: bool = False,
    ) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status not in {TaskStatus.PENDING, TaskStatus.RUNNING}:
                return False
            if require_lease_match and (
                task.owner_id != expected_owner_id or task.lease_token != expected_lease_token
            ):
                return False

            now = utc_now()
            task.status = TaskStatus.CANCELLED
            task.owner_id = None
            task.lease_token = None
            task.completed_at = now
            task.updated_at = now
            return True

    def _require_task(self, task_id: str) -> Task:
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    @staticmethod
    def _assert_expected_lease(
        task: Task,
        *,
        expected_owner_id: str | None,
        expected_lease_token: str | None,
    ) -> None:
        if expected_owner_id is not None and task.owner_id != expected_owner_id:
            raise LostTaskLeaseError(task.task_id)
        if expected_lease_token is not None and task.lease_token != expected_lease_token:
            raise LostTaskLeaseError(task.task_id)

    @staticmethod
    def _clone(task: Task) -> Task:
        return task.model_copy(deep=True)
