from datetime import timedelta

import pytest

from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import ArtifactStatus, TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
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
