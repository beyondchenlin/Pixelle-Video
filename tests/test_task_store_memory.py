from datetime import datetime, timedelta, timezone

import pytest

from api.tasks.models import ArtifactStatus, Task, TaskProgress, TaskStatus, TaskType
from api.tasks.store import InMemoryTaskStore, LostTaskLeaseError


@pytest.mark.asyncio
async def test_memory_store_reuses_active_task_by_fingerprint():
    store = InMemoryTaskStore()
    task = await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
            request_params={"text": "same"},
        )
    )

    reusable = await store.find_reusable_by_fingerprint(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        active_statuses={TaskStatus.PENDING, TaskStatus.RUNNING},
        completed_after=None,
    )

    assert reusable == task


@pytest.mark.asyncio
async def test_memory_store_reuses_recent_completed_task():
    store = InMemoryTaskStore()
    completed = await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
            status=TaskStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            artifact_status=ArtifactStatus.PERSISTED,
            result={"storage_key": "task-1/final.mp4"},
        )
    )

    reusable = await store.find_reusable_by_fingerprint(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        active_statuses={TaskStatus.PENDING, TaskStatus.RUNNING},
        completed_after=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    assert reusable == completed


@pytest.mark.asyncio
async def test_memory_store_rejects_stale_owner_status_update():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.RUNNING,
            owner_id="worker-current",
            lease_token="token-current",
        )
    )

    with pytest.raises(LostTaskLeaseError):
        await store.update_status(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            expected_owner_id="worker-old",
            expected_lease_token="token-old",
            result={"video_url": "/api/files/task-1/final.mp4"},
        )

    task = await store.get_task("task-1")
    assert task.status == TaskStatus.RUNNING
    assert task.result is None


@pytest.mark.asyncio
async def test_memory_store_claims_pending_task_once():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
        )
    )

    first = await store.claim_next_pending(
        owner_id="worker-1",
        lease_token="token-1",
        task_types={TaskType.VIDEO_GENERATION},
    )
    second = await store.claim_next_pending(
        owner_id="worker-2",
        lease_token="token-2",
        task_types={TaskType.VIDEO_GENERATION},
    )

    assert first is not None
    assert first.task_id == "task-1"
    assert second is None
    claimed = await store.get_task("task-1")
    assert claimed.status == TaskStatus.RUNNING
    assert claimed.owner_id == "worker-1"
    assert claimed.lease_token == "token-1"


@pytest.mark.asyncio
async def test_memory_store_claims_specific_running_task_with_current_fencing_token():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
            status=TaskStatus.RUNNING,
            owner_id="worker-old",
            lease_token="token-old",
        )
    )

    claimed = await store.claim_running_task(
        task_id="task-1",
        owner_id="worker-new",
        lease_token="token-new",
        expected_owner_id="worker-old",
        expected_lease_token="token-old",
    )

    assert claimed is not None
    assert claimed.owner_id == "worker-new"
    assert claimed.lease_token == "token-new"


@pytest.mark.asyncio
async def test_memory_store_does_not_cancel_terminal_task():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.COMPLETED,
            result={"storage_key": "task-1/final.mp4"},
        )
    )

    assert await store.cancel_task("task-1") is False
    task = await store.get_task("task-1")
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_memory_store_progress_update_requires_current_lease():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.RUNNING,
            owner_id="worker-current",
            lease_token="token-current",
        )
    )

    with pytest.raises(LostTaskLeaseError):
        await store.update_progress(
            task_id="task-1",
            progress=TaskProgress(current=1, total=5, percentage=20.0, message="bad"),
            expected_owner_id="worker-old",
            expected_lease_token="token-old",
        )

    await store.update_progress(
        task_id="task-1",
        progress=TaskProgress(current=2, total=5, percentage=40.0, message="ok"),
        expected_owner_id="worker-current",
        expected_lease_token="token-current",
    )

    task = await store.get_task("task-1")
    assert task.progress.message == "ok"
