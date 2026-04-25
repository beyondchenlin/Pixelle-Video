"""Generation task registry orchestration."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta
from typing import Callable

from api.tasks.artifacts import ArtifactStore
from api.tasks.lease import GenerationLease, LostLeaseError
from api.tasks.models import (
    ArtifactStatus,
    ClaimedTask,
    ReserveOutcome,
    Task,
    TaskStatus,
    TaskType,
    utc_now,
)
from api.tasks.store import LostTaskLeaseError, TaskAlreadyExistsError, TaskStore

ACTIVE_TASK_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}


class GenerationRegistry:
    """Coordinate idempotent generation task creation and worker ownership."""

    def __init__(
        self,
        *,
        store: TaskStore,
        lease: GenerationLease,
        artifact_store: ArtifactStore,
        task_id_factory: Callable[[], str] | None = None,
        submit_lock_wait_seconds: float = 2.0,
        submit_lock_poll_interval_seconds: float = 0.05,
    ) -> None:
        self.store = store
        self.lease = lease
        self.artifact_store = artifact_store
        self.task_id_factory = task_id_factory or (lambda: str(uuid.uuid4()))
        self.submit_lock_wait_seconds = submit_lock_wait_seconds
        self.submit_lock_poll_interval_seconds = submit_lock_poll_interval_seconds

    async def reserve_or_reuse(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        request_params: dict,
        reuse_completed_within_seconds: int,
    ) -> ReserveOutcome:
        submit_owner = f"submit-{uuid.uuid4()}"
        acquired = await self.lease.acquire_submit_lock(fingerprint, submit_owner)
        if not acquired:
            reusable = await self._wait_for_reusable(
                fingerprint=fingerprint,
                task_type=task_type,
                reuse_completed_within_seconds=reuse_completed_within_seconds,
            )
            if reusable is not None:
                return reusable
            raise RuntimeError("generation submit lock is already held")

        try:
            reusable = await self._find_reusable(
                fingerprint=fingerprint,
                task_type=task_type,
                reuse_completed_within_seconds=reuse_completed_within_seconds,
            )
            if reusable is not None:
                return reusable

            task = Task(
                task_id=self.task_id_factory(),
                task_type=task_type,
                status=TaskStatus.PENDING,
                request_params=request_params,
                generation_fingerprint=fingerprint,
            )
            try:
                created = await self.store.create_task(task)
            except TaskAlreadyExistsError:
                reusable = await self._find_reusable(
                    fingerprint=fingerprint,
                    task_type=task_type,
                    reuse_completed_within_seconds=reuse_completed_within_seconds,
                )
                if reusable is not None:
                    return reusable
                raise
            return ReserveOutcome(task=created, created=True)
        finally:
            await self.lease.release_submit_lock(fingerprint, submit_owner)

    async def claim_next_pending(
        self,
        *,
        worker_id: str,
        task_types: set[TaskType] | None = None,
    ) -> ClaimedTask | None:
        lease_token = self.lease.new_token()
        task = await self.store.claim_next_pending(
            owner_id=worker_id,
            lease_token=lease_token,
            task_types=task_types,
        )
        if task is None:
            return await self._claim_orphaned_running(
                worker_id=worker_id,
                task_types=task_types,
            )

        try:
            lease = await self.lease.create_task_lease(
                task_id=task.task_id,
                owner_id=worker_id,
                lease_token=lease_token,
            )
        except LostLeaseError as exc:
            await self.store.update_status(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                expected_owner_id=worker_id,
                expected_lease_token=lease_token,
                completed_at=utc_now(),
                error="generation lease initialization failed",
            )
            raise LostTaskLeaseError(task.task_id) from exc

        return ClaimedTask(task=task, lease=lease)

    async def _claim_orphaned_running(
        self,
        *,
        worker_id: str,
        task_types: set[TaskType] | None = None,
    ) -> ClaimedTask | None:
        running_tasks = await self.store.list_running_tasks(task_types=task_types, limit=100)
        for task in running_tasks:
            if task.owner_id and task.lease_token:
                if await self.lease.has_task_lease(task.task_id, task.owner_id, task.lease_token):
                    continue

            lease_token = self.lease.new_token()
            claimed = await self.store.claim_running_task(
                task_id=task.task_id,
                owner_id=worker_id,
                lease_token=lease_token,
                expected_owner_id=task.owner_id,
                expected_lease_token=task.lease_token,
            )
            if claimed is None:
                continue

            try:
                lease = await self.lease.create_task_lease(
                    task_id=claimed.task_id,
                    owner_id=worker_id,
                    lease_token=lease_token,
                )
            except LostLeaseError:
                continue
            try:
                await self.heartbeat(
                    task_id=claimed.task_id,
                    owner_id=worker_id,
                    lease_token=lease_token,
                )
            except LostTaskLeaseError:
                await self.lease.release_task_lease(claimed.task_id, worker_id, lease_token)
                continue
            return ClaimedTask(task=claimed, lease=lease)
        return None

    async def mark_completed(
        self,
        *,
        task_id: str,
        result: dict,
        owner_id: str,
        lease_token: str,
    ) -> None:
        await self.heartbeat(task_id=task_id, owner_id=owner_id, lease_token=lease_token)
        await self.store.update_status(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            expected_owner_id=owner_id,
            expected_lease_token=lease_token,
            completed_at=utc_now(),
            result=result,
            artifact_status=ArtifactStatus.PERSISTED,
        )
        await self.lease.release_task_lease(task_id, owner_id, lease_token)

    async def mark_failed(
        self,
        *,
        task_id: str,
        error: str,
        owner_id: str,
        lease_token: str,
    ) -> None:
        await self.heartbeat(task_id=task_id, owner_id=owner_id, lease_token=lease_token)
        await self.store.update_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            expected_owner_id=owner_id,
            expected_lease_token=lease_token,
            completed_at=utc_now(),
            error=error,
        )
        await self.lease.release_task_lease(task_id, owner_id, lease_token)

    async def heartbeat(self, *, task_id: str, owner_id: str, lease_token: str) -> None:
        task = await self.store.get_task(task_id)
        if task is None or task.owner_id != owner_id or task.lease_token != lease_token:
            raise LostTaskLeaseError(task_id)

        try:
            await self.lease.heartbeat(task_id, owner_id, lease_token)
        except LostLeaseError as exc:
            raise LostTaskLeaseError(task_id) from exc

    async def cancel(self, task_id: str) -> bool:
        task = await self.store.get_task(task_id)
        if task is None:
            return False

        cancelled = await self.store.cancel_task(task_id)
        if cancelled and task.owner_id and task.lease_token:
            await self.lease.release_task_lease(task_id, task.owner_id, task.lease_token)
        return cancelled

    async def get_task(self, task_id: str) -> Task | None:
        return await self.store.get_task(task_id)

    async def list_tasks(self, status: TaskStatus | None = None, limit: int = 100) -> list[Task]:
        return await self.store.list_tasks(status=status, limit=limit)

    async def _find_reusable(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        reuse_completed_within_seconds: int,
    ) -> ReserveOutcome | None:
        completed_after = None
        if reuse_completed_within_seconds > 0:
            completed_after = utc_now() - timedelta(seconds=reuse_completed_within_seconds)

        candidate = await self.store.find_reusable_by_fingerprint(
            fingerprint=fingerprint,
            task_type=task_type,
            active_statuses=ACTIVE_TASK_STATUSES,
            completed_after=completed_after,
        )
        if candidate is None:
            return None

        if candidate.status in ACTIVE_TASK_STATUSES:
            return ReserveOutcome(task=candidate, created=False, reused_reason="active")

        storage_key = None
        if isinstance(candidate.result, dict):
            storage_key = candidate.result.get("storage_key")
        if await self.artifact_store.exists(storage_key):
            return ReserveOutcome(
                task=candidate,
                created=False,
                reused_reason="recent_completed",
            )

        await self.store.update_status(
            task_id=candidate.task_id,
            status=TaskStatus.FAILED,
            completed_at=utc_now(),
            error="artifact missing",
            artifact_status=ArtifactStatus.MISSING,
        )
        return None

    async def _wait_for_reusable(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        reuse_completed_within_seconds: int,
    ) -> ReserveOutcome | None:
        deadline = time.monotonic() + self.submit_lock_wait_seconds
        while True:
            reusable = await self._find_reusable(
                fingerprint=fingerprint,
                task_type=task_type,
                reuse_completed_within_seconds=reuse_completed_within_seconds,
            )
            if reusable is not None:
                return reusable
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(self.submit_lock_poll_interval_seconds)
