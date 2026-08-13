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


def test_bgm_resource_name_prefers_custom_resource_over_working_directory(
    monkeypatch,
    tmp_path,
):
    project_root = tmp_path / "project"
    custom_bgm = project_root / "data" / "bgm" / "music.mp3"
    custom_bgm.parent.mkdir(parents=True)
    custom_bgm.write_bytes(b"custom")
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    (working_dir / "music.mp3").write_bytes(b"unrelated")
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(project_root))
    monkeypatch.chdir(working_dir)

    resolved = VideoService().resolve_bgm_path("music.mp3")

    assert resolved == str(custom_bgm.resolve())


def test_optional_bgm_returns_none_only_when_file_is_missing(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(project_root))
    service = VideoService()

    assert service.resolve_optional_bgm_path(None) is None
    assert service.resolve_optional_bgm_path("") is None
    assert service.resolve_optional_bgm_path("missing.mp3") is None

    with pytest.raises(ValueError, match="surrounding whitespace"):
        service.resolve_optional_bgm_path(" missing.mp3 ")


def test_bgm_publish_is_atomic_and_preserves_existing_output_on_failure(
    monkeypatch,
    tmp_path,
):
    video = tmp_path / "video.mp4"
    bgm = tmp_path / "music.mp3"
    output = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    bgm.write_bytes(b"music")
    output.write_bytes(b"previous-good-video")
    service = VideoService()

    def fail_after_partial_write(**kwargs):
        Path(kwargs["output"]).write_bytes(b"partial")
        raise RuntimeError("encoder failed")

    monkeypatch.setattr(service, "add_bgm", fail_after_partial_write)

    with pytest.raises(RuntimeError, match="encoder failed"):
        service._add_bgm_to_video(
            video=str(video),
            bgm_path=str(bgm),
            output=str(output),
        )

    assert output.read_bytes() == b"previous-good-video"
    assert list(tmp_path.glob(".*.adding_bgm.mp4")) == []


def test_multi_video_bgm_intermediate_is_unique_and_cleaned_on_failure(
    monkeypatch,
    tmp_path,
):
    service = VideoService()
    output = tmp_path / "final.webm"
    intermediate_paths = []
    monkeypatch.setattr(service, "resolve_optional_bgm_path", lambda value: value)

    def fake_concat(_videos, intermediate):
        path = Path(intermediate)
        intermediate_paths.append(path)
        path.write_bytes(b"concat")
        return str(path)

    monkeypatch.setattr(service, "_concat_demuxer", fake_concat)
    monkeypatch.setattr(
        service,
        "_add_bgm_to_video",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("mix failed")),
    )

    with pytest.raises(RuntimeError, match="mix failed"):
        service.concat_videos(
            ["one.webm", "two.webm"],
            str(output),
            bgm_path="resolved.mp3",
        )

    assert len(intermediate_paths) == 1
    assert intermediate_paths[0].suffix == ".webm"
    assert not intermediate_paths[0].exists()


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


def test_create_video_from_image_pads_decoded_audio_when_container_duration_is_inflated(
    monkeypatch,
    tmp_path,
):
    sample_rate = 22050
    audio_path = tmp_path / "inflated-metadata.wav"
    output_path = tmp_path / "segment.mp4"
    _create_silent_wav(
        audio_path,
        sample_count=sample_rate * 19 // 10,
        sample_rate=sample_rate,
    )

    real_probe = ffmpeg.probe
    inflated_probe = real_probe(str(audio_path))
    inflated_probe["format"]["duration"] = "1.970000"

    with monkeypatch.context() as context:
        context.setattr(ffmpeg, "probe", lambda _path: inflated_probe)
        VideoService().create_video_from_image(
            image=str(Path("resources/example.png")),
            audio=str(audio_path),
            output=str(output_path),
            fps=30,
        )

    durations = _probe_stream_durations(output_path)

    assert abs(durations["video"] - durations["audio"]) <= 0.005
    assert durations["audio"] >= 1.97


