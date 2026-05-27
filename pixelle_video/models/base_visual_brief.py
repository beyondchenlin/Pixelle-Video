from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BaseVisualBrief:
    """Structured design brief for the image before any recurring visual anchor is inserted."""

    frame_id: str
    core_message: str
    visual_moment: str
    main_subjects: tuple[str, ...] = ()
    subject_identity_anchors: tuple[str, ...] = ()
    subject_relationship: str = ""
    setting: str = ""
    spatial_layout: str = ""
    camera_plan: str = ""
    composition_rules: str = ""
    lighting_mood: str = ""
    style_surface: str = ""
    key_props_symbols: tuple[str, ...] = ()
    readability_constraints: tuple[str, ...] = ()
    anchor_affordances: tuple[str, ...] = ()
    anchor_forbidden_zones: tuple[str, ...] = ()
    anchor_integration_notes: tuple[str, ...] = ()
    base_image_prompt: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "base_visual_brief.v2_scene_affordances"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "core_message", _optional_text(self.core_message))
        object.__setattr__(self, "visual_moment", _optional_text(self.visual_moment))
        for field_name in (
            "main_subjects",
            "subject_identity_anchors",
            "key_props_symbols",
            "readability_constraints",
            "anchor_affordances",
            "anchor_forbidden_zones",
            "anchor_integration_notes",
        ):
            object.__setattr__(self, field_name, _normalize_text_tuple(field_name, getattr(self, field_name)))
        for field_name in (
            "subject_relationship",
            "setting",
            "spatial_layout",
            "camera_plan",
            "composition_rules",
            "lighting_mood",
            "style_surface",
            "base_image_prompt",
        ):
            object.__setattr__(self, field_name, _optional_text(getattr(self, field_name)))
        if not self.base_image_prompt:
            object.__setattr__(self, "base_image_prompt", _fallback_base_prompt(self))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "version", _require_non_empty("version", self.version))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frame_id": self.frame_id,
            "core_message": self.core_message,
            "visual_moment": self.visual_moment,
            "main_subjects": list(self.main_subjects),
            "subject_identity_anchors": list(self.subject_identity_anchors),
            "subject_relationship": self.subject_relationship,
            "setting": self.setting,
            "spatial_layout": self.spatial_layout,
            "camera_plan": self.camera_plan,
            "composition_rules": self.composition_rules,
            "lighting_mood": self.lighting_mood,
            "style_surface": self.style_surface,
            "key_props_symbols": list(self.key_props_symbols),
            "readability_constraints": list(self.readability_constraints),
            "anchor_affordances": list(self.anchor_affordances),
            "anchor_forbidden_zones": list(self.anchor_forbidden_zones),
            "anchor_integration_notes": list(self.anchor_integration_notes),
            "base_image_prompt": self.base_image_prompt,
            "metadata": dict(self.metadata),
        }


def _fallback_base_prompt(brief: BaseVisualBrief) -> str:
    parts = [
        brief.visual_moment,
        brief.subject_relationship,
        brief.setting,
        brief.spatial_layout,
        brief.camera_plan,
        brief.composition_rules,
        brief.lighting_mood,
        brief.style_surface,
    ]
    return "，".join(part for part in parts if part) or brief.core_message or "清晰可读的主体画面"


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_text_tuple(field_name: str, values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
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


__all__ = ["BaseVisualBrief"]
