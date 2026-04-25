import pytest

from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore


def build_manager(task_id="task-1"):
    store = InMemoryTaskStore()
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: task_id,
    )
    return TaskManager(store=store, registry=registry, execution_mode="embedded")


@pytest.mark.asyncio
async def test_manager_reserve_or_reuse_generation_task_reuses_duplicate():
    manager = build_manager()
    first = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={"text": "same"},
    )
    second = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={"text": "same"},
    )

    assert first.created is True
    assert second.created is False
    assert second.reused_reason == "active"
    assert second.task.task_id == first.task.task_id


@pytest.mark.asyncio
async def test_manager_execute_task_updates_store_result():
    manager = build_manager()
    await manager.start()
    outcome = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={},
    )

    async def generate():
        return {
            "video_url": "/api/files/task-1/final.mp4",
            "storage_key": "task-1/final.mp4",
        }

    await manager.execute_task(outcome.task.task_id, generate)
    future = manager._task_futures[outcome.task.task_id]
    await future

    task = await manager.get_task(outcome.task.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result["video_url"] == "/api/files/task-1/final.mp4"
    await manager.stop()


@pytest.mark.asyncio
async def test_manager_list_tasks_reads_registry_store_before_legacy_tasks():
    manager = build_manager()
    await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={},
    )
    manager.create_task(
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"generation_fingerprint": "legacy-fp"},
    )

    tasks = await manager.list_tasks(limit=10)

    assert {task.task_id for task in tasks} >= {"task-1"}
    assert len(tasks) == 2
