import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.config import config_manager
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.timing_planner import TimingPlan


def _workflow_info(key: str) -> dict:
    source, name = key.split("/", 1)
    return {
        "name": name,
        "display_name": f"{name} - {source.title()}",
        "source": source,
        "path": f"workflows/{key}",
        "key": key,
    }


class _ResolverService:
    def __init__(self, defaults: dict[str, str]):
        self.defaults = defaults

    def _resolve_workflow(self, workflow=None, workflow_domain=None):
        key = workflow or self.defaults[workflow_domain or "tts"]
        return _workflow_info(key)


class _DummyCore:
    def __init__(self, *, tts_defaults=None, media_defaults=None):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.frame_processor = SimpleNamespace()
        self.tts = _ResolverService(tts_defaults or {"tts": "selfhost/tts_edge.json"})
        self.media = _ResolverService(
            media_defaults
            or {
                "image": "selfhost/image_z_image_turbo.json",
                "video": "runninghub/video_wan2.1_fusionx.json",
            }
        )


class _RecordingAlignmentService:
    def __init__(self):
        self.calls = []
        self.duration_calls = []

    def align_blocks(self, blocks, sentences, language=None):
        self.calls.append(([block.id for block in blocks], [sentence.id for sentence in sentences]))
        return list(sentences)

    def align_blocks_by_duration(self, blocks, sentences):
        self.duration_calls.append(([block.id for block in blocks], [sentence.id for sentence in sentences]))
        return list(sentences)


def _build_ctx(
    *,
    frame_template: str = "1080x1920/image_default.html",
    tts_inference_mode: str = "comfyui",
    tts_workflow: str | None = None,
    media_workflow: str | None = None,
) -> PipelineContext:
    ctx = PipelineContext(input_text="topic", params={})
    ctx.config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        tts_inference_mode=tts_inference_mode,
        tts_workflow=tts_workflow,
        media_workflow=media_workflow,
        frame_template=frame_template,
    )
    return ctx


def test_resolve_asset_execution_mode_uses_staged_mode_for_default_selfhost_image_workflows():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx()

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.tts_workflow_key == "selfhost/tts_edge.json"
    assert execution_mode.media_workflow_key == "selfhost/image_z_image_turbo.json"
    assert execution_mode.media_domain == "image"
    assert execution_mode.is_runninghub is False
    assert execution_mode.use_staged_mode is True


def test_resolve_asset_execution_mode_disables_staged_mode_for_explicit_video_workflow():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(media_workflow="selfhost/video_wan2.1_fusionx.json")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.template_type == "image"
    assert execution_mode.media_domain == "video"
    assert execution_mode.media_workflow_key == "selfhost/video_wan2.1_fusionx.json"
    assert execution_mode.use_staged_mode is False


def test_resolve_asset_execution_mode_disables_staged_mode_for_local_tts():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_ctx(tts_inference_mode="local")

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.tts_workflow_key is None
    assert execution_mode.use_staged_mode is False


def test_resolve_effective_tts_audio_strategy_uses_master_track_for_legacy_comfyui_auto():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_storyboard_ctx(tts_inference_mode="comfyui")

    assert pipeline._resolve_effective_tts_audio_strategy(ctx) == "master_track"


class _RecordingFrameProcessor:
    def __init__(self, *, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    async def _step_generate_audio(self, frame, config):
        self.calls.append(("audio", frame.index))
        if self.fail_on == ("audio", frame.index):
            raise RuntimeError(f"audio failed for frame {frame.index}")
        frame.audio_path = f"audio-{frame.index}.mp3"
        frame.duration = float(frame.index + 1)

    async def _step_generate_media(self, frame, config):
        self.calls.append(("media", frame.index))
        if self.fail_on == ("media", frame.index):
            raise RuntimeError(f"media failed for frame {frame.index}")
        frame.media_type = "image"
        frame.image_path = f"image-{frame.index}.png"

    async def _step_compose_frame(self, frame, storyboard, config):
        self.calls.append(("compose", frame.index))
        frame.composed_image_path = f"composed-{frame.index}.png"

    async def _step_create_video_segment(self, frame, config):
        self.calls.append(("segment", frame.index))
        frame.video_segment_path = f"segment-{frame.index}.mp4"


def _build_storyboard_ctx(**kwargs) -> PipelineContext:
    ctx = _build_ctx(**kwargs)
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="scene 1", image_prompt="prompt 1"),
            StoryboardFrame(index=1, narration="scene 2", image_prompt="prompt 2"),
        ],
    )
    return ctx


@pytest.mark.asyncio
async def test_produce_assets_runs_staged_selfhost_image_flow_in_phase_order():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("audio", 0),
        ("audio", 1),
        ("media", 0),
        ("media", 1),
        ("compose", 0),
        ("compose", 1),
        ("segment", 0),
        ("segment", 1),
    ]
    assert ctx.storyboard.total_duration == 3.0
    assert [frame.video_segment_path for frame in ctx.storyboard.frames] == [
        "segment-0.mp4",
        "segment-1.mp4",
    ]


