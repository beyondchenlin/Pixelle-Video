from pathlib import Path

import pytest

from pixelle_video.models.media import MediaResult
from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor


@pytest.mark.asyncio
async def test_step_generate_media_forwards_media_negative_prompt(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt="bird-universe dog sprint")
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        media_negative_prompt="photo realism",
    )

    await processor._step_generate_media(frame, config)

    assert captured["negative_prompt"] == "photo realism"


@pytest.mark.asyncio
async def test_step_generate_media_uses_video_template_when_workflow_missing(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="video", url="https://example.com/frame.mp4", duration=2.5)

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.mp4")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt="dynamic bird-world dog sprint", duration=2.0)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/video_default.html",
        media_workflow=None,
    )

    await processor._step_generate_media(frame, config)

    assert captured["media_type"] == "video"
    assert captured["duration"] == 2.0


@pytest.mark.asyncio
async def test_compose_frame_html_uses_caption_punctuation_mode_for_subtitle_text(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
        template_text_policy="template_body",
    )
    frame = StoryboardFrame(
        index=0,
        narration="\u4f60\u597d\uff0c\u4e16\u754c\uff01",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="测试标题", config=config, frames=[frame])

    result = await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "composed.png"),
    )

    assert result == str(tmp_path / "composed.png")
    assert captured["text"] == "\u4f60\u597d\u4e16\u754c"
    assert frame.template_visual_path == str(tmp_path / "composed.png")


@pytest.mark.asyncio
async def test_compose_frame_html_allows_blank_template_body_text_for_shell_only_render(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
    )
    frame = StoryboardFrame(
        index=0,
        narration="Original subtitle text.",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "shell-only.png"),
        template_body_text="",
    )

    assert captured["text"] == ""
    assert frame.template_visual_path == str(tmp_path / "shell-only.png")


@pytest.mark.asyncio
async def test_compose_frame_html_uses_nonempty_template_body_text(monkeypatch, tmp_path):
    captured = {}

    class _FakeHTMLFrameGenerator:
        width = 1024
        height = 1024

        def __init__(self, template_path):
            captured["template_path"] = template_path

        async def generate_frame(self, **kwargs):
            captured.update(kwargs)
            return kwargs["output_path"]

    monkeypatch.setattr(
        "pixelle_video.services.template_visual_materializer.HTMLFrameGenerator",
        _FakeHTMLFrameGenerator,
    )
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        frame_template="1080x1920/image_life_insights_light.html",
    )
    frame = StoryboardFrame(
        index=0,
        narration="Original subtitle text.",
        image_prompt="prompt",
        image_path=str(tmp_path / "frame.png"),
        media_type="image",
    )
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    await processor._compose_frame_html(
        frame=frame,
        storyboard=storyboard,
        config=config,
        output_path=str(tmp_path / "override.png"),
        template_body_text="Override subtitle.",
    )

    assert captured["text"] == "Override subtitle"


@pytest.mark.asyncio
async def test_frame_processor_call_forwards_template_body_text_to_shell_only_render(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_generate_audio(frame, config):
        frame.audio_path = str(tmp_path / "audio.mp3")
        frame.duration = 1.0

    async def fake_generate_media(frame, config):
        frame.image_path = str(tmp_path / "frame.png")
        frame.media_type = "image"

    async def fake_compose_frame(frame, storyboard, config, *, template_body_text=None):
        captured["template_body_text"] = template_body_text
        frame.composed_image_path = str(tmp_path / "composed.png")

    async def fake_create_video_segment(frame, config):
        frame.video_segment_path = str(tmp_path / "segment.mp4")

    monkeypatch.setattr(processor, "_step_generate_audio", fake_generate_audio)
    monkeypatch.setattr(processor, "_step_generate_media", fake_generate_media)
    monkeypatch.setattr(processor, "_step_compose_frame", fake_compose_frame)
    monkeypatch.setattr(processor, "_step_create_video_segment", fake_create_video_segment)

    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
    )
    frame = StoryboardFrame(index=0, narration="Original subtitle text.", image_prompt="prompt")
    storyboard = Storyboard(title="Test title", config=config, frames=[frame])

    result = await processor(
        frame=frame,
        storyboard=storyboard,
        config=config,
        template_body_text="",
    )

    assert result is frame
    assert captured["template_body_text"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_fps", "expected_fps"),
    [
        (30, 90),
        (120, 120),
    ],
)
async def test_step_create_video_segment_uses_high_precision_fps_for_image_frames(
    monkeypatch,
    tmp_path,
    configured_fps,
    expected_fps,
):
    captured = {}

    class _FakeVideoService:
        def create_video_from_image(self, **kwargs):
            captured.update(kwargs)
            output = tmp_path / "segment.mp4"
            output.write_text("segment", encoding="utf-8")
            return str(output)

    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_frame_path",
        lambda task_id, index, kind: str(tmp_path / f"{index:02d}_{kind}"),
    )

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        video_fps=configured_fps,
    )
    frame = StoryboardFrame(
        index=0,
        narration="场景",
        image_prompt="prompt",
        audio_path=str(tmp_path / "audio.mp3"),
        composed_image_path=str(tmp_path / "composed.png"),
        media_type="image",
    )

    await processor._step_create_video_segment(frame, config)

    assert captured["fps"] == expected_fps


@pytest.mark.asyncio
async def test_step_create_video_segment_uses_element_motion_video_when_present(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class _FakeVideoService:
        def merge_audio_video(self, **kwargs):
            captured.update(kwargs)
            Path(kwargs["output"]).write_text("segment", encoding="utf-8")
            return kwargs["output"]

        def create_video_from_image(self, **kwargs):
            raise AssertionError("element motion video should bypass image segment creation")

    monkeypatch.setattr("pixelle_video.services.video.VideoService", _FakeVideoService)
    monkeypatch.setattr(
        "pixelle_video.utils.os_util.get_task_frame_path",
        lambda task_id, index, kind: str(tmp_path / f"{index:02d}_{kind}.mp4"),
    )

    processor = FrameProcessor(None)
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
    )
    frame = StoryboardFrame(
        index=0,
        narration="scene",
        image_prompt="prompt",
        audio_path=str(tmp_path / "audio.mp3"),
        image_path=str(tmp_path / "frame.png"),
        composed_image_path=str(tmp_path / "composed.png"),
        element_motion_video_path=str(tmp_path / "motion.mp4"),
        media_type="image",
    )

    await processor._step_create_video_segment(frame, config)

    assert captured == {
        "video": str(tmp_path / "motion.mp4"),
        "audio": str(tmp_path / "audio.mp3"),
        "output": str(tmp_path / "00_segment.mp4"),
        "replace_audio": True,
        "audio_volume": 1.0,
    }
    assert frame.video_segment_path == str(tmp_path / "00_segment.mp4")
