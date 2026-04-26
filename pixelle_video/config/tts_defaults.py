from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_TTS_INFERENCE_MODE = "comfyui"
VALID_TTS_INFERENCE_MODES = {"local", "comfyui"}


def normalize_tts_inference_mode(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in VALID_TTS_INFERENCE_MODES else None


def get_configured_tts_inference_mode(runtime_config: Mapping[str, Any] | None) -> str:
    if not isinstance(runtime_config, Mapping):
        return DEFAULT_TTS_INFERENCE_MODE

    comfyui_config = runtime_config.get("comfyui", {})
    if not isinstance(comfyui_config, Mapping):
        return DEFAULT_TTS_INFERENCE_MODE

    tts_config = comfyui_config.get("tts", {})
    if not isinstance(tts_config, Mapping):
        return DEFAULT_TTS_INFERENCE_MODE

    return normalize_tts_inference_mode(tts_config.get("inference_mode")) or DEFAULT_TTS_INFERENCE_MODE


def resolve_tts_inference_mode(
    runtime_config: Mapping[str, Any] | None,
    requested_mode: Any = None,
) -> str:
    return normalize_tts_inference_mode(requested_mode) or get_configured_tts_inference_mode(
        runtime_config
    )
