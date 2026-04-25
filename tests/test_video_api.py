from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routers.video import generate_video_async, generate_video_sync
from api.schemas.video import VideoGenerateRequest


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


def test_video_generate_request_accepts_text_layer_policy():
    request = VideoGenerateRequest(
        text="demo",
        frame_template="1080x1920/image_default.html",
        text_layer={
            "enabled": True,
            "mode": "hybrid",
            "renderer_targets": ["hyperframes", "ass"],
            "density": "low",
            "max_items_per_frame": 1,
        },
    )

    assert request.text_layer == {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes", "ass"],
        "density": "low",
        "max_items_per_frame": 1,
    }


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
            world_preset_id="neutral_knowledge_storyboard",
            shot_preset_id="balanced_explainer",
            consistency_strength="strong",
            content_mode="concept_explainer",
            role_strategy="auto",
            role_locking_strength="strong",
            shot_strategy="strict",
            forbid_embedded_text_in_image=False,
            text_layer={
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["ass"],
            },
            frame_overrides=[
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
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
            "n_scenes": 5,
            "min_narration_words": 5,
            "max_narration_words": 20,
            "min_image_prompt_words": 30,
            "max_image_prompt_words": 60,
            "media_width": 1080,
            "media_height": 1920,
            "media_workflow": None,
            "video_fps": 30,
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": None,
            "bgm_path": None,
            "bgm_volume": 0.3,
            "request_id": "req_test",
            "render_backend": "hyperframes_compiled",
            "world_preset_id": "neutral_knowledge_storyboard",
            "shot_preset_id": "balanced_explainer",
            "consistency_strength": "strong",
            "content_mode": "concept_explainer",
            "role_strategy": "auto",
            "role_locking_strength": "strong",
            "shot_strategy": "strict",
            "forbid_embedded_text_in_image": False,
            "text_layer": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["ass"],
            },
            "frame_overrides": [
                {
                    "scene_id": "scene-1",
                    "snapshot_identity": "snapshot:scene-1",
                    "locked_fields": ["shot_type"],
                    "shot_type": "medium_shot",
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
async def test_generate_video_async_passes_no_text_toggle_to_video_core(monkeypatch, tmp_path):
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
            forbid_embedded_text_in_image=False,
            text_layer={
                "enabled": True,
                "mode": "hybrid",
                "renderer_targets": ["hyperframes"],
            },
        ),
        fake_pixelle_video,
        SimpleNamespace(base_url="http://testserver/"),
    )

    assert response.task_id == "task-1"
    assert captured["task_id"] == "task-1"
    assert fake_pixelle_video.calls[0]["request_id"] == "req_test"
    assert fake_pixelle_video.calls[0]["api_task_id"] == "task-1"
    assert fake_pixelle_video.calls[0]["forbid_embedded_text_in_image"] is False
    assert fake_pixelle_video.calls[0]["text_layer"] == {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes"],
    }
