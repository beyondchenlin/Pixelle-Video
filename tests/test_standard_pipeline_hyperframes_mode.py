from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import AudioBlock, SentenceUnit
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan
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

    async def _step_compose_frame(self, frame, storyboard, config, *, template_body_text=None):
        self.calls.append(("compose", frame.index, template_body_text))
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
        self.duration_calls: list[tuple[list[str], list[str]]] = []

    def align_blocks(self, blocks, sentences, language=None):
        self.calls.append(
            ([block.id for block in blocks], [sentence.id for sentence in sentences])
        )
        for sentence in sentences:
            sentence.source_start = 0.1
            sentence.source_end = 1.1
        return list(sentences)

    def align_blocks_by_duration(self, blocks, sentences):
        self.duration_calls.append(
            ([block.id for block in blocks], [sentence.id for sentence in sentences])
        )
        blocks_by_id = {block.id: block for block in blocks}
        grouped = {}
        for sentence in sentences:
            grouped.setdefault(sentence.block_id, []).append(sentence)

        for block_id, group in grouped.items():
            block = blocks_by_id[block_id]
            duration = max(0.0, float(block.end) - float(block.start))
            weights = [max(1, len(sentence.text.split())) for sentence in group]
            total = sum(weights)
            cursor = 0.0
            for index, (sentence, weight) in enumerate(zip(group, weights)):
                sentence.source_start = cursor
                if index == len(group) - 1:
                    sentence.source_end = duration
                else:
                    cursor += duration * (weight / total)
                    sentence.source_end = cursor
                    continue
                cursor = duration
        return list(sentences)


class _FakeAudioEditService:
    def __init__(self):
        self.remap_calls: list[object] = []
        self.trim_calls: list[tuple[str, str, int | None]] = []

    def trim_audio_and_export_timeline(self, audio_path, output_path, margin_ms=None):
        self.trim_calls.append((audio_path, output_path, margin_ms))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"trimmed-audio")
        return SimpleNamespace(
            trimmed_audio_path=output_path,
            timeline=AutoEditorTimeline(
                chunks=[[0, 10, 0.0], [10, 20, 1.0], [20, 30, 0.0], [30, 60, 1.0]],
                timebase=10.0,
            ),
        )

    def export_trimmed_audio_and_timeline(self, audio_path, output_path, margin_ms=None):
        return self.trim_audio_and_export_timeline(audio_path, output_path, margin_ms=margin_ms)

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
        self.write_project_calls: list[dict] = []

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

    def write_project(self, manifest, *, template_params=None, master_audio_duration=None):
        self.manifest = manifest
        self.write_project_calls.append(
            {
                "manifest": manifest,
                "template_params": dict(template_params or {}),
                "master_audio_duration": master_audio_duration,
            }
        )
        return self.write_project_data(
            manifest,
            master_audio_duration=master_audio_duration,
        )


class _FakeHyperFramesRenderer:
    def __init__(self):
        self.calls: list[dict] = []

    def render(
        self,
        project_dir,
        output_path=None,
        *,
        width=None,
        height=None,
        fps=None,
        expected_duration=None,
        expect_audio=None,
    ):
        self.calls.append(
            {
                "project_dir": project_dir,
                "output_path": output_path,
                "width": width,
                "height": height,
                "fps": fps,
                "expected_duration": expected_duration,
                "expect_audio": expect_audio,
            }
        )
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


class _NoPostRenderBgmVideoService:
    def concat_videos(self, videos, output, **kwargs):
        raise AssertionError("legacy concat path should not run in hyperframes mode")

    def _add_bgm_to_video(self, *, video, bgm_path, output, volume, mode):
        raise AssertionError("BGM must be compiled as a HyperFrames audio track")


class _RecordingPersistence:
    def __init__(self):
        self.saved_metadata = None
        self.saved_storyboard = None

    async def save_task_metadata(self, task_id, metadata):
        self.saved_metadata = (task_id, metadata)

    async def save_storyboard(self, task_id, storyboard):
        self.saved_storyboard = (task_id, storyboard)


class _DummyCore:
    def __init__(self, tmp_path: Path):
        self.config = {}
        self.llm = object()
        self.video = object()
        self.tts = _FakeTTS()
        self.media = _ResolverService({"image": "selfhost/image_z_image_turbo_gguf.json"})
        self.frame_processor = _HyperframesFrameProcessor(tmp_path)
        self.alignment_service = _FakeAlignmentService()
        self.audio_edit_service = _FakeAudioEditService()
        self.hyperframes_project_service = _FakeHyperFramesProjectService(
            tmp_path / "task-1" / "hyperframes"
        )
        self.hyperframes_renderer = _FakeHyperFramesRenderer()
        self.persistence = _RecordingPersistence()


