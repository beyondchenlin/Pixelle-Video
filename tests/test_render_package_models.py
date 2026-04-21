import pytest

from pixelle_video.config.loader import load_config_dict, save_config_dict
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderManifest,
    SentenceUnit,
    VisualClip,
)
from pixelle_video.models.storyboard import StoryboardConfig
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.pipelines.custom import CustomPipeline
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.pipelines.storyboard_config import resolve_storyboard_render_kwargs
from pixelle_video.services.persistence import PersistenceService


def test_render_manifest_round_trip_and_timing_config_defaults():
    config = StoryboardConfig(media_width=1080, media_height=1920)
    assert config.tts_batching_mode == "paragraph"
    assert config.subtitle_alignment_engine == "qwen_forced_aligner"
    assert config.silence_trim_tool is None

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
    assert restored.audio_blocks[0].end == 4.2


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


def test_storyboard_config_render_fields_round_trip_through_persistence(tmp_path):
    config = StoryboardConfig(
        media_width=1080,
        media_height=1920,
        tts_batching_mode="sentence",
        tts_batch_max_sentences=4,
        tts_batch_max_chars=120,
        subtitle_alignment_engine="whisperx",
        silence_trim_tool="ffmpeg",
        silence_trim_margin_ms=80,
        render_backend="hyperframes",
    )

    service = PersistenceService(output_dir=str(tmp_path))
    restored = service._dict_to_config(service._config_to_dict(config))

    assert restored.tts_batching_mode == "sentence"
    assert restored.tts_batch_max_sentences == 4
    assert restored.tts_batch_max_chars == 120
    assert restored.subtitle_alignment_engine == "whisperx"
    assert restored.silence_trim_tool == "ffmpeg"
    assert restored.silence_trim_margin_ms == 80
    assert restored.render_backend == "hyperframes"


def test_render_config_loads_and_saves_through_yaml_round_trip(tmp_path):
    config_path = tmp_path / "config.yaml"
    saved_path = tmp_path / "saved-config.yaml"
    config_path.write_text(
        """
render:
  backend: hyperframes
  timing:
    tts_batching_mode: sentence
    tts_batch_max_sentences: 6
    tts_batch_max_chars: 180
    subtitle_alignment_engine: whisperx
    silence_trim_tool: ffmpeg
    silence_trim_margin_ms: 90
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config_dict(str(config_path))

    parsed = PixelleVideoConfig(**loaded)
    assert parsed.render.backend == "hyperframes"
    assert parsed.render.timing.tts_batching_mode == "sentence"
    assert parsed.render.timing.tts_batch_max_sentences == 6
    assert parsed.render.timing.tts_batch_max_chars == 180
    assert parsed.render.timing.subtitle_alignment_engine == "whisperx"
    assert parsed.render.timing.silence_trim_tool == "ffmpeg"
    assert parsed.render.timing.silence_trim_margin_ms == 90

    save_config_dict(parsed.to_dict(), str(saved_path))
    reloaded = load_config_dict(str(saved_path))
    reparsed = PixelleVideoConfig(**reloaded)

    assert reparsed.render.backend == "hyperframes"
    assert reparsed.render.timing.tts_batching_mode == "sentence"
    assert reparsed.render.timing.silence_trim_tool == "ffmpeg"


def test_resolve_storyboard_render_kwargs_honors_explicit_none_over_config_default():
    runtime_config = {
        "render": {
            "backend": "cinematic",
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
    assert resolved["render_backend"] == "cinematic"


@pytest.mark.asyncio
async def test_standard_pipeline_initialize_storyboard_uses_render_config_defaults():
    fake_core = type(
        "FakeCore",
        (),
        {
            "config": {
                "render": {
                    "backend": "cinematic",
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
    ctx.narrations = ["Sentence 1."]
    ctx.image_prompts = ["prompt"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.tts_batching_mode == "sentence"
    assert ctx.config.tts_batch_max_sentences == 5
    assert ctx.config.tts_batch_max_chars == 160
    assert ctx.config.subtitle_alignment_engine == "whisperx"
    assert ctx.config.silence_trim_tool == "ffmpeg"
    assert ctx.config.silence_trim_margin_ms == 75
    assert ctx.config.render_backend == "cinematic"
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
                    "backend": "cinematic",
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
    ctx.narrations = ["Sentence 1. Sentence 2!"]
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
                    "backend": "cinematic",
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
    assert captured["render_backend"] == "cinematic"


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
                    "backend": "cinematic",
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
    assert captured["render_backend"] == "cinematic"
