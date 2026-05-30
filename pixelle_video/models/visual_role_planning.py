from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.models.visual_role_strategy import VisualConsistencyMode, VisualRoleMode


@dataclass(frozen=True)
class VisualRoleIntegratedPromptPlan:
    frame_id: str
    expression_mode: VisualExpressionMode
    role_mode: VisualRoleMode
    consistency_mode: VisualConsistencyMode
    role_assignment: str
    scene_rewrite_level: str
    integration_strategy: str
    original_intent_summary: str
    retained_intent: tuple[str, ...]
    transformed_scene_logic: str
    role_action: str
    role_manifestation: str
    role_location: str
    integrated_scene_prompt: str
    quality_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "visual_role_integrated_prompt_plan.v4_1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(self, "expression_mode", VisualExpressionMode(self.expression_mode))
        object.__setattr__(self, "role_mode", VisualRoleMode(self.role_mode))
        object.__setattr__(self, "consistency_mode", VisualConsistencyMode(self.consistency_mode))
        for field_name in (
            "role_assignment",
            "scene_rewrite_level",
            "integration_strategy",
            "original_intent_summary",
            "transformed_scene_logic",
            "role_action",
            "role_manifestation",
            "role_location",
            "integrated_scene_prompt",
        ):
            object.__setattr__(self, field_name, _require_text(field_name, getattr(self, field_name)))
        object.__setattr__(self, "retained_intent", _normalize_tuple(self.retained_intent))
        object.__setattr__(self, "quality_notes", _normalize_tuple(self.quality_notes))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "version", _require_text("version", self.version))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "expression_mode": self.expression_mode.value,
            "role_mode": self.role_mode.value,
            "consistency_mode": self.consistency_mode.value,
            "role_assignment": self.role_assignment,
            "scene_rewrite_level": self.scene_rewrite_level,
            "integration_strategy": self.integration_strategy,
            "original_intent_summary": self.original_intent_summary,
            "retained_intent": list(self.retained_intent),
            "transformed_scene_logic": self.transformed_scene_logic,
            "role_action": self.role_action,
            "role_manifestation": self.role_manifestation,
            "role_location": self.role_location,
            "integrated_scene_prompt": self.integrated_scene_prompt,
            "quality_notes": list(self.quality_notes),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VisualRolePromptIssue:
    code: str
    severity: Literal["blocking", "warning"]
    message: str
    repair_instruction: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text("code", self.code))
        object.__setattr__(self, "severity", "blocking" if self.severity == "blocking" else "warning")
        object.__setattr__(self, "message", _require_text("message", self.message))
        object.__setattr__(self, "repair_instruction", _require_text("repair_instruction", self.repair_instruction))

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "repair_instruction": self.repair_instruction,
        }


@dataclass(frozen=True)
class VisualRoleCritique:
    frame_id: str
    issues: tuple[VisualRolePromptIssue, ...] = ()
    reviewer: str = "rule"
    version: str = "visual_role_critique.v4_1"

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "blocking" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "passed": self.passed,
            "reviewer": self.reviewer,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _require_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_tuple(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
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
    return tuple(result)


__all__ = [
    "VisualRoleCritique",
    "VisualRoleIntegratedPromptPlan",
    "VisualRolePromptIssue",
]