def _build_storyboard_context(
    tmp_path: Path,
    *,
    render_backend: str = "hyperframes_compiled",
    silence_trim_tool: str | None = None,
    frame_template: str = "1080x1920/image_life_insights_light.html",
) -> PipelineContext:
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        task_id="task-1",
        render_backend=render_backend,
        tts_inference_mode="local",
        frame_template=frame_template,
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


def test_hyperframes_default_template_alias_resolves_to_supported_template(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/default.html",
    )

    assert pipeline._resolve_hyperframes_template_id(ctx.config) == "image_default"
    assert pipeline._get_hyperframes_fallback_reason(ctx) is None


@pytest.mark.parametrize(
    "frame_template, expected_template_id",
    [
        ("1080x1920/default.html", "image_default"),
        ("1920x1080/image_landscape_full.html", "image_landscape_full"),
        ("1920x1080/image_landscape_minimal.html", "image_landscape_minimal"),
    ],
)
def test_hyperframes_template_id_resolution_and_fallback_contract(tmp_path, frame_template, expected_template_id):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, frame_template=frame_template)

    assert pipeline._resolve_hyperframes_template_id(ctx.config) == expected_template_id
    assert pipeline._get_hyperframes_fallback_reason(ctx) is None


def test_hyperframes_legacy_image_full_template_falls_back_without_native_template(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1920x1080/image_full.html",
    )

    assert pipeline._resolve_hyperframes_template_id(ctx.config) == "image_full"
    assert "HyperFrames template directory" in pipeline._get_hyperframes_fallback_reason(ctx)


def test_build_hyperframes_visual_clips_cover_master_audio_without_gaps(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )

    ctx.storyboard.total_duration = 13.621134
    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.24,
                source_end=3.04,
            ),
            SentenceUnit(
                id="sentence-2",
                text="Sentence 2.",
                frame_indices=[1],
                block_id="block-1",
                source_start=3.28,
                source_end=13.2,
            ),
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1. Sentence 2.",
                source_frame_indices=[0, 1],
                start=0.0,
                end=13.621134,
            )
        ],
    )

    clips = pipeline._build_hyperframes_visual_clips(ctx.storyboard, ctx.timing_plan)

    assert [(clip.start, clip.end) for clip in clips] == [
        (pytest.approx(0.0), pytest.approx(3.28)),
        (pytest.approx(3.28), pytest.approx(13.621134)),
    ]


def test_build_hyperframes_visual_clips_splits_shared_sentence_window_between_frames(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )

    ctx.storyboard.total_duration = 10.0
    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="One spoken unit spans two storyboard frames.",
                frame_indices=[0, 1],
                block_id="block-1",
                source_start=0.0,
                source_end=10.0,
            ),
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="One spoken unit spans two storyboard frames.",
                source_frame_indices=[0, 1],
                start=0.0,
                end=10.0,
            )
        ],
    )

    clips = pipeline._build_hyperframes_visual_clips(ctx.storyboard, ctx.timing_plan)

    assert [(clip.start, clip.end) for clip in clips] == [
        (pytest.approx(0.0), pytest.approx(5.0)),
        (pytest.approx(5.0), pytest.approx(10.0)),
    ]


