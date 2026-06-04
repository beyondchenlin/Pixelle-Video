from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureConsistencyMode,
    SeriesVisualSignatureMode,
    SeriesVisualSignatureStrategyControls,
)


class SeriesVisualSignaturePresentationMode(str, Enum):
    AUTO = "auto"
    VISIBLE_SUPPORTING_CHARACTER = "visible_supporting_character"
    EMBEDDED_SCENE_MARK = "embedded_scene_mark"
    PRIMARY_CHARACTER = "primary_character"


class SeriesVisualSignatureEnforcementMode(str, Enum):
    SOFT = "soft"
    STRICT = "strict"


class SeriesVisualSignatureFallbackMode(str, Enum):
    AUTO_REPAIR = "auto_repair"
    DEFAULT_SIGNATURE = "default_signature"
    DISABLED = "disabled"


PRESENTATION_CONTROL_OPTION_KEYS = frozenset(
    {
        "series_visual_signature_presentation_mode",
        "series_visual_signature_enforcement",
        "series_visual_signature_fallback_enabled",
        "series_visual_signature_fallback_mode",
        "series_visual_signature_min_visibility",
    }
)

_ADVANCED_STRATEGY_KEYS = frozenset(
    {
        "series_visual_signature_mode",
        "series_visual_signature_consistency_mode",
    }
)


