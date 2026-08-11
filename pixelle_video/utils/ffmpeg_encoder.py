from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from loguru import logger

H264EncoderFamily = Literal["cpu", "nvenc", "qsv", "vaapi"]


@dataclass(frozen=True)
class FfmpegH264Backend:
    encoder: str
    family: H264EncoderFamily
    preset: str | None
    quality_option: tuple[str, object] | None
    extra_options: tuple[tuple[str, object], ...] = ()
    requires_hardware_frames: bool = False

    @property
    def is_hardware(self) -> bool:
        return self.family != "cpu"

    @property
    def supports_simple_software_frame_output(self) -> bool:
        return not self.requires_hardware_frames

    def output_kwargs(self) -> dict[str, object]:
        params: dict[str, object] = {"vcodec": self.encoder}
        if self.preset:
            params["preset"] = self.preset
        if self.quality_option is not None:
            key, value = self.quality_option
            params[key] = value
        for key, value in self.extra_options:
            params[key] = value
        return params


_CPU_BACKEND = FfmpegH264Backend(
    encoder="libx264",
    family="cpu",
    preset="medium",
    quality_option=("crf", 23),
)
_NVENC_BACKEND = FfmpegH264Backend(
    encoder="h264_nvenc",
    family="nvenc",
    preset="p4",
    quality_option=("cq", 23),
    extra_options=(("rc", "vbr"), ("b_ref_mode", "middle")),
)
_QSV_BACKEND = FfmpegH264Backend(
    encoder="h264_qsv",
    family="qsv",
    preset="medium",
    quality_option=("global_quality", 23),
)
_VAAPI_BACKEND = FfmpegH264Backend(
    encoder="h264_vaapi",
    family="vaapi",
    preset=None,
    quality_option=("qp", 23),
    requires_hardware_frames=True,
)
_BACKENDS_BY_ENCODER = {
    backend.encoder: backend
    for backend in (_CPU_BACKEND, _NVENC_BACKEND, _QSV_BACKEND, _VAAPI_BACKEND)
}
_HARDWARE_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_vaapi")
_SIMPLE_HARDWARE_CANDIDATES = ("h264_nvenc", "h264_qsv")
_DISABLED_ENCODERS: dict[str, str] = {}
_DISABLED_ENCODERS_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _probe_ffmpeg_encoders() -> set[str]:
    """Return encoders compiled into the local FFmpeg binary.

    This is discovery only. Presence in this set is not treated as proof that the
    hardware, driver, device permissions, or runtime encoder initialization work.
    """

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        logger.warning(
            "ffmpeg -encoders exited with code {}; hardware encoder discovery skipped",
            result.returncode,
        )
        return set()

    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        codec = parts[1]
        if codec in _BACKENDS_BY_ENCODER:
            encoders.add(codec)
    return encoders


def ffmpeg_h264_backend(vcodec: str) -> FfmpegH264Backend:
    try:
        return _BACKENDS_BY_ENCODER[vcodec]
    except KeyError as exc:
        raise ValueError(f"unsupported H264 encoder backend: {vcodec}") from exc


def _vaapi_device() -> str | None:
    override = os.environ.get("PIXELLE_FFMPEG_VAAPI_DEVICE", "").strip()
    if override:
        return override
    default = Path("/dev/dri/renderD128")
    return str(default) if default.exists() else None


def _probe_command(vcodec: str) -> tuple[str, ...] | None:
    backend = ffmpeg_h264_backend(vcodec)
    command: list[str] = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if backend.family == "vaapi":
        device = _vaapi_device()
        if not device:
            return None
        command.extend(("-vaapi_device", device))

    command.extend(
        (
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=25:d=0.04",
            "-frames:v",
            "1",
            "-an",
        )
    )
    if backend.family == "vaapi":
        command.extend(("-vf", "format=nv12,hwupload"))

    command.extend(("-c:v", backend.encoder))
    for key, value in backend.output_kwargs().items():
        if key == "vcodec":
            continue
        command.extend((f"-{key}", str(value)))
    command.extend(("-f", "null", "-"))
    return tuple(command)


@lru_cache(maxsize=8)
def _probe_encoder_runtime(vcodec: str) -> bool:
    """Prove a hardware encoder can encode one real frame on this machine."""

    backend = ffmpeg_h264_backend(vcodec)
    if not backend.is_hardware:
        return True
    if vcodec not in _probe_ffmpeg_encoders():
        return False
    command = _probe_command(vcodec)
    if command is None:
        return False
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if result.returncode == 0:
        return True
    stderr = " ".join((result.stderr or "").strip().split())
    logger.warning(
        "FFmpeg runtime probe failed for {}: {}",
        vcodec,
        stderr[-400:] if stderr else f"exit code {result.returncode}",
    )
    return False


