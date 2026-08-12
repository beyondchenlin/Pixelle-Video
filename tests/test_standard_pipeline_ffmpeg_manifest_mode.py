from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.services.timing_planner import TimingPlan


class _DummyCore:
    def __init__(self):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.tts = object()
        self.media = _ResolverService()
        self.frame_processor = object()
        self.alignment_service = object()
        self.audio_edit_service = None
        self.hyperframes_project_service = None
        self.hyperframes_renderer = None
        self.persistence = _RecordingPersistence()


class _ResolverService:
    def _resolve_workflow(self, workflow=None, workflow_domain=None):
        key = workflow or "selfhost/image_z_image_turbo_gguf.json"
        return {"key": key}


class _RecordingPersistence:
    def __init__(self):
        self.saved_metadata = None
        self.saved_storyboard = None

    async def save_task_metadata(self, task_id, metadata):
        self.saved_metadata = (task_id, metadata)

    async def save_storyboard(self, task_id, storyboard):
        self.saved_storyboard = (task_id, storyboard)


def _build_context(tmp_path: Path) -> PipelineContext:
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        render_backend="ffmpeg_manifest",
        tts_inference_mode="local",
        frame_template="1080x1920/image_default.html",
        video_fps=30,
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
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=1.0,
            ),
            SentenceUnit(
                id="sentence-2",
                text="Sentence 2.",
                frame_indices=[1],
                block_id="block-2",
                source_start=1.0,
                source_end=2.5,
            ),
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1.",
                source_frame_indices=[0],
                start=0.0,
                end=1.0,
            ),
            AudioBlock(
                id="block-2",
                text="Sentence 2.",
                source_frame_indices=[1],
                start=1.0,
                end=2.5,
            ),
        ],
    )
    master_audio = tmp_path / "task-1" / "audio" / "master_audio.wav"
    master_audio.parent.mkdir(parents=True, exist_ok=True)
    master_audio.write_bytes(b"audio")
    ctx.master_audio_path = str(master_audio)
    ctx.master_audio_duration = 2.5
    storyboard.total_duration = 2.5
    return ctx


