from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    freeze_json_value,
    thaw_json_value,
)


def _freeze_json_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    frozen = freeze_json_value(dict(value or {}))
    if not isinstance(frozen, Mapping):
        raise TypeError("Expected a JSON object mapping.")
    return frozen


def _freeze_json_mapping_tuple(
    values: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None,
) -> tuple[Mapping[str, FrozenJSONValue], ...]:
    return tuple(_freeze_json_mapping(value) for value in values or ())


@dataclass(frozen=True)
class TextLayoutPlan:
    version: str = "text_layout_plan.v1"
    safe_areas: tuple[Mapping[str, FrozenJSONValue], ...] = ()
    wrapped_lines: tuple[Mapping[str, FrozenJSONValue], ...] = ()
    collisions: tuple[Mapping[str, FrozenJSONValue], ...] = ()
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "safe_areas", _freeze_json_mapping_tuple(self.safe_areas)
        )
        object.__setattr__(
            self, "wrapped_lines", _freeze_json_mapping_tuple(self.wrapped_lines)
        )
        object.__setattr__(
            self, "collisions", _freeze_json_mapping_tuple(self.collisions)
        )
        object.__setattr__(self, "diagnostics", _freeze_json_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "safe_areas": [thaw_json_value(item) for item in self.safe_areas],
            "wrapped_lines": [thaw_json_value(item) for item in self.wrapped_lines],
            "collisions": [thaw_json_value(item) for item in self.collisions],
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "TextLayoutPlan":
        payload = dict(data or {})
        return cls(
            version=str(payload.get("version", "text_layout_plan.v1")),
            safe_areas=tuple(payload.get("safe_areas", ())),
            wrapped_lines=tuple(payload.get("wrapped_lines", ())),
            collisions=tuple(payload.get("collisions", ())),
            diagnostics=payload.get("diagnostics", {}),
        )
