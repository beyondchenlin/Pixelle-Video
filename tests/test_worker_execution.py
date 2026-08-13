import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.config import APIConfig
from api.tasks.artifacts import LocalArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import TaskStatus, TaskType, utc_now
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore
from api.tasks.worker import GenerationWorker
from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat
from pixelle_video.models.progress import ProgressEvent, ProgressEventType


class FakeCore:
    async def generate_video(self, **params):
        output = Path(params["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        return SimpleNamespace(video_path=str(output), duration=2.5)


def test_worker_rejects_ambiguous_relative_output_root() -> None:
    with pytest.raises(ValueError, match="output_root must be absolute"):
        GenerationWorker(
            registry=object(),
            core=object(),
            artifact_store=object(),
            output_root="output",
        )


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
    executor_registry = TaskExecutorRegistry()
    from api.video.executor_factory import register_video_generation_executor

    register_video_generation_executor(
        executor_registry,
        core_provider=lambda: FakeCore(),
        artifact_store=artifact_store,
    )
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=artifact_store,
        output_root=tmp_path / "work",
        executor_registry=executor_registry,
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
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        executor_registry=TaskExecutorRegistry(),
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
    executor_registry = TaskExecutorRegistry()
    from api.video.executor_factory import register_video_generation_executor

    register_video_generation_executor(
        executor_registry,
        core_provider=lambda: FailingCore(),
        artifact_store=registry.artifact_store,
    )
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.FAILED
    assert task.error == "generation exploded"


@pytest.mark.asyncio
async def test_worker_heartbeats_while_generation_is_running(tmp_path):
    class CountingRegistry(GenerationRegistry):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.heartbeat_count = 0

        async def heartbeat(self, **kwargs):
            self.heartbeat_count += 1
            await super().heartbeat(**kwargs)

    class SlowCore:
        async def generate_video(self, **params):
            await asyncio.sleep(0.03)
            output = Path(params["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"video")
            return SimpleNamespace(video_path=str(output), duration=2.5)

    registry = CountingRegistry(
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
    executor_registry = TaskExecutorRegistry()
    from api.video.executor_factory import register_video_generation_executor

    register_video_generation_executor(
        executor_registry,
        core_provider=lambda: SlowCore(),
        artifact_store=registry.artifact_store,
    )
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        heartbeat_interval_seconds=0.005,
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    assert registry.heartbeat_count > 0


@pytest.mark.asyncio
async def test_worker_leaves_cancelled_task_cancelled_after_generation_finishes(tmp_path):
    class CancellingCore:
        def __init__(self, registry):
            self.registry = registry

        async def generate_video(self, **params):
            await self.registry.cancel("task-1")
            output = Path(params["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"video")
            return SimpleNamespace(video_path=str(output), duration=2.5)

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
    executor_registry = TaskExecutorRegistry()
    from api.video.executor_factory import register_video_generation_executor

    register_video_generation_executor(
        executor_registry,
        core_provider=lambda: CancellingCore(registry),
        artifact_store=registry.artifact_store,
    )
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_worker_persists_progress_from_pipeline_dispatcher(tmp_path):
    class ProgressCore:
        async def generate_video(self, **params):
            dispatcher = params["progress_dispatcher"]
            dispatcher.emit(
                ProgressEvent(
                    event_type=ProgressEventType.SYNTHESIZING_AUDIO,
                    progress=0.82,
                )
            )
            output = Path(params["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"video")
            return SimpleNamespace(video_path=str(output), duration=2.5)

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
    executor_registry = TaskExecutorRegistry()
    from api.video.executor_factory import register_video_generation_executor

    register_video_generation_executor(
        executor_registry,
        core_provider=lambda: ProgressCore(),
        artifact_store=registry.artifact_store,
    )
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    task = await registry.get_task("task-1")
    assert task is not None
    assert task.progress is not None
    assert task.progress.event_type == "synthesizing_audio"


@pytest.mark.asyncio
async def test_worker_core_factory_attaches_platform_dependencies(tmp_path):
    from api.tasks.worker import build_worker_core

    core = await build_worker_core(
        config=APIConfig(
            runtime_profile="dev",
            artifact_base_path=str(tmp_path / "output"),
        )
    )
    try:
        assert hasattr(core, "artifact_repository")
        assert hasattr(core, "storyboard_workbench_state_store")
    finally:
        await core.cleanup()


@pytest.mark.asyncio
async def test_worker_claims_frame_image_regeneration_tasks(tmp_path):
    from api.tasks.artifacts import MissingArtifactStore

    store = InMemoryTaskStore()
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "regen-task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fingerprint-frame-0001",
        task_type=TaskType.FRAME_IMAGE_REGENERATION,
        request_params={"workspace_id": "workspace_1"},
        reuse_completed_within_seconds=0,
    )
    calls: list[dict[str, object]] = []

    async def executor(*, task_id: str, request_params: dict, progress_dispatcher=None):
        calls.append({"task_id": task_id, "request_params": request_params})
        return {"ok": True}

    executor_registry = TaskExecutorRegistry()
    executor_registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        worker_id="worker-1",
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    assert calls == [
        {
            "task_id": "regen-task-1",
            "request_params": {"workspace_id": "workspace_1"},
        }
    ]


@pytest.mark.asyncio
async def test_worker_mode_manager_reports_frame_regeneration_executable_after_worker_heartbeat():
    from api.tasks.manager import TaskManager

    worker_registry = InMemoryWorkerRegistry()
    await worker_registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=utc_now(),
        )
    )

    manager = TaskManager(
        execution_mode="worker",
        worker_capability_registry=worker_registry,
    )

    assert await manager.can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION) is True


def test_generation_worker_executes_only_through_task_executor_registry():
    source = Path("api/tasks/worker.py").read_text(encoding="utf-8")

    assert "core.generate_video" not in source
    assert "TaskType.VIDEO_GENERATION}" not in source
    assert ".execute(" in source
    assert "WorkerHeartbeat" in source
