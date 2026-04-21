from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.audio_edit_service import AutoEditorTimeline
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


class _HyperframesFrameProcessor:
    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.calls: list[tuple] = []

    async def __call__(self, frame, storyboard, config, total_frames=1, progress_callback=None):
        self.calls.append(("legacy_call", frame.index))
        frame.video_segment_path = str(self.tmp_path / f"legacy-{frame.index}.mp4")
        frame.duration = 1.0
        return frame

    async def _step_generate_audio(self, frame, config):
        self.calls.append(("audio", frame.index))
        frame.audio_path = str(self.tmp_path / f"{frame.index:02d}_audio.mp3")
        frame.duration = 1.0

    async def _step_generate_media(self, frame, config):
        self.calls.append(("media", frame.index))
        frame.media_type = "image"
        frame.image_path = str(self.tmp_path / f"{frame.index:02d}_raw.png")

    async def _step_compose_frame(self, frame, storyboard, config, *, body_text_override=None):
        self.calls.append(("compose", frame.index, body_text_override))
        frame.composed_image_path = str(self.tmp_path / f"{frame.index:02d}_shell.png")

    async def _step_create_video_segment(self, frame, config):
        self.calls.append(("segment", frame.index))
        frame.video_segment_path = str(self.tmp_path / f"{frame.index:02d}_segment.mp4")


class _FakeTTS:
    def __init__(self):
        self.calls: list[dict] = []

    def _resolve_workflow(self, workflow=None, workflow_domain=None):
        key = workflow or "selfhost/tts_edge.json"
        return _workflow_info(key)

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return str(output_path)


class _FakeAlignmentService:
    def __init__(self):
        self.calls: list[tuple[list[str], list[str]]] = []

    def align_blocks(self, blocks, sentences, language=None):
        self.calls.append(
            ([block.id for block in blocks], [sentence.id for sentence in sentences])
        )
        for sentence in sentences:
            sentence.source_start = 0.1
            sentence.source_end = 1.1
        return list(sentences)


class _FakeAudioEditService:
    def __init__(self):
        self.remap_calls: list[object] = []
        self.trim_calls: list[tuple[str, str]] = []

    def trim_audio_and_export_timeline(self, audio_path, output_path):
        self.trim_calls.append((audio_path, output_path))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"trimmed-audio")
        return SimpleNamespace(
            trimmed_audio_path=output_path,
            timeline=AutoEditorTimeline(
                chunks=[[0, 10, 0.0], [10, 20, 1.0], [20, 30, 0.0], [30, 60, 1.0]],
                timebase=10.0,
            ),
        )

    def export_trimmed_audio_and_timeline(self, audio_path, output_path):
        return self.trim_audio_and_export_timeline(audio_path, output_path)

    def remap_sentence_units(self, sentence_units, timeline):
        self.remap_calls.append(timeline)
        for sentence in sentence_units:
            sentence.remapped_start = timeline.remap_time(0.1)
            sentence.remapped_end = timeline.remap_time(1.2)
        return list(sentence_units)

    def remap_sentence_units_from_audio(self, audio_path, sentence_units):
        return self.remap_sentence_units(
            sentence_units,
            AutoEditorTimeline(
                chunks=[[0, 10, 0.0], [10, 20, 1.0], [20, 30, 0.0], [30, 60, 1.0]],
                timebase=10.0,
            ),
        )


class _FakeHyperFramesProjectService:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.manifest = None

    def write_project_data(self, manifest, master_audio_duration=None):
        self.manifest = manifest
        data_dir = self.project_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            task_dir=self.project_dir.parent,
            project_dir=self.project_dir,
            data_dir=data_dir,
            manifest_path=data_dir / "render_manifest.json",
            captions_path=data_dir / "captions.json",
        )


