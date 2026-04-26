import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pixelle_video.config.loader import load_config_dict, save_config_dict
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderAudioTrack,
    RenderManifest,
    SentenceUnit,
    TextCue,
    TextTrack,
    VisualClip,
    resolve_render_window,
)
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.text_overlay import TextOverlayPlan
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.custom import CustomPipeline
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.services.persistence import PersistenceService


def _storyboard_plan_from_segments(segments: list[str]) -> StoryboardPlan:
    source_text = "".join(segments)
    frames = []
    cursor = 0
    for index, segment in enumerate(segments, start=1):
        start = cursor
        end = start + len(segment)
        frames.append(
            StoryboardPlanFrame(
                index=index,
                source_text=segment,
                visual_goal=f"Visualize segment {index}.",
                prompt_intent=f"Prompt for segment {index}.",
                source_start=start,
                source_end=end,
            )
        )
        cursor = end
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=source_text,
        frames=frames,
    )


def test_render_manifest_round_trip_and_timing_config_defaults():
    config = StoryboardConfig(media_width=1080, media_height=1920)
    assert config.tts_batching_mode == "paragraph"
    assert config.tts_audio_strategy == "auto"
    assert config.tts_split_mode == "internal_only"
    assert config.tts_sentence_joiner_mode == "direct"
    assert config.caption_punctuation_mode == "strip_all"
    assert config.preserve_natural_punctuation is True
    assert config.max_chars_per_tts_segment == 90
    assert config.tts_audio_boundary_fade_ms == 8
    assert config.subtitle_alignment_engine == "qwen_forced_aligner"
    assert config.silence_trim_tool is None
    assert config.render_backend == "legacy"

    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_life_insights_light",
        master_audio_path="output/task-1/master_audio.wav",
        audio_blocks=[
            AudioBlock(
                id="block-1",
                text="Sentence 1. Sentence 2.",
                audio_path="block-1.wav",
                start=0.0,
                end=4.2,
            )
        ],
        sentence_units=[
            SentenceUnit(
                id="s1",
                text="Sentence 1.",
                frame_indices=[0],
                block_id="block-1",
                source_start=0.0,
                source_end=2.0,
            )
        ],
        visual_clips=[
            VisualClip(
                id="v1",
                frame_index=0,
                start=0.0,
                end=2.0,
                media_path="01_image.png",
                media_type="image",
                track_index=0,
            )
        ],
        caption_rendering_enabled=False,
        caption_renderer_targets=["ass"],
        caption_cues=[
            CaptionCue(
                id="c1",
                text="Sentence 1",
                start=0.0,
                end=2.0,
                frame_indices=[0],
                style_profile="image_life_insights_light",
            )
        ],
    )

    data = manifest.to_dict()
    restored = RenderManifest.from_dict(data)

    assert restored.caption_cues[0].text == "Sentence 1"
    assert restored.caption_rendering_enabled is False
    assert restored.caption_renderer_targets == ["ass"]
    assert restored.audio_blocks[0].end == 4.2
    assert restored.caption_punctuation_mode == "strip_all"