@dataclass(frozen=True)
class SeriesVisualSignaturePresentationPolicy:
    """Product-level presentation policy for recurring visual signatures.

    This layer is deliberately above the legacy low-level strategy fields.  Web
    users choose how the signature should appear; the backend maps that intent
    to strategy controls, prompt guidance, validation, and fallback behavior.
    """

    presentation_mode: SeriesVisualSignaturePresentationMode = SeriesVisualSignaturePresentationMode.AUTO
    enforcement: SeriesVisualSignatureEnforcementMode = SeriesVisualSignatureEnforcementMode.SOFT
    fallback_enabled: bool = True
    fallback_mode: SeriesVisualSignatureFallbackMode = SeriesVisualSignatureFallbackMode.AUTO_REPAIR
    min_visibility: str = "clear"
    explicit_fields: tuple[str, ...] = ()
    overridden_advanced_fields: tuple[str, ...] = ()
    source: str = "default"

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
        *,
        default_enforcement: SeriesVisualSignatureEnforcementMode | str = SeriesVisualSignatureEnforcementMode.SOFT,
    ) -> "SeriesVisualSignaturePresentationPolicy":
        mapping = dict(source or {})
        explicit_fields = tuple(
            key
            for key in sorted(PRESENTATION_CONTROL_OPTION_KEYS | _ADVANCED_STRATEGY_KEYS)
            if key in mapping and mapping.get(key) is not None
        )
        has_product_mode = "series_visual_signature_presentation_mode" in mapping and mapping.get(
            "series_visual_signature_presentation_mode"
        ) is not None
        if has_product_mode:
            presentation_mode = _presentation_mode_from_value(
                mapping.get("series_visual_signature_presentation_mode"),
                default=SeriesVisualSignaturePresentationMode.AUTO,
            )
            source_label = "product_field"
        else:
            legacy_strategy = SeriesVisualSignatureStrategyControls.from_mapping(mapping)
            presentation_mode = _presentation_mode_from_strategy(legacy_strategy)
            source_label = "legacy_strategy" if set(explicit_fields) & _ADVANCED_STRATEGY_KEYS else "default"

        enforcement = _enforcement_from_value(
            mapping.get("series_visual_signature_enforcement"),
            default=_enforcement_from_value(default_enforcement),
        )
        fallback_mode = _fallback_mode_from_value(
            mapping.get("series_visual_signature_fallback_mode"),
            default=SeriesVisualSignatureFallbackMode.AUTO_REPAIR,
        )
        fallback_enabled = _coerce_bool(
            mapping.get("series_visual_signature_fallback_enabled"),
            default=fallback_mode is not SeriesVisualSignatureFallbackMode.DISABLED,
        )
        if fallback_mode is SeriesVisualSignatureFallbackMode.DISABLED:
            fallback_enabled = False

        policy = cls(
            presentation_mode=presentation_mode,
            enforcement=enforcement,
            fallback_enabled=fallback_enabled,
            fallback_mode=fallback_mode,
            min_visibility=_normalize_min_visibility(
                mapping.get("series_visual_signature_min_visibility"),
                default="clear",
            ),
            explicit_fields=explicit_fields,
            source=source_label,
        )
        object.__setattr__(
            policy,
            "overridden_advanced_fields",
            _advanced_conflicts(mapping, policy.strategy_controls()) if has_product_mode else (),
        )
        return policy

    @classmethod
    def from_strategy(
        cls,
        strategy: SeriesVisualSignatureStrategyControls | Mapping[str, Any] | None,
        *,
        enforcement: SeriesVisualSignatureEnforcementMode | str = SeriesVisualSignatureEnforcementMode.SOFT,
    ) -> "SeriesVisualSignaturePresentationPolicy":
        controls = strategy if isinstance(strategy, SeriesVisualSignatureStrategyControls) else SeriesVisualSignatureStrategyControls.from_mapping(strategy)
        return cls(
            presentation_mode=_presentation_mode_from_strategy(controls),
            enforcement=_enforcement_from_value(enforcement),
            fallback_enabled=True,
            fallback_mode=SeriesVisualSignatureFallbackMode.AUTO_REPAIR,
            source="strategy",
        )

    @property
    def strict(self) -> bool:
        return self.enforcement is SeriesVisualSignatureEnforcementMode.STRICT

    def strategy_controls(self) -> SeriesVisualSignatureStrategyControls:
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER:
            return SeriesVisualSignatureStrategyControls(
                signature_mode=SeriesVisualSignatureMode.SUPPORTING_INTEGRATION,
                consistency_mode=SeriesVisualSignatureConsistencyMode.SUPPORTING_CHARACTER,
            )
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK:
            return SeriesVisualSignatureStrategyControls(
                signature_mode=SeriesVisualSignatureMode.SUPPORTING_INTEGRATION,
                consistency_mode=SeriesVisualSignatureConsistencyMode.OFF,
            )
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.PRIMARY_CHARACTER:
            return SeriesVisualSignatureStrategyControls(
                signature_mode=SeriesVisualSignatureMode.SUBJECT_REPLACEMENT,
                consistency_mode=SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER,
            )
        return SeriesVisualSignatureStrategyControls(
            signature_mode=SeriesVisualSignatureMode.AUTO,
            consistency_mode=SeriesVisualSignatureConsistencyMode.OFF,
        )

    def to_generation_dict(self) -> dict[str, Any]:
        return {
            "series_visual_signature_presentation_mode": self.presentation_mode.value,
            "series_visual_signature_enforcement": self.enforcement.value,
            "series_visual_signature_fallback_enabled": self.fallback_enabled,
            "series_visual_signature_fallback_mode": self.fallback_mode.value,
            "series_visual_signature_min_visibility": self.min_visibility,
            **self.strategy_controls().to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_visual_signature_presentation_mode": self.presentation_mode.value,
            "series_visual_signature_enforcement": self.enforcement.value,
            "series_visual_signature_fallback_enabled": self.fallback_enabled,
            "series_visual_signature_fallback_mode": self.fallback_mode.value,
            "series_visual_signature_min_visibility": self.min_visibility,
            "source": self.source,
            "explicit_fields": list(self.explicit_fields),
            "overridden_advanced_fields": list(self.overridden_advanced_fields),
            **self.strategy_controls().to_dict(),
        }

    def to_prompt_policy(self) -> dict[str, Any]:
        return {
            **self.to_dict(),
            "prompt_guidance": self.prompt_guidance(),
        }

    def prompt_guidance(self) -> list[str]:
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER:
            return [
                "The configured identity should appear in every frame as a real, visible, small supporting character.",
                "Do not turn it into a watermark, logo, corner badge, bookplate, stamp, mirror mark, or abstract surface graphic.",
                "Do not replace the source subject; place the identity beside, near, behind, or slightly in front of the source subject.",
                "Use concrete physical placement: foreground ground, floor, roadside, grass, desk edge, room corner, beside the main subject, or edge of the scene.",
                "The final prompt must preserve the exact identity phrase and describe a physical relationship such as standing, sitting, lying, watching, following, leaning, or walking near the scene.",
            ]
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK:
            return [
                "The configured identity should appear as a clear but subordinate in-scene mark, prop graphic, bookplate, poster, screen graphic, surface motif, or small object.",
                "The identity must remain readable and specific; never collapse it into a generic channel identifier.",
                "Keep the source subject primary and integrate the mark into a real carrier surface.",
            ]
        if self.presentation_mode is SeriesVisualSignaturePresentationMode.PRIMARY_CHARACTER:
            return [
                "The configured identity is allowed to become the primary subject or protagonist.",
                "Preserve the source meaning while making the identity carry the main action.",
            ]
        return [
            "Choose the least disruptive visible presentation that preserves the source intent.",
            "Prefer visible supporting integration; use embedded scene marks when a supporting character would damage the scene.",
            "Always preserve the configured identity phrase in the final prompt.",
        ]


