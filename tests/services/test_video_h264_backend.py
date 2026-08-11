from __future__ import annotations

import ffmpeg

from pixelle_video.services import video as video_module
from pixelle_video.services.video import VideoService


def test_video_service_uses_family_specific_backend_kwargs(monkeypatch) -> None:
    monkeypatch.setattr(
        video_module,
        "resolve_ffmpeg_h264_encoder",
        lambda: "h264_qsv",
    )
    monkeypatch.setattr(
        video_module,
        "ffmpeg_h264_output_kwargs",
        lambda name: {
            "vcodec": name,
            "preset": "medium",
            "global_quality": 23,
        },
    )

    assert VideoService._h264_encode_params() == {
        "vcodec": "h264_qsv",
        "preset": "medium",
        "global_quality": 23,
    }


def test_video_service_disables_failed_hardware_and_retries_cpu(monkeypatch) -> None:
    service = VideoService()
    monkeypatch.setattr(
        service,
        "_h264_encode_params",
        lambda: {
            "vcodec": "h264_nvenc",
            "preset": "p4",
            "cq": 23,
            "rc": "vbr",
            "b_ref_mode": "middle",
        },
    )

    disabled: list[tuple[str, str]] = []
    monkeypatch.setattr(
        video_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append((name, reason)),
    )
    monkeypatch.setattr(
        video_module,
        "ffmpeg_h264_fallback_kwargs",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )

    build_calls: list[dict[str, object]] = []
    run_calls: list[dict[str, bool]] = []

    class FakeOutput:
        def __init__(self, params: dict[str, object]) -> None:
            self.params = params

        def run(self, **kwargs):
            run_calls.append(kwargs)
            if self.params["vcodec"] == "h264_nvenc":
                raise ffmpeg.Error(
                    "ffmpeg",
                    b"",
                    b"Cannot load libcuda; hardware initialization failed",
                )
            return b"", b""

    def build_output(**params):
        build_calls.append(params)
        return FakeOutput(params)

    service._encode_run(build_output, quiet=True)

    assert [call["vcodec"] for call in build_calls] == ["h264_nvenc", "libx264"]
    assert build_calls[1] == {
        "vcodec": "libx264",
        "preset": "medium",
        "crf": 23,
    }
    assert len(disabled) == 1
    assert disabled[0][0] == "h264_nvenc"
    assert "Cannot load libcuda" in disabled[0][1]
    assert run_calls == [
        {"capture_stdout": True, "capture_stderr": True, "quiet": True},
        {"capture_stdout": True, "capture_stderr": True, "quiet": True},
    ]


def test_video_service_does_not_hide_cpu_encoder_failure(monkeypatch) -> None:
    service = VideoService()
    monkeypatch.setattr(
        service,
        "_h264_encode_params",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )

    disabled: list[str] = []
    monkeypatch.setattr(
        video_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append(name),
    )

    class FailingOutput:
        def run(self, **kwargs):
            raise ffmpeg.Error("ffmpeg", b"", b"software encode failed")

    try:
        service._encode_run(lambda **params: FailingOutput())
    except ffmpeg.Error:
        pass
    else:
        raise AssertionError("CPU encoder failure must propagate")

    assert disabled == []
