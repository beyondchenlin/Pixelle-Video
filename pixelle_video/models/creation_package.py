from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    JSONValue,
    TextOverlayPlan,
    freeze_json_value,
    thaw_json_value,
)


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    return freeze_json_value(dict(value or {}))


@dataclass(frozen=True)
class CreationPackage:
    task_id: str
    version: str = "creation_package.v1"
    content_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    storyboard_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    style_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    prompt_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    audio_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    text_overlay_plan: TextOverlayPlan | None = None
    asset_manifest: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    render_plan: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    observability_refs: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "content_plan",
            "storyboard_plan",
            "style_plan",
            "prompt_plan",
            "audio_plan",
            "asset_manifest",
            "render_plan",
            "observability_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping(getattr(self, field_name)),
            )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "task_id": self.task_id,
            "content_plan": thaw_json_value(self.content_plan),
            "storyboard_plan": thaw_json_value(self.storyboard_plan),
            "style_plan": thaw_json_value(self.style_plan),
            "prompt_plan": thaw_json_value(self.prompt_plan),
            "audio_plan": thaw_json_value(self.audio_plan),
            "text_overlay_plan": (
                self.text_overlay_plan.to_dict()
                if self.text_overlay_plan is not None
                else None
            ),
            "asset_manifest": thaw_json_value(self.asset_manifest),
            "render_plan": thaw_json_value(self.render_plan),
            "observability_refs": thaw_json_value(self.observability_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CreationPackage":
        raw_plan = data.get("text_overlay_plan")
        return cls(
            version=str(data.get("version", "creation_package.v1")),
            task_id=str(data["task_id"]),
            content_plan=data.get("content_plan", {}),
            storyboard_plan=data.get("storyboard_plan", {}),
            style_plan=data.get("style_plan", {}),
            prompt_plan=data.get("prompt_plan", {}),
            audio_plan=data.get("audio_plan", {}),
            text_overlay_plan=(
                TextOverlayPlan.from_dict(raw_plan)
                if isinstance(raw_plan, Mapping)
                else None
            ),
            asset_manifest=data.get("asset_manifest", {}),
            render_plan=data.get("render_plan", {}),
            observability_refs=data.get("observability_refs", {}),
        )
