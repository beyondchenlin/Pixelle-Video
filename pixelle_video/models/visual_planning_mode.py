from __future__ import annotations

from enum import Enum
from typing import Any


class VisualPlanningMode(str, Enum):
    AUTO = "auto"
    SCENE_INTEGRATION = "scene_integration"
    COGNITIVE_ILLUSTRATION = "cognitive_illustration"
    STRUCTURAL_EXPLAINER = "structural_explainer"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAP = "relationship_map"

    @classmethod
    def from_value(cls, value: Any) -> "VisualPlanningMode":
        return _enum_from_value(value, cls, cls.AUTO)


class PrimaryVisualTask(str, Enum):
    SCENE_RECONSTRUCTION = "scene_reconstruction"
    COGNITIVE_EXPLANATION = "cognitive_explanation"
    STRUCTURE_EXPLANATION = "structure_explanation"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAPPING = "relationship_mapping"

    @classmethod
    def from_value(cls, value: Any) -> "PrimaryVisualTask":
        return _enum_from_value(value, cls, cls.SCENE_RECONSTRUCTION)


class VisibleTextPolicy(str, Enum):
    NO_VISIBLE_TEXT = "no_visible_text"
    SOURCE_TEXT_ONLY = "source_text_only"
    SYMBOLIC_LABELS_ONLY = "symbolic_labels_only"
    APPROVED_LABELS_ONLY = "approved_labels_only"

    @classmethod
    def from_value(cls, value: Any) -> "VisibleTextPolicy":
        return _enum_from_value(value, cls, cls.NO_VISIBLE_TEXT)


def _enum_from_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    return default


__all__ = [
    "PrimaryVisualTask",
    "VisibleTextPolicy",
    "VisualPlanningMode",
]
