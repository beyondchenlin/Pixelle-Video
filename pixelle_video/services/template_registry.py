from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from pixelle_video.models.layered_template import LayeredTemplateSpec, RectSpec
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.utils.template_util import (
    TemplateInfo,
    get_all_templates_with_info,
    get_template_type,
    parse_template_size,
)


def build_layered_spec_from_template_descriptor(item: TemplateInfo) -> LayeredTemplateSpec:
    canvas_width, canvas_height = parse_template_size(item.template_path)
    orientation = item.display_info.orientation
    return LayeredTemplateSpec(
        version="layered_template.v1",
        template_id=f"system:{item.template_path}",
        template_name=item.display_info.name,
        template_type=get_template_type(item.display_info.name),
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        media_width=canvas_width,
        media_height=canvas_height,
        safe_area=RectSpec(x=0, y=0, width=canvas_width, height=canvas_height),
        layers=(),
        metadata={
            "source_kind": "legacy_html",
            "legacy_template_path": item.template_path,
            "orientation": orientation,
        },
    )


def build_system_template_presets() -> list[TemplatePreset]:
    presets: list[TemplatePreset] = []
    for item in get_all_templates_with_info():
        spec = build_layered_spec_from_template_descriptor(item)
        presets.append(
            TemplatePreset(
                preset_id=f"system:{item.template_path}",
                name=Path(item.display_info.name).name,
                source="system",
                orientation=item.display_info.orientation,
                template_type=get_template_type(item.display_info.name),
                spec=spec,
                editable=False,
            )
        )
    return presets


class TemplateRegistry:
    def __init__(self, repository: TemplatePresetRepository | None = None) -> None:
        self.repository = repository or TemplatePresetRepository()

    def list_presets(self, *, source: str = "all") -> list[TemplatePreset]:
        if source == "system":
            return build_system_template_presets()
        if source == "user":
            return self.repository.list_all(source="user")
        if source == "recent":
            return self.repository.list_recent(limit=5)
        if source != "all":
            raise ValueError(f"unsupported template preset source: {source}")
        return build_system_template_presets() + self.repository.list_all(source="user")

    def list_recent(self, *, limit: int = 5) -> list[TemplatePreset]:
        return self.repository.list_recent(limit=limit)

    def get_preset(self, preset_id: str) -> TemplatePreset | None:
        persisted = self.repository.get(preset_id)
        if persisted is not None:
            return persisted
        for preset in build_system_template_presets():
            if preset.preset_id == preset_id:
                return preset
        return None

    def mark_used(self, preset_id: str, used_at: str | None = None) -> TemplatePreset:
        timestamp = used_at or datetime.now(timezone.utc).isoformat()
        persisted = self.repository.get(preset_id)
        if persisted is not None:
            return self.repository.touch_last_used(preset_id, timestamp)
        system_preset = self.get_preset(preset_id)
        if system_preset is None:
            raise KeyError(f"unknown template preset id: {preset_id}")
        return self.repository.save_recent_snapshot(
            replace(system_preset, last_used_at=timestamp),
            timestamp,
        )

    def delete_recent(self, preset_id: str) -> bool:
        return self.repository.delete(preset_id)