def test_build_hyperframes_visual_clips_carries_element_motion_artifacts(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )

    ctx.storyboard.total_duration = 3.0
    first_raw = tmp_path / "00_raw.png"
    second_raw = tmp_path / "01_raw.png"
    second_motion = tmp_path / "01_motion.mp4"
    for path in (first_raw, second_raw, second_motion):
        path.write_bytes(b"media")

    ctx.storyboard.frames[0].media_type = "image"
    ctx.storyboard.frames[0].image_path = str(first_raw)
    ctx.storyboard.frames[0].element_animation_manifest_path = "element/frame_000.json"
    ctx.storyboard.frames[1].media_type = "image"
    ctx.storyboard.frames[1].image_path = str(second_raw)
    ctx.storyboard.frames[1].element_animation_manifest_path = "element/frame_001.json"
    ctx.storyboard.frames[1].element_motion_video_path = str(second_motion)

    ctx.timing_plan.sentences[0].source_start = 0.0
    ctx.timing_plan.sentences[0].source_end = 1.2
    ctx.timing_plan.sentences[1].source_start = 1.2
    ctx.timing_plan.sentences[1].source_end = 3.0
    ctx.timing_plan.blocks[0].start = 0.0
    ctx.timing_plan.blocks[0].end = 1.2
    ctx.timing_plan.blocks[1].start = 1.2
    ctx.timing_plan.blocks[1].end = 3.0

    clips = pipeline._build_hyperframes_visual_clips(ctx.storyboard, ctx.timing_plan)

    assert [clip.element_animation_manifest_path for clip in clips] == [
        "element/frame_000.json",
        "element/frame_001.json",
    ]
    assert clips[0].media_path == str(first_raw)
    assert clips[0].media_type == "image"
    assert clips[0].source_kind == "raw_media"
    assert clips[1].media_path == str(second_motion)
    assert clips[1].media_type == "video"
    assert clips[1].source_kind == "element_motion_video"
    assert clips[1].media_role == "final_frame"
    assert clips[1].source_media_path == str(second_raw)


def test_ffmpeg_manifest_rejects_frame_audio_as_master_audio_fallback(monkeypatch, tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )
    ctx.config.render_backend = "ffmpeg_manifest"

    for frame in ctx.storyboard.frames:
        audio_path = tmp_path / f"{frame.index:02d}_audio.wav"
        audio_path.write_bytes(b"audio")
        frame.audio_path = str(audio_path)

    def fail_concat(*_args, **_kwargs):
        raise AssertionError("frame audio must not be promoted to master audio")

    monkeypatch.setattr(pipeline, "_concat_audio_files", fail_concat)

    with pytest.raises(RuntimeError, match="requires master audio"):
        pipeline._resolve_master_audio_for_manifest(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("tts_audio_strategy", ["per_frame", "bogus"])
async def test_hyperframes_asset_path_rejects_unsupported_tts_audio_strategy_before_work(
    monkeypatch,
    tts_audio_strategy,
):
    core = SimpleNamespace(llm=None, tts=None, media=None, video=None)
    pipeline = StandardPipeline(core)
    ctx = SimpleNamespace(
        storyboard=SimpleNamespace(frames=[]),
        config=SimpleNamespace(tts_audio_strategy=tts_audio_strategy),
    )
    calls = []

    async def fail_hyperframes_assets(context):
        calls.append(context)
        raise AssertionError("HyperFrames asset work must not start")

    monkeypatch.setattr(pipeline, "_is_hyperframes_render_path", lambda context: True)
    monkeypatch.setattr(pipeline, "_produce_assets_hyperframes", fail_hyperframes_assets)

    with pytest.raises(ValueError, match="tts_audio_strategy|per_frame"):
        await pipeline.produce_assets(ctx)

    assert calls == []


@pytest.mark.asyncio
async def test_post_production_renders_with_hyperframes_and_uses_raw_media_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, silence_trim_tool="auto_editor")
    ctx.storyboard.config.template_params = {"author": "demo", "footer": "LanRen"}
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

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
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
        (
            str(Path(ctx.task_dir) / "audio" / "master_audio.wav"),
            str(Path(ctx.task_dir) / "audio" / "trimmed_master_audio.wav"),
            120,
        )
    ]
    assert core.audio_edit_service.remap_calls
    assert manifest.master_audio_path.endswith("trimmed_master_audio.wav")
    assert ctx.storyboard.total_duration == pytest.approx(1.8)
    assert core.hyperframes_project_service.write_project_calls == [
        {
            "manifest": manifest,
            "template_params": {"author": "demo", "footer": "LanRen"},
            "master_audio_duration": 1.8,
        }
    ]
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
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "expected_duration": 1.8,
            "expect_audio": True,
        }
    ]
    assert requested_output.exists()
    assert ctx.final_video_path == str(requested_output)
    assert ctx.storyboard.final_video_path == str(requested_output)


