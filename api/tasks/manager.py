# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Task Manager facade.

The manager keeps the legacy in-memory API alive while new async callers move to
the GenerationRegistry/TaskStore path.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from api.config import api_config
from api.tasks.artifacts import MissingArtifactStore
from api.tasks.executors import TaskExecutorRegistry, WorkerCapabilityRegistry
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import Task, TaskProgress, TaskStatus, TaskType, utc_now
from api.tasks.progress import TaskProgressSink
from api.tasks.registry import ACTIVE_TASK_STATUSES, GenerationRegistry
from api.tasks.store import InMemoryTaskStore, LostTaskLeaseError, TaskStore
from pixelle_video.models.progress import ProgressDispatcher
from pixelle_video.utils.logging_util import bind_log_context


class TaskManager:
    """Facade for async task lifecycle, backed by a TaskStore and registry."""

    def __init__(
        self,
        *,
        store: TaskStore | None = None,
        registry: GenerationRegistry | None = None,
        execution_mode: str = "embedded",
        executor_registry: TaskExecutorRegistry | None = None,
        worker_capability_registry: WorkerCapabilityRegistry | None = None,
    ) -> None:
        self.store = store or InMemoryTaskStore()
        self.registry = registry or GenerationRegistry(
            store=self.store,
            lease=InMemoryGenerationLease(),
            artifact_store=MissingArtifactStore(),
        )
        self.execution_mode = execution_mode
        self.executor_registry = executor_registry or TaskExecutorRegistry()
        self.worker_capability_registry = worker_capability_registry

        # Legacy task map used by the current async video route until it migrates
        # to reserve_or_reuse_generation_task().
        self._tasks: dict[str, Task] = {}
        self._task_futures: dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start task manager and cleanup scheduler."""
        if self._running:
            logger.warning("Task manager already running")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ Task manager started")

    async def stop(self) -> None:
        """Stop task manager and cancel local futures."""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        for task_id, future in self._task_futures.items():
            if not future.done():
                future.cancel()
                logger.info(f"Cancelled task: {task_id}")

        self._tasks.clear()
        self._task_futures.clear()
        logger.info("✅ Task manager stopped")

    async def reserve_or_reuse_generation_task(
        self,
        *,
        task_type: TaskType,
        generation_fingerprint: str,
        request_params: dict,
    ):
        """Reserve or reuse an idempotent generation task through the registry."""
        outcome = await self.registry.reserve_or_reuse(
            fingerprint=generation_fingerprint,
            task_type=task_type,
            request_params=request_params,
            reuse_completed_within_seconds=getattr(
                api_config,
                "completed_reuse_seconds",
                api_config.task_retention_time,
            ),
        )
        if (
            outcome.created
            and self.execution_mode == "embedded"
            and self.executor_registry.can_execute(task_type).can_execute
        ):

            async def _run_registered_executor(*, progress_dispatcher=None):
                return await self.executor_registry.execute(
                    task_type,
                    task_id=outcome.task.task_id,
                    request_params=dict(request_params),
                    progress_dispatcher=progress_dispatcher,
                )

            await self.execute_task(
                task_id=outcome.task.task_id,
                coro_func=_run_registered_executor,
            )
        return outcome

    async def can_execute_task_type(self, task_type: TaskType) -> bool:
        """Return whether this runtime currently has an executor for a task type."""
        if self.execution_mode == "embedded":
            return self.executor_registry.can_execute(task_type).can_execute
        if self.execution_mode == "worker" and self.worker_capability_registry is not None:
            return await self.worker_capability_registry.supports(task_type)
        return False

    async def wait_for_task_completion_for_test(self, task_id: str) -> None:
        """Wait for an embedded future in tests without exposing futures as API."""
        future = self._task_futures.get(task_id)
        if future is not None:
            await future

    def create_task(
        self,
        task_type: TaskType,
        request_params: Optional[dict] = None,
    ) -> Task:
        """Create a legacy in-memory task."""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            request_params=request_params,
            generation_fingerprint=(request_params or {}).get("generation_fingerprint"),
        )

        self._tasks[task_id] = task
        logger.info(f"Created task {task_id} ({task_type})")
        return task

    def find_active_task_by_request_fingerprint(
        self,
        *,
        request_fingerprint: str,
        task_type: Optional[TaskType] = None,
    ) -> Optional[Task]:
        """Return an active legacy task that already represents this request."""
        for task in self._tasks.values():
            if task_type is not None and task.task_type != task_type:
                continue
            if task.status not in ACTIVE_TASK_STATUSES:
                continue
            if (task.request_params or {}).get("generation_fingerprint") == request_fingerprint:
                return task
        return None

    async def execute_task(
        self,
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        """Execute a task in embedded mode."""
        if task_id in self._tasks:
            await self._execute_legacy_task(task_id, coro_func, *args, **kwargs)
            return

        if self.execution_mode != "embedded":
            logger.info(f"Task {task_id} is queued for worker execution")
            return

        await self._execute_registry_task(task_id, coro_func, *args, **kwargs)

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID from the store, falling back to legacy memory."""
        task = await self.store.get_task(task_id)
        if task is not None:
            return task
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks from the store and legacy memory."""
        legacy_tasks = list(self._tasks.values())
        if status is not None:
            legacy_tasks = [task for task in legacy_tasks if task.status == status]

        deduped_legacy_tasks = []
        for task in legacy_tasks:
            store_task = await self.store.get_task(task.task_id)
            if store_task is not None:
                continue
            deduped_legacy_tasks.append(task)

        legacy_tasks = deduped_legacy_tasks
        if not legacy_tasks:
            return await self.store.list_tasks(status=status, limit=limit, offset=offset)

        store_tasks = await self.store.list_tasks(status=status, limit=limit + offset)
        by_id = {task.task_id: task for task in store_tasks}

        for task in legacy_tasks:
            by_id.setdefault(task.task_id, task)

        tasks = list(by_id.values())
        tasks.sort(key=lambda task: (task.created_at, task.task_id), reverse=True)
        return tasks[offset : offset + limit]

    async def count_tasks(self, status: Optional[TaskStatus] = None) -> int:
        """Count tasks from the store and legacy memory without duplicate ids."""
        total = await self.store.count_tasks(status=status)

        legacy_tasks = list(self._tasks.values())
        if status:
            legacy_tasks = [task for task in legacy_tasks if task.status == status]

        for task in legacy_tasks:
            store_task = await self.store.get_task(task.task_id)
            if store_task is None:
                total += 1

        return total

    def update_progress(
        self,
        task_id: str,
        current: int,
        total: int,
        message: str = "",
    ) -> None:
        """Update legacy task progress."""
        task = self._tasks.get(task_id)
        if not task:
            return

        percentage = (current / total * 100) if total > 0 else 0
        task.progress = TaskProgress(
            current=current,
            total=total,
            percentage=percentage,
            message=message,
        )
        task.updated_at = utc_now()

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running or pending task."""
        future = self._task_futures.get(task_id)
        if future and not future.done():
            future.cancel()

        store_cancelled = await self.registry.cancel(task_id)
        legacy_cancelled = False

        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.completed_at = utc_now()
            task.updated_at = utc_now()
            legacy_cancelled = True
            logger.info(f"Cancelled task {task_id}")

        return store_cancelled or legacy_cancelled

    async def _execute_legacy_task(
        self,
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        async def _execute():
            with bind_log_context(api_task_id=task_id, channel="runtime"):
                try:
                    task.status = TaskStatus.RUNNING
                    task.started_at = utc_now()
                    task.updated_at = task.started_at
                    logger.info("task started")

                    result = await coro_func(*args, **kwargs)

                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = utc_now()
                    task.updated_at = task.completed_at
                    logger.info("task completed")

                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = utc_now()
                    task.updated_at = task.completed_at
                    logger.error(f"task failed: {e}")

        future = asyncio.create_task(_execute())
        self._task_futures[task_id] = future

    async def _execute_registry_task(
        self,
        task_id: str,
        coro_func: Callable,
        *args,
        **kwargs,
    ) -> None:
        owner_id = f"embedded-{uuid.uuid4()}"
        lease_token = self.registry.lease.new_token()

        async def _execute():
            with bind_log_context(api_task_id=task_id, channel="runtime"):
                try:
                    started_at = utc_now()
                    await self.store.update_status(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        owner_id=owner_id,
                        lease_token=lease_token,
                        started_at=started_at,
                    )
                    await self.registry.lease.create_task_lease(
                        task_id=task_id,
                        owner_id=owner_id,
                        lease_token=lease_token,
                    )
                    logger.info("task started")
                    progress_sink = TaskProgressSink(
                        registry=self.registry,
                        task_id=task_id,
                        owner_id=owner_id,
                        lease_token=lease_token,
                    )
                    progress_dispatcher = ProgressDispatcher([progress_sink])

                    try:
                        result = await coro_func(
                            *args,
                            progress_dispatcher=progress_dispatcher,
                            **kwargs,
                        )
                    finally:
                        await progress_sink.drain()
                    if not isinstance(result, dict):
                        result = {"result": result}

                    await self.registry.mark_completed(
                        task_id=task_id,
                        result=result,
                        owner_id=owner_id,
                        lease_token=lease_token,
                    )
                    logger.info("task completed")

                except Exception as exc:
                    await self._mark_registry_task_failed(
                        task_id=task_id,
                        error=str(exc),
                        owner_id=owner_id,
                        lease_token=lease_token,
                    )
                    logger.error(f"task failed: {exc}")

        future = asyncio.create_task(_execute())
        self._task_futures[task_id] = future

    async def _mark_registry_task_failed(
        self,
        *,
        task_id: str,
        error: str,
        owner_id: str,
        lease_token: str,
    ) -> None:
        try:
            await self.registry.mark_failed(
                task_id=task_id,
                error=error,
                owner_id=owner_id,
                lease_token=lease_token,
            )
        except LostTaskLeaseError:
            logger.warning(f"Could not mark task {task_id} failed because lease was lost")
        except Exception as failure_error:
            logger.error(f"Could not mark task {task_id} failed: {failure_error}")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up old completed legacy tasks."""
        while self._running:
            try:
                await asyncio.sleep(api_config.task_cleanup_interval)
                self._cleanup_old_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    def _cleanup_old_tasks(self) -> None:
        """Remove old completed/failed legacy tasks."""
        cutoff_time = datetime.now() - timedelta(seconds=api_config.task_retention_time)

        tasks_to_remove = []
        for task_id, task in self._tasks.items():
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                completed_at = task.completed_at
                if completed_at and completed_at.tzinfo is not None:
                    completed_at = completed_at.replace(tzinfo=None)
                if completed_at and completed_at < cutoff_time:
                    tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            del self._tasks[task_id]
            if task_id in self._task_futures:
                del self._task_futures[task_id]

        if tasks_to_remove:
            logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")


task_manager = TaskManager()