class _FakeHyperFramesRenderer:
    def __init__(self):
        self.calls: list[dict] = []

    def render(self, project_dir, output_path=None):
        self.calls.append({"project_dir": project_dir, "output_path": output_path})
        resolved_output = Path(output_path or Path(project_dir) / "renders" / "task.mp4")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        resolved_output.write_bytes(b"video")
        return str(resolved_output)


class _NoConcatVideoService:
    def concat_videos(self, videos, output, **kwargs):
        raise AssertionError("legacy concat path should not run in hyperframes mode")


class _RecordingVideoService:
    def __init__(self, calls: dict):
        self.calls = calls

    def concat_videos(self, videos, output, **kwargs):
        self.calls["videos"] = videos
        self.calls["output"] = output
        self.calls["kwargs"] = kwargs
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"legacy-video")
        return output


class _DummyCore:
    def __init__(self, tmp_path: Path):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.tts = _FakeTTS()
        self.media = _ResolverService({"image": "selfhost/image_z_image_turbo.json"})
        self.frame_processor = _HyperframesFrameProcessor(tmp_path)
        self.alignment_service = _FakeAlignmentService()
        self.audio_edit_service = _FakeAudioEditService()
        self.hyperframes_project_service = _FakeHyperFramesProjectService(
            tmp_path / "task-1" / "hyperframes"
        )
        self.hyperframes_renderer = _FakeHyperFramesRenderer()


def _build_storyboard_context(
    tmp_path: Path,
    *,
    render_backend: str = "hyperframes",
    silence_trim_tool: str | None = None,
) -> PipelineContext:
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        render_backend=render_backend,
        tts_inference_mode="local",
        frame_template="1080x1920/image_life_insights_light.html",
        silence_trim_tool=silence_trim_tool,
    )
    frames = [
        StoryboardFrame(index=0, narration="Sentence 1.", image_prompt="prompt 1"),
        StoryboardFrame(index=1, narration="Sentence 2.", image_prompt="prompt 2"),
    ]
    storyboard = Storyboard(title="Demo", config=config, frames=frames)
    ctx = PipelineContext(input_text="topic", params={})
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path / "task-1")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.config = config
    ctx.storyboard = storyboard
    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
            ),
            SentenceUnit(
                id="sentence-2",
                text="Sentence 2.",
                frame_indices=[1],
                block_id="block-2",
            ),
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1.",
                source_frame_indices=[0],
            ),
            AudioBlock(
                id="block-2",
                text="Sentence 2.",
                source_frame_indices=[1],
            ),
        ],
    )
    return ctx


@pytest.mark.asyncio
async def test_produce_assets_uses_shell_only_hyperframes_path_without_segments(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)

    await pipeline.produce_assets(ctx)

    assert core.frame_processor.calls == [
        ("media", 0),
        ("compose", 0, ""),
        ("media", 1),
        ("compose", 1, ""),
    ]
    assert [frame.composed_image_path for frame in ctx.storyboard.frames] == [
        str(tmp_path / "00_shell.png"),
        str(tmp_path / "01_shell.png"),
    ]
    assert [frame.video_segment_path for frame in ctx.storyboard.frames] == [None, None]


