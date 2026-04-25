from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSONValue = (
    JSONPrimitive | tuple["FrozenJSONValue", ...] | Mapping[str, "FrozenJSONValue"]
)

_TEXT_MODES = {"suppress", "programmatic_only", "native_hint", "hybrid"}
_TARGETS = {"hyperframes", "html", "ass", "native_prompt", "python"}
_DENSITIES = {"low", "medium", "high"}
DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT = (
    "no visible text, no Chinese characters, no English letters, no words, "
    "no subtitles, no captions, no watermark, no logo text, convey the idea "
    "through objects, symbols, composition, and scene elements instead of written text"
)


def freeze_json_value(value: Any) -> FrozenJSONValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def thaw_json_value(value: Any) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]
    if isinstance(value, list):
        return [thaw_json_value(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, FrozenJSONValue]:
    return freeze_json_value(dict(value or {}))


@dataclass(frozen=True)
class TextOverlaySettings:
    enabled: bool = False
    mode: str = "programmatic_only"
    renderer_targets: tuple[str, ...] = ()
    density: str = "medium"
    max_items_per_frame: int = 2


@dataclass(frozen=True)
class ImageTextPromptPolicy:
    suppress_embedded_text: bool = False
    positive_prompt: str = DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT
    negative_prompt: str | None = None


@dataclass(frozen=True)
class TextRenderingSettings:
    overlay: TextOverlaySettings = field(default_factory=TextOverlaySettings)
    image_text: ImageTextPromptPolicy = field(default_factory=ImageTextPromptPolicy)


def build_text_rendering_settings(data: Mapping[str, Any] | None) -> TextRenderingSettings:
    payload = dict(data or {})
    overlay_payload = dict(payload.get("overlay") or {})
    image_payload = dict(payload.get("image_text") or {})
    return TextRenderingSettings(
        overlay=TextOverlaySettings(
            enabled=bool(overlay_payload.get("enabled", False)),
            mode=str(overlay_payload.get("mode", "programmatic_only")),
            renderer_targets=tuple(overlay_payload.get("renderer_targets", ())),
            density=str(overlay_payload.get("density", "medium")),
            max_items_per_frame=int(overlay_payload.get("max_items_per_frame", 2)),
        ),
        image_text=ImageTextPromptPolicy(
            suppress_embedded_text=bool(
                image_payload.get("suppress_embedded_text", False)
            ),
            positive_prompt=str(
                image_payload.get(
                    "positive_prompt", DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT
                )
                or ""
            ).strip(),
            negative_prompt=(
                str(image_payload.get("negative_prompt")).strip()
                if image_payload.get("negative_prompt") is not None
                else None
            ),
        ),
    )


@dataclass(frozen=True)
class TextRenderingPolicy:
    version: str = "text_rendering_policy.v1"
    image_text_mode: str = "programmatic_only"
    enabled_targets: tuple[str, ...] = ()
    density: str = "medium"
    max_items_per_frame: int = 2
    allow_native_text_in_image: bool = False
    suppress_unplanned_embedded_text: bool = True

    def __post_init__(self) -> None:
        if self.image_text_mode not in _TEXT_MODES:
            raise ValueError(f"Unsupported image_text_mode: {self.image_text_mode}")
        if self.density not in _DENSITIES:
            raise ValueError(f"Unsupported text density: {self.density}")
        if self.max_items_per_frame < 0:
            raise ValueError("max_items_per_frame must be non-negative")
        unknown_targets = set(self.enabled_targets) - _TARGETS
        if unknown_targets:
            raise ValueError(f"Unsupported renderer targets: {sorted(unknown_targets)}")
        if self.image_text_mode in {"suppress", "programmatic_only"}:
            if "native_prompt" in self.enabled_targets:
                raise ValueError(
                    "native_prompt target is not allowed for suppress/programmatic_only"
                )
            if self.allow_native_text_in_image:
                raise ValueError(
                    "allow_native_text_in_image must be false unless native hints are enabled"
                )
        if not self.suppress_unplanned_embedded_text:
            raise ValueError(
                "suppress_unplanned_embedded_text must remain true for phase-0 policy"
            )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "image_text_mode": self.image_text_mode,
            "enabled_targets": list(self.enabled_targets),
            "density": self.density,
            "max_items_per_frame": self.max_items_per_frame,
            "allow_native_text_in_image": self.allow_native_text_in_image,
            "suppress_unplanned_embedded_text": self.suppress_unplanned_embedded_text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextRenderingPolicy":
        return cls(
            version=str(data.get("version", "text_rendering_policy.v1")),
            image_text_mode=str(data.get("image_text_mode", "programmatic_only")),
            enabled_targets=tuple(data.get("enabled_targets", ())),
            density=str(data.get("density", "medium")),
            max_items_per_frame=int(data.get("max_items_per_frame", 2)),
            allow_native_text_in_image=bool(
                data.get("allow_native_text_in_image", False)
            ),
            suppress_unplanned_embedded_text=bool(
                data.get("suppress_unplanned_embedded_text", True)
            ),
        )


def build_text_rendering_policy(
    overlay: TextOverlaySettings | Mapping[str, Any] | None,
    *,
    forbid_embedded_text_in_image: bool | None = None,
) -> TextRenderingPolicy:
    if isinstance(overlay, TextOverlaySettings):
        request = {
            "enabled": overlay.enabled,
            "mode": overlay.mode,
            "renderer_targets": overlay.renderer_targets,
            "density": overlay.density,
            "max_items_per_frame": overlay.max_items_per_frame,
        }
    else:
        request = dict(overlay or {})

    if not request:
        if forbid_embedded_text_in_image is False:
            return TextRenderingPolicy(
                image_text_mode="native_hint",
                enabled_targets=("native_prompt",),
                density="medium",
                max_items_per_frame=2,
                allow_native_text_in_image=True,
                suppress_unplanned_embedded_text=True,
            )
        return TextRenderingPolicy()

    if request.get("enabled", False) is False:
        return TextRenderingPolicy()

    mode = str(request.get("mode", "programmatic_only"))
    targets = tuple(str(target) for target in request.get("renderer_targets", ()))
    if mode in {"native_hint", "hybrid"} and "native_prompt" not in targets:
        targets = (*targets, "native_prompt")
    return TextRenderingPolicy(
        image_text_mode=mode,
        enabled_targets=targets,
        density=str(request.get("density", "medium")),
        max_items_per_frame=int(request.get("max_items_per_frame", 2)),
        allow_native_text_in_image=mode in {"native_hint", "hybrid"},
        suppress_unplanned_embedded_text=True,
    )


@dataclass(frozen=True)
class TextOverlayCandidate:
    id: str
    text: str
    role: str
    suggested_slot: str | None = None
    renderer_targets: tuple[str, ...] = ()
    importance: float = 0.0
    confidence: float = 0.0
    source: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "renderer_targets", tuple(self.renderer_targets))
        object.__setattr__(self, "source", _freeze_mapping(self.source))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "text": self.text,
            "role": self.role,
            "suggested_slot": self.suggested_slot,
            "renderer_targets": list(self.renderer_targets),
            "importance": self.importance,
            "confidence": self.confidence,
            "source": thaw_json_value(self.source),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextOverlayCandidate":
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            role=str(data["role"]),
            suggested_slot=data.get("suggested_slot"),
            renderer_targets=tuple(data.get("renderer_targets", ())),
            importance=float(data.get("importance", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            source=data.get("source", {}),
        )


@dataclass(frozen=True)
class TextOverlayPlan:
    version: str = "text_overlay_plan.v1"
    candidates: tuple[TextOverlayCandidate, ...] = ()
    source_summary: Mapping[str, FrozenJSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "source_summary", _freeze_mapping(self.source_summary))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "version": self.version,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "source_summary": thaw_json_value(self.source_summary),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextOverlayPlan":
        return cls(
            version=str(data.get("version", "text_overlay_plan.v1")),
            candidates=tuple(
                TextOverlayCandidate.from_dict(item)
                for item in data.get("candidates", ())
            ),
            source_summary=data.get("source_summary", {}),
        )
