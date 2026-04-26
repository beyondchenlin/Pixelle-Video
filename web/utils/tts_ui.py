"""Shared helpers for TTS-related Web UI defaults."""

from __future__ import annotations

from pixelle_video.config.tts_defaults import get_configured_tts_inference_mode


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
