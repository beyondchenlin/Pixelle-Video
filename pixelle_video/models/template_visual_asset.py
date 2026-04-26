from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class TemplateVisualAsset:
    path: str
    frame_index: int
    template_id: str
    template_path: str
    width: int
    height: int
    media_path: str | None
    text_policy: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
