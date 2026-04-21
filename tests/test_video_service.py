from pathlib import Path
import subprocess

import ffmpeg
import pytest

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


def _probe_stream_durations(path: Path) -> dict[str, float]:
    probe = ffmpeg.probe(str(path))
    return {
        stream["codec_type"]: float(stream["duration"])
        for stream in probe["streams"]
        if stream.get("codec_type") in {"audio", "video"}
    }


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
