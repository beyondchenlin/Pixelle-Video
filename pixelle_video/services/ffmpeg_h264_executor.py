from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import ffmpeg
from loguru import logger

from pixelle_video.utils.ffmpeg_encoder import (
    disable_ffmpeg_h264_encoder,
    ffmpeg_h264_fallback_kwargs,
    ffmpeg_h264_output_kwargs,
    resolve_ffmpeg_h264_encoder,
)

CommandBuilder = Callable[[tuple[str, ...]], Sequence[str]]
OutputBuilder = Callable[..., Any]


@dataclass(frozen=True)
class FfmpegH264Executor:
    """Single execution authority for H.264 re-encode operations.

    The executor owns runtime backend selection, CPU proof fallback, and
    process-local hardware disable caching for both ffmpeg-python output graphs
    and raw FFmpeg commands.
    """

    def selected_output_kwargs(self) -> dict[str, object]:
        return ffmpeg_h264_output_kwargs(resolve_ffmpeg_h264_encoder())

    def run_output(
        self,
        build_output: OutputBuilder,
        *,
        quiet: bool = False,
        selected_params: Mapping[str, object] | None = None,
    ) -> None:
        params = dict(selected_params or self.selected_output_kwargs())
        run_kwargs: dict[str, bool] = {
            "capture_stdout": True,
            "capture_stderr": True,
        }
        if quiet:
            run_kwargs["quiet"] = True

        try:
            build_output(**params).run(**run_kwargs)
            return
        except ffmpeg.Error as hardware_exc:
            vcodec = str(params.get("vcodec") or "")
            if vcodec == "libx264":
                raise

            logger.warning(
                "Hardware encoder {} failed; validating the same output graph with CPU libx264",
                vcodec,
            )
            try:
                build_output(**ffmpeg_h264_fallback_kwargs()).run(**run_kwargs)
            except ffmpeg.Error:
                # CPU failure means the task/input/filter/output is not proven valid;
                # do not poison the process-wide hardware capability cache.
                raise

            self._disable_after_proven_hardware_failure(
                vcodec,
                _ffmpeg_error_reason(hardware_exc),
            )

    def run_command(
        self,
        build_command: CommandBuilder,
        *,
        timeout: float | None = None,
        selected_params: Mapping[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        params = dict(selected_params or self.selected_output_kwargs())
        vcodec = str(params.get("vcodec") or "")
        command = list(build_command(ffmpeg_h264_cli_args(params)))
        result = _run_command(command, timeout=timeout)
        if result.returncode == 0:
            return result
        if vcodec == "libx264":
            raise _command_error(command, result)

        logger.warning(
            "Hardware encoder {} failed; validating the same command with CPU libx264",
            vcodec,
        )
        fallback_command = list(
            build_command(ffmpeg_h264_cli_args(ffmpeg_h264_fallback_kwargs()))
        )
        fallback_result = _run_command(fallback_command, timeout=timeout)
        if fallback_result.returncode != 0:
            raise _command_error(fallback_command, fallback_result)

        self._disable_after_proven_hardware_failure(
            vcodec,
            _process_reason(result),
        )
        return fallback_result

    @staticmethod
    def _disable_after_proven_hardware_failure(vcodec: str, reason: str) -> None:
        disable_ffmpeg_h264_encoder(
            vcodec,
            reason=reason or "hardware-specific runtime encode failure",
        )
        logger.warning(
            "CPU fallback succeeded; disabled hardware encoder {} for this process",
            vcodec,
        )


def ffmpeg_h264_cli_args(params: Mapping[str, object]) -> tuple[str, ...]:
    """Compile ffmpeg-python style H.264 kwargs to command-line arguments."""

    args: list[str] = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        option = "-c:v" if key == "vcodec" else f"-{key}"
        args.extend((option, str(value)))
    return tuple(args)


def _run_command(
    command: Sequence[str],
    *,
    timeout: float | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _ffmpeg_error_reason(exc: ffmpeg.Error) -> str:
    stderr = getattr(exc, "stderr", None)
    if isinstance(stderr, bytes):
        reason = stderr.decode("utf-8", errors="replace")
    else:
        reason = str(stderr or exc)
    return " ".join(reason.strip().split())[-400:]


def _process_reason(result: subprocess.CompletedProcess[str]) -> str:
    reason = " ".join(str(result.stderr or "").strip().split())
    return reason[-400:] if reason else f"exit code {result.returncode}"


def _command_error(
    command: Sequence[str],
    result: subprocess.CompletedProcess[str],
) -> RuntimeError:
    reason = _process_reason(result)
    return RuntimeError(
        "FFmpeg H264 re-encode command failed "
        f"(exit={result.returncode}, command={command!r}): {reason}"
    )


__all__ = [
    "FfmpegH264Executor",
    "ffmpeg_h264_cli_args",
]
