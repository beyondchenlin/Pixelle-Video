from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class VisualExpressionMode(str, Enum):
    AUTO = "auto"
    NARRATIVE_SCENE = "narrative_scene"
    EXPLANATORY_DIAGRAM = "explanatory_diagram"
    COGNITIVE_METAPHOR = "cognitive_metaphor"
    INFOGRAPHIC_LAYOUT = "infographic_layout"
    COMPARISON_OR_DEBATE_SCENE = "comparison_or_debate_scene"
    PRODUCT_OR_OBJECT_SCENE = "product_or_object_scene"
    PORTRAIT_OR_HOST_SCENE = "portrait_or_host_scene"
    ENVIRONMENT_BRANDING = "environment_branding"

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        default: "VisualExpressionMode" | None = None,
    ) -> "VisualExpressionMode":
        fallback = default or cls.AUTO
        if isinstance(value, cls):
            return value
        text = str(value or "").strip()
        if not text:
            return fallback
        for item in cls:
            if text == item.value or text.lower() == item.name.lower():
                return item
        return fallback


@dataclass(frozen=True)
class VisualExpressionDecision:
    frame_id: str
    expression_mode: VisualExpressionMode
    reason: str = ""
    source: str = "rule"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(self, "expression_mode", normalize_visual_expression_mode(self.expression_mode))
        object.__setattr__(self, "reason", _optional_text(self.reason))
        object.__setattr__(self, "source", _optional_text(self.source) or "rule")

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "expression_mode": self.expression_mode.value,
            "reason": self.reason,
            "source": self.source,
        }


def normalize_visual_expression_mode(
    value: Any,
    *,
    default: VisualExpressionMode = VisualExpressionMode.AUTO,
) -> VisualExpressionMode:
    return VisualExpressionMode.from_value(value, default=default)


def visual_expression_mode_from_mapping(source: Mapping[str, Any] | None) -> VisualExpressionMode:
    mapping = source or {}
    return normalize_visual_expression_mode(
        mapping.get("visual_expression_mode") or mapping.get("expression_mode")
    )


def _require_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "VisualExpressionDecision",
    "VisualExpressionMode",
    "normalize_visual_expression_mode",
    "visual_expression_mode_from_mapping",
]
