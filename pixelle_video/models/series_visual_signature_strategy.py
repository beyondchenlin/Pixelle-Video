from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SeriesVisualSignatureMode(str, Enum):
    AUTO = "auto"
    SUBJECT_REPLACEMENT = "subject_replacement"
    SUPPORTING_INTEGRATION = "supporting_integration"


class SeriesVisualSignatureConsistencyMode(str, Enum):
    OFF = "off"
    SUPPORTING_CHARACTER = "supporting_character"
    PRIMARY_CHARACTER = "primary_character"


class SeriesVisualSignatureStrategy(str, Enum):
    AUTO = "auto"
    HOST_EXPLAINER = "host_explainer"
    SIGNATURE_PRESENCE = "signature_presence"
    OBSERVER_GUIDE = "observer_guide"
    PARTICIPANT = "participant"
    BACKGROUND_SIGNATURE = "background_signature"

    @classmethod
    def from_value(cls, value: Any) -> "SeriesVisualSignatureStrategy":
        if isinstance(value, cls):
            return value
        return _strict_enum_value(value, cls, "series_visual_signature_strategy", cls.AUTO)


@dataclass(frozen=True)
class SeriesVisualSignatureStrategyControls:
    signature_mode: SeriesVisualSignatureMode = SeriesVisualSignatureMode.AUTO
    consistency_mode: SeriesVisualSignatureConsistencyMode = SeriesVisualSignatureConsistencyMode.OFF

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "SeriesVisualSignatureStrategyControls":
        source = dict(source or {})
        return cls(
            signature_mode=_strict_enum_value(
                _mapping_value(source, "series_visual_signature_mode", "signature_mode"),
                SeriesVisualSignatureMode,
                "series_visual_signature_mode",
                SeriesVisualSignatureMode.AUTO,
            ),
            consistency_mode=_strict_enum_value(
                _mapping_value(source, "series_visual_signature_consistency_mode", "consistency_mode"),
                SeriesVisualSignatureConsistencyMode,
                "series_visual_signature_consistency_mode",
                SeriesVisualSignatureConsistencyMode.OFF,
            ),
        )

    @property
    def effective_signature_mode(self) -> SeriesVisualSignatureMode:
        if self.consistency_mode is SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER:
            return SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
        if self.consistency_mode is SeriesVisualSignatureConsistencyMode.SUPPORTING_CHARACTER:
            return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
        return self.signature_mode

    @property
    def requires_subject_replacement(self) -> bool:
        return self.effective_signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT

    @property
    def requires_supporting_integration(self) -> bool:
        return self.effective_signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION

    @property
    def requires_visible_signature(self) -> bool:
        return True

    def to_dict(self) -> dict[str, str]:
        return {
            "series_visual_signature_mode": self.signature_mode.value,
            "series_visual_signature_consistency_mode": self.consistency_mode.value,
            "effective_series_visual_signature_mode": self.effective_signature_mode.value,
        }

    def prompt_guidance(self) -> list[str]:
        guidance = [
            "The configured visual identity must appear in every final integrated prompt.",
            "Never return hidden, suppressed, skipped, absent, fallback, or not suitable as a successful result.",
            "The model may recompose the scene, add carriers, use a TV/projection/frame/exhibit/desk/wall/book, or rewrite camera framing while preserving source intent.",
        ]
        if self.requires_subject_replacement:
            guidance.append("The visual identity must become the primary subject or protagonist.")
        elif self.requires_supporting_integration:
            guidance.append("The visual identity must not replace the source subject; it must appear as a real in-scene supporting element.")
        else:
            guidance.append("Use visible supporting integration by default; primary replacement requires an explicit primary role setting.")
        return guidance


