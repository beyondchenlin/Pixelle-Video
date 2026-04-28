import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import api.schemas.video as video_schema_module
from api.routers.video import (
    build_video_generation_params,
    generate_video_async,
    generate_video_sync,
)
from api.schemas.video import VideoGenerateRequest
from pixelle_video.models.size_contract import (
    GenerationSizeContract,
    STANDARD_VIDEO_SIZE_PRESETS,
)
from pixelle_video.models.storyboard_limits import StoryboardGenerationLimits


class _FakePixelleVideo:
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.calls: list[dict] = []

    async def generate_video(self, **kwargs):
        self.calls.append(kwargs)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(b"video")
        return SimpleNamespace(
            video_path=str(self.output_path),
            duration=2.5,
        )


def test_video_generate_request_rejects_removed_hyperframes_alias():
    with pytest.raises(ValidationError, match="hyperframes_compiled"):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            render_backend="hyperframes",
        )


def test_video_generate_request_accepts_text_rendering_policy():
    request = VideoGenerateRequest(
        text="hello",
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
                "density": "medium",
                "max_items_per_frame": 2,
            },
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "no letters in image",
                "negative_prompt": "letters, watermark",
            },
        },
    )

    assert request.text_rendering.overlay.enabled is True
    assert request.text_rendering.image_text.suppress_embedded_text is True
    assert request.text_rendering.image_text.positive_prompt == "no letters in image"


def test_video_generate_request_rejects_legacy_text_fields():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", text_layer={"enabled": True})

    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", forbid_embedded_text_in_image=True)


@pytest.mark.parametrize(
    "text_rendering",
    [
        {"unexpected": {}},
        {"overlay": {"enabled": True, "unexpected": "x"}},
        {"image_text": {"suppress_embedded_text": True, "unexpected": "x"}},
    ],
)
def test_video_generate_request_rejects_unknown_text_rendering_keys(text_rendering: dict):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", text_rendering=text_rendering)


def test_video_generate_request_accepts_tts_text_policy_controls():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        tts_split_mode="external_only",
        max_chars_per_tts_segment=88,
        tts_split_overflow_policy="hard_limit",
        tts_boundary_search_radius=7,
        tts_soft_overflow_chars=2,
        tts_audio_boundary_fade_ms=12,
        tts_sentence_joiner_mode="space",
        caption_punctuation_mode="preserve",
        preserve_natural_punctuation=False,
    )

    assert request.tts_split_mode == "external_only"
    assert request.max_chars_per_tts_segment == 88
    assert request.tts_sentence_joiner_mode == "space"
    assert request.caption_punctuation_mode == "preserve"
    assert request.preserve_natural_punctuation is False


def test_video_generate_request_accepts_prompt_generation_performance_controls():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        llm_prompt_batch_size=8,
        llm_prompt_batch_concurrent_limit=3,
    )

    assert request.llm_prompt_batch_size == 8
    assert request.llm_prompt_batch_concurrent_limit == 3


def test_video_generate_request_accepts_size_contract_controls():
    request = VideoGenerateRequest(
        text="demo",
        canvas_width=1280,
        canvas_height=720,
        media_width=768,
        media_height=768,
        video_orientation="landscape",
        video_resolution_preset="landscape_hd",
        media_orientation="square",
        media_resolution_preset="768",
        sync_media_size_to_canvas=False,
    )

    assert request.canvas_width == 1280
    assert request.canvas_height == 720
    assert request.media_width == 768
    assert request.media_height == 768
    assert request.video_orientation == "landscape"
    assert request.video_resolution_preset == "landscape_hd"
    assert request.media_orientation == "square"
    assert request.media_resolution_preset == "768"
    assert request.sync_media_size_to_canvas is False


def test_video_generate_request_accepts_new_full_hd_preset():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="landscape_full_hd",
        ),
        request_id="req_test",
    )

    assert (params["canvas_width"], params["canvas_height"]) == (1920, 1080)
    assert params["video_resolution_preset"] == "landscape_full_hd"