@pytest.mark.asyncio
async def test_produce_assets_legacy_comfyui_auto_prepares_master_track_audio_first(monkeypatch):
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx(tts_inference_mode="comfyui")
    calls = []

    async def fake_prepare(context):
        calls.append([frame.index for frame in context.storyboard.frames])
        for frame in context.storyboard.frames:
            frame.audio_path = f"master-{frame.index}.mp3"
            frame.duration = 2.0

    monkeypatch.setattr(pipeline, "_prepare_legacy_master_track_audio", fake_prepare, raising=False)

    await pipeline.produce_assets(ctx)

    assert calls == [[0, 1]]
    assert core.frame_processor.calls == [
        ("media", 0),
        ("media", 1),
        ("compose", 0),
        ("compose", 1),
        ("segment", 0),
        ("segment", 1),
    ]
    assert ctx.storyboard.total_duration == 4.0


@pytest.mark.asyncio
async def test_produce_assets_aborts_immediately_on_staged_image_failure():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor(fail_on=("media", 1))
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()

    with pytest.raises(RuntimeError, match="media failed for frame 1"):
        await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("audio", 0),
        ("audio", 1),
        ("media", 0),
        ("media", 1),
    ]
    assert ctx.storyboard.frames[0].video_segment_path is None
    assert ctx.storyboard.frames[1].video_segment_path is None


class _CallableFrameProcessor(_RecordingFrameProcessor):
    def __init__(self):
        super().__init__()
        self.invocations = []

    async def __call__(
        self,
        frame,
        storyboard,
        config,
        total_frames=1,
        progress_callback=None,
    ):
        self.invocations.append(frame.index)
        if progress_callback:
            progress_callback(
                ProgressEvent(
                    event_type="frame_step",
                    progress=0.0,
                    frame_current=frame.index + 1,
                    frame_total=total_frames,
                    step=1,
                    action="audio",
                )
            )
        frame.duration = 1.0
        frame.video_segment_path = f"legacy-{frame.index}.mp4"
        return frame


class _ConcurrentCallableFrameProcessor(_CallableFrameProcessor):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def __call__(
        self,
        frame,
        storyboard,
        config,
        total_frames=1,
        progress_callback=None,
    ):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            return await super().__call__(
                frame,
                storyboard,
                config,
                total_frames=total_frames,
                progress_callback=progress_callback,
            )
        finally:
            self.active -= 1


def test_resolve_asset_execution_mode_disables_runninghub_parallel_for_mixed_selfhost_media():
    pipeline = StandardPipeline(
        _DummyCore(
            tts_defaults={"tts": "runninghub/tts_edge.json"},
            media_defaults={
                "image": "selfhost/image_z_image_turbo.json",
                "video": "runninghub/video_wan2.1_fusionx.json",
            },
        )
    )
    ctx = _build_ctx()

    execution_mode = pipeline._resolve_asset_execution_mode(ctx)

    assert execution_mode.is_runninghub is True
    assert execution_mode.use_staged_mode is False
    assert execution_mode.use_runninghub_parallel is False


@pytest.mark.asyncio
async def test_produce_assets_emits_monotonic_staged_progress():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    events = []
    ctx.progress_callback = events.append

    await pipeline.produce_assets(ctx)

    frame_events = [event for event in events if event.event_type == "frame_step"]
    assert [(event.step, event.frame_current) for event in frame_events] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
        (3, 1),
        (3, 2),
        (4, 1),
        (4, 2),
    ]
    assert [event.progress for event in frame_events] == sorted(
        event.progress for event in frame_events
    )
    assert frame_events[-1].progress == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_produce_assets_keeps_callable_frame_processor_path_for_runninghub(monkeypatch):
    core = _DummyCore(
        tts_defaults={"tts": "runninghub/tts_edge.json"},
        media_defaults={
            "image": "runninghub/image_flux.json",
            "video": "runninghub/video_wan2.1_fusionx.json",
        },
    )
    core.frame_processor = _CallableFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    monkeypatch.setattr(config_manager.config.comfyui, "runninghub_concurrent_limit", 1)

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.invocations == [0, 1]
    assert [frame.video_segment_path for frame in ctx.storyboard.frames] == [
        "legacy-0.mp4",
        "legacy-1.mp4",
    ]


@pytest.mark.asyncio
async def test_produce_assets_staged_skips_existing_audio_and_media():
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    ctx.storyboard.frames[0].audio_path = "existing-0.mp3"
    ctx.storyboard.frames[0].duration = 9.0
    ctx.storyboard.frames[1].image_prompt = None
    ctx.storyboard.frames[1].image_path = "existing-1.png"
    ctx.storyboard.frames[1].media_type = "image"

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("audio", 1),
        ("media", 0),
        ("compose", 0),
        ("compose", 1),
        ("segment", 0),
        ("segment", 1),
    ]
    assert ctx.storyboard.frames[0].audio_path == "existing-0.mp3"
    assert ctx.storyboard.frames[1].image_path == "existing-1.png"
    assert ctx.storyboard.total_duration == 11.0