def test_render_manifest_preserves_explicit_empty_caption_renderer_targets():
    manifest = RenderManifest(
        task_id="task-empty-caption-targets",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        caption_renderer_targets=[],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.caption_renderer_targets == []


def test_render_manifest_round_trips_declarative_audio_tracks():
    manifest = RenderManifest(
        task_id="task-audio",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        audio_tracks=[
            RenderAudioTrack(
                id="narration",
                path="assets/audio/master_audio.wav",
                start=0.0,
                end=12.5,
                volume=1.0,
                role="narration",
            ),
            RenderAudioTrack(
                id="background",
                path="assets/audio/background_audio.wav",
                start=0.0,
                end=12.5,
                volume=0.35,
                role="background",
            ),
        ],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert [track.id for track in restored.audio_tracks] == ["narration", "background"]
    assert restored.audio_tracks[1].path == "assets/audio/background_audio.wav"
    assert restored.audio_tracks[1].volume == pytest.approx(0.35)
    assert restored.to_dict()["audio_tracks"][1]["role"] == "background"


def test_render_audio_track_rejects_invalid_timing_and_volume():
    with pytest.raises(ValueError, match="end"):
        RenderAudioTrack(
            id="bad-time",
            path="assets/audio/bad.wav",
            start=2.0,
            end=1.0,
        )

    with pytest.raises(ValueError, match="volume"):
        RenderAudioTrack(
            id="bad-volume",
            path="assets/audio/bad.wav",
            start=0.0,
            end=1.0,
            volume=-0.1,
        )


def test_visual_clip_round_trips_template_and_motion_metadata():
    clip = VisualClip(
        id="clip-1",
        frame_index=0,
        start=0.0,
        end=2.0,
        media_path="frames/frame_000.png",
        media_type="image",
        source_kind="template_frame",
        media_role="final_frame",
        template_id="image_default",
        template_path="1080x1920/image_default.html",
        text_policy="caption_renderer",
        element_animation_manifest_path="element/frame_000.json",
        source_media_path="raw/frame_000.png",
        diagnostics={"template_has_text_slot": True},
    )
    restored = VisualClip.from_dict(clip.to_dict())
    assert restored.source_kind == "template_frame"
    assert restored.media_role == "final_frame"
    assert restored.template_id == "image_default"
    assert restored.element_animation_manifest_path == "element/frame_000.json"
    assert restored.diagnostics["template_has_text_slot"] is True


def test_text_track_and_text_cue_round_trip_with_immutable_layout_and_source():
    cue = TextCue(
        id="cue-1",
        track_id="track-overlay",
        text="重点词",
        start=0.2,
        end=1.4,
        role="keyword",
        frame_indices=(0,),
        slot="center",
        layout={"x": 0.5, "y": 0.35, "tokens": ["重点词"]},
        style_profile="default",
        layer=5,
        priority=10,
        language="zh-CN",
        source={"kind": "text_overlay_plan", "candidate_id": "candidate-1"},
    )

    restored = TextCue.from_dict(cue.to_dict())

    assert restored.version == "text_cue.v1"
    assert restored.frame_indices == (0,)
    assert restored.layout["tokens"] == ("重点词",)
    assert restored.to_dict()["layout"]["tokens"] == ["重点词"]
    assert restored.source["candidate_id"] == "candidate-1"


def test_pipeline_context_can_hold_creation_package_contract():
    package = CreationPackage(
        task_id="task-1",
        text_overlay_plan=TextOverlayPlan(source_summary={"candidate_count": 0}),
    )

    ctx = PipelineContext(
        input_text="demo",
        params={},
        creation_package=package,
    )

    assert ctx.creation_package is package
    assert ctx.creation_package.text_overlay_plan.source_summary["candidate_count"] == 0


def test_render_manifest_round_trips_text_tracks_and_text_cues_while_preserving_captions():
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_tracks=[
            TextTrack(
                id="track-overlay",
                kind="overlay",
                name="重点词轨",
                renderer_targets=("hyperframes",),
                style_profile="default",
                layer=5,
            )
        ],
        text_cues=[
            TextCue(
                id="cue-1",
                track_id="track-overlay",
                text="重点词",
                start=0.2,
                end=1.4,
                role="keyword",
                frame_indices=(0,),
                slot="center",
            )
        ],
        caption_cues=[
            CaptionCue(
                id="caption-1",
                text="字幕",
                start=0.0,
                end=1.0,
                frame_indices=[0],
            )
        ],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.text_tracks[0].kind == "overlay"
    assert restored.text_cues[0].role == "keyword"
    assert restored.caption_cues[0].text == "字幕"


def test_render_manifest_round_trips_text_style_profiles():
    manifest = RenderManifest(
        task_id="task-1",
        title="Text styles",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        text_style_profiles=[
            TextStyleProfile(
                id="caption-default",
                name="Caption Default",
                font_size=66,
                primary_color="#ffff00",
            )
        ],
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.version == "render_manifest.v1"
    assert restored.to_dict()["version"] == "render_manifest.v1"
    assert restored.text_style_profiles[0].id == "caption-default"
    assert restored.text_style_profiles[0].font_size == 66
    assert restored.to_dict()["text_style_profiles"][0]["primary_color"] == "#FFFF00"


def test_render_manifest_golden_fixture_preserves_text_style_profiles():
    payload = json.loads(
        Path(
            "tests/fixtures/text_rendering/render_manifest_with_text_styles.json"
        ).read_text(encoding="utf-8")
    )

    restored = RenderManifest.from_dict(payload).to_dict()

    assert restored["version"] == "render_manifest.v1"
    assert [profile["id"] for profile in restored["text_style_profiles"]] == [
        "caption-default",
        "overlay-default",
    ]


def test_render_manifest_round_trip_preserves_element_animation_manifest_path():
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        element_animation_manifest_path="data/element_animation_manifest.json",
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert (
        restored.element_animation_manifest_path
        == "data/element_animation_manifest.json"
    )


def test_render_manifest_from_old_payload_defaults_text_layer_to_empty_lists():
    payload = {
        "task_id": "task-old",
        "title": "demo",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "template_id": "image_default",
        "caption_cues": [],
    }

    restored = RenderManifest.from_dict(payload)

    assert restored.text_tracks == []
    assert restored.text_cues == []


def test_render_manifest_distinguishes_canvas_from_media_dimensions():
    manifest = RenderManifest(
        task_id="task-1",
        title="demo",
        canvas_width=1080,
        canvas_height=1920,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_default",
    )

    data = manifest.to_dict()

    assert data["canvas_width"] == 1080
    assert data["media_width"] == 768


def test_sentence_unit_round_trip_preserves_remapped_times():
    sentence = SentenceUnit(
        id="s1",
        text="Sentence 1.",
        frame_indices=[0],
        block_id="block-1",
        source_start=0.0,
        source_end=2.0,
        remapped_start=0.0,
        remapped_end=1.6,
    )

    restored = SentenceUnit.from_dict(sentence.to_dict())

    assert restored.remapped_start == 0.0
    assert restored.remapped_end == 1.6


def test_resolve_render_window_prefers_remapped_times():
    sentence = SentenceUnit(
        id="s1",
        text="Sentence 1.",
        frame_indices=[0],
        block_id="block-1",
        source_start=0.2,
        source_end=1.8,
        remapped_start=0.1,
        remapped_end=1.5,
    )

    assert resolve_render_window(sentence) == (0.1, 1.5)


def test_storyboard_config_render_fields_round_trip_through_persistence(tmp_path):
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        tts_batching_mode="sentence",
        tts_audio_strategy="master_track",
        tts_batch_max_sentences=4,
        tts_batch_max_chars=120,
        subtitle_alignment_engine="whisperx",
        silence_trim_tool="ffmpeg",
        silence_trim_margin_ms=80,
        render_backend="hyperframes_compiled",
    )

    service = PersistenceService(output_dir=str(tmp_path))
    restored = service._dict_to_config(service._config_to_dict(config))

    assert restored.tts_batching_mode == "sentence"
    assert restored.tts_audio_strategy == "master_track"
    assert restored.tts_batch_max_sentences == 4
    assert restored.tts_batch_max_chars == 120
    assert restored.subtitle_alignment_engine == "whisperx"
    assert restored.silence_trim_tool == "ffmpeg"
    assert restored.silence_trim_margin_ms == 80
    assert restored.render_backend == "hyperframes_compiled"


def test_storyboard_config_rejects_removed_hyperframes_alias():
    with pytest.raises(ValueError, match="render_backend"):
        StoryboardConfig(
            media_width=1080,
            media_height=1920,
            render_backend="hyperframes",
        )


def test_storyboard_config_accepts_ffmpeg_manifest_backend():
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        render_backend="ffmpeg_manifest",
    )

    assert config.render_backend == "ffmpeg_manifest"


def test_persistence_loads_historical_hyperframes_backend_as_compiled(tmp_path):
    config = {
        "task_id": "task-1",
        "n_storyboard": 1,
        "min_narration_words": 5,
        "max_narration_words": 20,
        "min_image_prompt_words": 30,
        "max_image_prompt_words": 60,
        "video_fps": 30,
        "tts_inference_mode": "local",
        "voice_id": None,
        "tts_workflow": None,
        "tts_speed": None,
        "ref_audio": None,
        "tts_batching_mode": "paragraph",
        "tts_audio_strategy": "auto",
        "tts_batch_max_sentences": 8,
        "tts_batch_max_chars": 220,
        "subtitle_alignment_engine": "qwen_forced_aligner",
        "silence_trim_tool": None,
        "silence_trim_margin_ms": 120,
        "render_backend": "hyperframes",
        "media_width": 1080,
        "media_height": 1920,
        "media_workflow": None,
        "media_negative_prompt": None,
        "frame_template": "1080x1920/image_default.html",
        "template_params": None,
    }

    service = PersistenceService(output_dir=str(tmp_path))
    restored = service._dict_to_config(config)

    assert restored.render_backend == "hyperframes_compiled"


def test_render_config_loads_and_saves_through_yaml_round_trip(tmp_path):
    config_path = tmp_path / "config.yaml"
    saved_path = tmp_path / "saved-config.yaml"
    config_path.write_text(
        """
render:
  backend: hyperframes_compiled
  timing:
    tts_batching_mode: sentence
    tts_audio_strategy: master_track
    tts_batch_max_sentences: 6
    tts_batch_max_chars: 180
    tts_sentence_joiner_mode: space
    caption_punctuation_mode: preserve
    preserve_natural_punctuation: false
    subtitle_alignment_engine: whisperx
    silence_trim_tool: ffmpeg
    silence_trim_margin_ms: 90
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config_dict(str(config_path))

    parsed = PixelleVideoConfig(**loaded)
    assert parsed.render.backend == "hyperframes_compiled"
    assert parsed.render.timing.tts_batching_mode == "sentence"
    assert parsed.render.timing.tts_audio_strategy == "master_track"
    assert parsed.render.timing.tts_batch_max_sentences == 6
    assert parsed.render.timing.tts_batch_max_chars == 180
    assert parsed.render.timing.tts_sentence_joiner_mode == "space"
    assert parsed.render.timing.caption_punctuation_mode == "preserve"
    assert parsed.render.timing.preserve_natural_punctuation is False
    assert parsed.render.timing.subtitle_alignment_engine == "whisperx"
    assert parsed.render.timing.silence_trim_tool == "ffmpeg"
    assert parsed.render.timing.silence_trim_margin_ms == 90

    save_config_dict(parsed.to_dict(), str(saved_path))
    reloaded = load_config_dict(str(saved_path))
    reparsed = PixelleVideoConfig(**reloaded)

    assert reparsed.render.backend == "hyperframes_compiled"
    assert reparsed.render.timing.tts_batching_mode == "sentence"
    assert reparsed.render.timing.tts_audio_strategy == "master_track"
    assert reparsed.render.timing.tts_sentence_joiner_mode == "space"
    assert reparsed.render.timing.caption_punctuation_mode == "preserve"
    assert reparsed.render.timing.preserve_natural_punctuation is False
    assert reparsed.render.timing.silence_trim_tool == "ffmpeg"


def test_resolve_storyboard_render_kwargs_includes_tts_audio_strategy():
    resolved = resolve_storyboard_render_kwargs(
        {
            "render": {
                "backend": "legacy",
                "timing": {
                    "tts_batching_mode": "sentence",
                    "tts_audio_strategy": "master_track",
                    "tts_split_mode": "external_only",
                    "max_chars_per_tts_segment": 120,
                    "tts_sentence_joiner_mode": "space",
                    "caption_punctuation_mode": "preserve",
                    "preserve_natural_punctuation": False,
                },
            }
        }
    )

    assert resolved["tts_batching_mode"] == "sentence"
    assert resolved["tts_audio_strategy"] == "master_track"
    assert resolved["tts_split_mode"] == "external_only"
    assert resolved["max_chars_per_tts_segment"] == 120
    assert resolved["tts_sentence_joiner_mode"] == "space"
    assert resolved["caption_punctuation_mode"] == "preserve"
    assert resolved["preserve_natural_punctuation"] is False


def test_render_config_rejects_removed_hyperframes_alias(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
render:
  backend: hyperframes
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config_dict(str(config_path))

    with pytest.raises(ValidationError, match="hyperframes_compiled"):
        PixelleVideoConfig(**loaded)


def test_resolve_storyboard_render_kwargs_honors_explicit_none_over_config_default():
    runtime_config = {
        "render": {
            "backend": "legacy",
            "timing": {
                "tts_batching_mode": "sentence",
                "tts_batch_max_sentences": 6,
                "tts_batch_max_chars": 180,
                "subtitle_alignment_engine": "whisperx",
                "silence_trim_tool": "ffmpeg",
                "silence_trim_margin_ms": 90,
            },
        }
    }
    request_params = {
        "tts_batching_mode": "paragraph",
        "silence_trim_tool": None,
    }

    resolved = resolve_storyboard_render_kwargs(runtime_config, request_params)

    assert resolved["tts_batching_mode"] == "paragraph"
    assert resolved["silence_trim_tool"] is None
    assert resolved["silence_trim_margin_ms"] == 90
    assert resolved["render_backend"] == "legacy"


def test_resolve_storyboard_render_kwargs_accepts_explicit_release_backend_override():
    runtime_config = {
        "render": {
            "backend": "legacy",
            "timing": {},
        }
    }
    request_params = {
        "render_backend": "hyperframes_compiled",
    }

    resolved = resolve_storyboard_render_kwargs(runtime_config, request_params)

    assert resolved["render_backend"] == "hyperframes_compiled"


@pytest.mark.asyncio
async def test_standard_pipeline_initialize_storyboard_uses_render_config_defaults():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "render": {
                    "backend": "legacy",
                    "timing": {
                        "tts_batching_mode": "sentence",
                        "tts_batch_max_sentences": 5,
                        "tts_batch_max_chars": 160,
                        "subtitle_alignment_engine": "whisperx",
                        "silence_trim_tool": "ffmpeg",
                        "silence_trim_margin_ms": 75,
                    },
                }
            },
            "llm": None,
            "tts": None,
            "media": None,
            "video": None,
        },
    )()

    pipeline = StandardPipeline(fake_core)
    ctx = PipelineContext(
        input_text="demo",
        params={
            "media_width": 1080,
            "media_height": 1920,
        },
    )
    ctx.task_id = "task-1"
    ctx.title = "demo"
    ctx.storyboard_plan = _storyboard_plan_from_segments(["Sentence 1."])
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.tts_batching_mode == "sentence"
    assert ctx.config.tts_batch_max_sentences == 5
    assert ctx.config.tts_batch_max_chars == 160
    assert ctx.config.subtitle_alignment_engine == "whisperx"
    assert ctx.config.silence_trim_tool == "ffmpeg"
    assert ctx.config.silence_trim_margin_ms == 75
    assert ctx.config.render_backend == "legacy"
    assert ctx.timing_plan is not None
    assert [sentence.text for sentence in ctx.timing_plan.sentences] == [
        "Sentence 1.",
    ]
    assert [block.text for block in ctx.timing_plan.blocks] == [
        "Sentence 1.",
    ]


@pytest.mark.asyncio
async def test_standard_pipeline_initialize_storyboard_builds_sentence_level_timing_plan():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "render": {
                    "backend": "legacy",
                    "timing": {
                        "tts_batching_mode": "paragraph",
                        "tts_batch_max_sentences": 8,
                        "tts_batch_max_chars": 220,
                        "subtitle_alignment_engine": "whisperx",
                        "silence_trim_tool": "ffmpeg",
                        "silence_trim_margin_ms": 75,
                    },
                }
            },
            "llm": None,
            "tts": None,
            "media": None,
            "video": None,
        },
    )()

    pipeline = StandardPipeline(fake_core)
    ctx = PipelineContext(
        input_text="demo",
        params={
            "media_width": 1080,
            "media_height": 1920,
        },
    )
    ctx.task_id = "task-2"
    ctx.title = "demo"
    ctx.storyboard_plan = _storyboard_plan_from_segments(["Sentence 1. Sentence 2!"])
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.timing_plan is not None
    assert [sentence.text for sentence in ctx.timing_plan.sentences] == [
        "Sentence 1.",
        "Sentence 2!",
    ]
    assert [sentence.frame_indices for sentence in ctx.timing_plan.sentences] == [
        [0],
        [0],
    ]
    assert [block.source_frame_indices for block in ctx.timing_plan.blocks] == [
        [0, 0],
    ]


@pytest.mark.asyncio
async def test_custom_pipeline_uses_render_config_defaults_when_building_storyboard_config(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class _CapturedConfig(Exception):
        pass

    def _capture_storyboard_config(**kwargs):
        captured.update(kwargs)
        raise _CapturedConfig

    async def _fake_generate_title(llm, text, strategy):
        return "Custom title"

    class _FakeFrameHtmlGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    monkeypatch.setattr("pixelle_video.pipelines.custom.StoryboardConfig", _capture_storyboard_config)
    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_title", _fake_generate_title)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.create_task_output_dir",
        lambda: (str(tmp_path / "task"), "task-1"),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_final_video_path",
        lambda task_id: str(tmp_path / f"{task_id}.mp4"),
    )
    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameHtmlGenerator,
    )

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "render": {
                    "backend": "legacy",
                    "timing": {
                        "tts_batching_mode": "sentence",
                        "tts_batch_max_sentences": 5,
                        "tts_batch_max_chars": 160,
                        "subtitle_alignment_engine": "whisperx",
                        "silence_trim_tool": "ffmpeg",
                        "silence_trim_margin_ms": 75,
                    },
                },
                "template": {
                    "default_template": "1080x1920/static_default.html",
                },
            },
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
            "frame_processor": object(),
            "persistence": object(),
        },
    )()

    pipeline = CustomPipeline(fake_core)

    with pytest.raises(_CapturedConfig):
        await pipeline(
            text="line one\nline two",
            frame_template="1080x1920/static_default.html",
        )

    assert captured["tts_batching_mode"] == "sentence"
    assert captured["tts_batch_max_sentences"] == 5
    assert captured["tts_batch_max_chars"] == 160
    assert captured["subtitle_alignment_engine"] == "whisperx"
    assert captured["silence_trim_tool"] == "ffmpeg"
    assert captured["silence_trim_margin_ms"] == 75
    assert captured["render_backend"] == "legacy"


@pytest.mark.asyncio
async def test_asset_based_pipeline_initialize_storyboard_uses_render_config_defaults(
    monkeypatch,
):
    captured = {}

    class _CapturedConfig(Exception):
        pass

    def _capture_storyboard_config(**kwargs):
        captured.update(kwargs)
        raise _CapturedConfig

    monkeypatch.setattr("pixelle_video.models.storyboard.StoryboardConfig", _capture_storyboard_config)

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "render": {
                    "backend": "legacy",
                    "timing": {
                        "tts_batching_mode": "sentence",
                        "tts_batch_max_sentences": 5,
                        "tts_batch_max_chars": 160,
                        "subtitle_alignment_engine": "whisperx",
                        "silence_trim_tool": "ffmpeg",
                        "silence_trim_margin_ms": 75,
                    },
                }
            },
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
        },
    )()

    pipeline = AssetBasedPipeline(fake_core)
    ctx = PipelineContext(
        input_text="intent",
        params={"template_params": {}},
    )
    ctx.task_id = "task-1"
    ctx.title = "Asset title"
    ctx.matched_scenes = [
        {
            "scene_number": 1,
            "asset_path": "assets/example.png",
            "narrations": ["Sentence 1."],
        }
    ]

    with pytest.raises(_CapturedConfig):
        await pipeline.initialize_storyboard(ctx)

    assert captured["tts_batching_mode"] == "sentence"
    assert captured["tts_batch_max_sentences"] == 5
    assert captured["tts_batch_max_chars"] == 160
    assert captured["subtitle_alignment_engine"] == "whisperx"
    assert captured["silence_trim_tool"] == "ffmpeg"
    assert captured["silence_trim_margin_ms"] == 75
    assert captured["render_backend"] == "legacy"


@pytest.mark.asyncio
async def test_custom_pipeline_persist_task_data_records_render_backend(tmp_path):
    class _RecordingPersistence:
        def __init__(self):
            self.saved_metadata = None

        async def save_task_metadata(self, task_id, metadata):
            self.saved_metadata = (task_id, metadata)

        async def save_storyboard(self, task_id, storyboard):
            return None

        def get_task_runtime_log_path(self, task_id):
            return tmp_path / task_id / "logs" / "runtime.jsonl"

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "llm": {"model": "demo-llm", "base_url": "http://llm"},
                "comfyui": {"comfyui_url": "http://comfyui", "runninghub_api_key": None},
            },
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
            "persistence": _RecordingPersistence(),
        },
    )()

    pipeline = CustomPipeline(fake_core)
    storyboard = Storyboard(
        title="demo",
        config=StoryboardConfig(
            media_width=1080,
            media_height=1920,
            task_id="task-1",
            render_backend="legacy",
        ),
    )
    result = type(
        "Result",
        (),
        {
            "video_path": str(tmp_path / "final.mp4"),
            "duration": 2.0,
            "file_size": 123,
        },
    )()

    await pipeline._persist_task_data(
        storyboard=storyboard,
        result=result,
        input_params={"text": "demo"},
    )

    assert fake_core.persistence.saved_metadata is not None
    _, metadata = fake_core.persistence.saved_metadata
    assert metadata["config"]["render_backend"] == "legacy"
    assert metadata["input"]["render_backend"] == "legacy"
    assert metadata["observability"]["runtime_log_path"] == str(
        tmp_path / "task-1" / "logs" / "runtime.jsonl"
    )


@pytest.mark.asyncio
async def test_asset_based_pipeline_persist_task_data_records_render_backend(tmp_path):
    class _RecordingPersistence:
        def __init__(self):
            self.saved_metadata = None

        async def save_task_metadata(self, task_id, metadata):
            self.saved_metadata = (task_id, metadata)

        async def save_storyboard(self, task_id, storyboard):
            return None

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "llm": {"model": "demo-llm", "base_url": "http://llm"},
            },
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
            "persistence": _RecordingPersistence(),
        },
    )()

    pipeline = AssetBasedPipeline(fake_core)
    output_path = tmp_path / "final.mp4"
    output_path.write_bytes(b"video")
    storyboard = Storyboard(
        title="demo",
        config=StoryboardConfig(
            media_width=1080,
            media_height=1920,
            task_id="task-1",
            render_backend="legacy",
        ),
    )
    ctx = PipelineContext(input_text="demo", params={})
    ctx.task_id = "task-1"
    ctx.final_video_path = str(output_path)
    ctx.storyboard = storyboard
    ctx.title = "demo"
    ctx.request = {"source": "runninghub"}

    await pipeline._persist_task_data(ctx)

    assert fake_core.persistence.saved_metadata is not None
    _, metadata = fake_core.persistence.saved_metadata
    assert metadata["config"]["render_backend"] == "legacy"
    assert metadata["input"]["render_backend"] == "legacy"
