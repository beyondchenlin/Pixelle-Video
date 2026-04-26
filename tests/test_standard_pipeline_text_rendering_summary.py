import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import SentenceUnit, TextCue, TextTrack
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.text_overlay import TextOverlayCandidate, TextOverlayPlan
from pixelle_video.models.text_style import DEFAULT_OVERLAY_STYLE_ID
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def _storyboard_plan(text: str) -> StoryboardPlan:
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=text,
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text=text,
                visual_goal="Show the text.",
                prompt_intent="Use the text as visual context.",
                source_start=0,
                source_end=len(text),
            )
        ],
    )


def test_record_caption_rendering_summary_is_independent_from_text_layer():
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(observability={})

    pipeline._record_caption_rendering_summary(
        ctx,
        caption_cue_count=12,
        style_profile=TextStyleProfile(
            id="caption-yellow",
            name="Caption Yellow",
            primary_color="#FFFF00",
        ),
        renderer_targets=("hyperframes", "ass"),
        artifacts={"subtitle_only_ass": "text_layer/subtitle_only.ass"},
    )

    summary = ctx.observability["caption_rendering_summary"]

    assert summary["enabled"] is True
    assert summary["caption_cue_count"] == 12
    assert summary["style_profile_id"] == "caption-yellow"
    assert summary["renderer_targets"] == ["ass", "hyperframes"]
    assert summary["artifacts"]["subtitle_only_ass"] == "text_layer/subtitle_only.ass"
    assert "text_layer_summary" not in ctx.observability


def test_record_caption_rendering_summary_keeps_enabled_state_with_zero_cues():
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(observability={})

    pipeline._record_caption_rendering_summary(
        ctx,
        enabled=True,
        caption_cue_count=0,
        style_profile="caption-default",
        renderer_targets=("hyperframes",),
        artifacts={},
    )

    summary = ctx.observability["caption_rendering_summary"]

    assert summary["enabled"] is True
    assert summary["caption_cue_count"] == 0
    assert summary["style_profile_id"] == "caption-default"


def test_text_rendering_result_persists_caption_style_when_overlay_disabled(tmp_path):
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(
        params={
            "text_rendering": {
                "overlay": {"enabled": False},
                "caption_style": {
                    "font_size": 72,
                    "primary_color": "#ffff00",
                },
            },
        },
        narrations=["first narration"],
        task_id="task-caption-only",
        task_dir=str(tmp_path),
        observability={},
    )

    result = pipeline._get_text_rendering_result(ctx)

    assert result.settings.overlay.enabled is False
    assert result.caption_style.primary_color == "#FFFF00"
    assert result.caption_style.font_size == 72
    assert result.text_render_package.text_style_profiles[0].primary_color == "#FFFF00"
    assert getattr(ctx, "text_render_package") is result.text_render_package
    package_payload = json.loads(
        (tmp_path / "text_render_package.json").read_text(encoding="utf-8")
    )
    assert package_payload["text_style_profiles"][0]["primary_color"] == "#FFFF00"
    assert package_payload["diagnostics"]["disabled_reasons"] == ["overlay_disabled"]


def test_text_rendering_result_attaches_contract_to_creation_package(tmp_path):
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(
        params={
            "text_rendering": {
                "overlay": {
                    "enabled": True,
                    "renderer_targets": ["ass"],
                    "max_items_per_frame": 1,
                },
                "overlay_style": {"primary_color": "#00ff00"},
            },
        },
        storyboard_plan=_storyboard_plan("alpha beta gamma"),
        task_id="task-static-contract",
        task_dir=str(tmp_path),
        observability={},
    )

    result = pipeline._get_text_rendering_result(ctx)

    assert ctx.creation_package.text_overlay_plan is result.overlay_plan
    assert ctx.creation_package.prompt_plan["text_render_package"] == (
        "text_render_package.json"
    )
    assert list(
        ctx.creation_package.prompt_plan["text_rendering_policy"]["enabled_targets"]
    ) == ["ass"]
    assert len(ctx.creation_package.text_overlay_plan.candidates) == 1


