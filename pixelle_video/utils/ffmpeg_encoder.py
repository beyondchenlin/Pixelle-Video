from __future__ import annotations

import os
import subprocess
from functools import lru_cache

from loguru import logger

_NVENC_CANDIDATES = ("h264_nvenc", "h264_qsv", "h264_vaapi")
_NVENC_PRESET = "p4"


@lru_cache(maxsize=1)
def _probe_ffmpeg_encoders() -> set[str]:
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
            "ffmpeg -encoders exited with code {}; "
            "hardware encoder detection skipped",
            result.returncode,
        )
        return set()
    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            codec = parts[1]
            if codec.endswith("_nvenc") or codec.endswith("_qsv") or codec.endswith("_vaapi"):
                encoders.add(codec)
    return encoders


@lru_cache(maxsize=1)
def resolve_ffmpeg_h264_encoder() -> str:
    override = os.environ.get("PIXELLE_FFMPEG_H264_ENCODER", "").strip()
    if override:
        logger.info("ffmpeg encoder overridden via PIXELLE_FFMPEG_H264_ENCODER={}", override)
        return override
    encoders = _probe_ffmpeg_encoders()
    for candidate in _NVENC_CANDIDATES:
        if candidate in encoders:
            return candidate
    return "libx264"


def ffmpeg_h264_preset(vcodec: str) -> str:
    if vcodec == "libx264":
        return "medium"
    return _NVENC_PRESET


def ffmpeg_h264_encode_kwargs(vcodec: str) -> dict[str, object]:
    params: dict[str, object] = {}
    if vcodec in _NVENC_CANDIDATES:
        params["rc"] = "vbr"
        params["cq"] = 23
        params["b_ref_mode"] = "middle"
    return params


def has_gpu_encoder() -> bool:
    return resolve_ffmpeg_h264_encoder() != "libx264"


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


_CPU_ENCODER = "libx264"


def ffmpeg_h264_fallback_kwargs() -> dict[str, object]:
    return {
        "vcodec": _CPU_ENCODER,
        "preset": "medium",
        "crf": 23,
    }