@pytest.mark.parametrize(
    ("orientation", "preset"),
    [
        (orientation, preset)
        for orientation, presets in STANDARD_VIDEO_SIZE_PRESETS.items()
        for preset in presets
    ],
)
def test_video_generate_request_infers_orientation_from_standard_preset(
    orientation: str,
    preset: str,
):
    request = VideoGenerateRequest(text="demo", video_resolution_preset=preset)

    assert request.video_orientation == orientation
    assert request.video_resolution_preset == preset


def test_video_generate_request_rejects_conflicting_standard_preset_orientation():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            video_orientation="landscape",
            video_resolution_preset="portrait_hd",
        )


def test_video_generate_request_rejects_non_standard_1920x720_output():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            video_resolution_preset="1920x720",
        )


def test_video_generate_request_accepts_size_contract_default_params():
    params = GenerationSizeContract.default().to_params()
    request = VideoGenerateRequest(text="demo", **params)

    assert request.video_resolution_preset == "landscape_hd"


def test_build_video_generation_params_preserves_legacy_media_only_canvas_size():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            media_width=1080,
            media_height=1920,
        ),
        request_id="req_test",
    )

    assert (params["canvas_width"], params["canvas_height"]) == (1080, 1920)
    assert (params["media_width"], params["media_height"]) == (1080, 1920)


def test_video_generate_request_rejects_invalid_size_contract_controls():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_orientation="landscape",
            media_resolution_preset="768",
        )


def test_video_generate_request_rejects_video_preset_for_media_resolution():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            media_resolution_preset="landscape_hd",
        )


def test_video_generate_request_accepts_storyboard_generation_contract_fields():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        mode="generate",
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=4,
        storyboard_prompt_language="zh_CN",
        script_length_mode="custom",
        script_target_words=180,
    )

    assert request.storyboard_mode == "smart"
    assert request.storyboard_count_mode == "manual"
    assert request.storyboard_scene_count == 4
    assert request.storyboard_prompt_language == "zh_CN"
    assert request.script_length_mode == "custom"
    assert request.script_target_words == 180


def test_video_generate_request_defaults_punctuation_max_scene_count_for_punctuation_mode():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        storyboard_mode="punctuation",
    )

    assert request.storyboard_max_scene_count == 60


def test_video_generate_request_defaults_deterministic_max_scene_count_for_sentence_mode():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        storyboard_mode="sentence",
    )

    assert request.storyboard_max_scene_count == 60


def test_video_generate_request_clamps_deterministic_default_to_configured_limit(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(
            min_scene_count=1,
            max_scene_count=4,
            deterministic_max_scene_count_limit=40,
        ),
    )

    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        storyboard_mode="punctuation",
    )

    assert request.storyboard_max_scene_count == 40


def test_video_generate_request_defaults_storyboard_prompt_language_to_english_for_api_compatibility():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
    )

    assert request.storyboard_prompt_language == "zh_CN"


def test_video_generate_request_accepts_plan_identity_frame_overrides():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        frame_overrides=[
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": ["visual_goal", "prompt_intent"],
                "visual_goal": "Locked visual goal.",
                "prompt_intent": "Locked prompt intent.",
            }
        ],
    )

    assert request.frame_overrides[0].frame_id == "frame_0001"
    assert request.frame_overrides[0].locked_fields == ["visual_goal", "prompt_intent"]


def test_video_generate_request_rejects_removed_narration_text_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["narration_text"],
                    "narration_text": "This old field must not be accepted.",
                }
            ],
        )


def test_video_generate_request_schema_describes_source_text_contract_not_narration_generation():
    schema_text = json.dumps(VideoGenerateRequest.model_json_schema())

    assert "AI generates narrations" not in schema_text
    assert "narration generation" not in schema_text
    assert "complete source_text" in schema_text


def test_video_generate_request_rejects_non_sha256_frame_override_source_digest():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "z" * 64,
                    "locked_fields": ["visual_goal"],
                    "visual_goal": "Locked visual goal.",
                }
            ],
        )


