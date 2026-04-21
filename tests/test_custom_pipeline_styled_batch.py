from pathlib import Path

import pytest

from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.custom import CustomPipeline


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

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt="avoid realism",
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

    result = await pipeline(
        text="scene one",
        tts_inference_mode="local",
    )

    assert captured["prompt_prefix"] is None
    assert captured["media_negative_prompt"] == "avoid realism"
    assert result.storyboard.frames[0].image_prompt == "styled prompt"


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
