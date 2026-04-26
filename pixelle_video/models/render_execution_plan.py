from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from pixelle_video.models.text_overlay import (
    FrozenJSONValue,
    freeze_json_value,
    thaw_json_value,
)


def _freeze_json_mapping(
    value: Mapping[str, Any] | None,
) -> Mapping[str, FrozenJSONValue]:
    frozen = freeze_json_value(dict(value or {}))
    if not isinstance(frozen, Mapping):
        raise TypeError("Expected a JSON object mapping.")
    return frozen


@dataclass(frozen=True)
class RenderExecutionArtifact:
    role: str
    path: str
    frame_index: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", str(self.role))
        object.__setattr__(self, "path", str(self.path))
        if self.frame_index is not None:
            object.__setattr__(self, "frame_index", int(self.frame_index))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "frame_index": self.frame_index,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderExecutionArtifact":
        return cls(
            role=str(data["role"]),
            path=str(data["path"]),
            frame_index=(
                int(data["frame_index"])
                if data.get("frame_index") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class RenderExecutionPlan:
    requested_backend: str
    effective_backend: str
    fallback_reason: Optional[str] = None
    template_materialization_mode: str = "none"
    element_motion_mode: str = "none"
    subtitle_mode: str = "none"
    audio_strategy: str = "auto"
    artifacts: tuple[RenderExecutionArtifact, ...] = ()
    diagnostics: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_backend", str(self.requested_backend))
        object.__setattr__(self, "effective_backend", str(self.effective_backend))
        object.__setattr__(
            self,
            "fallback_reason",
            str(self.fallback_reason) if self.fallback_reason is not None else None,
        )
        object.__setattr__(
            self,
            "template_materialization_mode",
            str(self.template_materialization_mode),
        )
        object.__setattr__(self, "element_motion_mode", str(self.element_motion_mode))
        object.__setattr__(self, "subtitle_mode", str(self.subtitle_mode))
        object.__setattr__(self, "audio_strategy", str(self.audio_strategy))
        object.__setattr__(
            self,
            "artifacts",
            tuple(
                artifact
                if isinstance(artifact, RenderExecutionArtifact)
                else RenderExecutionArtifact.from_dict(artifact)
                for artifact in self.artifacts
            ),
        )
        object.__setattr__(self, "diagnostics", _freeze_json_mapping(self.diagnostics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "effective_backend": self.effective_backend,
            "fallback_reason": self.fallback_reason,
            "template_materialization_mode": self.template_materialization_mode,
            "element_motion_mode": self.element_motion_mode,
            "subtitle_mode": self.subtitle_mode,
            "audio_strategy": self.audio_strategy,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "diagnostics": thaw_json_value(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderExecutionPlan":
        return cls(
            requested_backend=str(data["requested_backend"]),
            effective_backend=str(data["effective_backend"]),
            fallback_reason=data.get("fallback_reason"),
            template_materialization_mode=str(
                data.get("template_materialization_mode", "none")
            ),
            element_motion_mode=str(data.get("element_motion_mode", "none")),
            subtitle_mode=str(data.get("subtitle_mode", "none")),
            audio_strategy=str(data.get("audio_strategy", "auto")),
            artifacts=tuple(
                RenderExecutionArtifact.from_dict(item)
                for item in data.get("artifacts", ())
            ),
            diagnostics=data.get("diagnostics", {}),
        )
