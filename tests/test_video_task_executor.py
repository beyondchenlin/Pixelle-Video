from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_video_generation_executor_persists_storage_identity_without_transport_url(
    tmp_path,
):
    from api.tasks.artifacts import LocalArtifactStore
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.models import TaskType
    from api.video.executor_factory import register_video_generation_executor

    generated = tmp_path / "generated" / "final.mp4"

    class Core:
        def __init__(self) -> None:
            self.calls = []

        async def generate_video(self, **kwargs):
            self.calls.append(kwargs)
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_bytes(b"video")
            return SimpleNamespace(video_path=str(generated), duration=2.5)

    core = Core()
    registry = TaskExecutorRegistry()
    register_video_generation_executor(
        registry,
        core_provider=lambda: core,
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
    )

    result = await registry.execute(
        TaskType.VIDEO_GENERATION,
        task_id="task-video-1",
        request_params={"text": "demo", "request_id": "req_1"},
        progress_dispatcher=object(),
    )

    assert result["storage_key"] == "task-video-1/final.mp4"
    assert result["duration"] == 2.5
    assert result["file_size"] == 5
    assert "video_url" not in result
    assert core.calls[0]["api_task_id"] == "task-video-1"
    assert core.calls[0]["progress_dispatcher"] is not None
    assert "generation_fingerprint" not in core.calls[0]
