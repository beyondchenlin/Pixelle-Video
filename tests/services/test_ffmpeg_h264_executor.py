from __future__ import annotations

import subprocess

import ffmpeg
import pytest

from pixelle_video.services import ffmpeg_h264_executor as executor_module
from pixelle_video.services.ffmpeg_h264_executor import (
    FfmpegH264Executor,
    ffmpeg_h264_cli_args,
)


def test_cli_args_compile_encoder_options() -> None:
    assert ffmpeg_h264_cli_args(
        {
            "vcodec": "h264_qsv",
            "preset": "medium",
            "global_quality": 23,
        }
    ) == (
        "-c:v",
        "h264_qsv",
        "-preset",
        "medium",
        "-global_quality",
        "23",
    )


def test_output_executor_disables_hardware_only_after_cpu_success(monkeypatch) -> None:
    executor = FfmpegH264Executor()
    monkeypatch.setattr(
        executor_module,
        "ffmpeg_h264_fallback_kwargs",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )
    disabled: list[str] = []
    monkeypatch.setattr(
        executor_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append(name),
    )

    class Output:
        def __init__(self, codec: str) -> None:
            self.codec = codec

        def run(self, **kwargs):
            if self.codec == "h264_nvenc":
                raise ffmpeg.Error("ffmpeg", b"", b"NVENC init failed")
            return b"", b""

    executor.run_output(
        lambda **params: Output(str(params["vcodec"])),
        selected_params={"vcodec": "h264_nvenc", "preset": "p4", "cq": 23},
    )

    assert disabled == ["h264_nvenc"]


def test_output_executor_keeps_hardware_enabled_when_cpu_also_fails(monkeypatch) -> None:
    executor = FfmpegH264Executor()
    monkeypatch.setattr(
        executor_module,
        "ffmpeg_h264_fallback_kwargs",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )
    disabled: list[str] = []
    monkeypatch.setattr(
        executor_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append(name),
    )

    class Output:
        def run(self, **kwargs):
            raise ffmpeg.Error("ffmpeg", b"", b"shared filter failure")

    with pytest.raises(ffmpeg.Error):
        executor.run_output(
            lambda **params: Output(),
            selected_params={"vcodec": "h264_nvenc", "preset": "p4", "cq": 23},
        )

    assert disabled == []


def test_command_executor_retries_cpu_and_disables_proven_bad_hardware(monkeypatch) -> None:
    executor = FfmpegH264Executor()
    monkeypatch.setattr(
        executor_module,
        "ffmpeg_h264_fallback_kwargs",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )
    disabled: list[str] = []
    monkeypatch.setattr(
        executor_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append(name),
    )
    commands: list[list[str]] = []

    def fake_run(command, *, timeout):
        commands.append(list(command))
        codec = command[command.index("-c:v") + 1]
        return subprocess.CompletedProcess(
            command,
            1 if codec == "h264_qsv" else 0,
            stdout="",
            stderr="QSV init failed" if codec == "h264_qsv" else "",
        )

    monkeypatch.setattr(executor_module, "_run_command", fake_run)

    result = executor.run_command(
        lambda encode_args: ["ffmpeg", *encode_args, "out.mp4"],
        selected_params={
            "vcodec": "h264_qsv",
            "preset": "medium",
            "global_quality": 23,
        },
    )

    assert result.returncode == 0
    assert [command[command.index("-c:v") + 1] for command in commands] == [
        "h264_qsv",
        "libx264",
    ]
    assert disabled == ["h264_qsv"]


def test_command_executor_does_not_disable_when_cpu_command_also_fails(monkeypatch) -> None:
    executor = FfmpegH264Executor()
    monkeypatch.setattr(
        executor_module,
        "ffmpeg_h264_fallback_kwargs",
        lambda: {"vcodec": "libx264", "preset": "medium", "crf": 23},
    )
    disabled: list[str] = []
    monkeypatch.setattr(
        executor_module,
        "disable_ffmpeg_h264_encoder",
        lambda name, *, reason: disabled.append(name),
    )

    monkeypatch.setattr(
        executor_module,
        "_run_command",
        lambda command, *, timeout: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="shared input failure",
        ),
    )

    with pytest.raises(RuntimeError, match="shared input failure"):
        executor.run_command(
            lambda encode_args: ["ffmpeg", *encode_args, "out.mp4"],
            selected_params={"vcodec": "h264_nvenc", "preset": "p4", "cq": 23},
        )

    assert disabled == []