def test_caption_cues_rebuild_from_current_timing_plan(tmp_path):
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(
        params={"text_rendering": {}},
        narrations=["caption"],
        task_id="task-caption-timing",
        task_dir=str(tmp_path),
        observability={},
    )
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )

    initial_cues = pipeline._build_caption_cues_for_render(ctx, rebuild=True)
    pipeline._update_text_render_package(ctx, caption_cues=initial_cues)
    ctx.timing_plan.sentences[0].remapped_start = 2.0
    ctx.timing_plan.sentences[0].remapped_end = 3.5

    rebuilt_cues = pipeline._build_caption_cues_for_render(ctx, rebuild=True)

    assert initial_cues[0].start == 0.0
    assert rebuilt_cues[0].start == 2.0
    assert rebuilt_cues[0].end == 3.5


def test_caption_cues_use_top_level_punctuation_mode(tmp_path):
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(
        params={
            "caption_punctuation_mode": "preserve",
            "text_rendering": {},
        },
        narrations=["caption."],
        task_id="task-caption-punctuation",
        task_dir=str(tmp_path),
        observability={},
    )
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )

    result = pipeline._get_text_rendering_result(ctx)
    cues = pipeline._build_caption_cues_for_render(ctx, rebuild=True)

    assert result.caption_settings.punctuation_mode == "preserve"
    assert cues[0].text == "caption."


def test_caption_cues_are_filtered_by_renderer_targets(tmp_path):
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(
        params={
            "text_rendering": {
                "caption": {"renderer_targets": ["ass"]},
            },
        },
        narrations=["caption"],
        task_id="task-caption-target-filter",
        task_dir=str(tmp_path),
        observability={},
    )
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )

    cues = pipeline._build_caption_cues_for_render(ctx, rebuild=True)

    assert pipeline._caption_cues_for_renderer(
        ctx,
        caption_cues=cues,
        renderer="hyperframes",
    ) == []
    assert pipeline._caption_cues_for_renderer(
        ctx,
        caption_cues=cues,
        renderer="ass",
    ) == cues


def test_record_text_layer_summary_only_describes_overlay_text_layer():
    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = SimpleNamespace(observability={})

    pipeline._record_text_layer_summary(
        ctx,
        renderer="ass",
        text_tracks=[
            TextTrack(
                id="track-ass-keyword",
                kind="keyword",
                name="keyword",
                renderer_targets=("ass",),
                style_profile=DEFAULT_OVERLAY_STYLE_ID,
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-ass-keyword",
                text="Keyword",
                start=0.0,
                end=1.0,
                role="keyword",
                style_profile=DEFAULT_OVERLAY_STYLE_ID,
            )
        ],
    )

    summary = ctx.observability["text_layer_summary"]

    assert summary["style_profile_ids"] == [DEFAULT_OVERLAY_STYLE_ID]
    assert "caption_cue_count" not in summary
    assert "caption_rendering_summary" not in summary
    assert "caption_rendering_summary" not in ctx.observability


class _LegacyVideoService:
    def __init__(self, calls):
        self.calls = calls

    def concat_videos(self, videos, output, **kwargs):
        self.calls.append(("concat", videos, output, kwargs))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"concat")
        return output

    def burn_ass_subtitles(self, input_video, ass_file, output):
        self.calls.append(("burn", input_video, ass_file, output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"burned")
        return output


class _CapturingAssTextAdapter:
    manifest = None

    def export(self, *, manifest, output_dir):
        type(self).manifest = manifest
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        master = output_dir / "master.ass"
        subtitle_only = output_dir / "subtitle_only.ass"
        overlay_only = output_dir / "overlay_only.ass"
        master.write_text("", encoding="utf-8")
        subtitle_only.write_text("", encoding="utf-8")
        overlay_only.write_text("", encoding="utf-8")
        return SimpleNamespace(
            master=master,
            subtitle_only=subtitle_only,
            overlay_only=overlay_only,
            diagnostics={"fallbacks": []},
        )


class _FakeHyperFramesProjectService:
    manifest = None

    def write_project(self, manifest, **kwargs):
        type(self).manifest = manifest
        captions_path = Path("hyperframes") / "data" / "captions.json"
        return SimpleNamespace(
            project_dir=Path("hyperframes"),
            captions_path=captions_path,
        )


class _FakeHyperFramesRenderer:
    def render(self, project_dir, **kwargs):
        output_path = kwargs["output_path"]
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"hyperframes")
        return output_path


