"""Storyboard planning data contracts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

ContentMode = Literal["theme_mapping", "concept_explainer"]
ConsistencyStrength = Literal["standard", "strong"]
RoleStrategy = Literal["auto", "stable_explainer_cast", "theme_mapping"]
ShotOverridePolicy = Literal["adaptive", "strict"]
FrameSource = Literal["planner_generated", "user_edited", "repair_adjusted", "fallback_regenerated"]
FrameOverrideSource = Literal["user_preview"]
ReplanScope = Literal["local", "adjacent", "global"]


def _to_list(values: tuple[Any, ...] | list[Any]) -> list[Any]:
    return list(values)


def _normalize_scene_id_value(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")
    if not isinstance(value, str):
        raise ValueError("storyboard frame field scene_id must be a string or integer-like number")

    normalized = value.strip()
    if not normalized:
        raise ValueError("storyboard frame field scene_id must be a non-empty string")
    return normalized


@dataclass(frozen=True)
class WorldPresetDefinition:
    preset_id: str
    display_name: str
    supported_modes: tuple[ContentMode, ...]
    display_name_key: Optional[str] = None
    description_key: Optional[str] = None
    style_core: str = ""
    world_elements: tuple[str, ...] = ()
    knowledge_scene_rules: tuple[str, ...] = ()
    negative_rules: tuple[str, ...] = ()
    default_shot_preset_ids: tuple[str, ...] = ()
    cast_slots: tuple[dict[str, Any], ...] = ()
    cast_slots_by_mode: dict[ContentMode, tuple[dict[str, Any], ...]] = field(default_factory=dict)
    conservative_fallback_mode: ContentMode = "concept_explainer"
    safe_default: bool = False
    forced_mode: Optional[ContentMode] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "display_name_key": self.display_name_key,
            "description_key": self.description_key,
            "supported_modes": _to_list(self.supported_modes),
            "style_core": self.style_core,
            "world_elements": _to_list(self.world_elements),
            "knowledge_scene_rules": _to_list(self.knowledge_scene_rules),
            "negative_rules": _to_list(self.negative_rules),
            "default_shot_preset_ids": _to_list(self.default_shot_preset_ids),
            "cast_slots": [dict(slot) for slot in self.cast_slots],
            "cast_slots_by_mode": {
                mode: [dict(slot) for slot in slots]
                for mode, slots in self.cast_slots_by_mode.items()
            },
            "conservative_fallback_mode": self.conservative_fallback_mode,
            "safe_default": self.safe_default,
            "forced_mode": self.forced_mode,
        }


@dataclass(frozen=True)
class ShotPresetDefinition:
    preset_id: str
    display_name: str
    supported_scene_count: tuple[int, ...]
    display_name_key: Optional[str] = None
    description_key: Optional[str] = None
    max_consecutive_same: int = 2
    shot_distribution_rules: tuple[str, ...] = ()
    opening_rules: tuple[str, ...] = ()
    closing_rules: tuple[str, ...] = ()
    transition_rules: tuple[str, ...] = ()
    purpose_bias: str = ""
    override_policy: ShotOverridePolicy = "adaptive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "display_name_key": self.display_name_key,
            "description_key": self.description_key,
            "supported_scene_count": _to_list(self.supported_scene_count),
            "max_consecutive_same": self.max_consecutive_same,
            "shot_distribution_rules": _to_list(self.shot_distribution_rules),
            "opening_rules": _to_list(self.opening_rules),
            "closing_rules": _to_list(self.closing_rules),
            "transition_rules": _to_list(self.transition_rules),
            "purpose_bias": self.purpose_bias,
            "override_policy": self.override_policy,
        }


@dataclass(frozen=True)
class ResolvedContentMode:
    mode: ContentMode
    confidence: float = 1.0
    mixed_content_flag: bool = False
    dominant_anchor_type: str = ""
    reason_summary: str = ""
    selection_source: str = "fallback_mode"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "mixed_content_flag": self.mixed_content_flag,
            "dominant_anchor_type": self.dominant_anchor_type,
            "reason_summary": self.reason_summary,
            "selection_source": self.selection_source,
        }


@dataclass(frozen=True)
class ResolvedShotPreset:
    preset_id: str
    override_policy: ShotOverridePolicy
    supported_scene_count: tuple[int, ...] = ()
    max_consecutive_same: int = 2
    selection_source: str = "auto_selected"
    fallback_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "override_policy": self.override_policy,
            "supported_scene_count": _to_list(self.supported_scene_count),
            "max_consecutive_same": self.max_consecutive_same,
            "selection_source": self.selection_source,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class FramePlan:
    scene_id: str
    narration_fragment: str = ""
    knowledge_goal: str = ""
    shot_type: str = ""
    shot_purpose: str = ""
    primary_subject: str = ""
    secondary_subjects: tuple[str, ...] = ()
    world_elements: tuple[str, ...] = ()
    continuity_anchors: tuple[str, ...] = ()
    focus_detail: str = ""
    prompt_intent: str = ""
    locked_fields: tuple[str, ...] = ()
    override_source: Optional[FrameOverrideSource] = None
    frame_source: FrameSource = "planner_generated"
    replan_scope: ReplanScope = "local"
    planner_version: str = "1.0"

    @classmethod
    def required_prompt_fields(cls) -> tuple[str, ...]:
        return (
            "scene_id",
            "narration_fragment",
            "knowledge_goal",
            "shot_type",
            "shot_purpose",
            "primary_subject",
            "secondary_subjects",
            "world_elements",
            "continuity_anchors",
            "focus_detail",
            "prompt_intent",
            "locked_fields",
            "override_source",
            "frame_source",
            "replan_scope",
            "planner_version",
        )

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "narration_fragment": self.narration_fragment,
            "knowledge_goal": self.knowledge_goal,
            "shot_type": self.shot_type,
            "shot_purpose": self.shot_purpose,
            "primary_subject": self.primary_subject,
            "secondary_subjects": _to_list(self.secondary_subjects),
            "world_elements": _to_list(self.world_elements),
            "continuity_anchors": _to_list(self.continuity_anchors),
            "focus_detail": self.focus_detail,
            "prompt_intent": self.prompt_intent,
            "locked_fields": _to_list(self.locked_fields),
            "override_source": self.override_source,
            "frame_source": self.frame_source,
            "replan_scope": self.replan_scope,
            "planner_version": self.planner_version,
        }


class StoryboardPlanningFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str = Field(
        description='Quoted string scene identifier matching narration order, for example "1", "2", "3". Never return it as a number.'
    )
    narration_fragment: str
    knowledge_goal: str
    shot_type: str
    shot_purpose: str
    primary_subject: str
    secondary_subjects: list[str]
    world_elements: list[str]
    continuity_anchors: list[str]
    focus_detail: str
    prompt_intent: str
    locked_fields: list[str]
    override_source: Optional[FrameOverrideSource] = None
    frame_source: FrameSource
    replan_scope: ReplanScope
    planner_version: str

    @field_validator("scene_id", mode="before")
    @classmethod
    def _validate_scene_id(cls, value: Any) -> str:
        return _normalize_scene_id_value(value)

    @model_validator(mode="before")
    @classmethod
    def _convert_comma_separated_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        list_fields = ["secondary_subjects", "world_elements", "continuity_anchors", "locked_fields"]
        for field_name in list_fields:
            if field_name in values:
                value = values[field_name]
                if value is None:
                    values[field_name] = []
                elif isinstance(value, str):
                    if not value.strip():
                        values[field_name] = []
                    else:
                        converted = [item.strip() for item in value.split(",") if item.strip()]
                        logger.warning(
                            f"LLM returned comma-separated string for field '{field_name}' instead of list. "
                            f"Converted '{value}' -> {converted}. Consider updating the prompt to enforce list output."
                        )
                        values[field_name] = converted
                elif isinstance(value, list):
                    if not all(isinstance(item, str) for item in value):
                        raise ValueError(f"list items must be strings, got {[type(i).__name__ for i in value if not isinstance(i, str)]}")
        return values

    def to_frame_plan(self) -> "FramePlan":
        return FramePlan(
            scene_id=self.scene_id,
            narration_fragment=self.narration_fragment,
            knowledge_goal=self.knowledge_goal,
            shot_type=self.shot_type,
            shot_purpose=self.shot_purpose,
            primary_subject=self.primary_subject,
            secondary_subjects=tuple(self.secondary_subjects),
            world_elements=tuple(self.world_elements),
            continuity_anchors=tuple(self.continuity_anchors),
            focus_detail=self.focus_detail,
            prompt_intent=self.prompt_intent,
            locked_fields=tuple(self.locked_fields),
            override_source=self.override_source,
            frame_source=self.frame_source,
            replan_scope=self.replan_scope,
            planner_version=self.planner_version,
        )


class StoryboardPlanningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: list[StoryboardPlanningFrameResponse]

    def to_frame_plans(self) -> list["FramePlan"]:
        return [frame.to_frame_plan() for frame in self.frames]


@dataclass(frozen=True)
class StoryboardPlanningResult:
    requested_content_mode: Optional[ContentMode]
    resolved_content_mode: ResolvedContentMode
    world_preset_id: str
    resolved_shot_preset: ResolvedShotPreset
    planning_snapshot: dict[str, Any] = field(default_factory=dict)
    frames: tuple[FramePlan, ...] = ()
    scene_count: int = 0
    consistency_strength: ConsistencyStrength = "standard"
    role_strategy: RoleStrategy = "auto"
    warnings: tuple[str, ...] = ()
    planner_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_content_mode": self.requested_content_mode,
            "resolved_content_mode": self.resolved_content_mode.to_dict(),
            "world_preset_id": self.world_preset_id,
            "resolved_shot_preset": self.resolved_shot_preset.to_dict(),
            "planning_snapshot": dict(self.planning_snapshot),
            "frames": [frame.to_prompt_dict() for frame in self.frames],
            "scene_count": self.scene_count,
            "consistency_strength": self.consistency_strength,
            "role_strategy": self.role_strategy,
            "warnings": _to_list(self.warnings),
            "planner_version": self.planner_version,
        }