@pytest.mark.parametrize(
    "legacy_payload",
    [
        {"n_scenes": 5},
        {"split_mode": "sentence"},
    ],
)
def test_video_generate_request_rejects_legacy_storyboard_fields(legacy_payload):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            **legacy_payload,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"storyboard_mode": "smart", "storyboard_count_mode": "auto", "storyboard_scene_count": 4},
        {"storyboard_mode": "smart", "storyboard_count_mode": "manual"},
        {"storyboard_mode": "smart", "storyboard_max_scene_count": 60},
        {"storyboard_mode": "sentence", "storyboard_count_mode": "manual", "storyboard_scene_count": 2},
        {"storyboard_mode": "punctuation", "storyboard_count_mode": "auto", "storyboard_scene_count": 2},
        {"storyboard_mode": "punctuation", "storyboard_max_scene_count": 201},
        {"storyboard_mode": "sentence", "storyboard_max_scene_count": 201},
        {"mode": "fixed", "script_length_mode": "short"},
        {"mode": "fixed", "script_target_words": 120},
        {"mode": "generate", "script_length_mode": "custom"},
        {"mode": "generate", "script_length_mode": "auto", "script_target_words": 120},
    ],
)
def test_video_generate_request_rejects_invalid_storyboard_contract_combinations(payload):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            **payload,
        )


def test_video_generate_request_rejects_deterministic_scene_limit_above_configured_cap(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(
            min_scene_count=1,
            max_scene_count=4,
            deterministic_max_scene_count_limit=40,
        ),
    )

    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            storyboard_mode="sentence",
            storyboard_max_scene_count=41,
        )


def test_video_generate_request_rejects_scene_count_above_configured_limit(monkeypatch):
    monkeypatch.setattr(
        video_schema_module,
        "current_storyboard_generation_limits",
        lambda: StoryboardGenerationLimits(min_scene_count=1, max_scene_count=4),
    )

    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("llm_prompt_batch_size", 0),
        ("llm_prompt_batch_size", 51),
        ("llm_prompt_batch_concurrent_limit", 0),
        ("llm_prompt_batch_concurrent_limit", 11),
    ],
)
def test_video_generate_request_rejects_invalid_prompt_generation_performance_controls(
    field_name: str,
    value: int,
):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            **{field_name: value},
        )


@pytest.mark.asyncio
async def test_generate_video_sync_passes_tts_text_policy_controls_to_video_core(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-tts-policy" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            tts_split_mode="external_only",
            max_chars_per_tts_segment=88,
            tts_split_overflow_policy="hard_limit",
            tts_boundary_search_radius=7,
            tts_soft_overflow_chars=2,
            tts_audio_boundary_fade_ms=12,
            tts_sentence_joiner_mode="space",
            caption_punctuation_mode="preserve",
            preserve_natural_punctuation=False,
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    call = fake_pixelle_video.calls[0]
    assert call["tts_split_mode"] == "external_only"
    assert call["max_chars_per_tts_segment"] == 88
    assert call["tts_split_overflow_policy"] == "hard_limit"
    assert call["tts_boundary_search_radius"] == 7
    assert call["tts_soft_overflow_chars"] == 2
    assert call["tts_audio_boundary_fade_ms"] == 12
    assert call["tts_sentence_joiner_mode"] == "space"
    assert call["caption_punctuation_mode"] == "preserve"
    assert call["preserve_natural_punctuation"] is False


@pytest.mark.asyncio
async def test_generate_video_sync_passes_prompt_generation_performance_controls_to_video_core(
    monkeypatch,
    tmp_path,
):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-prompt-performance" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            llm_prompt_batch_size=8,
            llm_prompt_batch_concurrent_limit=3,
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    call = fake_pixelle_video.calls[0]
    assert call["llm_prompt_batch_size"] == 8
    assert call["llm_prompt_batch_concurrent_limit"] == 3


@pytest.mark.asyncio
async def test_generate_video_sync_passes_explicit_size_contract_without_template_lookup(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "task-size-contract" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    def fail_template_size_lookup(*args, **kwargs):
        raise AssertionError("API must not derive size from frame_template")

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        fail_template_size_lookup,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            canvas_width=1280,
            canvas_height=720,
            media_width=768,
            media_height=768,
            video_orientation="landscape",
            video_resolution_preset="1k",
            media_orientation="square",
            media_resolution_preset="768",
            sync_media_size_to_canvas=False,
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    call = fake_pixelle_video.calls[0]
    assert (call["canvas_width"], call["canvas_height"]) == (1280, 720)
    assert (call["media_width"], call["media_height"]) == (768, 768)
    assert call["video_orientation"] == "landscape"
    assert call["video_resolution_preset"] == "1k"
    assert call["media_orientation"] == "square"
    assert call["media_resolution_preset"] == "768"
    assert call["sync_media_size_to_canvas"] is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("content_mode", "bogus"),
        ("role_strategy", "bogus"),
        ("consistency_strength", "bogus"),
        ("role_locking_strength", "bogus"),
        ("shot_strategy", "bogus"),
    ],
)
def test_video_generate_request_rejects_invalid_storyboard_controls(field_name: str, value: str):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            **{field_name: value},
        )