@pytest.mark.asyncio
async def test_post_production_materializes_element_motion_after_final_hyperframes_timing(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )
    ctx.config.element_animation_enabled = True
    ctx.config.element_animation_backend = "hyperframes_canvas"
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_bytes(b"raw")

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_get_audio_duration(audio_path):
        return 3.0 if str(audio_path).endswith("master_audio.wav") else 1.5

    materialized: list[tuple[int, float]] = []

    async def fake_materialize_element_motion(context, frame):
        materialized.append((frame.index, frame.duration))
        frame.element_animation_manifest_path = f"element/frame_{frame.index:03d}.json"

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)
    monkeypatch.setattr(
        pipeline,
        "_materialize_element_motion_for_frame",
        fake_materialize_element_motion,
    )

    await pipeline.post_production(ctx)

    assert materialized == [
        (0, pytest.approx(1.6)),
        (1, pytest.approx(1.4)),
    ]
    assert [
        clip.element_animation_manifest_path
        for clip in core.hyperframes_project_service.manifest.visual_clips
    ] == [
        "element/frame_000.json",
        "element/frame_001.json",
    ]


@pytest.mark.asyncio
async def test_post_production_compiles_bgm_as_hyperframes_audio_track(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoPostRenderBgmVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    final_output = tmp_path / "task-1" / "final.mp4"
    ctx.final_video_path = str(final_output)
    ctx.params.update(
        {
            "bgm_path": "default.mp3",
            "bgm_volume": 0.35,
            "bgm_mode": "once",
        }
    )

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    bgm_prepare_calls = []

    def fake_prepare_bgm_audio(input_path, output_path, *, duration, mode):
        bgm_prepare_calls.append(
            {
                "input_path": input_path,
                "output_path": output_path,
                "duration": duration,
                "mode": mode,
            }
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"bgm-wav")
        return output_path

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_prepare_bgm_audio_for_hyperframes", fake_prepare_bgm_audio, raising=False)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda audio_path: 2.0)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest

    assert core.hyperframes_renderer.calls[0]["output_path"] == str(final_output)
    assert bgm_prepare_calls == [
        {
            "input_path": "default.mp3",
            "output_path": str(Path(ctx.task_dir) / "audio" / "background_audio.wav"),
            "duration": 2.0,
            "mode": "once",
        }
    ]
    assert [track.id for track in manifest.audio_tracks] == [
        "narration-audio",
        "background-audio",
    ]
    assert manifest.audio_tracks[0].path.endswith("master_audio.wav")
    assert manifest.audio_tracks[0].volume == pytest.approx(1.0)
    assert manifest.audio_tracks[1].path.endswith("background_audio.wav")
    assert manifest.audio_tracks[1].end == pytest.approx(2.0)
    assert manifest.audio_tracks[1].volume == pytest.approx(0.35)
    assert manifest.audio_tracks[1].role == "background"
    assert ctx.final_video_path == str(final_output)
    assert ctx.storyboard.final_video_path == str(final_output)


def test_prepare_bgm_audio_for_hyperframes_resolves_and_loops_bgm(monkeypatch, tmp_path):
    commands = []

    class _ResolvingVideoService:
        def resolve_bgm_path(self, bgm_path):
            assert bgm_path == "default.mp3"
            return str(tmp_path / "resolved-default.mp3")

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _ResolvingVideoService)
    monkeypatch.setattr("pixelle_video.pipelines.standard.subprocess.run", fake_run)

    pipeline = StandardPipeline(_DummyCore(tmp_path))
    output_path = tmp_path / "task-1" / "audio" / "background_audio.wav"

    result = pipeline._prepare_bgm_audio_for_hyperframes(
        "default.mp3",
        str(output_path),
        duration=12.5,
        mode="loop",
    )

    command, kwargs = commands[0]
    assert result == str(output_path)
    assert command[:4] == ["ffmpeg", "-stream_loop", "-1", "-i"]
    assert command[4] == str(tmp_path / "resolved-default.mp3")
    assert command[command.index("-t") + 1] == "12.5"
    assert command[command.index("-c:a") + 1] == "pcm_s16le"
    assert command[-2:] == ["-y", str(output_path)]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False


@pytest.mark.asyncio
async def test_hyperframes_manifest_receives_compiled_text_cues(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.creation_package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(
            candidates=(
                TextOverlayCandidate(
                    id="candidate-1",
                    text="重点词",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("hyperframes",),
                    source={"frame_index": 0, "sentence_id": "sentence-1"},
                ),
            )
        ),
    )

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        frame.composed_image_path = str(tmp_path / f"{frame.index:02d}_shell.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")
        Path(frame.composed_image_path).write_text("shell", encoding="utf-8")

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda audio_path: 2.0)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest

    assert manifest.text_tracks
    assert manifest.text_cues[0].text == "重点词"
    assert manifest.text_cues[0].source["candidate_id"] == "candidate-1"
    assert manifest.text_cues[0].start == pytest.approx(0.1)
    assert ctx.observability["text_layer_summary"]["renderer"] == "hyperframes"
    assert ctx.observability["text_layer_summary"]["cue_count"] == 1