@pytest.mark.asyncio
async def test_legacy_ass_manifest_receives_text_style_profiles_from_package(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        lambda: _LegacyVideoService(calls),
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.AssTextAdapter",
        _CapturingAssTextAdapter,
    )
    _CapturingAssTextAdapter.manifest = None

    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = PipelineContext(
        input_text="topic",
        params={
            "text_rendering": {
                "caption_style": {"primary_color": "#ffff00"},
                "overlay": {
                    "enabled": True,
                    "renderer_targets": ["ass"],
                    "max_items_per_frame": 1,
                },
            }
        },
    )
    ctx.task_id = "task-1"
    ctx.task_dir = str(tmp_path / "task-1")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    ctx.config = StoryboardConfig(
        task_id="task-1",
        media_width=1080,
        media_height=1920,
        video_fps=30,
        frame_template="1080x1920/image_default.html",
        render_backend="legacy",
    )
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="scene 1", image_prompt="prompt 1")
        ],
    )
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
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
                    text="Keyword",
                    role="keyword",
                    suggested_slot="center",
                    renderer_targets=("ass",),
                    source={"frame_index": 0, "sentence_id": "sentence-1"},
                ),
            )
        ),
    )

    await pipeline.post_production(ctx)

    manifest = _CapturingAssTextAdapter.manifest
    assert manifest is not None
    assert [profile.id for profile in manifest.text_style_profiles] == [
        "caption-default",
        DEFAULT_OVERLAY_STYLE_ID,
    ]
    assert manifest.text_style_profiles[0].primary_color == "#FFFF00"
    assert ctx.observability["caption_rendering_summary"]["style_profile_id"] == (
        "caption-default"
    )


@pytest.mark.asyncio
async def test_legacy_ass_exports_caption_only_when_overlay_disabled(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        lambda: _LegacyVideoService(calls),
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.AssTextAdapter",
        _CapturingAssTextAdapter,
    )
    _CapturingAssTextAdapter.manifest = None

    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = PipelineContext(
        input_text="topic",
        params={
            "text_rendering": {
                "caption_style": {"primary_color": "#ffff00"},
                "overlay": {"enabled": False},
            }
        },
    )
    ctx.task_id = "task-caption-only"
    ctx.task_dir = str(tmp_path / "task-caption-only")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.final_video_path = str(tmp_path / "task-caption-only" / "final.mp4")
    ctx.config = StoryboardConfig(
        task_id="task-caption-only",
        media_width=1080,
        media_height=1920,
        video_fps=30,
        frame_template="1080x1920/image_default.html",
        render_backend="legacy",
    )
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="caption only", image_prompt="prompt")
        ],
    )
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption only.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )

    await pipeline.post_production(ctx)

    manifest = _CapturingAssTextAdapter.manifest
    assert manifest is not None
    assert manifest.caption_cues[0].style_profile == "caption-default"
    assert manifest.text_cues[0].role == "subtitle"
    assert manifest.text_style_profiles[0].primary_color == "#FFFF00"
    assert ctx.text_render_package.caption_cues[0].id == "sentence-1"
    assert ctx.observability["caption_rendering_summary"]["caption_cue_count"] == 1
    assert ctx.observability["caption_rendering_summary"]["artifacts"][
        "subtitle_only_ass"
    ].endswith("subtitle_only.ass")
    assert ctx.observability["text_layer_summary"]["enabled"] is False
    assert ctx.observability["text_layer_summary"]["cue_count"] == 0
    assert ctx.observability["text_layer_summary"]["artifacts"] == {}
    assert ctx.observability["text_layer_summary"]["fallbacks"] == []
    assert any(call[0] == "burn" for call in calls)


