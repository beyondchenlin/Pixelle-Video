import subprocess
import wave
from pathlib import Path

import ffmpeg
import pytest

from pixelle_video.services import video as video_module
from pixelle_video.services.video import VideoService


def _create_sine_mp3(output_path: Path, duration: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}:sample_rate=22050",
            "-c:a",
            "libmp3lame",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _create_silent_wav(output_path: Path, *, sample_count: int, sample_rate: int = 22050) -> None:
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * sample_count)


def _probe_stream_durations(path: Path) -> dict[str, float]:
    probe = ffmpeg.probe(str(path))
    return {
        stream["codec_type"]: float(stream["duration"])
        for stream in probe["streams"]
        if stream.get("codec_type") in {"audio", "video"}
    }


def _probe_format_duration(path: Path) -> float:
    probe = ffmpeg.probe(str(path))
    return float(probe["format"]["duration"])


@pytest.mark.parametrize("duration", [1.915646, 1.917])
def test_create_video_from_image_aligns_output_stream_durations(tmp_path, duration):
    audio_path = tmp_path / "sample.mp3"
    output_path = tmp_path / "segment.mp4"

    _create_sine_mp3(audio_path, duration=duration)

    service = VideoService()
    service.create_video_from_image(
        image=str(Path("resources/example.png")),
        audio=str(audio_path),
        output=str(output_path),
        fps=30,
    )

    durations = _probe_stream_durations(output_path)
    drift = abs(durations["video"] - durations["audio"])

    assert drift <= 0.005


@pytest.mark.parametrize("duration", [1.915646, 1.917, 2.449705])
def test_create_video_from_image_does_not_end_before_source_audio(tmp_path, duration):
    audio_path = tmp_path / "sample.mp3"
    output_path = tmp_path / "segment.mp4"

    _create_sine_mp3(audio_path, duration=duration)
    raw_audio_duration = _probe_format_duration(audio_path)

    service = VideoService()
    service.create_video_from_image(
        image=str(Path("resources/example.png")),
        audio=str(audio_path),
        output=str(output_path),
        fps=30,
    )

    durations = _probe_stream_durations(output_path)

    assert durations["audio"] >= raw_audio_duration
    assert durations["audio"] - raw_audio_duration < (1 / 30) + 0.005


def test_create_video_from_image_handles_tiny_positive_pad_duration(tmp_path):
    sample_rate = 22050
    fps = 90
    frame_count = 173
    samples_per_frame = sample_rate // fps

    assert sample_rate % fps == 0

    audio_path = tmp_path / "tiny-pad.wav"
    output_path = tmp_path / "segment.mp4"
    _create_silent_wav(
        audio_path,
        sample_count=samples_per_frame * frame_count - 1,
        sample_rate=sample_rate,
    )

    raw_audio_duration = _probe_format_duration(audio_path)
    expected_pad_duration = frame_count / fps - raw_audio_duration

    assert 0 < expected_pad_duration < 0.0001

    service = VideoService()
    service.create_video_from_image(
        image=str(Path("resources/example.png")),
        audio=str(audio_path),
        output=str(output_path),
        fps=fps,
    )

    durations = _probe_stream_durations(output_path)
    output_duration = _probe_format_duration(output_path)

    assert output_duration >= raw_audio_duration
    assert output_duration - raw_audio_duration < (1 / fps) + 0.005
    assert abs(durations["video"] - durations["audio"]) <= 0.005


def test_burn_ass_subtitles_rejects_same_input_and_output(tmp_path):
    video = tmp_path / "final.mp4"
    ass = tmp_path / "master.ass"
    video.write_bytes(b"video")
    ass.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="same path"):
        VideoService().burn_ass_subtitles(str(video), str(ass), str(video))


def test_escape_ffmpeg_filter_path_handles_windows_drive_and_spaces():
    escaped = VideoService()._escape_ffmpeg_filter_path(
        r"C:\测试 路径\master.ass"
    )

    assert r"C\:" in escaped
    assert r"C\\:" not in escaped
    assert "测试 路径" in escaped
    assert "master.ass" in escaped


def test_video_service_initialization_does_not_require_ffmpeg(monkeypatch):
    monkeypatch.setattr(video_module.shutil, "which", lambda _name: None)

    service = VideoService()

    with pytest.raises(RuntimeError, match="ffmpeg, ffprobe"):
        service._ensure_ffmpeg()


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1.0])
def test_ffmpeg_duration_rejects_invalid_values(duration):
    with pytest.raises(ValueError, match="finite non-negative"):
        video_module._ffmpeg_duration(duration)


def test_trim_silent_video_omits_audio_codec_option(monkeypatch, tmp_path):
    captured = {}

    class FakeGraph:
        def output(self, output, **options):
            captured["output"] = output
            captured["options"] = options
            return self

        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            return None

    service = VideoService()
    service._ffmpeg_checked = True
    monkeypatch.setattr(video_module.ffmpeg, "input", lambda *_args, **_kwargs: FakeGraph())
    monkeypatch.setattr(service, "has_audio_stream", lambda _video: False)
    monkeypatch.setattr(
        service,
        "_get_unique_temp_path",
        lambda _prefix, _name: str(tmp_path / "trimmed.mp4"),
    )

    service._trim_video_to_duration("silent.mp4", 1.5)

    assert captured["options"] == {"vcodec": "copy"}


@pytest.mark.parametrize("fps", [0, -1, 1.5, True])
def test_create_video_from_image_rejects_invalid_fps_before_running_ffmpeg(fps):
    with pytest.raises(ValueError, match="positive integer"):
        VideoService().create_video_from_image("image.png", "audio.mp3", "video.mp4", fps=fps)
