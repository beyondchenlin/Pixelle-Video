import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pixelle_video.config.loader import load_config_dict, save_config_dict
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.models.creation_package import CreationPackage
from pixelle_video.models.layered_template import (
    LayeredTemplateSpec,
    LayerSourceSpec,
    RectSpec,
    TemplateLayer,
)
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
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.text_overlay import TextOverlayPlan
from pixelle_video.models.text_style import TextStyleProfile
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.tts_split_strategy import DEFAULT_TTS_SPLIT_MODE


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


def _layered_spec_payload(template_id="demo") -> dict:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id=template_id,
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(
            TemplateLayer(
                id="media",
                type="generated_media",
                name="Generated media",
                rect=RectSpec(x=64, y=320, width=952, height=952),
                z_index=10,
                opacity=1.0,
                rotation=0.0,
                locked=False,
                source=LayerSourceSpec(
                    kind="generated_media",
                    ref="generated://primary",
                ),
                style={"object_fit": "contain"},
            ),
        ),
        metadata={},
    ).to_dict()


def _empty_layered_spec_payload(template_id="demo") -> dict:
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id=template_id,
        template_name="Demo",
        template_type="image",
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
        safe_area=RectSpec(x=64, y=64, width=952, height=1792),
        layers=(),
        metadata={},
    ).to_dict()


def test_render_manifest_round_trip_and_timing_config_defaults():
    config = StoryboardConfig(media_width=1080, media_height=1920)
    assert config.tts_batching_mode == "paragraph"
    assert config.tts_audio_strategy == "master_track"
    assert config.tts_split_mode == DEFAULT_TTS_SPLIT_MODE
    assert config.tts_sentence_joiner_mode == "direct"
    assert config.caption_punctuation_mode == "strip_all"
    assert config.preserve_natural_punctuation is True
    assert config.max_chars_per_tts_segment == 90
    assert config.tts_audio_boundary_fade_ms == 8
    assert config.subtitle_alignment_engine == "qwen_forced_aligner"
    assert config.silence_trim_tool is None
    assert config.render_backend == "hyperframes_compiled"

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


def test_storyboard_config_defaults_template_text_policy_to_caption_renderer():
    config = StoryboardConfig(media_width=1080, media_height=1920)

    assert config.template_text_policy == "caption_renderer"


def test_storyboard_config_rejects_invalid_template_text_policy():
    with pytest.raises(ValueError, match="template_text_policy"):
        StoryboardConfig(
            media_width=1080,
            media_height=1920,
            template_text_policy="invalid",
        )


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
    assert restored.caption_rendering_enabled is True


def test_render_manifest_round_trips_template_display_settings():
    manifest = RenderManifest(
        task_id="task-template-display",
        title="demo",
        width=1080,
        height=1920,
        fps=30,
        template_id="image_default",
        template_display={"show_title": True, "show_signature": False},
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.template_display.to_dict() == {
        "show_title": True,
        "show_signature": False,
    }


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
        "title-default",
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


def test_render_manifest_serializes_canvas_size_from_size_contract():
    manifest = RenderManifest(
        task_id="task-size",
        title="Size Demo",
        fps=30,
        template_id="image_landscape_minimal",
        canvas_width=1920,
        canvas_height=1080,
        media_width=768,
        media_height=768,
    )

    data = manifest.to_dict()

    assert (data["canvas_width"], data["canvas_height"]) == (1920, 1080)
    assert (data["width"], data["height"]) == (1920, 1080)
    assert (data["media_width"], data["media_height"]) == (768, 768)


def test_render_manifest_derives_canvas_media_layout_from_synced_media():
    manifest = RenderManifest(
        task_id="task-size",
        title="Size Demo",
        fps=30,
        template_id="image_landscape_minimal",
        canvas_width=1280,
        canvas_height=720,
        media_width=1280,
        media_height=720,
        sync_media_size_to_canvas=True,
    )

    data = manifest.to_dict()
    restored = RenderManifest.from_dict(data)

    assert data["media_layout_mode"] == "canvas"
    assert restored.media_layout_mode == "canvas"
    assert restored.sync_media_size_to_canvas is True


def test_render_manifest_round_trips_media_placement():
    manifest = RenderManifest(
        task_id="task-media-placement",
        title="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        fps=30,
        template_id="image_landscape_minimal",
        media_placement={"scale_percent": 90, "anchor": "bottom_right"},
    )

    restored = RenderManifest.from_dict(manifest.to_dict())

    assert restored.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 0,
        "offset_y": 0,
    }


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
        template_text_policy="template_body",
        storyboard_prompt_language="zh_CN",
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
    assert restored.template_text_policy == "template_body"
    assert restored.storyboard_prompt_language == "zh_CN"


