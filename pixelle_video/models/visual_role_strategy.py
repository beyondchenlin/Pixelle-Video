from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any
import re


class VisualRoleMode(str, Enum):
    AUTO = "auto"
    SUBJECT_REPLACEMENT = "subject_replacement"
    SUPPORTING_INTEGRATION = "supporting_integration"


class VisualConsistencyMode(str, Enum):
    OFF = "off"
    SUPPORTING_CHARACTER = "supporting_character"
    PRIMARY_CHARACTER = "primary_character"


@dataclass(frozen=True)
class VisualRoleStrategyControls:
    role_mode: VisualRoleMode = VisualRoleMode.AUTO
    consistency_mode: VisualConsistencyMode = VisualConsistencyMode.OFF

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "VisualRoleStrategyControls":
        source = dict(source or {})
        return cls(
            role_mode=_enum_value(source.get("visual_role_mode") or source.get("role_mode"), VisualRoleMode, VisualRoleMode.AUTO),
            consistency_mode=_enum_value(source.get("visual_consistency_mode") or source.get("consistency_mode"), VisualConsistencyMode, VisualConsistencyMode.OFF),
        )

    @property
    def effective_role_mode(self) -> VisualRoleMode:
        if self.consistency_mode is VisualConsistencyMode.PRIMARY_CHARACTER:
            return VisualRoleMode.SUBJECT_REPLACEMENT
        return self.role_mode

    @property
    def requires_subject_replacement(self) -> bool:
        return self.effective_role_mode is VisualRoleMode.SUBJECT_REPLACEMENT

    @property
    def requires_supporting_integration(self) -> bool:
        return self.effective_role_mode is VisualRoleMode.SUPPORTING_INTEGRATION

    @property
    def requires_visible_signature(self) -> bool:
        return True

    def to_dict(self) -> dict[str, str]:
        return {
            "visual_role_mode": self.role_mode.value,
            "visual_consistency_mode": self.consistency_mode.value,
            "effective_visual_role_mode": self.effective_role_mode.value,
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
            guidance.append("Choose primary replacement only when it preserves the source intent; otherwise use visible supporting integration.")
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


def _enum_value(value: Any, enum_cls: type[Enum], default: Enum) -> Enum:
    text = str(value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    return default


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
    "VisualRoleMode",
    "VisualConsistencyMode",
    "VisualRoleStrategyControls",
    "build_visual_identity_kernel",
]