def _is_runtime_disabled(vcodec: str) -> bool:
    with _DISABLED_ENCODERS_LOCK:
        return vcodec in _DISABLED_ENCODERS


def disable_ffmpeg_h264_encoder(vcodec: str, *, reason: str) -> None:
    backend = ffmpeg_h264_backend(vcodec)
    if not backend.is_hardware:
        return
    with _DISABLED_ENCODERS_LOCK:
        _DISABLED_ENCODERS[vcodec] = str(reason or "runtime encode failure")
    resolve_ffmpeg_h264_encoder.cache_clear()
    logger.warning("Disabled FFmpeg encoder {} for this process: {}", vcodec, reason)


def _usable_simple_backend(vcodec: str) -> bool:
    backend = ffmpeg_h264_backend(vcodec)
    return bool(
        backend.supports_simple_software_frame_output
        and not _is_runtime_disabled(vcodec)
        and _probe_encoder_runtime(vcodec)
    )


@lru_cache(maxsize=1)
def resolve_ffmpeg_h264_encoder() -> str:
    """Resolve a runtime-proven encoder compatible with current simple outputs."""

    override = os.environ.get("PIXELLE_FFMPEG_H264_ENCODER", "").strip()
    if override:
        if override not in _BACKENDS_BY_ENCODER:
            raise ValueError(
                "PIXELLE_FFMPEG_H264_ENCODER must be one of "
                + ", ".join(_BACKENDS_BY_ENCODER)
            )
        backend = ffmpeg_h264_backend(override)
        if not backend.supports_simple_software_frame_output:
            logger.warning(
                "FFmpeg encoder override {} requires a hardware-frame executor; "
                "falling back to libx264 for simple output paths",
                override,
            )
            return _CPU_BACKEND.encoder
        if not backend.is_hardware or _usable_simple_backend(override):
            logger.info("FFmpeg H264 encoder override resolved to {}", override)
            return override
        logger.warning(
            "FFmpeg H264 encoder override {} is not runnable; falling back to libx264",
            override,
        )
        return _CPU_BACKEND.encoder

    for candidate in _SIMPLE_HARDWARE_CANDIDATES:
        if _usable_simple_backend(candidate):
            return candidate
    return _CPU_BACKEND.encoder


def ffmpeg_h264_output_kwargs(vcodec: str) -> dict[str, object]:
    backend = ffmpeg_h264_backend(vcodec)
    if not backend.supports_simple_software_frame_output:
        raise ValueError(
            f"{vcodec} requires hardware-frame upload and cannot use simple output kwargs"
        )
    return backend.output_kwargs()


def ffmpeg_h264_preset(vcodec: str) -> str:
    """Compatibility helper for callers that only need the family preset."""

    backend = ffmpeg_h264_backend(vcodec)
    return backend.preset or ""


def ffmpeg_h264_encode_kwargs(vcodec: str) -> dict[str, object]:
    """Compatibility helper returning family-specific non-base options."""

    backend = ffmpeg_h264_backend(vcodec)
    params = backend.output_kwargs()
    params.pop("vcodec", None)
    params.pop("preset", None)
    if backend.family == "cpu":
        params.pop("crf", None)
    return params


def has_gpu_encoder() -> bool:
    return ffmpeg_h264_backend(resolve_ffmpeg_h264_encoder()).is_hardware


@lru_cache(maxsize=1)
def _probe_nvidia_gpu_count() -> int:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    return len([line for line in result.stdout.strip().splitlines() if line.strip()])


def gpu_count() -> int:
    return _probe_nvidia_gpu_count()


def ffmpeg_h264_fallback_kwargs() -> dict[str, object]:
    return _CPU_BACKEND.output_kwargs()


def clear_ffmpeg_h264_encoder_caches() -> None:
    """Clear discovery/runtime state. Intended for tests and controlled reprobes."""

    _probe_ffmpeg_encoders.cache_clear()
    _probe_encoder_runtime.cache_clear()
    _probe_nvidia_gpu_count.cache_clear()
    resolve_ffmpeg_h264_encoder.cache_clear()
    with _DISABLED_ENCODERS_LOCK:
        _DISABLED_ENCODERS.clear()


__all__ = [
    "FfmpegH264Backend",
    "clear_ffmpeg_h264_encoder_caches",
    "disable_ffmpeg_h264_encoder",
    "ffmpeg_h264_backend",
    "ffmpeg_h264_encode_kwargs",
    "ffmpeg_h264_fallback_kwargs",
    "ffmpeg_h264_output_kwargs",
    "ffmpeg_h264_preset",
    "gpu_count",
    "has_gpu_encoder",
    "resolve_ffmpeg_h264_encoder",
]
