from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class SceneCast:
    scene_cast_id: str
    workspace_id: str
    project_id: str
    storyboard_plan_id: str
    frame_id: str
    asset_bible_id: str
    character_ids: tuple[str, ...] = ()
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = ()
    style_id: str | None = None
    continuity_notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_cast_id", _require_non_empty("scene_cast_id", self.scene_cast_id))
        object.__setattr__(self, "workspace_id", _require_non_empty("workspace_id", self.workspace_id))
        object.__setattr__(self, "project_id", _require_non_empty("project_id", self.project_id))
        object.__setattr__(
            self,
            "storyboard_plan_id",
            _require_non_empty("storyboard_plan_id", self.storyboard_plan_id),
        )
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(
            self,
            "asset_bible_id",
            _require_non_empty("asset_bible_id", self.asset_bible_id),
        )
        object.__setattr__(
            self,
            "character_ids",
            _normalize_id_tuple("character_ids", self.character_ids),
        )
        object.__setattr__(self, "scene_id", _optional_str(self.scene_id))
        object.__setattr__(self, "prop_ids", _normalize_id_tuple("prop_ids", self.prop_ids))
        object.__setattr__(self, "style_id", _optional_str(self.style_id))
        object.__setattr__(
            self,
            "continuity_notes",
            _normalize_text_tuple("continuity_notes", self.continuity_notes),
        )
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_cast_id": self.scene_cast_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "frame_id": self.frame_id,
            "asset_bible_id": self.asset_bible_id,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "continuity_notes": list(self.continuity_notes),
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SceneCast":
        if not isinstance(payload, Mapping):
            raise ValueError("SceneCast payload must be a mapping")
        return cls(
            scene_cast_id=payload.get("scene_cast_id", ""),
            workspace_id=payload.get("workspace_id", ""),
            project_id=payload.get("project_id", ""),
            storyboard_plan_id=payload.get("storyboard_plan_id", ""),
            frame_id=payload.get("frame_id", ""),
            asset_bible_id=payload.get("asset_bible_id", ""),
            character_ids=tuple(payload.get("character_ids") or ()),
            scene_id=payload.get("scene_id"),
            prop_ids=tuple(payload.get("prop_ids") or ()),
            style_id=payload.get("style_id"),
            continuity_notes=tuple(payload.get("continuity_notes") or ()),
            metadata=payload.get("metadata") or {},
        )


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


def _normalize_id_tuple(field_name: str, value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized = tuple(_require_non_empty(field_name, item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _normalize_text_tuple(field_name: str, value: Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
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


__all__ = ["SceneCast"]
