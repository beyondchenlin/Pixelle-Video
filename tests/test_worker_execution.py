from pathlib import Path
from types import SimpleNamespace

import pytest

from api.tasks.artifacts import LocalArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore
from api.tasks.worker import GenerationWorker


class FakeCore:
    async def generate_video(self, **params):
        output = Path(params["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        return SimpleNamespace(video_path=str(output), duration=2.5)


@pytest.mark.asyncio
async def test_worker_claims_pending_task_and_marks_completed(tmp_path):
    store = InMemoryTaskStore()
    artifact_store = LocalArtifactStore(output_root=tmp_path / "output", base_url="/api/files")
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "demo", "frame_template": "1080x1920/image_default.html"},
        reuse_completed_within_seconds=86400,
    )
    worker = GenerationWorker(
        registry=registry,
        core=FakeCore(),
        artifact_store=artifact_store,
        output_root=tmp_path / "work",
    )

    did_work = await worker.run_once()

    assert did_work is True
    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.COMPLETED
    assert task.result["storage_key"] == "task-1/final.mp4"


@pytest.mark.asyncio
async def test_worker_returns_false_when_no_pending_task(tmp_path):
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
    )
    worker = GenerationWorker(
        registry=registry,
        core=FakeCore(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
    )

    assert await worker.run_once() is False


@pytest.mark.asyncio
async def test_worker_marks_task_failed_when_generation_raises(tmp_path):
    class FailingCore:
        async def generate_video(self, **_params):
            raise RuntimeError("generation exploded")

    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "demo"},
        reuse_completed_within_seconds=86400,
    )
    worker = GenerationWorker(
        registry=registry,
        core=FailingCore(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
    )

    assert await worker.run_once() is True
    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.FAILED
    assert task.error == "generation exploded"
