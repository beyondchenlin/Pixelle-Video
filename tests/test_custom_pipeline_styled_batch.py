from pathlib import Path

import pytest

from pixelle_video.models.storyboard_planning import FramePlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch, StyleSourceSpec
from pixelle_video.pipelines.custom import CustomPipeline
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import apply_no_text_policy


@pytest.mark.asyncio
async def test_custom_pipeline_uses_styled_batch_and_threads_negative_prompt(monkeypatch, tmp_path):
    captured = {}
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    final_path = tmp_path / "final.mp4"

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1024, 1024

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            Path(output).write_bytes(b"video")
            return output

    class _FakePersistence:
        async def save_task_metadata(self, task_id, metadata):
            return None

        async def save_storyboard(self, task_id, storyboard):
            return None

    class _FakeFrameProcessor:
        async def __call__(self, frame, storyboard, config, total_frames, progress_callback=None):
            captured["media_negative_prompt"] = config.media_negative_prompt
            frame.duration = 1.0
            segment_path = tmp_path / f"segment_{frame.index}.mp4"
            segment_path.write_bytes(b"segment")
            frame.video_segment_path = str(segment_path)
            return frame

    class _FakeCore:
        def __init__(self):
            self.config = {"template": {"default_template": "1080x1920/image_default.html"}}
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.frame_processor = _FakeFrameProcessor()
            self.persistence = _FakePersistence()

    async def fake_generate_title(*args, **kwargs):
        return "Custom Title"

    async def real_styled_batch_with_capture(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        captured["world_preset_id"] = kwargs["world_preset_id"]
        captured["shot_preset_id"] = kwargs["shot_preset_id"]
        captured["content_mode"] = kwargs["content_mode"]
        captured["consistency_strength"] = kwargs["consistency_strength"]
        captured["role_strategy"] = kwargs["role_strategy"]
        captured["role_locking_strength"] = kwargs["role_locking_strength"]
        captured["shot_strategy"] = kwargs["shot_strategy"]
        return await generate_styled_image_prompt_batch(**kwargs)

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["styled prompt"]

    async def fake_plan_storyboard_batch(**kwargs):
        return type(
            "PlanResult",
            (),
            {
                "frames": (
                    FramePlan(
                        scene_id="scene-1",
                        shot_type="medium_shot",
                        shot_purpose="context",
                        world_elements=("strategy board",),
                        prompt_intent="teach the first relationship",
                    ),
                ),
                "planning_snapshot": {
                    "world_preset_id": "neutral_knowledge_storyboard",
                    "effective_final_shot_preset": "balanced_explainer",
                    "resolved_content_mode": "concept_explainer",
                    "selected_consistency_strength": "strong",
                    "resolved_role_strategy": "stable_explainer_cast",
                    "selected_role_locking_strength": "strong",
                    "selected_shot_strategy": "strict",
                    "world_preset": {
                        "display_name": "Neutral Knowledge Storyboard",
                        "style_core": "clean educational illustration",
                    },
                },
            },
        )()

    async def fake_resolve_style_spec(*args, **kwargs):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr("pixelle_video.utils.os_util.create_task_output_dir", lambda: (str(task_dir), "task-1"))
    monkeypatch.setattr("pixelle_video.utils.os_util.get_task_final_video_path", lambda task_id: str(final_path))
    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_title", fake_generate_title)
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_styled_image_prompt_batch",
        real_styled_batch_with_capture,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.plan_storyboard_batch",
        fake_plan_storyboard_batch,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="flat illustration",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeHTMLFrameGenerator)
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda template_name: "image")
    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)

    pipeline = CustomPipeline(_FakeCore())

    result = await pipeline(
        text="scene one",
        tts_inference_mode="local",
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        content_mode="concept_explainer",
        consistency_strength="strong",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
    )

    assert captured["prompt_prefix"] is None
    assert captured["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["shot_preset_id"] == "balanced_explainer"
    assert captured["content_mode"] == "concept_explainer"
    assert captured["consistency_strength"] == "strong"
    assert captured["role_strategy"] == "auto"
    assert captured["role_locking_strength"] == "strong"
    assert captured["shot_strategy"] == "strict"
    assert captured["media_negative_prompt"] is not None
    assert "text" in captured["media_negative_prompt"]
    assert "Chinese characters" in captured["media_negative_prompt"]
    assert result.storyboard.planning_snapshot["world_preset_id"] == "neutral_knowledge_storyboard"
    assert result.storyboard.planning_snapshot["frames"][0]["shot_type"] == "medium_shot"
    assert result.storyboard.config.world_preset_id == "neutral_knowledge_storyboard"
    assert result.storyboard.config.shot_preset_id == "balanced_explainer"
    assert result.storyboard.config.content_mode == "concept_explainer"
    assert result.storyboard.config.consistency_strength == "strong"
    assert result.storyboard.config.role_strategy == "stable_explainer_cast"
    assert result.storyboard.config.role_locking_strength == "strong"
    assert result.storyboard.config.shot_strategy == "strict"
    assert result.storyboard.frames[0].shot_type == "medium_shot"
    assert result.storyboard.frames[0].shot_purpose == "context"
    assert result.storyboard.frames[0].frame_source == "planner_generated"
    assert result.storyboard.frames[0].image_prompt == apply_no_text_policy(
        "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, styled prompt"
    )


@pytest.mark.asyncio
async def test_custom_pipeline_accepts_shared_prompt_prefix_override(monkeypatch, tmp_path):
    captured = {}
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    final_path = tmp_path / "final.mp4"

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1024, 1024

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            Path(output).write_bytes(b"video")
            return output

    class _FakePersistence:
        async def save_task_metadata(self, task_id, metadata):
            return None

        async def save_storyboard(self, task_id, storyboard):
            return None

    class _FakeFrameProcessor:
        async def __call__(self, frame, storyboard, config, total_frames, progress_callback=None):
            frame.duration = 1.0
            segment_path = tmp_path / f"segment_{frame.index}.mp4"
            segment_path.write_bytes(b"segment")
            frame.video_segment_path = str(segment_path)
            return frame

    class _FakeCore:
        def __init__(self):
            self.config = {
                "template": {"default_template": "1080x1920/image_default.html"},
                "comfyui": {"image": {"prompt_prefix": "legacy image prefix"}},
            }
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.frame_processor = _FakeFrameProcessor()
            self.persistence = _FakePersistence()

    async def fake_generate_title(*args, **kwargs):
        return "Custom Title"

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr("pixelle_video.utils.os_util.create_task_output_dir", lambda: (str(task_dir), "task-1"))
    monkeypatch.setattr("pixelle_video.utils.os_util.get_task_final_video_path", lambda task_id: str(final_path))
    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_title", fake_generate_title)
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeHTMLFrameGenerator)
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda template_name: "image")
    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)

    pipeline = CustomPipeline(_FakeCore())

    await pipeline(
        text="scene one",
        tts_inference_mode="local",
        prompt_prefix="angry birds world",
    )

    assert captured["prompt_prefix"] == "angry birds world"


