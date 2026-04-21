import pytest

from pixelle_video.models.media import MediaResult
from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
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
