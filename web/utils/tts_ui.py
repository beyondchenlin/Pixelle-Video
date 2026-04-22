"""Shared helpers for TTS-related Web UI defaults."""

from __future__ import annotations


def resolve_comfyui_tts_speed(tts_config: dict | None) -> float:
    """Resolve the effective ComfyUI speed for preview and generation flows."""
    config = tts_config or {}
    comfyui_config = config.get("comfyui", {}) or {}
    local_config = config.get("local", {}) or {}

    value = comfyui_config.get("speed")
    if value is None:
        value = local_config.get("speed", 1.2)
    return float(value)
