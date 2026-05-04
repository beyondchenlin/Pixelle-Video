"""Shared helpers for TTS-related Web UI defaults."""

from __future__ import annotations

from pixelle_video.config.tts_defaults import get_configured_tts_inference_mode
from pixelle_video.tts_workflow_contract import (
    tts_workflow_exposes_param,
    tts_workflow_missing_required_ref_audio,
)


def resolve_configured_tts_mode(tts_config: dict | None) -> str:
    """Resolve the effective TTS mode from a UI-facing TTS config block."""
    return get_configured_tts_inference_mode({"comfyui": {"tts": tts_config or {}}})


def resolve_comfyui_tts_speed(tts_config: dict | None) -> float:
    """Resolve the effective ComfyUI speed for preview and generation flows."""
    config = tts_config or {}
    comfyui_config = config.get("comfyui", {}) or {}
    local_config = config.get("local", {}) or {}

    value = comfyui_config.get("speed")
    if value is None:
        value = local_config.get("speed", 1.2)
    return float(value)


def tts_workflow_reference_audio_missing(
    *,
    tts_mode: str,
    tts_workflow_key: str | None,
    ref_audio_path: str | None,
) -> bool:
    """Return whether the selected UI TTS workflow is missing required reference audio."""
    return (
        tts_mode == "comfyui"
        and tts_workflow_missing_required_ref_audio(tts_workflow_key, ref_audio_path)
    )


def tts_workflow_supports_duration(tts_workflow_key: str | None) -> bool:
    return tts_workflow_exposes_param(tts_workflow_key, "duration")