@pytest.mark.asyncio
async def test_custom_pipeline_supports_video_templates(monkeypatch, tmp_path):
    captured = {}
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    final_path = tmp_path / "final.mp4"

    class _FakeHTMLFrameGenerator:
        def __init__(self, template_path):
            self.template_path = template_path

        def get_media_size(self):
            return 1024, 1024

    class _FakeVideoService:
        def concat_videos(self, videos, output, **kwargs):
            Path(output).write_bytes(b"video")
            return output

    class _FakePersistence:
        async def save_task_metadata(self, task_id, metadata):
            return None

        async def save_storyboard(self, task_id, storyboard):
            return None

    class _FakeFrameProcessor:
        async def __call__(self, frame, storyboard, config, total_frames, progress_callback=None):
            captured["media_negative_prompt"] = config.media_negative_prompt
            frame.duration = 1.0
            segment_path = tmp_path / f"segment_{frame.index}.mp4"
            segment_path.write_bytes(b"segment")
            frame.video_segment_path = str(segment_path)
            return frame

    class _FakeCore:
        def __init__(self):
            self.config = {
                "template": {"default_template": "1080x1920/video_default.html"},
                "comfyui": {"video": {"prompt_prefix": "legacy video"}},
            }
            self.llm = object()
            self.tts = object()
            self.media = object()
            self.video = object()
            self.frame_processor = _FakeFrameProcessor()
            self.persistence = _FakePersistence()

    async def fake_generate_title(*args, **kwargs):
        return "Custom Title"

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["media_type"] = kwargs["media_type"]
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["styled video prompt"],
            negative_prompt="avoid blur",
            resolved_style=None,
        )

    monkeypatch.setattr("pixelle_video.utils.os_util.create_task_output_dir", lambda: (str(task_dir), "task-1"))
    monkeypatch.setattr("pixelle_video.utils.os_util.get_task_final_video_path", lambda task_id: str(final_path))
    monkeypatch.setattr("pixelle_video.utils.content_generators.generate_title", fake_generate_title)
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeHTMLFrameGenerator)
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda template_name: "video")
    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)

    pipeline = CustomPipeline(_FakeCore())

    result = await pipeline(
        text="scene one",
        tts_inference_mode="local",
        media_workflow=None,
    )

    assert captured["media_type"] == "video"
    assert captured["prompt_prefix"] is None
    assert captured["media_negative_prompt"] == "avoid blur"
    assert result.storyboard.frames[0].image_prompt == "styled video prompt"
