from types import SimpleNamespace

import pytest

from api.routers import video
from api.schemas.video import VideoGenerateRequest
from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus, TaskType
from pixelle_video.models.progress import ProgressEvent, ProgressEventType


class FakeTaskManager:
    def __init__(self, *, created: bool) -> None:
        self.created = created
        self.reserve_calls = []
        self.execution_mode = "embedded"

    async def reserve_or_reuse_generation_task(
        self,
        *,
        task_type,
        generation_fingerprint,
        request_params,
    ):
        self.reserve_calls.append(
            {
                "task_type": task_type,
                "generation_fingerprint": generation_fingerprint,
                "request_params": request_params,
            }
        )
        task = SimpleNamespace(
            task_id="task-1",
            task_type=task_type,
            request_params=request_params,
        )
        return SimpleNamespace(
            task=task,
            created=self.created,
            reused_reason=None if self.created else "active",
        )


def build_request() -> VideoGenerateRequest:
    return VideoGenerateRequest(text="demo", tts_inference_mode="local")


@pytest.mark.asyncio
async def test_async_video_endpoint_returns_reused_task_without_execution(monkeypatch):
    manager = FakeTaskManager(created=False)
    monkeypatch.setattr(video, "task_manager", manager)

    response = await video.generate_video_async(
        build_request(),
        pixelle_video=SimpleNamespace(),
        request=SimpleNamespace(base_url="http://test/"),
    )

    assert response.task_id == "task-1"
    assert response.message == "Task already running"
    assert manager.reserve_calls[0]["task_type"] == TaskType.VIDEO_GENERATION


@pytest.mark.asyncio
async def test_async_video_endpoint_submits_new_task_without_router_execution(monkeypatch):
    manager = FakeTaskManager(created=True)
    monkeypatch.setattr(video, "task_manager", manager)

    response = await video.generate_video_async(
        build_request(),
        pixelle_video=SimpleNamespace(),
        request=SimpleNamespace(base_url="http://test/"),
    )

    assert response.task_id == "task-1"
    request_params = manager.reserve_calls[0]["request_params"]
    assert request_params["generation_fingerprint"]
    assert request_params["request_id"].startswith("req_")
    assert manager.reserve_calls[0]["task_type"] == TaskType.VIDEO_GENERATION


@pytest.mark.asyncio
async def test_async_video_generation_fingerprint_ignores_request_id(monkeypatch):
    manager = FakeTaskManager(created=False)
    request_ids = iter(["req_first", "req_second"])
    monkeypatch.setattr(video, "task_manager", manager)
    monkeypatch.setattr(video, "new_correlation_id", lambda _prefix: next(request_ids))

    for _ in range(2):
        await video.generate_video_async(
            build_request(),
            pixelle_video=SimpleNamespace(),
            request=SimpleNamespace(base_url="http://test/"),
        )

    first_call, second_call = manager.reserve_calls
    assert first_call["request_params"]["request_id"] == "req_first"
    assert second_call["request_params"]["request_id"] == "req_second"
    assert first_call["generation_fingerprint"] == second_call["generation_fingerprint"]


@pytest.mark.asyncio
async def test_embedded_registry_task_persists_progress_from_pipeline_dispatcher():
    manager = TaskManager(execution_mode="embedded")
    outcome = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-progress",
        request_params={"text": "demo"},
    )

    async def generate(progress_dispatcher=None):
        progress_dispatcher.emit(
            ProgressEvent(
                event_type=ProgressEventType.SYNTHESIZING_AUDIO,
                progress=0.82,
            )
        )
        return {"ok": True}

    await manager.execute_task(outcome.task.task_id, generate)
    future = manager._task_futures[outcome.task.task_id]
    await future

    task = await manager.get_task(outcome.task.task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.progress is not None
    assert task.progress.event_type == "synthesizing_audio"
