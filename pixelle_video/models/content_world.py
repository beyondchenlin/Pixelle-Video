from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

_HEX_COLOR_RE = re.compile(
    r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])"
)


class ContentWorldHintSource(str, Enum):
    MANUAL = "manual"
    GENERATED_FROM_SCRIPT = "generated_from_script"
    IP_DEFAULT = "ip_default"
    EMPTY = "empty"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class ContentWorldProfile:
    summary: str | None = None
    time_space: str | None = None
    visual_environment: str | None = None
    atmosphere: str | None = None
    cultural_context: str | None = None
    story_constraints: str | None = None
    ip_integration_guidance: str | None = None
    hint_source: ContentWorldHintSource = ContentWorldHintSource.EMPTY
    generation_failed: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "summary",
            "time_space",
            "visual_environment",
            "atmosphere",
            "cultural_context",
            "story_constraints",
            "ip_integration_guidance",
        ):
            value = _optional_text(getattr(self, field_name))
            _reject_hex_colors(field_name, value)
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "hint_source", _coerce_source(self.hint_source))
        object.__setattr__(self, "generation_failed", bool(self.generation_failed))

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "time_space": self.time_space,
            "visual_environment": self.visual_environment,
            "atmosphere": self.atmosphere,
            "cultural_context": self.cultural_context,
            "story_constraints": self.story_constraints,
            "ip_integration_guidance": self.ip_integration_guidance,
            "hint_source": self.hint_source.value,
            "generation_failed": self.generation_failed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "ContentWorldProfile":
        mapping = dict(payload or {})
        return cls(
            summary=mapping.get("summary"),
            time_space=mapping.get("time_space"),
            visual_environment=mapping.get("visual_environment"),
            atmosphere=mapping.get("atmosphere"),
            cultural_context=mapping.get("cultural_context"),
            story_constraints=mapping.get("story_constraints"),
            ip_integration_guidance=mapping.get("ip_integration_guidance"),
            hint_source=mapping.get("hint_source") or ContentWorldHintSource.EMPTY,
            generation_failed=bool(mapping.get("generation_failed", False)),
        )

    def has_content(self) -> bool:
        return any(
            (
                self.summary,
                self.time_space,
                self.visual_environment,
                self.atmosphere,
                self.cultural_context,
                self.story_constraints,
                self.ip_integration_guidance,
            )
        )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_source(value: Any) -> ContentWorldHintSource:
    if isinstance(value, ContentWorldHintSource):
        return value
    try:
        return ContentWorldHintSource(str(value))
    except ValueError:
        return ContentWorldHintSource.EMPTY


def _reject_hex_colors(field_name: str, value: str | None) -> None:
    if value and _HEX_COLOR_RE.search(value):
        raise ValueError(f"{field_name} must not contain hex color literals")


__all__ = ["ContentWorldHintSource", "ContentWorldProfile"]
