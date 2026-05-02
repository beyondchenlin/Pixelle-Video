import asyncio

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


@pytest.mark.asyncio
async def test_task_progress_sink_drain_surfaces_fast_unexpected_failures():
    class FailingRegistry:
        async def update_progress(self, **_kwargs):
            raise RuntimeError("progress backend failed")

    sink = TaskProgressSink(
        registry=FailingRegistry(),
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
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="progress backend failed"):
        await sink.drain()


@pytest.mark.asyncio
async def test_task_progress_sink_preserves_emit_order_when_registry_writes_complete_out_of_order():
    started = []
    first_can_finish = asyncio.Event()
    persisted = []

    class OrderedRegistry:
        async def update_progress(self, **kwargs):
            event_type = kwargs["progress"].event_type
            started.append(event_type)
            if event_type == "synthesizing_audio":
                await first_can_finish.wait()
            persisted.append(event_type)

    sink = TaskProgressSink(
        registry=OrderedRegistry(),
        task_id="task-1",
        owner_id="worker-1",
        lease_token="token-1",
    )

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.SYNTHESIZING_AUDIO,
            progress=0.82,
        )
    )
    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.RENDERING_HYPERFRAMES,
            progress=0.90,
        )
    )

    await asyncio.sleep(0)

    assert started == ["synthesizing_audio"]
    assert persisted == []

    first_can_finish.set()
    await sink.drain()

    assert started == ["synthesizing_audio", "rendering_hyperframes"]
    assert persisted == ["synthesizing_audio", "rendering_hyperframes"]


@pytest.mark.asyncio
async def test_task_progress_sink_restarts_writer_for_events_emitted_after_worker_completes():
    persisted = []

    class RecordingRegistry:
        async def update_progress(self, **kwargs):
            persisted.append(kwargs["progress"].event_type)

    sink = TaskProgressSink(
        registry=RecordingRegistry(),
        task_id="task-1",
        owner_id="worker-1",
        lease_token="token-1",
    )

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.SYNTHESIZING_AUDIO,
            progress=0.82,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.RENDERING_HYPERFRAMES,
            progress=0.90,
        )
    )
    await sink.drain()

    assert persisted == ["synthesizing_audio", "rendering_hyperframes"]
