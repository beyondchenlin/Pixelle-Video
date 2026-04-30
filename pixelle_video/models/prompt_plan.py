from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class ImagePromptDraft:
    image_prompt_draft_id: str
    storyboard_plan_id: str
    frame_id: str
    prompt_text: str
    source_trace_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "image_prompt_draft_id",
            _require_non_empty("image_prompt_draft_id", self.image_prompt_draft_id),
        )
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "prompt_text", _require_non_empty("prompt_text", self.prompt_text))
        object.__setattr__(self, "source_trace_id", _optional_str(self.source_trace_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "prompt_text": self.prompt_text,
            "source_trace_id": self.source_trace_id,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImagePromptDraft":
        if not isinstance(payload, Mapping):
            raise ValueError("ImagePromptDraft payload must be a mapping")
        return cls(
            image_prompt_draft_id=payload.get("image_prompt_draft_id", ""),
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            frame_id=payload.get("frame_id", ""),
            prompt_text=payload.get("prompt_text", ""),
            source_trace_id=payload.get("source_trace_id"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class PromptPlan:
    prompt_plan_id: str
    storyboard_plan_id: str
    frame_id: str
    image_prompt_draft_id: str
    prompt_sections: Mapping[str, str]
    final_prompt: str
    source_trace_id: str | None = None
    character_ids: tuple[str, ...] = ()
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = ()
    style_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_plan_id", _require_non_empty("prompt_plan_id", self.prompt_plan_id))
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "image_prompt_draft_id",
            _require_non_empty("image_prompt_draft_id", self.image_prompt_draft_id),
        )
        object.__setattr__(self, "prompt_sections", _freeze_prompt_sections(self.prompt_sections))
        object.__setattr__(self, "final_prompt", _require_non_empty("final_prompt", self.final_prompt))
        object.__setattr__(self, "source_trace_id", _optional_str(self.source_trace_id))
        object.__setattr__(self, "character_ids", _normalize_id_tuple("character_ids", self.character_ids))
        object.__setattr__(self, "scene_id", _optional_str(self.scene_id))
        object.__setattr__(self, "prop_ids", _normalize_id_tuple("prop_ids", self.prop_ids))
        object.__setattr__(self, "style_id", _optional_str(self.style_id))
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan_id": self.prompt_plan_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "prompt_sections": dict(self.prompt_sections),
            "final_prompt": self.final_prompt,
            "source_trace_id": self.source_trace_id,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptPlan":
        if not isinstance(payload, Mapping):
            raise ValueError("PromptPlan payload must be a mapping")
        return cls(
            prompt_plan_id=payload.get("prompt_plan_id", ""),
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            frame_id=payload.get("frame_id", ""),
            image_prompt_draft_id=payload.get("image_prompt_draft_id", ""),
            prompt_sections=payload.get("prompt_sections") or {},
            final_prompt=payload.get("final_prompt", ""),
            source_trace_id=payload.get("source_trace_id"),
            character_ids=tuple(payload.get("character_ids") or ()),
            scene_id=payload.get("scene_id"),
            prop_ids=tuple(payload.get("prop_ids") or ()),
            style_id=payload.get("style_id"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class PromptProjection:
    prompt_plan_id: str
    storyboard_plan_id: str
    frame_id: str
    final_prompt: str
    prompt_sections: Mapping[str, str]
    asset_refs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_plan_id", _require_non_empty("prompt_plan_id", self.prompt_plan_id))
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "final_prompt", _require_non_empty("final_prompt", self.final_prompt))
        object.__setattr__(self, "prompt_sections", _freeze_prompt_sections(self.prompt_sections))
        object.__setattr__(self, "asset_refs", _deep_freeze_mapping(self.asset_refs))

    @classmethod
    def from_prompt_plan(cls, prompt_plan: PromptPlan) -> "PromptProjection":
        return cls(
            prompt_plan_id=prompt_plan.prompt_plan_id,
            storyboard_plan_id=prompt_plan.storyboard_plan_id,
            frame_id=prompt_plan.frame_id,
            final_prompt=prompt_plan.final_prompt,
            prompt_sections=prompt_plan.prompt_sections,
            asset_refs={
                "character_ids": list(prompt_plan.character_ids),
                "scene_id": prompt_plan.scene_id,
                "prop_ids": list(prompt_plan.prop_ids),
                "style_id": prompt_plan.style_id,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan_id": self.prompt_plan_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "final_prompt": self.final_prompt,
            "prompt_sections": dict(self.prompt_sections),
            "asset_refs": _json_safe_copy(self.asset_refs),
        }


def _require_non_empty(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings")
    stripped = value.strip()
    return stripped or None


def _freeze_prompt_sections(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("prompt_sections must be a non-empty mapping")
    normalized = {}
    for key, item in value.items():
        normalized_key = _require_non_empty("prompt_sections key", key)
        normalized[normalized_key] = _require_non_empty(f"prompt_sections.{normalized_key}", item)
    return MappingProxyType(normalized)


def _normalize_id_tuple(field_name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType({
        str(key): _deep_freeze(item)
        for key, item in value.items()
    })


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _deep_freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return deepcopy(value)


__all__ = [
    "ImagePromptDraft",
    "PromptPlan",
    "PromptProjection",
]