@pytest.mark.parametrize(
    "frame_overrides",
    [
        [{"scene_id": "1"}],
        [
            {
                "scene_id": "1",
                "snapshot_identity": "snapshot:demo",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
                "unexpected": "value",
            }
        ],
    ],
)
def test_video_generate_request_rejects_malformed_frame_overrides(frame_overrides: list[dict[str, str]]):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            frame_overrides=frame_overrides,
        )


def test_video_generate_request_rejects_legacy_scene_identity_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            frame_overrides=[
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
                }
            ],
        )


def test_video_generate_request_rejects_narration_text_frame_override():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["narration_text"],
                    "narration_text": "legacy narration",
                }
            ],
        )


@pytest.mark.parametrize("tts_audio_strategy", ["per_frame", "bogus"])
def test_video_generate_request_rejects_unsupported_tts_audio_strategy(tts_audio_strategy):
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            tts_audio_strategy=tts_audio_strategy,
        )


@pytest.mark.asyncio
async def test_generate_video_sync_passes_storyboard_controls_to_video_core(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-1" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            render_backend="hyperframes_compiled",
            tts_audio_strategy="master_track",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=4,
            storyboard_prompt_language="zh_CN",
            script_length_mode="custom",
            script_target_words=180,
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="auto",
            role_locking_strength="strong",
            shot_strategy="strict",
            text_rendering={
                "overlay": {
                    "enabled": True,
                    "mode": "programmatic_only",
                    "renderer_targets": ["ass"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "no letters in image",
                    "negative_prompt": "letters, watermark",
                },
            },
            frame_overrides=[
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal", "prompt_intent"],
                    "visual_goal": "Locked visual goal.",
                    "prompt_intent": "Locked prompt intent.",
                }
            ],
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert fake_pixelle_video.calls == [
        {
            "text": "demo",
            "mode": "generate",
            "title": None,
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 4,
            "storyboard_max_scene_count": None,
            "storyboard_prompt_language": "zh_CN",
            "script_length_mode": "custom",
            "script_target_words": 180,
            "min_image_prompt_words": 30,
            "max_image_prompt_words": 60,
            "canvas_width": 1280,
            "canvas_height": 720,
            "media_width": 768,
            "media_height": 768,
            "video_orientation": "landscape",
            "video_resolution_preset": "landscape_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
            "media_workflow": None,
            "video_fps": 30,
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": None,
            "bgm_path": None,
            "bgm_volume": 0.3,
            "request_id": "req_test",
            "render_backend": "hyperframes_compiled",
            "tts_audio_strategy": "master_track",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "text_rendering": {
                "overlay": {
                    "enabled": True,
                    "mode": "programmatic_only",
                    "renderer_targets": ["ass"],
                    "density": "medium",
                    "max_items_per_frame": 2,
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "no letters in image",
                    "negative_prompt": "letters, watermark",
                },
            },
            "frame_overrides": [
                {
                    "plan_id": "plan_abc",
                    "plan_revision": 1,
                    "frame_id": "frame_0001",
                    "source_digest": "a" * 64,
                    "locked_fields": ["visual_goal", "prompt_intent"],
                    "visual_goal": "Locked visual goal.",
                    "prompt_intent": "Locked prompt intent.",
                }
            ],
        }
    ]


@pytest.mark.asyncio
async def test_generate_video_async_reuses_active_duplicate_task(monkeypatch, tmp_path):
    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    class _ExistingTask:
        task_id = "existing-task"

    class _FakeTaskManager:
        execution_mode = "embedded"

        async def reserve_or_reuse_generation_task(
            self,
            *,
            task_type,
            generation_fingerprint,
            request_params,
        ):
            assert task_type.value == "video_generation"
            assert generation_fingerprint
            assert request_params["generation_fingerprint"] == generation_fingerprint
            return SimpleNamespace(
                task=_ExistingTask(),
                created=False,
                reused_reason="active",
            )

        async def execute_task(self, **_kwargs):
            raise AssertionError("duplicate async request should not start execution")

    monkeypatch.setattr("api.routers.video.task_manager", _FakeTaskManager())
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    response = await generate_video_async(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert response.task_id == "existing-task"
    assert response.message == "Task already running"
    assert fake_pixelle_video.calls == []


@pytest.mark.asyncio
async def test_generate_video_async_passes_text_rendering_to_video_core(monkeypatch, tmp_path):
    class _FakeFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1080, 1920

    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)
    captured = {}

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    class _FakeTaskManager:
        execution_mode = "embedded"

        async def reserve_or_reuse_generation_task(
            self,
            *,
            task_type,
            generation_fingerprint,
            request_params,
        ):
            assert task_type.value == "video_generation"
            assert generation_fingerprint
            assert request_params["generation_fingerprint"] == generation_fingerprint
            return SimpleNamespace(
                task=SimpleNamespace(task_id="task-1"),
                created=True,
                reused_reason=None,
            )

        async def execute_task(self, *, task_id, coro_func):
            captured["task_id"] = task_id
            captured["result"] = await coro_func()

    monkeypatch.setattr("api.routers.video.task_manager", _FakeTaskManager())

    response = await generate_video_async(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            text_rendering={
                "overlay": {
                    "enabled": True,
                    "mode": "hybrid",
                    "renderer_targets": ["hyperframes"],
                },
                "image_text": {
                    "suppress_embedded_text": True,
                    "negative_prompt": "letters",
                },
            },
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert response.task_id == "task-1"
    assert captured["task_id"] == "task-1"
    assert fake_pixelle_video.calls[0]["request_id"] == "req_test"
    assert fake_pixelle_video.calls[0]["api_task_id"] == "task-1"
    text_rendering = fake_pixelle_video.calls[0]["text_rendering"]
    assert text_rendering["overlay"] == {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes"],
        "density": "medium",
        "max_items_per_frame": 2,
    }
    assert text_rendering["image_text"]["suppress_embedded_text"] is True
    assert "no visible text" in text_rendering["image_text"]["positive_prompt"]
    assert "no watermark" in text_rendering["image_text"]["positive_prompt"]
    assert text_rendering["image_text"]["negative_prompt"] == "letters"
    assert "caption_style" not in text_rendering
    assert "overlay_style" not in text_rendering


@pytest.mark.asyncio
async def test_generate_video_async_preserves_explicit_text_styles(monkeypatch, tmp_path):
    output_path = tmp_path / "task-async" / "final.mp4"
    fake_pixelle_video = _FakePixelleVideo(output_path)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        lambda template_path: SimpleNamespace(get_media_size=lambda: (1080, 1920)),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda template_path: template_path,
    )
    monkeypatch.setattr("api.routers.video.new_correlation_id", lambda prefix: f"{prefix}_test")

    class _FakeTaskManager:
        async def reserve_or_reuse_generation_task(self, **_kwargs):
            return SimpleNamespace(
                created=True,
                task=SimpleNamespace(task_id="task-1"),
            )

        async def execute_task(self, *, task_id, coro_func):
            await coro_func()

    monkeypatch.setattr("api.routers.video.task_manager", _FakeTaskManager())

    await generate_video_async(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            text_rendering={
                "caption_style": {
                    "font_size": 72,
                    "primary_color": "#FFFF00",
                },
                "overlay_style": {
                    "font_size": 88,
                    "position": "center",
                },
            },
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    text_rendering = fake_pixelle_video.calls[0]["text_rendering"]
    assert text_rendering["caption_style"]["font_size"] == 72
    assert text_rendering["caption_style"]["primary_color"] == "#FFFF00"
    assert text_rendering["overlay_style"]["font_size"] == 88
    assert text_rendering["overlay_style"]["position"] == "center"
