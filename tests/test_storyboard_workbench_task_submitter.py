from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


class _FakeMedia:
    def __init__(
        self,
        generated_path: Path,
        default_workflow: str = "selfhost/default_image_workflow.json",
    ) -> None:
        self.generated_path = generated_path
        self.default_workflow = default_workflow
        self.calls: list[dict[str, Any]] = []

    def resolve_workflow_key(self, *, workflow=None, media_type="image"):
        assert media_type == "image"
        return workflow or self.default_workflow

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "MediaResult",
            (),
            {
                "media_type": "image",
                "is_image": True,
                "url": str(self.generated_path),
            },
        )()


class _FakePromptPlanRepository:
    async def load_prompt_plans_by_storyboard(self, workspace_id, storyboard_id):
        return [
            {
                "prompt_plan_id": "prompt_plan_001",
                "storyboard_plan_id": storyboard_id,
                "frame_id": "frame_0001",
                "image_prompt_draft_id": "draft_001",
                "prompt_sections": {"visual_goal": "A quiet lab"},
                "final_prompt": "A quiet lab, cinematic lighting",
            }
        ]


class _FakeStateStore:
    def __init__(self):
        self.saved: list[tuple[str, str, str, dict[str, Any]]] = []

    async def load_frame_state(self, workspace_id, storyboard_id, frame_id):
        return {
            "frame_id": frame_id,
            "prompt_plan_id": "prompt_plan_001",
            "selected_image_artifact_id": "artifact_frame_0001_image",
            "selected_image_version_id": "artifact_version_001",
            "candidate_image_version_ids": ["artifact_version_001"],
            "lock_policy": "unlocked",
            "stale_flags": [],
        }

    async def save_frame_state(self, workspace_id, storyboard_id, frame_id, state):
        self.saved.append((workspace_id, storyboard_id, frame_id, dict(state)))
        return state


@pytest.mark.asyncio
async def test_execute_frame_image_regeneration_generates_image_and_records_candidate(tmp_path):
    from api.workbench.frame_image_regeneration import execute_frame_image_regeneration
    from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
    from tests.test_storyboard_frame_regeneration import (
        RecordingArtifactRepository,
        RecordingObjectStore,
        RecordingTraceRepository,
        UnusedPromptPlanRepository,
    )

    generated = tmp_path / "generated.png"
    generated.write_bytes(b"image")
    artifact_repository = RecordingArtifactRepository(created_versions=[])
    object_store = RecordingObjectStore(uploaded_files=[])
    trace_repository = RecordingTraceRepository(events=[])
    service = StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=UnusedPromptPlanRepository(),
    )
    state_store = _FakeStateStore()
    media = _FakeMedia(generated)
    core = type(
        "Core",
        (),
        {
            "media": media,
            "storyboard_workbench_service": service,
            "storyboard_workbench_state_store": state_store,
            "prompt_plan_repository": _FakePromptPlanRepository(),
            "prompt_trace_output_dir": tmp_path / "prompt_trace_runtime",
        },
    )()

    result = await execute_frame_image_regeneration(
        core=core,
        task_id="regen-task-1",
        request_params={
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "prompt_plan_id": "prompt_plan_001",
            "artifact_id": "artifact_frame_0001_image",
            "provider": "comfyui",
            "model": "selfhost/image_z_image_turbo_gguf.json",
            "media_width": 768,
            "media_height": 768,
            "media_negative_prompt": "blurry",
        },
    )

    assert media.calls == [
        {
            "prompt": "A quiet lab, cinematic lighting",
            "media_type": "image",
            "workflow": "selfhost/image_z_image_turbo_gguf.json",
            "width": 768,
            "height": 768,
            "negative_prompt": "blurry",
        }
    ]
    assert result["artifact_version_id"] == artifact_repository.created_versions[-1][2]["version_id"]
    assert state_store.saved[-1][3]["last_generation_job_id"] == "regen-task-1"
    trace_content = next((tmp_path / "prompt_trace_runtime").rglob("final_visual_prompts.md")).read_text(
        encoding="utf-8"
    )
    assert "A quiet lab, cinematic lighting" in trace_content
    assert '"source": "storyboard_workbench.frame_image_regeneration"' in trace_content
    assert '"workflow": "selfhost/image_z_image_turbo_gguf.json"' in trace_content
    assert '"requested_workflow": "selfhost/image_z_image_turbo_gguf.json"' in trace_content
    assert '"canvas_width": 768' in trace_content
    assert '"canvas_height": 768' in trace_content


