from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routers.video import generate_video_sync
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


@pytest.mark.asyncio
async def test_generate_video_sync_passes_render_backend_to_video_core(monkeypatch, tmp_path):
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

    await generate_video_sync(
        VideoGenerateRequest(
            text="demo",
            frame_template="1080x1920/image_default.html",
            render_backend="hyperframes_compiled",
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
            "render_backend": "hyperframes_compiled",
        }
    ]