def test_storyboard_config_layered_template_fields_round_trip_through_persistence(tmp_path):
    spec = _layered_spec_payload()
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        layered_template_spec=spec,
        selected_template_preset_id="user:demo",
    )

    service = PersistenceService(output_dir=str(tmp_path))
    restored = service._dict_to_config(service._config_to_dict(config))

    assert restored.layered_template_spec == spec
    assert restored.selected_template_preset_id == "user:demo"


def test_storyboard_config_empty_layered_template_snapshot_is_not_persisted(tmp_path):
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        layered_template_spec=_empty_layered_spec_payload(),
        selected_template_preset_id="system:1080x1920/image_default.html",
    )

    service = PersistenceService(output_dir=str(tmp_path))
    serialized = service._config_to_dict(config)
    restored = service._dict_to_config(serialized)

    assert "layered_template_spec" not in serialized
    assert restored.layered_template_spec is None
    assert restored.selected_template_preset_id is None


def test_storyboard_frame_template_visual_fields_round_trip_through_persistence(tmp_path):
    frame = StoryboardFrame(
        index=0,
        narration="Scene",
        image_prompt="Prompt",
        template_visual_path="frames/00_template.png",
        element_animation_manifest_path="frames/00_elements.json",
        element_motion_video_path="frames/00_motion.mp4",
    )

    service = PersistenceService(output_dir=str(tmp_path))
    restored = service._dict_to_frame(service._frame_to_dict(frame))

    assert restored.template_visual_path == "frames/00_template.png"
    assert restored.element_animation_manifest_path == "frames/00_elements.json"
    assert restored.element_motion_video_path == "frames/00_motion.mp4"


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
            "trace_repository": object(),
            "raw_payload_store": object(),
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
async def test_standard_pipeline_initialize_storyboard_preserves_media_placement():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {},
            "llm": None,
            "tts": None,
            "media": None,
            "video": None,
            "trace_repository": object(),
            "raw_payload_store": object(),
        },
    )()

    pipeline = StandardPipeline(fake_core)
    ctx = PipelineContext(
        input_text="demo",
        params={
            "media_width": 768,
            "media_height": 768,
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_placement": {"scale_percent": 90, "anchor": "right"},
        },
    )
    ctx.task_id = "task-placement"
    ctx.title = "demo"
    ctx.storyboard_plan = _storyboard_plan_from_segments(["Sentence 1."])
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.media_placement.to_dict() == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 90,
        "offset_x": 0,
        "offset_y": 0,
    }