@pytest.mark.asyncio
async def test_post_production_uses_template_canvas_size_instead_of_square_media_size(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(
        tmp_path,
        frame_template="1080x1920/image_default.html",
    )
    ctx.config.media_width = 768
    ctx.config.media_height = 768
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_get_audio_duration(audio_path):
        return 4.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert (manifest.canvas_width, manifest.canvas_height) == (1080, 1920)
    assert (manifest.media_width, manifest.media_height) == (768, 768)
    assert core.hyperframes_renderer.calls == [
        {
            "project_dir": str(tmp_path / "task-1" / "hyperframes"),
            "output_path": str(tmp_path / "task-1" / "final.mp4"),
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "expected_duration": 4.0,
            "expect_audio": True,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frame_template",
    ["1920x1080/image_landscape_full.html", "1920x1080/image_landscape_minimal.html"],
)
async def test_post_production_uses_landscape_template_canvas_size(monkeypatch, tmp_path, frame_template):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, frame_template=frame_template)
    ctx.config.media_width = 768
    ctx.config.media_height = 768
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_get_audio_duration(audio_path):
        return 4.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert (manifest.canvas_width, manifest.canvas_height) == (1920, 1080)
    assert core.hyperframes_renderer.calls[0]["width"] == 1920
    assert core.hyperframes_renderer.calls[0]["height"] == 1080


@pytest.mark.asyncio
async def test_post_production_respects_direct_duration_alignment_engine(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.config.subtitle_alignment_engine = "direct_duration"
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    ctx.timing_plan = TimingPlan(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="Short line.",
                frame_indices=[0],
                block_id="block-1",
            ),
            SentenceUnit(
                id="sentence-2",
                text="A much longer second line.",
                frame_indices=[1],
                block_id="block-1",
            ),
        ],
        blocks=[
            AudioBlock(
                id="block-1",
                text="Short line. A much longer second line.",
                source_frame_indices=[0, 1],
            )
        ],
    )

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    def fake_get_audio_duration(audio_path):
        return 4.0

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest

    assert core.alignment_service.calls == []
    assert core.alignment_service.duration_calls == [
        (["block-1"], ["sentence-1", "sentence-2"])
    ]
    assert manifest.sentence_units[0].source_start == pytest.approx(0.0)
    assert manifest.sentence_units[0].source_end <= manifest.sentence_units[1].source_start
    assert manifest.sentence_units[-1].source_end == pytest.approx(4.0)


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

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
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

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-wav")

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert manifest.visual_clips == []


@pytest.mark.asyncio
async def test_post_production_warns_and_keeps_clips_for_mixed_raw_media_availability(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)

    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")

    ctx.storyboard.frames[0].media_type = "image"
    ctx.storyboard.frames[0].image_path = str(tmp_path / "00_raw.png")
    Path(ctx.storyboard.frames[0].image_path).write_text("raw", encoding="utf-8")
    ctx.storyboard.frames[0].composed_image_path = str(tmp_path / "00_shell.png")
    Path(ctx.storyboard.frames[0].composed_image_path).write_text("shell", encoding="utf-8")

    ctx.storyboard.frames[1].media_type = "image"
    ctx.storyboard.frames[1].image_path = None
    ctx.storyboard.frames[1].composed_image_path = str(tmp_path / "01_shell.png")
    Path(ctx.storyboard.frames[1].composed_image_path).write_text("shell", encoding="utf-8")

    warnings: list[str] = []

    def fake_warning(message):
        warnings.append(message)

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-wav")

    def fake_get_audio_duration(audio_path):
        return 2.0

    monkeypatch.setattr("pixelle_video.pipelines.standard.logger.warning", fake_warning)
    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", fake_get_audio_duration)

    await pipeline.post_production(ctx)

    manifest = core.hyperframes_project_service.manifest
    assert [clip.media_path for clip in manifest.visual_clips] == [str(tmp_path / "00_raw.png")]
    assert warnings
    assert "missing raw media" in warnings[0]


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
    ctx = _build_storyboard_context(tmp_path, render_backend="hyperframes_compiled")
    ctx.config.frame_template = "1080x1920/image_modern.html"
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
    ctx = _build_storyboard_context(tmp_path, render_backend="legacy")
    ctx.final_video_path = str(tmp_path / "legacy-final.mp4")
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.storyboard.frames[1].video_segment_path = "segment-1.mp4"

    await pipeline.post_production(ctx)

    assert calls["videos"] == ["segment-0.mp4", "segment-1.mp4"]
    assert calls["output"] == ctx.final_video_path
    assert calls["kwargs"]["bgm_mode"] == "loop"