@pytest.mark.asyncio
async def test_post_production_renders_with_hyperframes_and_uses_raw_media_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, silence_trim_tool="auto_editor")
    internal_output = tmp_path / "task-1" / "final.mp4"
    requested_output = tmp_path / "deliverables" / "demo.mp4"
    ctx.final_video_path = str(internal_output)
    ctx.params["output_path"] = str(requested_output)

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        frame.composed_image_path = str(tmp_path / f"{frame.index:02d}_shell.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")
        Path(frame.composed_image_path).write_text("shell", encoding="utf-8")

    def fake_concat_audio_files(audio_paths, output_path):
        Path(output_path).write_bytes(b"master-audio")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_get_audio_duration(audio_path):
        audio_path = str(audio_path)
        if audio_path.endswith("trimmed_master_audio.wav"):
            return 1.8
        if audio_path.endswith("master_audio.wav"):
            return 2.6
        return 1.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest

    assert [call["text"] for call in core.tts.calls] == ["Sentence 1.", "Sentence 2."]
    assert core.alignment_service.calls == [
        (["block-1", "block-2"], ["sentence-1", "sentence-2"])
    ]
    assert core.audio_edit_service.trim_calls == [
        (str(Path(ctx.task_dir) / "audio" / "master_audio.wav"), str(Path(ctx.task_dir) / "audio" / "trimmed_master_audio.wav"))
    ]
    assert core.audio_edit_service.remap_calls
    assert manifest.master_audio_path.endswith("trimmed_master_audio.wav")
    assert ctx.storyboard.total_duration == pytest.approx(1.8)
    assert [clip.media_path for clip in manifest.visual_clips] == [
        str(tmp_path / "00_raw.png"),
        str(tmp_path / "01_raw.png"),
    ]
    assert [clip.media_type for clip in manifest.visual_clips] == ["image", "image"]
    assert manifest.template_id == "image_life_insights_light"
    assert manifest.sentence_units[0].remapped_start == pytest.approx(0.0)
    assert manifest.sentence_units[1].remapped_end == pytest.approx(0.2)
    assert core.hyperframes_renderer.calls == [
        {
            "project_dir": str(tmp_path / "task-1" / "hyperframes"),
            "output_path": str(internal_output),
        }
    ]
    assert requested_output.exists()
    assert ctx.final_video_path == str(requested_output)
    assert ctx.storyboard.final_video_path == str(requested_output)


@pytest.mark.asyncio
async def test_post_production_uses_stable_master_audio_duration_for_storyboard_timeline(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path):
        Path(output_path).write_bytes(b"master-wav")

    def fake_get_audio_duration(audio_path):
        audio_path = str(audio_path)
        if audio_path.endswith("master_audio.wav"):
            return 1.9
        return 1.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert manifest.master_audio_path.endswith("master_audio.wav")
    assert [block.audio_path for block in manifest.audio_blocks] == [
        str(Path(ctx.task_dir) / "audio" / "block-1.wav"),
        str(Path(ctx.task_dir) / "audio" / "block-2.wav"),
    ]
    assert manifest.audio_blocks[-1].end == pytest.approx(1.9)
    assert ctx.storyboard.total_duration == pytest.approx(1.9)


@pytest.mark.asyncio
async def test_post_production_skips_shell_image_fallback_for_missing_raw_media(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = None
        frame.composed_image_path = str(tmp_path / f"{frame.index:02d}_shell.png")
        Path(frame.composed_image_path).write_text("shell", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path):
        Path(output_path).write_bytes(b"master-wav")

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert manifest.visual_clips == []


@pytest.mark.asyncio
async def test_post_production_warns_when_hyperframes_falls_back_to_legacy_rendering(monkeypatch, tmp_path):
    calls = {}
    warnings: list[str] = []

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        lambda: _RecordingVideoService(calls),
    )
    monkeypatch.setattr("pixelle_video.pipelines.standard.logger.warning", lambda message: warnings.append(message))

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, render_backend="hyperframes")
    ctx.config.frame_template = "1080x1920/default.html"
    ctx.final_video_path = str(tmp_path / "legacy-final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"

    await pipeline.post_production(ctx)

    assert calls["videos"] == ["segment-0.mp4", "segment-1.mp4"]
    assert warnings
    assert "HyperFrames" in warnings[0]


@pytest.mark.asyncio
async def test_post_production_keeps_legacy_concat_path_when_not_in_hyperframes_mode(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        lambda: _RecordingVideoService(calls),
    )

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, render_backend="cinematic")
    ctx.final_video_path = str(tmp_path / "legacy-final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"

    await pipeline.post_production(ctx)

    assert calls["videos"] == ["segment-0.mp4", "segment-1.mp4"]
    assert calls["output"] == ctx.final_video_path
    assert calls["kwargs"]["bgm_mode"] == "loop"