@pytest.mark.asyncio
async def test_post_production_routes_ffmpeg_manifest_to_renderer(monkeypatch, tmp_path):
    calls = {}

    class FakeFfmpegManifestRenderer:
        def render(self, **kwargs):
            calls.update(kwargs)
            output_path = Path(kwargs["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"video")
            return str(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.ffmpeg_manifest_renderer.FfmpegManifestRenderer",
        FakeFfmpegManifestRenderer,
    )

    core = _DummyCore()
    pipeline = StandardPipeline(core)
    ctx = _build_context(tmp_path)
    bgm_path = tmp_path / "default.mp3"
    bgm_path.write_bytes(b"music")
    captions_path = tmp_path / "captions.ass"
    captions_path.write_text("[Script Info]\n", encoding="utf-8")
    ctx.params["bgm_path"] = str(bgm_path)
    ctx.params["bgm_volume"] = 0.4
    ctx.params["bgm_mode"] = "once"

    first_shell = tmp_path / "00_shell.png"
    second_motion = tmp_path / "01_motion.mp4"
    first_shell.write_bytes(b"png")
    second_motion.write_bytes(b"video")
    ctx.storyboard.frames[0].composed_image_path = str(first_shell)
    ctx.storyboard.frames[0].image_path = str(tmp_path / "00_raw.png")
    ctx.storyboard.frames[0].duration = 1.0
    ctx.storyboard.frames[1].composed_image_path = str(tmp_path / "01_shell.png")
    ctx.storyboard.frames[1].element_motion_video_path = str(second_motion)
    ctx.storyboard.frames[1].element_animation_manifest_path = "element/frame_001.json"
    ctx.storyboard.frames[1].duration = 1.5

    monkeypatch.setattr(
        pipeline,
        "_export_ass_for_manifest_if_needed",
        lambda context, manifest: SimpleNamespace(master=captions_path),
    )

    await pipeline.post_production(ctx)

    manifest = calls["manifest"]
    execution_plan = calls["execution_plan"]
    assert calls["output_path"] == str(tmp_path / "task-1" / "final.mp4")
    assert calls["ass_path"] == str(captions_path)
    assert calls["bgm_path"] == str(bgm_path)
    assert calls["bgm_volume"] == 0.4
    assert calls["bgm_mode"] == "once"
    assert manifest.master_audio_path == str(Path(ctx.master_audio_path))
    assert [(clip.start, clip.end) for clip in manifest.visual_clips] == [
        (0.0, 1.0),
        (1.0, 2.5),
    ]
    assert [clip.media_path for clip in manifest.visual_clips] == [
        str(first_shell),
        str(second_motion),
    ]
    assert [clip.media_type for clip in manifest.visual_clips] == ["image", "video"]
    assert manifest.visual_clips[0].source_kind == "template_frame"
    assert manifest.visual_clips[1].source_kind == "element_motion_video"
    assert (
        manifest.visual_clips[1].element_animation_manifest_path
        == "element/frame_001.json"
    )
    assert execution_plan.requested_backend == "ffmpeg_manifest"
    assert execution_plan.effective_backend == "ffmpeg_manifest"
    assert ctx.observability["render_execution_plan"]["effective_backend"] == (
        "ffmpeg_manifest"
    )
    assert ctx.final_video_path == str(tmp_path / "task-1" / "final.mp4")
    assert ctx.storyboard.final_video_path == ctx.final_video_path


def test_resolve_effective_backend_uses_capability_resolver_for_ffmpeg(tmp_path):
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_context(tmp_path)

    assert pipeline._resolve_effective_render_backend(ctx) == "ffmpeg_manifest"
    assert pipeline._get_render_backend_fallback_reason(ctx) is None


def test_build_render_manifest_uses_canvas_contract_separately_from_media(tmp_path):
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_context(tmp_path)
    ctx.config.canvas_width = 1280
    ctx.config.canvas_height = 720
    ctx.config.media_width = 768
    ctx.config.media_height = 768

    manifest = pipeline._build_render_manifest_for_current_timeline(ctx)

    assert manifest.version == "render_manifest.v2"
    assert (manifest.canvas_width, manifest.canvas_height) == (1280, 720)
    assert (manifest.media_width, manifest.media_height) == (768, 768)
    assert all(clip.resolved_media_box is not None for clip in manifest.visual_clips)


def test_resolve_effective_backend_records_ffmpeg_fallback_for_canvas_motion(tmp_path):
    pipeline = StandardPipeline(_DummyCore())
    ctx = _build_context(tmp_path)
    ctx.config.element_animation_enabled = True
    ctx.config.element_animation_backend = "hyperframes_canvas"

    assert pipeline._resolve_effective_render_backend(ctx) == "hyperframes_compiled"
    assert "hyperframes_canvas" in pipeline._get_render_backend_fallback_reason(ctx)


@pytest.mark.asyncio
async def test_persist_task_data_records_render_execution_plan(tmp_path):
    core = _DummyCore()
    pipeline = StandardPipeline(core)
    ctx = _build_context(tmp_path)
    output_path = Path(ctx.final_video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"video")
    ctx.storyboard.completed_at = ctx.storyboard.created_at
    ctx.result = SimpleNamespace(
        video_path=str(output_path),
        duration=2.5,
        file_size=output_path.stat().st_size,
    )
    ctx.observability["render_execution_plan"] = {
        "requested_backend": "ffmpeg_manifest",
        "effective_backend": "legacy",
        "fallback_reason": "ffmpeg_manifest requires prerendered template assets",
    }

    await pipeline._persist_task_data(ctx)

    assert core.persistence.saved_metadata is not None
    _, metadata = core.persistence.saved_metadata
    assert metadata["result"]["render_execution_plan"] == {
        "requested_backend": "ffmpeg_manifest",
        "effective_backend": "legacy",
        "fallback_reason": "ffmpeg_manifest requires prerendered template assets",
    }