def _presentation_mode_from_strategy(strategy: SeriesVisualSignatureStrategyControls) -> SeriesVisualSignaturePresentationMode:
    if strategy.effective_signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return SeriesVisualSignaturePresentationMode.PRIMARY_CHARACTER
    if (
        strategy.effective_signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
        and strategy.consistency_mode is SeriesVisualSignatureConsistencyMode.SUPPORTING_CHARACTER
    ):
        return SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER
    if strategy.effective_signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION:
        return SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK
    return SeriesVisualSignaturePresentationMode.AUTO


def _presentation_mode_from_value(
    value: Any,
    *,
    default: SeriesVisualSignaturePresentationMode,
) -> SeriesVisualSignaturePresentationMode:
    if isinstance(value, SeriesVisualSignaturePresentationMode):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for item in SeriesVisualSignaturePresentationMode:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError("series_visual_signature_presentation_mode must be a supported presentation mode")


def _enforcement_from_value(
    value: Any,
    default: SeriesVisualSignatureEnforcementMode = SeriesVisualSignatureEnforcementMode.SOFT,
) -> SeriesVisualSignatureEnforcementMode:
    if isinstance(value, SeriesVisualSignatureEnforcementMode):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for item in SeriesVisualSignatureEnforcementMode:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError("series_visual_signature_enforcement must be soft or strict")


def _fallback_mode_from_value(
    value: Any,
    default: SeriesVisualSignatureFallbackMode,
) -> SeriesVisualSignatureFallbackMode:
    if isinstance(value, SeriesVisualSignatureFallbackMode):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for item in SeriesVisualSignatureFallbackMode:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError("series_visual_signature_fallback_mode must be auto_repair, default_signature, or disabled")


def _normalize_min_visibility(value: Any, *, default: str) -> str:
    text = str(value or "").strip() or default
    if text not in {"subtle", "clear", "prominent"}:
        return default
    return text


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _advanced_conflicts(
    mapping: Mapping[str, Any],
    mapped_strategy: SeriesVisualSignatureStrategyControls,
) -> tuple[str, ...]:
    legacy = SeriesVisualSignatureStrategyControls.from_mapping(mapping)
    conflicts: list[str] = []
    if "series_visual_signature_mode" in mapping and legacy.signature_mode is not mapped_strategy.signature_mode:
        conflicts.append("series_visual_signature_mode")
    if "series_visual_signature_consistency_mode" in mapping and legacy.consistency_mode is not mapped_strategy.consistency_mode:
        conflicts.append("series_visual_signature_consistency_mode")
    return tuple(conflicts)


__all__ = [
    "PRESENTATION_CONTROL_OPTION_KEYS",
    "SeriesVisualSignatureEnforcementMode",
    "SeriesVisualSignatureFallbackMode",
    "SeriesVisualSignaturePresentationMode",
    "SeriesVisualSignaturePresentationPolicy",
]