@pytest.mark.asyncio
async def test_produce_assets_legacy_comfyui_per_frame_override_skips_master_track_prep(monkeypatch):
    core = _DummyCore()
    core.frame_processor = _RecordingFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx(tts_inference_mode="comfyui")
    ctx.config.tts_audio_strategy = "per_frame"
    calls = []

    async def fake_prepare(context):
        calls.append("called")

    monkeypatch.setattr(pipeline, "_prepare_legacy_master_track_audio", fake_prepare, raising=False)

    await pipeline.produce_assets(ctx)

    assert calls == []
    assert core.frame_processor.calls[:2] == [("audio", 0), ("audio", 1)]


@pytest.mark.asyncio
async def test_prepare_legacy_master_track_audio_uses_ctx_task_dir_for_frame_clips(monkeypatch, tmp_path):
    core = _DummyCore()
    core.alignment_service = _RecordingAlignmentService()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx(tts_inference_mode="comfyui")
    ctx.task_dir = str(tmp_path / "task-1")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="scene 1",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=1.0,
            ),
            SentenceUnit(
                id="sentence-2",
                text="scene 2",
                frame_indices=[1],
                block_id="block-2",
                source_start=0.0,
                source_end=1.0,
            ),
        ],
        blocks=[
            AudioBlock(id="block-1", text="scene 1", start=0.0, end=1.0, source_frame_indices=[0]),
            AudioBlock(id="block-2", text="scene 2", start=1.0, end=2.0, source_frame_indices=[1]),
        ],
    )

    async def fake_synthesize(context):
        master_audio_path = Path(context.task_dir) / "audio" / "master_audio.wav"
        master_audio_path.parent.mkdir(parents=True, exist_ok=True)
        master_audio_path.write_bytes(b"wav")
        return str(master_audio_path), 2.0

    extracted_paths = []

    def fake_extract(input_path, output_path, *, start_time, end_time):
        extracted_paths.append(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"mp3")
        return output_path

    monkeypatch.setattr(pipeline, "_synthesize_hyperframes_audio", fake_synthesize)
    monkeypatch.setattr(pipeline, "_align_legacy_master_track_timings", lambda context: None)
    monkeypatch.setattr(pipeline, "_extract_audio_clip", fake_extract)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.get_task_frame_path",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy master-track extraction should stay inside ctx.task_dir")
        ),
    )

    await pipeline._prepare_legacy_master_track_audio(ctx)

    expected_paths = [
        str(Path(ctx.task_dir) / "frames" / "01_audio.mp3"),
        str(Path(ctx.task_dir) / "frames" / "02_audio.mp3"),
    ]
    assert extracted_paths == expected_paths
    assert [frame.audio_path for frame in ctx.storyboard.frames] == expected_paths


def test_align_legacy_master_track_timings_rejects_unsupported_engine():
    core = _DummyCore()
    core.alignment_service = _RecordingAlignmentService()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx(tts_inference_mode="comfyui")
    ctx.config.subtitle_alignment_engine = "bogus_engine"
    ctx.timing_plan = TimingPlan(
        sentences=[SentenceUnit(id="sentence-1", text="scene 1", frame_indices=[0], block_id="block-1")],
        blocks=[AudioBlock(id="block-1", text="scene 1", start=0.0, end=1.0, source_frame_indices=[0])],
    )

    with pytest.raises(ValueError, match="Unsupported subtitle_alignment_engine"):
        pipeline._align_legacy_master_track_timings(ctx)

    assert core.alignment_service.calls == []
    assert core.alignment_service.duration_calls == []


@pytest.mark.asyncio
async def test_produce_assets_disables_runninghub_parallel_for_mixed_selfhost_media(monkeypatch):
    core = _DummyCore(
        tts_defaults={"tts": "runninghub/tts_edge.json"},
        media_defaults={
            "image": "selfhost/image_z_image_turbo.json",
            "video": "runninghub/video_wan2.1_fusionx.json",
        },
    )
    core.frame_processor = _ConcurrentCallableFrameProcessor()
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_ctx()
    monkeypatch.setattr(config_manager.config.comfyui, "runninghub_concurrent_limit", 2)

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.invocations == [0, 1]
    assert core.frame_processor.max_active == 1


@pytest.mark.asyncio
async def test_post_production_uses_default_concat_for_standard_pipeline(monkeypatch, tmp_path):
    calls = {}

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            calls["videos"] = videos
            calls["output"] = output
            calls["kwargs"] = kwargs
            return output

    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _FakeVideoService)

    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_storyboard_ctx()
    ctx.final_video_path = str(tmp_path / "final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"

    await pipeline.post_production(ctx)

    assert calls["videos"] == ["segment-0.mp4", "segment-1.mp4"]
    assert calls["output"] == ctx.final_video_path
    assert "method" not in calls["kwargs"]
