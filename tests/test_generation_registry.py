from datetime import timedelta

import pytest

from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import ArtifactStatus, TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry, Task
from api.tasks.store import InMemoryTaskStore, LostTaskLeaseError


@pytest.mark.asyncio
async def test_registry_reuses_active_task():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
    )

    first = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    second = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert first.created is True
    assert second.created is False
    assert second.reused_reason == "active"
    assert second.task.task_id == first.task.task_id


@pytest.mark.asyncio
async def test_registry_reuses_completed_only_when_artifact_exists():
    artifact_store = MissingArtifactStore(existing_keys={"task-1/final.mp4"})
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: "task-1",
    )
    created = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")
    await registry.mark_completed(
        task_id=created.task.task_id,
        result={"storage_key": "task-1/final.mp4"},
        owner_id=claim.lease.owner_id,
        lease_token=claim.lease.lease_token,
    )

    reused = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert reused.created is False
    assert reused.reused_reason == "recent_completed"
    assert reused.task.artifact_status == ArtifactStatus.PERSISTED


@pytest.mark.asyncio
async def test_registry_marks_completed_missing_artifact_failed_before_regenerating():
    artifact_store = MissingArtifactStore(existing_keys=set())
    ids = iter(["task-old", "task-new"])
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: next(ids),
    )
    old = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")
    await registry.mark_completed(
        task_id=old.task.task_id,
        result={"storage_key": "task-old/final.mp4"},
        owner_id=claim.lease.owner_id,
        lease_token=claim.lease.lease_token,
    )

    new = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert new.created is True
    assert new.task.task_id == "task-new"
    failed_old = await registry.get_task("task-old")
    assert failed_old.status == TaskStatus.FAILED
    assert failed_old.artifact_status == ArtifactStatus.MISSING


@pytest.mark.asyncio
async def test_registry_rejects_stale_completion_after_lost_lease():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(existing_keys={"task-1/final.mp4"}),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=int(timedelta(days=1).total_seconds()),
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")

    with pytest.raises(LostTaskLeaseError):
        await registry.mark_completed(
            task_id="task-1",
            result={"storage_key": "task-1/final.mp4"},
            owner_id=claim.lease.owner_id,
            lease_token="stale-token",
        )


@pytest.mark.asyncio
async def test_registry_rejects_completion_after_redis_lease_is_lost():
    lease = InMemoryGenerationLease()
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=lease,
        artifact_store=MissingArtifactStore(existing_keys={"task-1/final.mp4"}),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")
    await lease.release_task_lease(
        "task-1",
        claim.lease.owner_id,
        claim.lease.lease_token,
    )

    with pytest.raises(LostTaskLeaseError):
        await registry.mark_completed(
            task_id="task-1",
            result={"storage_key": "task-1/final.mp4"},
            owner_id=claim.lease.owner_id,
            lease_token=claim.lease.lease_token,
        )

    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_registry_heartbeat_rejects_stale_lease_token():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")

    with pytest.raises(LostTaskLeaseError):
        await registry.heartbeat(
            task_id="task-1",
            owner_id=claim.lease.owner_id,
            lease_token="stale-token",
        )


@pytest.mark.asyncio
async def test_registry_reclaims_running_task_after_execution_lease_is_lost():
    lease = InMemoryGenerationLease()
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=lease,
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=86400,
    )
    first_claim = await registry.claim_next_pending(worker_id="worker-old")
    await lease.release_task_lease(
        "task-1",
        first_claim.lease.owner_id,
        first_claim.lease.lease_token,
    )

    reclaimed = await registry.claim_next_pending(worker_id="worker-new")

    assert reclaimed is not None
    assert reclaimed.task.task_id == "task-1"
    assert reclaimed.lease.owner_id == "worker-new"
    assert reclaimed.lease.lease_token != first_claim.lease.lease_token


@pytest.mark.asyncio
async def test_registry_confirms_orphan_claim_still_owns_db_and_redis_after_lease_creation():
    class RacingLease(InMemoryGenerationLease):
        def __init__(self, store):
            super().__init__()
            self.store = store
            self.raced = False

        async def create_task_lease(self, task_id, owner_id, lease_token):
            lease = await super().create_task_lease(task_id, owner_id, lease_token)
            if owner_id == "worker-new" and not self.raced:
                self.raced = True
                await self.store.claim_running_task(
                    task_id=task_id,
                    owner_id="worker-race",
                    lease_token="token-race",
                    expected_owner_id=owner_id,
                    expected_lease_token=lease_token,
                )
            return lease

    store = InMemoryTaskStore()
    lease = RacingLease(store)
    registry = GenerationRegistry(
        store=store,
        lease=lease,
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=86400,
    )
    first_claim = await registry.claim_next_pending(worker_id="worker-old")
    await lease.release_task_lease(
        "task-1",
        first_claim.lease.owner_id,
        first_claim.lease.lease_token,
    )

    assert await registry.claim_next_pending(worker_id="worker-new") is None
    task = await registry.get_task("task-1")
    assert task.owner_id == "worker-race"
    assert await lease.has_task_lease("task-1", "worker-new", task.lease_token or "") is False


@pytest.mark.asyncio
async def test_registry_does_not_reclaim_running_task_with_live_execution_lease():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=86400,
    )
    await registry.claim_next_pending(worker_id="worker-live")

    assert await registry.claim_next_pending(worker_id="worker-other") is None


@pytest.mark.asyncio
async def test_registry_waits_for_task_created_by_competing_submit_lock():
    class ContendedLease(InMemoryGenerationLease):
        async def acquire_submit_lock(self, fingerprint: str, owner_id: str) -> bool:
            return False

    class EventuallyReusableStore(InMemoryTaskStore):
        def __init__(self):
            super().__init__()
            self.find_calls = 0

        async def find_reusable_by_fingerprint(self, **kwargs):
            self.find_calls += 1
            if self.find_calls == 2:
                await self.create_task(
                    self._build_competing_task(kwargs["fingerprint"], kwargs["task_type"])
                )
            return await super().find_reusable_by_fingerprint(**kwargs)

        @staticmethod
        def _build_competing_task(fingerprint, task_type):
            return Task(
                task_id="task-from-other-submit",
                task_type=task_type,
                status=TaskStatus.PENDING,
                request_params={"text": "same"},
                generation_fingerprint=fingerprint,
            )

    store = EventuallyReusableStore()
    registry = GenerationRegistry(
        store=store,
        lease=ContendedLease(),
        artifact_store=MissingArtifactStore(),
        submit_lock_wait_seconds=0.05,
        submit_lock_poll_interval_seconds=0.001,
    )

    outcome = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert outcome.created is False
    assert outcome.reused_reason == "active"
    assert outcome.task.task_id == "task-from-other-submit"