@pytest.mark.asyncio
async def test_persist_task_data_records_resolved_render_backend(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, render_backend="legacy")
    output_path = Path(tmp_path / "task-1" / "final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"video")
    ctx.final_video_path = str(output_path)
    ctx.storyboard.completed_at = ctx.storyboard.created_at
    ctx.result = SimpleNamespace(
        video_path=str(output_path),
        duration=2.0,
        file_size=output_path.stat().st_size,
    )

    await pipeline._persist_task_data(ctx)

    assert core.persistence.saved_metadata is not None
    _, metadata = core.persistence.saved_metadata
    assert metadata["config"]["render_backend"] == "legacy"
    assert metadata["input"]["render_backend"] == "legacy"


@pytest.mark.asyncio
async def test_persist_task_data_records_text_layer_summary(tmp_path):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, render_backend="hyperframes_compiled")
    output_path = Path(tmp_path / "task-1" / "final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"video")
    ctx.final_video_path = str(output_path)
    ctx.storyboard.completed_at = ctx.storyboard.created_at
    ctx.observability["text_layer_summary"] = {
        "enabled": True,
        "renderer": "hyperframes",
        "cue_count": 2,
        "track_count": 1,
        "native_prompt_hint_count": 1,
        "targets": ["hyperframes", "native_prompt"],
    }
    ctx.observability["caption_rendering_summary"] = {
        "enabled": True,
        "caption_cue_count": 2,
        "style_profile_id": "caption-default",
    }
    ctx.observability["image_text_policy_summary"] = {
        "status": "not_applicable",
        "suppress_embedded_text": False,
    }
    ctx.result = SimpleNamespace(
        video_path=str(output_path),
        duration=2.0,
        file_size=output_path.stat().st_size,
    )

    await pipeline._persist_task_data(ctx)

    assert core.persistence.saved_metadata is not None
    _, metadata = core.persistence.saved_metadata
    assert metadata["result"]["text_layer_summary"] == {
        "enabled": True,
        "renderer": "hyperframes",
        "cue_count": 2,
        "track_count": 1,
        "native_prompt_hint_count": 1,
        "targets": ["hyperframes", "native_prompt"],
    }
    assert metadata["result"]["caption_rendering_summary"] == {
        "enabled": True,
        "caption_cue_count": 2,
        "style_profile_id": "caption-default",
    }
    assert metadata["result"]["image_text_policy_summary"] == {
        "status": "not_applicable",
        "suppress_embedded_text": False,
    }
    assert metadata["result"]["text_render_package_path"] == "text_render_package.json"


@pytest.mark.asyncio
async def test_persist_task_data_records_requested_and_effective_backend_when_hyperframes_falls_back(
    tmp_path,
):
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path, render_backend="hyperframes_compiled")
    ctx.config.frame_template = "1080x1920/image_modern.html"
    output_path = Path(tmp_path / "task-1" / "final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"video")
    ctx.final_video_path = str(output_path)
    ctx.storyboard.completed_at = ctx.storyboard.created_at
    ctx.result = SimpleNamespace(
        video_path=str(output_path),
        duration=2.0,
        file_size=output_path.stat().st_size,
    )

    await pipeline._persist_task_data(ctx)

    assert core.persistence.saved_metadata is not None
    _, metadata = core.persistence.saved_metadata
    assert metadata["input"]["render_backend"] == "legacy"
    assert metadata["input"]["render_backend_requested"] == "hyperframes_compiled"
    assert metadata["input"]["render_backend_effective"] == "legacy"
    assert metadata["config"]["render_backend"] == "legacy"
    assert metadata["config"]["render_backend_requested"] == "hyperframes_compiled"
    assert metadata["config"]["render_backend_effective"] == "legacy"
    execution_plan = metadata["result"]["render_execution_plan"]
    assert execution_plan["requested_backend"] == "hyperframes_compiled"
    assert execution_plan["effective_backend"] == "legacy"
    assert "HyperFrames template directory" in execution_plan["fallback_reason"]
    assert metadata["observability"]["render_execution_plan"] == execution_plan