@pytest.mark.asyncio
async def test_standard_pipeline_generate_content_defaults_prompt_language_to_english_for_internal_callers(
    monkeypatch,
):
    captured = {}

    class _FakeStoryboardGenerationService:
        def __init__(self, config):
            self.config = config

        async def generate(self, **kwargs):
            captured["prompt_language"] = kwargs["prompt_language"]
            return _storyboard_plan_from_segments(["Sentence 1."])

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService",
        _FakeStoryboardGenerationService,
    )

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {},
            "llm": None,
            "tts": None,
            "media": None,
            "video": None,
            "trace_repository": object(),
            "raw_payload_store": object(),
        },
    )()
    pipeline = StandardPipeline(fake_core)
    ctx = PipelineContext(
        input_text="Sentence 1.",
        params={"mode": "fixed"},
    )
    ctx.task_id = "task-default-language-content"

    await pipeline.generate_content(ctx)

    assert captured["prompt_language"] == DEFAULT_PROMPT_LANGUAGE


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_defaults_prompt_language_to_english_for_internal_callers(
    monkeypatch,
):
    captured = {}

    class _FakeImagePromptComposer:
        async def compose(self, **kwargs):
            captured["prompt_language"] = kwargs["prompt_language"]
            return SimpleNamespace(
                prompts=["prompt"],
                resolved_style=None,
                negative_prompt=None,
                planning_snapshot={},
                prompt_plan_bundle=None,
            )

    class _FakeNativePromptProjection:
        def project(self, plan, policy):
            return None

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer",
        _FakeImagePromptComposer,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.NativePromptProjection",
        _FakeNativePromptProjection,
    )

    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {"comfyui": {"image": {}}},
            "llm": None,
            "tts": None,
            "media": object(),
            "video": None,
            "trace_repository": object(),
            "raw_payload_store": object(),
        },
    )()
    pipeline = StandardPipeline(fake_core)
    monkeypatch.setattr(
        pipeline,
        "_get_text_rendering_result",
        lambda _ctx: SimpleNamespace(overlay_plan=None, overlay_policy=None),
    )
    ctx = PipelineContext(
        input_text="demo",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.storyboard_plan = _storyboard_plan_from_segments(["Sentence 1."])
    ctx.task_id = "task-default-language-visuals"

    await pipeline.plan_visuals(ctx)

    assert captured["prompt_language"] == DEFAULT_PROMPT_LANGUAGE
    assert ctx.image_prompts == ["prompt"]


@pytest.mark.asyncio
async def test_standard_pipeline_initialize_storyboard_defaults_prompt_language_to_english_when_missing():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {},
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

    assert ctx.config.storyboard_prompt_language == DEFAULT_PROMPT_LANGUAGE


@pytest.mark.asyncio
async def test_standard_pipeline_initialize_storyboard_preserves_prompt_language_when_snapshot_and_params_both_define_it():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {},
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
            "storyboard_prompt_language": "zh_CN",
        },
    )
    ctx.task_id = "task-1"
    ctx.title = "demo"
    ctx.storyboard_plan = _storyboard_plan_from_segments(["Sentence 1."])
    ctx.image_prompts = ["prompt"]
    ctx.planning_snapshot = {"storyboard_prompt_language": "zh_CN"}

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.storyboard_prompt_language == "zh_CN"


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
async def test_asset_based_pipeline_initialize_storyboard_uses_size_contract(
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
            "config": {},
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
        },
    )()

    pipeline = AssetBasedPipeline(fake_core)
    ctx = PipelineContext(
        input_text="intent",
        params={
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "1k",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
        },
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

    assert (captured["canvas_width"], captured["canvas_height"]) == (1280, 720)
    assert (captured["media_width"], captured["media_height"]) == (768, 768)
    assert captured["video_orientation"] == "landscape"
    assert captured["video_resolution_preset"] == "1k"
    assert captured["media_orientation"] == "square"
    assert captured["media_resolution_preset"] == "768"
    assert captured["sync_media_size_to_canvas"] is False


@pytest.mark.asyncio
async def test_asset_based_pipeline_initialize_storyboard_preserves_media_placement(
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
            "config": {},
            "llm": object(),
            "tts": object(),
            "media": object(),
            "video": object(),
        },
    )()

    pipeline = AssetBasedPipeline(fake_core)
    ctx = PipelineContext(
        input_text="intent",
        params={
            "media_placement": {"scale_percent": 90, "anchor": "bottom_left"},
        },
    )
    ctx.task_id = "task-asset-placement"
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

    assert captured["media_placement"] == {
        "scale_percent": 90,
        "anchor": "bottom_left",
    }


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