@pytest.mark.asyncio
async def test_legacy_ass_does_not_render_caption_when_ass_not_targeted(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        lambda: _LegacyVideoService(calls),
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.AssTextAdapter",
        _CapturingAssTextAdapter,
    )
    _CapturingAssTextAdapter.manifest = None

    pipeline = StandardPipeline.__new__(StandardPipeline)
    ctx = PipelineContext(
        input_text="topic",
        params={
            "text_rendering": {
                "caption": {"renderer_targets": ["hyperframes"]},
                "overlay": {"enabled": False},
            }
        },
    )
    ctx.task_id = "task-caption-targets"
    ctx.task_dir = str(tmp_path / "task-caption-targets")
    Path(ctx.task_dir).mkdir(parents=True, exist_ok=True)
    ctx.final_video_path = str(tmp_path / "task-caption-targets" / "final.mp4")
    ctx.config = StoryboardConfig(
        task_id="task-caption-targets",
        media_width=1080,
        media_height=1920,
        video_fps=30,
        frame_template="1080x1920/image_default.html",
        render_backend="legacy",
    )
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="caption only", image_prompt="prompt")
        ],
    )
    ctx.storyboard.frames[0].video_segment_path = "segment-0.mp4"
    ctx.timing_plan = SimpleNamespace(
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption only.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ]
    )

    await pipeline.post_production(ctx)

    assert _CapturingAssTextAdapter.manifest is None
    assert ctx.text_render_package.caption_cues == ()
    assert ctx.observability["caption_rendering_summary"]["enabled"] is False
    assert ctx.observability["caption_rendering_summary"]["caption_cue_count"] == 0
    assert ctx.observability["caption_rendering_summary"]["artifacts"] == {}
    assert [call[0] for call in calls] == ["concat"]


@pytest.mark.asyncio
async def test_hyperframes_summary_omits_caption_artifact_when_not_targeted(
    monkeypatch,
    tmp_path,
):
    async def fake_synthesize_hyperframes_audio(ctx):
        return "master.wav", 1.0

    pipeline = StandardPipeline.__new__(StandardPipeline)
    pipeline.core = SimpleNamespace(
        hyperframes_project_service=_FakeHyperFramesProjectService(),
        hyperframes_renderer=_FakeHyperFramesRenderer(),
        alignment_service=SimpleNamespace(
            align_blocks=lambda blocks, sentences: None,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "_synthesize_hyperframes_audio",
        fake_synthesize_hyperframes_audio,
    )
    monkeypatch.setattr(
        pipeline,
        "_is_hyperframes_render_path",
        lambda ctx: True,
    )
    _FakeHyperFramesProjectService.manifest = None

    ctx = PipelineContext(
        input_text="topic",
        params={
            "text_rendering": {
                "caption": {"renderer_targets": ["ass"]},
                "overlay": {"enabled": False},
            }
        },
    )
    ctx.task_id = "task-hyperframes-targets"
    ctx.task_dir = str(tmp_path / "task-hyperframes-targets")
    ctx.final_video_path = str(tmp_path / "task-hyperframes-targets" / "final.mp4")
    ctx.config = StoryboardConfig(
        task_id="task-hyperframes-targets",
        media_width=1080,
        media_height=1920,
        video_fps=30,
        frame_template="1080x1920/image_default.html",
        render_backend="hyperframes_compiled",
    )
    ctx.storyboard = Storyboard(
        title="Demo",
        config=ctx.config,
        frames=[
            StoryboardFrame(index=0, narration="caption only", image_prompt="prompt")
        ],
    )
    ctx.storyboard.frames[0].image_path = "frame.png"
    ctx.storyboard.frames[0].composed_image_path = "frame.png"
    ctx.storyboard.frames[0].media_type = "image"
    ctx.timing_plan = SimpleNamespace(
        blocks=[],
        sentences=[
            SentenceUnit(
                id="sentence-1",
                text="caption only.",
                frame_indices=[0],
                source_start=0.0,
                source_end=1.0,
            )
        ],
    )

    await pipeline._post_production_hyperframes(ctx)

    assert _FakeHyperFramesProjectService.manifest.caption_cues == []
    assert ctx.text_render_package.caption_cues == ()
    assert ctx.observability["caption_rendering_summary"]["enabled"] is False
    assert ctx.observability["caption_rendering_summary"]["caption_cue_count"] == 0
    assert ctx.observability["caption_rendering_summary"]["artifacts"] == {}
