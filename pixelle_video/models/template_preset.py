from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pixelle_video.models.layered_template import LayeredTemplateSpec

TemplatePresetSource = Literal["system", "user", "recent"]


@dataclass(frozen=True)
class TemplatePreset:
    preset_id: str
    name: str
    source: TemplatePresetSource
    orientation: str
    template_type: str
    spec: LayeredTemplateSpec
    thumbnail_ref: str | None = None
    editable: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    last_used_at: str | None = None

    def __post_init__(self) -> None:
        if not self.preset_id:
            raise ValueError("preset_id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")
        if not self.orientation:
            raise ValueError("orientation must be non-empty")
        if not self.template_type:
            raise ValueError("template_type must be non-empty")
        if not isinstance(self.spec, LayeredTemplateSpec):
            raise TypeError("spec must be a LayeredTemplateSpec")

