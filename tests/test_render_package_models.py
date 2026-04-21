from pixelle_video.models.render_package import (
    AudioBlock,
    CaptionCue,
    RenderManifest,
    SentenceUnit,
    VisualClip,
)
from pixelle_video.models.storyboard import StoryboardConfig
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
