from __future__ import annotations

import math
from dataclasses import dataclass

from pixelle_video.models.element_animation import (
    AnimationIntensity,
    AnimationPreset,
    BackgroundMode,
    ElementMotionBounds,
)


_UINT32_MASK = 0xFFFFFFFF
_UINT32_RANGE = 2**32


@dataclass(frozen=True)
class ElementTransform:
    x: float
    y: float
    rotate: float
    scale: float
    opacity: float = 1.0


def resolve_element_bounds(intensity: AnimationIntensity) -> ElementMotionBounds:
    if intensity == "low":
        return ElementMotionBounds(
            translate_px=8,
            rotate_deg=0.8,
            scale_delta=0.015,
        )
    if intensity == "high":
        return ElementMotionBounds(
            translate_px=28,
            rotate_deg=3.0,
            scale_delta=0.06,
        )
    if intensity == "medium":
        return ElementMotionBounds(
            translate_px=16,
            rotate_deg=1.8,
            scale_delta=0.035,
        )
    raise ValueError(f"Unsupported animation intensity: {intensity}")


def resolve_background_bounds(
    mode: BackgroundMode,
    intensity: AnimationIntensity,
) -> ElementMotionBounds:
    if mode == "source_image_low_motion":
        resolve_element_bounds(intensity)
        return ElementMotionBounds(
            translate_px=6 if intensity == "high" else 4,
            rotate_deg=0.4,
            scale_delta=0.012,
        )
    if mode == "inpainted":
        return resolve_element_bounds(intensity)
    raise ValueError(f"Unsupported background mode: {mode}")


def _phase(seed: int, channel: int) -> float:
    """Return a deterministic phase using JS-portable 32-bit integer math.

    The mix uses only XOR, unsigned shifts, and 32-bit multiplication. A
    HyperFrames renderer can port the same operations with `Math.imul` and
    `>>> 0`, then divide the unsigned result by 2**32.
    """
    value = (seed & _UINT32_MASK) ^ (
        ((channel + 1) * 0x9E3779B9) & _UINT32_MASK
    )
    value = ((value ^ (value >> 16)) * 0x85EBCA6B) & _UINT32_MASK
    value = ((value ^ (value >> 13)) * 0xC2B2AE35) & _UINT32_MASK
    value = (value ^ (value >> 16)) & _UINT32_MASK
    return (value / _UINT32_RANGE) * math.tau


def sample_transform(
    preset: AnimationPreset,
    *,
    time: float,
    duration: float,
    seed: int,
    bounds: ElementMotionBounds,
) -> ElementTransform:
    progress = 0.0 if duration <= 0 else max(0.0, min(1.0, time / duration))
    wave = math.sin(progress * math.tau + _phase(seed, 1))
    wave_b = math.cos(progress * math.tau + _phase(seed, 2))

    if preset == "pulse":
        return ElementTransform(
            x=wave_b * bounds.translate_px * 0.25,
            y=wave * bounds.translate_px * 0.25,
            rotate=wave_b * bounds.rotate_deg * 0.25,
            scale=1 + abs(wave) * bounds.scale_delta,
        )
    if preset == "drift":
        return ElementTransform(
            x=(progress - 0.5) * bounds.translate_px,
            y=wave * bounds.translate_px * 0.35,
            rotate=wave_b * bounds.rotate_deg,
            scale=1 + wave * bounds.scale_delta * 0.5,
        )
    if preset == "pop":
        pop = math.sin(min(1.0, progress * 2.5) * math.pi)
        return ElementTransform(
            x=wave_b * bounds.translate_px * 0.2,
            y=-pop * bounds.translate_px * 0.35,
            rotate=wave * bounds.rotate_deg * 0.4,
            scale=1 + pop * bounds.scale_delta,
        )
    if preset == "parallax":
        return ElementTransform(
            x=wave * bounds.translate_px,
            y=wave_b * bounds.translate_px * 0.25,
            rotate=wave * bounds.rotate_deg * 0.35,
            scale=1 + wave_b * bounds.scale_delta * 0.35,
        )
    if preset == "float":
        return ElementTransform(
            x=wave * bounds.translate_px * 0.6,
            y=wave_b * bounds.translate_px,
            rotate=wave * bounds.rotate_deg,
            scale=1 + wave_b * bounds.scale_delta,
        )
    raise ValueError(f"Unsupported animation preset: {preset}")