@pytest.mark.asyncio
async def test_execute_frame_image_regeneration_records_default_workflow_in_prompt_trace(tmp_path):
    from api.workbench.frame_image_regeneration import execute_frame_image_regeneration
    from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
    from tests.test_storyboard_frame_regeneration import (
        RecordingArtifactRepository,
        RecordingObjectStore,
        RecordingTraceRepository,
        UnusedPromptPlanRepository,
    )

    generated = tmp_path / "generated.png"
    generated.write_bytes(b"image")
    service = StoryboardWorkbenchService(
        artifact_repository=RecordingArtifactRepository(created_versions=[]),
        object_store=RecordingObjectStore(uploaded_files=[]),
        trace_repository=RecordingTraceRepository(events=[]),
        prompt_plan_repository=UnusedPromptPlanRepository(),
    )
    media = _FakeMedia(generated, default_workflow="selfhost/default_image_trace.json")
    core = type(
        "Core",
        (),
        {
            "media": media,
            "storyboard_workbench_service": service,
            "storyboard_workbench_state_store": _FakeStateStore(),
            "prompt_plan_repository": _FakePromptPlanRepository(),
            "prompt_trace_output_dir": tmp_path / "prompt_trace_runtime",
        },
    )()

    await execute_frame_image_regeneration(
        core=core,
        task_id="regen-task-default-workflow",
        request_params={
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "prompt_plan_id": "prompt_plan_001",
            "artifact_id": "artifact_frame_0001_image",
            "provider": "comfyui",
            "media_width": 768,
            "media_height": 768,
        },
    )

    trace_content = next((tmp_path / "prompt_trace_runtime").rglob("final_visual_prompts.md")).read_text(
        encoding="utf-8"
    )
    assert '"requested_workflow": null' in trace_content
    assert '"workflow": "selfhost/default_image_trace.json"' in trace_content
    assert '"canvas_width": 768' in trace_content
    assert '"canvas_height": 768' in trace_content


@pytest.mark.asyncio
async def test_task_manager_embedded_submitter_executes_frame_regeneration_when_executor_configured():
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    calls: list[dict[str, Any]] = []

    async def executor(*, task_id: str, request_params: dict[str, Any], progress_dispatcher=None):
        calls.append(
            {
                "task_id": task_id,
                "request_params": request_params,
                "has_progress": progress_dispatcher is not None,
            }
        )
        return {"ok": True}

    executor_registry = TaskExecutorRegistry()
    executor_registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    manager = TaskManager(executor_registry=executor_registry)
    await manager.start()
    try:
        submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)
        submission = await submitter.reserve_frame_image_regeneration(
            generation_fingerprint="fingerprint-frame-0001",
            request_params={"workspace_id": "workspace_1"},
        )
        await manager.wait_for_task_completion_for_test(submission.task_id)
    finally:
        await manager.stop()

    assert calls == [
        {
            "task_id": submission.task_id,
            "request_params": {
                "workspace_id": "workspace_1",
            },
            "has_progress": True,
        }
    ]


@pytest.mark.asyncio
async def test_task_manager_submitter_reports_unavailable_when_embedded_executor_is_missing():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    manager = TaskManager()
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": (
            "frame image regeneration execution is not configured"
        ),
    }