def build_visual_identity_kernel(anchor_profile: Any) -> tuple[str, ...]:
    values: list[str] = []
    for name in ("name", "visual_summary", "style_hint", "world_hint", "description"):
        _extend(values, getattr(anchor_profile, name, None))
    for name in ("identity_lock", "minimal_traits", "identity_anchors"):
        _extend(values, getattr(anchor_profile, name, None))
    tokens: list[str] = []
    for value in values:
        tokens.extend(_tokens(value))
    return tuple(_dedupe(tokens)) or ("频道视觉签名",)


def resolve_effective_signature_mode_with_v44_context(
    *,
    requested_signature_mode: Any,
    consistency_mode: Any,
    series_visual_signature_strategy: Any,
    subject_replacement_allowed: bool,
) -> SeriesVisualSignatureMode:
    signature_mode = _series_visual_signature_mode_from_value(requested_signature_mode)
    consistency = _series_visual_signature_consistency_mode_from_value(consistency_mode)
    strategy = SeriesVisualSignatureStrategy.from_value(series_visual_signature_strategy)

    protected_supporting_strategies = {
        SeriesVisualSignatureStrategy.SIGNATURE_PRESENCE,
        SeriesVisualSignatureStrategy.OBSERVER_GUIDE,
        SeriesVisualSignatureStrategy.BACKGROUND_SIGNATURE,
    }
    if strategy in protected_supporting_strategies and (
        signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
        or consistency is SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER
    ):
        return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    if not subject_replacement_allowed and (
        signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
        or (
            consistency is SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER
            and strategy is SeriesVisualSignatureStrategy.PARTICIPANT
        )
    ):
        return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    if subject_replacement_allowed and signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    if (
        subject_replacement_allowed
        and consistency is SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER
        and strategy is SeriesVisualSignatureStrategy.PARTICIPANT
    ):
        return SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    if consistency is SeriesVisualSignatureConsistencyMode.SUPPORTING_CHARACTER:
        return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    return signature_mode


def _series_visual_signature_mode_from_value(value: Any) -> SeriesVisualSignatureMode:
    if isinstance(value, SeriesVisualSignatureMode):
        return value
    return _strict_enum_value(value, SeriesVisualSignatureMode, "requested_signature_mode", SeriesVisualSignatureMode.AUTO)


def _series_visual_signature_consistency_mode_from_value(value: Any) -> SeriesVisualSignatureConsistencyMode:
    if isinstance(value, SeriesVisualSignatureConsistencyMode):
        return value
    return _strict_enum_value(value, SeriesVisualSignatureConsistencyMode, "consistency_mode", SeriesVisualSignatureConsistencyMode.OFF)


def _strict_enum_value(value: Any, enum_cls: type[Enum], field_name: str, default: Enum) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if value is None:
        return default
    if isinstance(value, Enum) or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
    text = value.strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _mapping_value(source: Mapping[str, Any], primary_key: str, legacy_key: str) -> Any:
    if primary_key in source and source[primary_key] is not None:
        return source[primary_key]
    if legacy_key in source and source[legacy_key] is not None:
        return source[legacy_key]
    return None


def _extend(target: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value.strip():
            target.append(value.strip())
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            _extend(target, item)
        return
    text = str(value).strip()
    if text:
        target.append(text)


_GENERIC = {"ip", "角色", "形象", "视觉", "签名", "视觉签名", "频道", "识别", "元素", "style", "identity", "visual", "signature", "character"}


def _tokens(text: str) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return []
    result = [text] if 2 <= len(text) <= 50 else []
    for part in re.split(r"[\s,，。.;；:：/、|]+", text):
        cleaned = part.strip(" ，,。.;；:：()（）[]【】<>《》\"'")
        if len(cleaned) >= 2 and cleaned.lower() not in _GENERIC:
            result.append(cleaned)
    return _dedupe(result)


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = [
    "SeriesVisualSignatureMode",
    "SeriesVisualSignatureConsistencyMode",
    "SeriesVisualSignatureStrategy",
    "SeriesVisualSignatureStrategyControls",
    "build_visual_identity_kernel",
    "resolve_effective_signature_mode_with_v44_context",
]
