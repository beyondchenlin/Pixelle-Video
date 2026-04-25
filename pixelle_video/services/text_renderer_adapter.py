from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from pixelle_video.models.render_package import RenderManifest
from pixelle_video.models.text_overlay import FrozenJSONValue, freeze_json_value, thaw_json_value
from pixelle_video.models.text_render_package import TextRenderPackage


@dataclass(frozen=True)
class TextRenderExportResult:
    target: str
    enabled: bool
    artifacts: Mapping[str, FrozenJSONValue] = field(default_factory=dict)
    cue_count: int = 0
    style_profile_ids: tuple[str, ...] = ()
    fallbacks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    duration_ms: float = 0.0
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", str(self.target))
        object.__setattr__(self, "enabled", bool(self.enabled))
        artifacts = freeze_json_value(dict(self.artifacts or {}))
        diagnostics = freeze_json_value(dict(self.diagnostics or {}))
        if not isinstance(artifacts, Mapping):
            raise TypeError("TextRenderExportResult artifacts must be a mapping")
        if not isinstance(diagnostics, Mapping):
            raise TypeError("TextRenderExportResult diagnostics must be a mapping")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "cue_count", int(self.cue_count))
        object.__setattr__(
            self,
            "style_profile_ids",
            tuple(str(value) for value in self.style_profile_ids),
        )
        object.__setattr__(
            self, "fallbacks", tuple(str(value) for value in self.fallbacks)
        )
        object.__setattr__(
            self, "warnings", tuple(str(value) for value in self.warnings)
        )
        object.__setattr__(self, "duration_ms", float(self.duration_ms))
        object.__setattr__(self, "diagnostics", diagnostics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "enabled": self.enabled,
            "artifacts": thaw_json_value(self.artifacts),
            "cue_count": self.cue_count,
            "style_profile_ids": list(self.style_profile_ids),
            "fallbacks": list(self.fallbacks),
            "warnings": list(self.warnings),
            "duration_ms": self.duration_ms,
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextRenderExportResult":
        payload = dict(data)
        return cls(
            target=str(payload["target"]),
            enabled=bool(payload["enabled"]),
            artifacts=payload.get("artifacts", {}),
            cue_count=int(payload.get("cue_count", 0)),
            style_profile_ids=tuple(payload.get("style_profile_ids", ())),
            fallbacks=tuple(payload.get("fallbacks", ())),
            warnings=tuple(payload.get("warnings", ())),
            duration_ms=float(payload.get("duration_ms", 0.0)),
            diagnostics=payload.get("diagnostics", {}),
        )


@runtime_checkable
class TextRendererAdapter(Protocol):
    target: str

    def supports(self, package: TextRenderPackage) -> bool:
        ...

    def export(
        self,
        *,
        package: TextRenderPackage,
        manifest: RenderManifest,
        output_dir: Path,
    ) -> TextRenderExportResult:
        ...
