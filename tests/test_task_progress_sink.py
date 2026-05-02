import pytest

from api.tasks.progress import TaskProgressSink, progress_event_to_task_progress
from pixelle_video.models.progress import ProgressEvent, ProgressEventType


def test_progress_event_to_task_progress_preserves_stable_event_type():
    progress = progress_event_to_task_progress(
        ProgressEvent(
            event_type=ProgressEventType.SYNTHESIZING_AUDIO,
            progress=0.823,
        )
    )

    assert progress.event_type == "synthesizing_audio"
    assert progress.percentage == 82.3
    assert progress.message == "Generating audio..."


@pytest.mark.asyncio
async def test_task_progress_sink_writes_with_owner_and_lease():
    class RecordingRegistry:
        def __init__(self):
            self.calls = []

        async def update_progress(self, **kwargs):
            self.calls.append(kwargs)

    registry = RecordingRegistry()
    sink = TaskProgressSink(
        registry=registry,
        task_id="task-1",
        owner_id="worker-1",
        lease_token="token-1",
    )

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.RENDERING_HYPERFRAMES,
            progress=0.9,
        )
    )
    await sink.drain()

    assert registry.calls[0]["task_id"] == "task-1"
    assert registry.calls[0]["owner_id"] == "worker-1"
    assert registry.calls[0]["lease_token"] == "token-1"
    assert registry.calls[0]["progress"].event_type == "rendering_hyperframes"
