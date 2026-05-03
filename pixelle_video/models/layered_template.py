from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, Mapping

LayerType = Literal["text", "image", "background", "generated_media"]
LayerSourceKind = Literal["color", "asset", "generated_media", "gradient"]

VALID_LAYER_TYPES = ("text", "image", "background", "generated_media")
VALID_LAYER_SOURCE_KINDS = ("color", "asset", "generated_media", "gradient")
VALID_RECT_UNITS = ("px",)
LAYERED_TEMPLATE_VERSION = "layered_template.v1"


@dataclass(frozen=True)
class RectSpec:
    x: float
    y: float
    width: float
    height: float
    unit: Literal["px"] = "px"

    def __post_init__(self) -> None:
        x = _normalize_finite_number("x", self.x)
        y = _normalize_finite_number("y", self.y)
        width = _normalize_finite_number("width", self.width)
        height = _normalize_finite_number("height", self.height)
        if width <= 0 or height <= 0:
            raise ValueError("rect width and height must be positive")
        if self.unit not in VALID_RECT_UNITS:
            raise ValueError(f"rect unit must be one of {VALID_RECT_UNITS}")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RectSpec:
        return cls(
            x=payload["x"],
            y=payload["y"],
            width=payload["width"],
            height=payload["height"],
            unit=payload.get("unit", "px"),
        )


@dataclass(frozen=True)
class LayerSourceSpec:
    kind: LayerSourceKind
    ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in VALID_LAYER_SOURCE_KINDS:
            raise ValueError(f"layer source kind must be one of {VALID_LAYER_SOURCE_KINDS}")
        if not isinstance(self.ref, str) or not self.ref:
            raise ValueError("layer source ref must be a non-empty string")
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> LayerSourceSpec | None:
        if payload is None:
            return None
        return cls(
            kind=payload["kind"],
            ref=str(payload["ref"]),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class TemplateLayer:
    id: str
    type: LayerType
    name: str
    rect: RectSpec
    z_index: int
    opacity: float
    rotation: float
    locked: bool
    source: LayerSourceSpec | None
    style: Mapping[str, Any]
    role: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("layer id must be a non-empty string")
        if self.type not in VALID_LAYER_TYPES:
            raise ValueError(f"layer type must be one of {VALID_LAYER_TYPES}")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("layer name must be a non-empty string")
        rect = self.rect if isinstance(self.rect, RectSpec) else RectSpec.from_dict(self.rect)
        opacity = _normalize_finite_number("opacity", self.opacity)
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("opacity must be between 0 and 1")
        rotation = _normalize_finite_number("rotation", self.rotation)
        source = (
            self.source
            if self.source is None or isinstance(self.source, LayerSourceSpec)
            else LayerSourceSpec.from_dict(self.source)
        )
        object.__setattr__(self, "rect", rect)
        object.__setattr__(self, "z_index", int(self.z_index))
        object.__setattr__(self, "opacity", opacity)
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "locked", bool(self.locked))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "style", _deep_freeze_mapping(self.style))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "rect": self.rect.to_dict(),
            "z_index": self.z_index,
            "opacity": self.opacity,
            "rotation": self.rotation,
            "locked": self.locked,
            "source": self.source.to_dict() if self.source else None,
            "style": _json_safe_copy(self.style),
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TemplateLayer:
        return cls(
            id=str(payload["id"]),
            type=payload["type"],
            name=str(payload["name"]),
            rect=RectSpec.from_dict(payload["rect"]),
            z_index=int(payload["z_index"]),
            opacity=payload["opacity"],
            rotation=payload.get("rotation", 0.0),
            locked=bool(payload.get("locked", False)),
            source=LayerSourceSpec.from_dict(payload.get("source")),
            style=payload.get("style") or {},
            role=payload.get("role"),
        )


@dataclass(frozen=True)
class LayeredTemplateSpec:
    version: str
    template_id: str
    template_name: str
    template_type: str
    canvas_width: int
    canvas_height: int
    media_width: int
    media_height: int
    safe_area: RectSpec
    layers: tuple[TemplateLayer, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version != LAYERED_TEMPLATE_VERSION:
            raise ValueError(f"layered template version must be {LAYERED_TEMPLATE_VERSION}")
        if not self.template_id:
            raise ValueError("template_id must be non-empty")
        if not self.template_name:
            raise ValueError("template_name must be non-empty")
        if not self.template_type:
            raise ValueError("template_type must be non-empty")
        canvas_width = _normalize_positive_int("canvas_width", self.canvas_width)
        canvas_height = _normalize_positive_int("canvas_height", self.canvas_height)
        media_width = _normalize_positive_int("media_width", self.media_width)
        media_height = _normalize_positive_int("media_height", self.media_height)
        safe_area = (
            self.safe_area
            if isinstance(self.safe_area, RectSpec)
            else RectSpec.from_dict(self.safe_area)
        )
        layers = tuple(
            layer if isinstance(layer, TemplateLayer) else TemplateLayer.from_dict(layer)
            for layer in self.layers
        )
        object.__setattr__(self, "canvas_width", canvas_width)
        object.__setattr__(self, "canvas_height", canvas_height)
        object.__setattr__(self, "media_width", media_width)
        object.__setattr__(self, "media_height", media_height)
        object.__setattr__(self, "safe_area", safe_area)
        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "metadata", _deep_freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "template_type": self.template_type,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "media_width": self.media_width,
            "media_height": self.media_height,
            "safe_area": self.safe_area.to_dict(),
            "layers": [layer.to_dict() for layer in self.layers],
            "metadata": _json_safe_copy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LayeredTemplateSpec:
        return cls(
            version=str(data["version"]),
            template_id=str(data["template_id"]),
            template_name=str(data["template_name"]),
            template_type=str(data["template_type"]),
            canvas_width=data["canvas_width"],
            canvas_height=data["canvas_height"],
            media_width=data["media_width"],
            media_height=data["media_height"],
            safe_area=RectSpec.from_dict(data["safe_area"]),
            layers=tuple(
                TemplateLayer.from_dict(item) for item in data.get("layers", ())
            ),
            metadata=data.get("metadata") or {},
        )


def layered_template_fingerprint(spec: LayeredTemplateSpec | Mapping[str, Any]) -> str:
    payload = spec.to_dict() if isinstance(spec, LayeredTemplateSpec) else dict(spec)
    visual_payload = {key: value for key, value in payload.items() if key != "metadata"}
    encoded = json.dumps(
        visual_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def layered_template_has_layers(
    spec: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> bool:
    if spec is None:
        return False
    normalized = coerce_layered_template_spec(spec)
    return bool(normalized and normalized.get("layers"))


def coerce_layered_template_spec(
    spec: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if spec is None:
        return None
    if isinstance(spec, LayeredTemplateSpec):
        return spec.to_dict()
    return LayeredTemplateSpec.from_dict(spec).to_dict()


def active_layered_template_spec(
    spec: LayeredTemplateSpec | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not layered_template_has_layers(spec):
        return None
    return coerce_layered_template_spec(spec)


def _normalize_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _normalize_positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _deep_freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata/style must be a mapping")
    return MappingProxyType({str(key): _deep_freeze_json(item) for key, item in value.items()})


def _deep_freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _deep_freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze_json(item) for item in value)
    return value


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe_copy(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_copy(item) for item in value]
    return value

