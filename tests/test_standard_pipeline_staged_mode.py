import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.config import config_manager
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.render_package import SentenceUnit
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


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


def test_standard_ai_creation_observability_summary_records_terminal_skip_and_fail_events():
    pipeline = StandardPipeline(_DummyCore())
    ctx = PipelineContext(input_text="demo", params={})

    pipeline._record_ai_creation_stage(
        ctx,
        {
            "channel": "ai_creation",
            "stage": "storyboard_planning",
            "event": "skip",
            "status": "skipped",
            "latency_ms": 0,
            "llm_call_count": 0,
            "retry_count": 0,
        },
    )
    pipeline._record_ai_creation_stage(
        ctx,
        {
            "channel": "ai_creation",
            "stage": "image_prompt_batch",
            "event": "fail",
            "status": "failed",
            "latency_ms": 42,
            "llm_call_count": 2,
            "retry_count": 1,
        },
    )

    summary = ctx.observability["ai_creation"]
    assert summary["llm_call_count"] == 2
    assert summary["slowest_stage"] == "image_prompt_batch"
    assert [item["status"] for item in summary["stages"]] == ["skipped", "failed"]


def test_extract_audio_clip_outputs_pcm_wav_with_boundary_fade(monkeypatch, tmp_path):
    pipeline = StandardPipeline(_DummyCore())
    commands = []

    def fake_run(command, capture_output=None, text=None, check=None):
        commands.append(command)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("pixelle_video.pipelines.standard.subprocess.run", fake_run)

    output_path = tmp_path / "frame.wav"
    result = pipeline._extract_audio_clip(
        "master.wav",
        str(output_path),
        start_time=1.25,
        end_time=3.25,
        fade_ms=8,
    )

    assert result == str(output_path)
    assert commands
    command = commands[0]
    assert "-af" in command
    audio_filter = command[command.index("-af") + 1]
    assert "afade=t=in:st=0:d=0.008" in audio_filter
    assert "afade=t=out:st=1.992:d=0.008" in audio_filter
    assert command[command.index("-c:a") + 1] == "pcm_s16le"


def test_concat_audio_files_applies_pcm_boundary_fade(monkeypatch, tmp_path):
    pipeline = StandardPipeline(_DummyCore())
    commands = []

    def fake_run(command, capture_output=None, text=None, check=None):
        commands.append(command)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("pixelle_video.pipelines.standard.subprocess.run", fake_run)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda path: 1.0)

    output_path = tmp_path / "joined.wav"
    pipeline._concat_audio_files(
        ["segment-1.wav", "segment-2.wav"],
        str(output_path),
        fade_ms=8,
    )

    assert commands
    command = commands[0]
    assert "-filter_complex" in command
    audio_filter = command[command.index("-filter_complex") + 1]
    assert "afade=t=out:st=0.992:d=0.008" in audio_filter
    assert "afade=t=in:st=0:d=0.008" in audio_filter
    assert "concat=n=2:v=0:a=1[out]" in audio_filter
    assert command[command.index("-c:a") + 1] == "pcm_s16le"


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


@pytest.mark.asyncio
async def test_legacy_post_production_burns_ass_before_user_output_copy(monkeypatch, tmp_path):
    calls = []

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            calls.append(("concat", output))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"concat")
            return output

        def burn_ass_subtitles(self, input_video, ass_file, output):
            calls.append(("burn", input_video, ass_file, output))
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_bytes(b"burned")
            return output

    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _FakeVideoService)

    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_storyboard_ctx()
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path / "task-1")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.params["output_path"] = str(tmp_path / "deliverables" / "final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="scene 1",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )
    ctx.creation_package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("ass",),
                    source={"frame_index": 0, "sentence_id": "sentence-1"},
                ),
            )
        ),
    )

    await pipeline.post_production(ctx)

    assert [item[0] for item in calls] == ["concat", "burn"]
    assert Path(calls[1][2]).name == "master.ass"
    assert Path(ctx.params["output_path"]).read_bytes() == b"burned"
    assert ctx.final_video_path == ctx.params["output_path"]
    assert ctx.observability["text_layer_summary"]["renderer"] == "ass"
    assert ctx.observability["text_layer_summary"]["cue_count"] == 1


def test_compile_text_layer_for_render_uses_storyboard_frame_durations():
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_storyboard_ctx()
    ctx.storyboard.frames[0].duration = 2.0
    ctx.storyboard.frames[1].duration = 3.5
    ctx.timing_plan = SimpleNamespace(sentences=[])
    ctx.creation_package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="Frame duration cue",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("ass",),
                    source={"frame_index": 1},
                ),
            )
        ),
    )

    _, cues = pipeline._compile_text_layer_for_render(ctx)

    assert cues[0].start == 2.0
    assert cues[0].end == 5.5


@pytest.mark.asyncio
async def test_determine_title_progress_does_not_regress_after_generate_content(monkeypatch):
    pipeline = StandardPipeline(_DummyCore())
    events = []
    ctx = PipelineContext(
        input_text="a sufficiently long topic for title generation",
        params={"mode": "generate", "n_scenes": 3},
        progress_callback=events.append,
    )

    async def fake_generate_narrations_from_topic(*args, **kwargs):
        return ["scene 1", "scene 2", "scene 3"]

    async def fake_generate_title(*args, **kwargs):
        return "Generated Title"

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_narrations_from_topic",
        fake_generate_narrations_from_topic,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_title",
        fake_generate_title,
    )

    await pipeline.generate_content(ctx)
    await pipeline.determine_title(ctx)

    assert [event.event_type for event in events] == [
        "generating_narrations",
        "generating_title",
    ]
    assert events[1].progress >= events[0].progress
