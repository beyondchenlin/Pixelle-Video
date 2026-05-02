from __future__ import annotations

from pathlib import Path

from pixelle_video.models.layered_template import (
    LAYERED_TEMPLATE_VERSION,
    LayeredTemplateSpec,
    RectSpec,
)
from pixelle_video.models.template_preset import TemplatePreset
from pixelle_video.repositories.template_presets import TemplatePresetRepository
from pixelle_video.utils.template_util import get_template_type, parse_template_size


class TemplateRegistry:
    def __init__(
        self,
        *,
        preset_repository: TemplatePresetRepository | None = None,
        repository: TemplatePresetRepository | None = None,
        templates_root: str | Path = "templates",
    ) -> None:
        if preset_repository is not None and repository is not None:
            raise ValueError("provide either preset_repository or repository, not both")
        self.preset_repository = preset_repository or repository or TemplatePresetRepository(
            "data/template_presets"
        )
        self.templates_root = Path(templates_root)

    def list_presets(self, *, source: str = "all") -> list[TemplatePreset]:
        if source == "all":
            return self.list_all()
        if source == "system":
            return self.list_system()
        if source == "user":
            return self.list_user()
        if source == "recent":
            return self.list_recent(limit=5)
        raise ValueError("source must be one of: all, system, user, recent")

    def list_system(self) -> list[TemplatePreset]:
        if not self.templates_root.exists():
            return []
        return [
            _system_template_to_preset(self.templates_root, path)
            for path in sorted(self.templates_root.rglob("*.html"))
        ]

    def list_user(self) -> list[TemplatePreset]:
        return self.preset_repository.list_all()

    def list_recent(self, limit: int = 5) -> list[TemplatePreset]:
        return self.preset_repository.list_recent(limit=limit)

    def list_all(self) -> list[TemplatePreset]:
        return [*self.list_system(), *self.list_user()]

    def get(self, preset_id: str) -> TemplatePreset:
        for preset in self.list_system():
            if preset.preset_id == preset_id:
                return preset
        user_preset = self.preset_repository.get(preset_id)
        if user_preset is not None:
            return user_preset
        raise KeyError(preset_id)

    def mark_used(self, preset_id: str) -> None:
        if preset_id.startswith("system:"):
            return
        self.preset_repository.touch_last_used(preset_id)


def _system_template_to_preset(root: Path, template_path: Path) -> TemplatePreset:
    relative_path = template_path.relative_to(root).as_posix()
    width, height = parse_template_size(relative_path)
    template_type = get_template_type(template_path.name)
    preset_id = f"system:{relative_path}"
    spec = LayeredTemplateSpec(
        version=LAYERED_TEMPLATE_VERSION,
        template_id=preset_id,
        template_name=template_path.name,
        template_type=template_type,
        canvas_width=width,
        canvas_height=height,
        media_width=width,
        media_height=height,
        safe_area=RectSpec(x=0, y=0, width=width, height=height),
        layers=(),
        metadata={
            "source_kind": "legacy_html",
            "legacy_template_path": relative_path,
        },
    )
    return TemplatePreset(
        preset_id=preset_id,
        name=template_path.name,
        source="system",
        orientation=_orientation(width, height),
        template_type=template_type,
        spec=spec,
        editable=False,
    )


def _orientation(width: int, height: int) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"
