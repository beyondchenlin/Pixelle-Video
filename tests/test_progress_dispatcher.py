from types import SimpleNamespace

import pytest

from pixelle_video.models.progress import (
    CallbackProgressSink,
    ProgressDispatcher,
    ProgressEvent,
    ProgressEventType,
)
from pixelle_video.pipelines.linear import LinearVideoPipeline


class RecordingSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def test_progress_dispatcher_emits_same_event_to_all_sinks():
    first = RecordingSink()
    second = RecordingSink()
    event = ProgressEvent(
        event_type=ProgressEventType.SYNTHESIZING_AUDIO,
        progress=0.82,
    )

    ProgressDispatcher([first, second]).emit(event)

    assert first.events == [event]
    assert second.events == [event]


def test_progress_dispatcher_isolates_sink_failures():
    event = ProgressEvent(
        event_type=ProgressEventType.SYNTHESIZING_AUDIO,
        progress=0.82,
    )
    receiver = RecordingSink()

    class FailingSink:
        def emit(self, _event):
            raise RuntimeError("sink failed")

    ProgressDispatcher([FailingSink(), receiver]).emit(event)

    assert receiver.events == [event]


def test_callback_progress_sink_preserves_legacy_callback_shape():
    events = []
    sink = CallbackProgressSink(events.append)
    event = ProgressEvent(
        event_type=ProgressEventType.PREPARING_RENDER_MANIFEST,
        progress=0.86,
    )

    sink.emit(event)

    assert events == [event]


class RecordingPipeline(LinearVideoPipeline):
    async def setup_environment(self, ctx):
        pass

    async def generate_content(self, ctx):
        pass

    async def determine_title(self, ctx):
        pass

    async def plan_visuals(self, ctx):
        pass

    async def initialize_storyboard(self, ctx):
        pass

    async def produce_assets(self, ctx):
        self._report_progress(
            ctx.progress_dispatcher,
            ProgressEventType.SYNTHESIZING_AUDIO,
            0.82,
        )

    async def post_production(self, ctx):
        pass

    async def finalize(self, ctx):
        return "ok"


@pytest.mark.asyncio
async def test_linear_pipeline_combines_legacy_callback_and_dispatcher():
    legacy_events = []
    dispatcher_events = []

    class RecordingSink:
        def emit(self, event):
            dispatcher_events.append(event)

    pipeline = RecordingPipeline(SimpleNamespace(llm=None, tts=None, media=None, video=None))

    result = await pipeline(
        text="demo",
        progress_callback=legacy_events.append,
        progress_dispatcher=ProgressDispatcher([RecordingSink()]),
    )

    assert result == "ok"
    assert [event.event_type for event in legacy_events] == ["synthesizing_audio"]
    assert [event.event_type for event in dispatcher_events] == ["synthesizing_audio"]


@pytest.mark.asyncio
async def test_linear_pipeline_excludes_progress_dispatcher_from_ctx_params():
    captured = {}

    class ParamInspectingPipeline(RecordingPipeline):
        async def setup_environment(self, ctx):
            captured["params"] = dict(ctx.params)

    pipeline = ParamInspectingPipeline(SimpleNamespace(llm=None, tts=None, media=None, video=None))

    await pipeline(
        text="demo",
        progress_dispatcher=ProgressDispatcher([RecordingSink()]),
    )

    assert "progress_dispatcher" not in captured["params"]
