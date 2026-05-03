from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from api.tasks.models import TaskType


@dataclass
class _Task:
    task_id: str
    task_type: TaskType


@dataclass
class _Outcome:
    task: _Task
    created: bool
    reused_reason: str | None


class _FakeTaskManager:
    def __init__(self, *, can_execute_frame_regeneration: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.can_execute_frame_regeneration = can_execute_frame_regeneration

    async def can_execute_task_type(self, task_type: TaskType) -> bool:
        return (
            task_type is TaskType.FRAME_IMAGE_REGENERATION
            and self.can_execute_frame_regeneration
        )

    async def reserve_or_reuse_generation_task(
        self,
        *,
        task_type: TaskType,
        generation_fingerprint: str,
        request_params: dict[str, Any],
    ) -> _Outcome:
        self.calls.append(
            {
                "task_type": task_type,
                "generation_fingerprint": generation_fingerprint,
                "request_params": request_params,
            }
        )
        return _Outcome(
            task=_Task("regen-task-1", task_type),
            created=True,
            reused_reason=None,
        )


@pytest.mark.asyncio
async def test_task_executor_registry_registers_capability_and_executes_task():
    from api.tasks.executors import TaskExecutorRegistry

    calls: list[dict[str, Any]] = []

    async def executor(
        *,
        task_id: str,
        request_params: dict[str, Any],
        progress_dispatcher=None,
    ):
        calls.append(
            {
                "task_id": task_id,
                "request_params": request_params,
                "has_progress": progress_dispatcher is not None,
            }
        )
        return {"ok": True}

    registry = TaskExecutorRegistry()

    assert registry.can_execute(TaskType.FRAME_IMAGE_REGENERATION).to_dict() == {
        "can_execute": False,
        "unavailable_reason": "task executor is not registered",
    }

    registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)

    assert registry.can_execute(TaskType.FRAME_IMAGE_REGENERATION).to_dict() == {
        "can_execute": True,
        "unavailable_reason": None,
    }
    assert await registry.execute(
        TaskType.FRAME_IMAGE_REGENERATION,
        task_id="regen-task-1",
        request_params={"workspace_id": "workspace_1"},
        progress_dispatcher=object(),
    ) == {"ok": True}
    assert calls == [
        {
            "task_id": "regen-task-1",
            "request_params": {"workspace_id": "workspace_1"},
            "has_progress": True,
        }
    ]


@pytest.mark.asyncio
async def test_worker_capability_registry_uses_recent_heartbeats():
    from datetime import timedelta

    from api.tasks.models import utc_now
    from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat

    now = utc_now()
    registry = InMemoryWorkerRegistry(heartbeat_ttl_seconds=30)

    assert await registry.supports(TaskType.FRAME_IMAGE_REGENERATION, now=now) is False

    await registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=now,
        )
    )

    assert await registry.supports(TaskType.FRAME_IMAGE_REGENERATION, now=now) is True
    assert await registry.supports(TaskType.VIDEO_GENERATION, now=now) is False
    assert (
        await registry.supports(
            TaskType.FRAME_IMAGE_REGENERATION,
            now=now + timedelta(seconds=31),
        )
        is False
    )


@pytest.mark.asyncio
async def test_task_manager_storyboard_submitter_reserves_frame_regeneration_task():
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    manager = _FakeTaskManager()
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)

    result = await submitter.reserve_frame_image_regeneration(
        generation_fingerprint="fingerprint-frame-0001",
        request_params={"workspace_id": "workspace_1"},
    )

    assert result.to_dict() == {
        "task_id": "regen-task-1",
        "task_type": "frame_image_regeneration",
        "created": True,
        "reused_reason": None,
    }
    assert manager.calls == [
        {
            "task_type": TaskType.FRAME_IMAGE_REGENERATION,
            "generation_fingerprint": "fingerprint-frame-0001",
            "request_params": {"workspace_id": "workspace_1"},
        }
    ]


@pytest.mark.asyncio
async def test_task_manager_reports_frame_regeneration_unavailable_by_default():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(TaskManager())

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": (
            "frame image regeneration execution is not configured"
        ),
    }


@pytest.mark.asyncio
async def test_task_manager_embedded_capability_comes_from_executor_registry():
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    async def executor(**_kwargs):
        return {"ok": True}

    registry = TaskExecutorRegistry()
    registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(
        TaskManager(executor_registry=registry)
    )

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }


@pytest.mark.asyncio
async def test_task_manager_worker_mode_uses_worker_capability_registry():
    from api.tasks.manager import TaskManager
    from api.tasks.models import utc_now
    from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat

    worker_registry = InMemoryWorkerRegistry()
    await worker_registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=utc_now(),
        )
    )
    assert (
        await TaskManager(execution_mode="worker").can_execute_task_type(
            TaskType.FRAME_IMAGE_REGENERATION
        )
        is False
    )
    assert (
        await TaskManager(
            execution_mode="worker",
            worker_capability_registry=worker_registry,
        ).can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION)
        is True
    )
