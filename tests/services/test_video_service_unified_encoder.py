from __future__ import annotations

from types import SimpleNamespace

import ffmpeg
from PIL import Image

from pixelle_video.services import element_animation_renderer as animation_module
from pixelle_video.services.element_animation_renderer import PythonElementAnimationRenderer
from pixelle_video.services.video import VideoService


def test_single_video_with_bgm_does_not_bypass_bgm(monkeypatch) -> None:
    service = VideoService()
    monkeypatch.setattr(service, "_ensure_ffmpeg", lambda: None)
    calls: list[dict[str, object]] = []

    def _add_bgm_to_video(**kwargs):
        calls.append(kwargs)
        return str(kwargs["output"])

    monkeypatch.setattr(service, "_add_bgm_to_video", _add_bgm_to_video)

    result = service.concat_videos(
        ["one.mp4"],
        "out.mp4",
        bgm_path="music.mp3",
        bgm_volume=0.3,
        bgm_mode="loop",
    )

    assert result == "out.mp4"
    assert calls == [
        {
            "video": "one.mp4",
            "bgm_path": "music.mp3",
            "output": "out.mp4",
            "volume": 0.3,
            "mode": "loop",
        }
    ]


def test_filter_concat_injects_silence_for_missing_audio(monkeypatch) -> None:
    service = VideoService()
    monkeypatch.setattr(service, "_ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(
        service,
        "has_audio_stream",
        lambda path: path == "with-audio.mp4",
    )
    monkeypatch.setattr(service, "_get_video_duration", lambda path: 2.5)
    compiled_commands: list[list[str]] = []

    def _encode_run(build_output, *, quiet=False):
        output = build_output(vcodec="libx264", preset="medium", crf=23)
        compiled_commands.append(ffmpeg.compile(output))
        return "libx264"

    monkeypatch.setattr(service, "_encode_run", _encode_run)

    result = service._concat_filter(
        ["silent.mp4", "with-audio.mp4"],
        "out.mp4",
    )

    assert result == "out.mp4"
    command = " ".join(compiled_commands[0])
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in command
    assert "concat=n=2" in command
    assert "-c:v libx264" in command


def test_overlay_preserves_source_audio_and_uses_encoder_boundary(monkeypatch) -> None:
    service = VideoService()
    monkeypatch.setattr(service, "_ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(service, "has_audio_stream", lambda path: True)
    monkeypatch.setattr(
        ffmpeg,
        "probe",
        lambda path: {
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920},
            ]
        },
    )
    compiled_commands: list[list[str]] = []

    def _encode_run(build_output, *, quiet=False):
        output = build_output(vcodec="libx264", preset="medium", crf=23)
        compiled_commands.append(ffmpeg.compile(output))
        return "libx264"

    monkeypatch.setattr(service, "_encode_run", _encode_run)

    result = service.overlay_image_on_video(
        "source.mp4",
        "overlay.png",
        "out.mp4",
    )

    assert result == "out.mp4"
    command = " ".join(compiled_commands[0])
    assert "-c:a copy" in command
    assert "-c:v libx264" in command
    assert "overlay" in command


def test_element_animation_delegates_video_encoding_to_unified_executor(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[dict[str, object]] = []

    class _FakeEncoder:
        def encode_png_sequence(self, **kwargs):
            calls.append(kwargs)
            return str(kwargs["output_path"])

    renderer = PythonElementAnimationRenderer(video_encoder=_FakeEncoder())
    monkeypatch.setattr(animation_module, "get_temp_path", lambda: str(tmp_path))
    monkeypatch.setattr(
        renderer,
        "render_frame",
        lambda manifest, *, time: Image.new("RGB", (4, 4), "black"),
    )
    manifest = SimpleNamespace(
        timeline=SimpleNamespace(duration=1.0, fps=1),
        audio_path=None,
    )
    output_path = tmp_path / "animation.mp4"

    result = renderer.render_video(manifest, str(output_path))

    assert result == str(output_path)
    assert len(calls) == 1
    assert calls[0]["fps"] == 1
    assert calls[0]["duration"] == 1.0
    assert calls[0]["audio_path"] is None
    assert calls[0]["output_path"] == output_path
    assert str(calls[0]["frame_pattern"]).endswith("frame_%06d.png")


def test_public_video_service_keeps_stable_base_operations() -> None:
    service = VideoService()
    assert callable(service.merge_audio_video)
    assert callable(service.create_video_from_image)
    assert callable(service._pad_video_to_duration)