@pytest.mark.parametrize(
    ("fps", "sample_rate"),
    [
        (30, 24000),
        (30, 48000),
        (60, 24000),
        (60, 48000),
    ],
)
def test_create_video_from_image_preserves_audio_tail_across_mp4_time_bases(
    tmp_path,
    fps,
    sample_rate,
):
    frame_count = 61
    sample_count = sample_rate * frame_count // fps - 1
    audio_path = tmp_path / f"tail-{fps}-{sample_rate}.wav"
    output_path = tmp_path / f"segment-{fps}-{sample_rate}.mp4"
    _create_silent_wav(
        audio_path,
        sample_count=sample_count,
        sample_rate=sample_rate,
    )
    raw_audio_duration = _probe_format_duration(audio_path)

    VideoService().create_video_from_image(
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


def test_iso_base_media_movie_timescale_uses_frame_and_sample_boundaries():
    probe = {
        "streams": [
            {"codec_type": "video"},
            {"codec_type": "audio", "sample_rate": "44100"},
        ]
    }

    assert (
        VideoService._resolve_iso_base_media_movie_timescale(
            output="segment.mp4",
            fps=60,
            probe=probe,
        )
        == 44_100
    )
    assert (
        VideoService._resolve_iso_base_media_movie_timescale(
            output="segment.m4v",
            fps=64,
            probe=probe,
        )
        == 705_600
    )
    assert (
        VideoService._resolve_iso_base_media_movie_timescale(
            output="segment.webm",
            fps=60,
            probe={"streams": []},
        )
        is None
    )


@pytest.mark.parametrize("sample_rate", [None, "0", "not-a-number"])
def test_iso_base_media_movie_timescale_rejects_invalid_sample_rate(sample_rate):
    probe = {
        "streams": [
            {"codec_type": "audio", "sample_rate": sample_rate},
        ]
    }

    with pytest.raises(ValueError, match="sample rate"):
        VideoService._resolve_iso_base_media_movie_timescale(
            output="segment.mov",
            fps=60,
            probe=probe,
        )


def test_iso_base_media_movie_timescale_rejects_integer_overflow():
    probe = {
        "streams": [
            {"codec_type": "audio", "sample_rate": "2147483647"},
        ]
    }

    with pytest.raises(ValueError, match="timescale limit"):
        VideoService._resolve_iso_base_media_movie_timescale(
            output="segment.mp4",
            fps=2,
            probe=probe,
        )


def test_burn_ass_subtitles_rejects_same_input_and_output(tmp_path):
    video = tmp_path / "final.mp4"
    ass = tmp_path / "master.ass"
    video.write_bytes(b"video")
    ass.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="same path"):
        VideoService().burn_ass_subtitles(str(video), str(ass), str(video))


def test_burn_ass_subtitles_validates_files_before_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(video_module.shutil, "which", lambda _name: None)

    with pytest.raises(ValueError, match="input_video must be an existing file"):
        VideoService().burn_ass_subtitles(
            str(tmp_path / "missing.mp4"),
            str(tmp_path / "missing.ass"),
            str(tmp_path / "output.mp4"),
        )


def test_escape_ffmpeg_filter_path_handles_windows_drive_and_spaces():
    escaped = VideoService()._escape_ffmpeg_filter_path(r"C:\测试 路径\master.ass")

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


@pytest.mark.parametrize("has_original_audio", [False, True])
def test_add_bgm_implements_fade_out_and_supports_silent_video(
    monkeypatch,
    tmp_path,
    has_original_audio,
):
    filter_calls = []
    output_calls = []

    class FakeStream:
        @property
        def audio(self):
            return self

        @property
        def video(self):
            return self

        def filter(self, name, *args, **kwargs):
            filter_calls.append((name, args, kwargs))
            return self

    class FakeOutput(FakeStream):
        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            return None

    monkeypatch.setattr(video_module.ffmpeg, "input", lambda *_args, **_kwargs: FakeStream())

    def fake_filter(_streams, name, *args, **kwargs):
        filter_calls.append((name, args, kwargs))
        return FakeStream()

    monkeypatch.setattr(video_module.ffmpeg, "filter", fake_filter)

    def fake_output(*streams, **kwargs):
        output_calls.append((streams, kwargs))
        return FakeOutput()

    monkeypatch.setattr(video_module.ffmpeg, "output", fake_output)

    service = VideoService()
    service._ffmpeg_checked = True
    monkeypatch.setattr(service, "_get_video_duration", lambda _video: 10.0)
    monkeypatch.setattr(service, "_get_audio_duration", lambda _audio: 8.0)
    monkeypatch.setattr(service, "has_audio_stream", lambda _video: has_original_audio)

    output = tmp_path / "mixed.mp4"
    service.add_bgm(
        "video.mp4",
        "music.mp3",
        str(output),
        loop=False,
        fade_in=1.0,
        fade_out=2.0,
    )

    fade_out_calls = [
        call for call in filter_calls if call[0] == "afade" and call[2].get("type") == "out"
    ]
    assert fade_out_calls == [
        (
            "afade",
            (),
            {"type": "out", "start_time": "6", "duration": "2"},
        )
    ]
    assert any(call[0] == "amix" for call in filter_calls) is has_original_audio
    assert output_calls[0][0][-1] == str(output)


@pytest.mark.parametrize("fps", [0, -1, 1.5, True])
def test_create_video_from_image_rejects_invalid_fps_before_running_ffmpeg(fps):
    with pytest.raises(ValueError, match="positive integer"):
        VideoService().create_video_from_image("image.png", "audio.mp3", "video.mp4", fps=fps)
