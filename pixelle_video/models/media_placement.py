from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Any, Literal, Mapping

MediaPlacementBasis = Literal["canvas"]
MediaPlacementFit = Literal["contain", "cover", "stretch", "original_size"]
MediaPlacementAnchor = Literal[
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
]

VALID_MEDIA_PLACEMENT_BASIS = ("canvas",)
VALID_MEDIA_PLACEMENT_FIT = ("contain", "cover", "stretch", "original_size")
VALID_CANVAS_PROJECTION_FIT = ("contain",)
MAX_MEDIA_BOX_AREA_MULTIPLIER = 64
MAX_MEDIA_BOX_EDGE_MULTIPLIER = 64
VALID_MEDIA_PLACEMENT_ANCHORS = (
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
)


@dataclass(frozen=True)
class MediaPlacement:
    basis: MediaPlacementBasis = "canvas"
    fit: MediaPlacementFit = "contain"
    scale_percent: int = 100
    offset_x: int = 0
    offset_y: int = 0
    anchor: MediaPlacementAnchor | None = None

    def __post_init__(self) -> None:
        scale_percent = _normalize_scale_percent(self.scale_percent)
        offset_x = _normalize_offset("offset_x", self.offset_x)
        offset_y = _normalize_offset("offset_y", self.offset_y)

        if self.basis not in VALID_MEDIA_PLACEMENT_BASIS:
            raise ValueError(f"basis must be one of {VALID_MEDIA_PLACEMENT_BASIS}")
        if self.fit not in VALID_MEDIA_PLACEMENT_FIT:
            raise ValueError(f"fit must be one of {VALID_MEDIA_PLACEMENT_FIT}")
        if not 10 <= scale_percent <= 100:
            raise ValueError("scale_percent must be between 10 and 100")
        if self.anchor is not None and self.anchor not in VALID_MEDIA_PLACEMENT_ANCHORS:
            raise ValueError(f"anchor must be one of {VALID_MEDIA_PLACEMENT_ANCHORS}")
        object.__setattr__(self, "scale_percent", scale_percent)
        object.__setattr__(self, "offset_x", offset_x)
        object.__setattr__(self, "offset_y", offset_y)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MediaPlacement:
        fields = ("basis", "fit", "scale_percent", "offset_x", "offset_y", "anchor")
        return cls(**{field: value[field] for field in fields if field in value})

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "fit": self.fit,
            "scale_percent": self.scale_percent,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }


@dataclass(frozen=True)
class MediaBox:
    width: float
    height: float
    left: float
    top: float

    def __post_init__(self) -> None:
        dimensions = _validate_positive_dimensions(
            width=self.width,
            height=self.height,
        )
        left = _normalize_finite_number("left", self.left)
        top = _normalize_finite_number("top", self.top)
        object.__setattr__(self, "width", dimensions["width"])
        object.__setattr__(self, "height", dimensions["height"])
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "top", top)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MediaBox:
        return cls(
            width=value["width"],
            height=value["height"],
            left=value["left"],
            top=value["top"],
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "width": self.width,
            "height": self.height,
            "left": self.left,
            "top": self.top,
        }


def resolve_media_placement(value: MediaPlacement | Mapping[str, Any] | None) -> MediaPlacement:
    if value is None:
        return MediaPlacement()
    if isinstance(value, MediaPlacement):
        return value
    if isinstance(value, Mapping):
        return MediaPlacement.from_dict(value)
    raise TypeError("media placement must be a MediaPlacement, mapping, or None")


def calculate_media_box(
    *,
    canvas_width: float,
    canvas_height: float,
    media_source_width: float,
    media_source_height: float,
    placement: MediaPlacement | Mapping[str, Any] | None = None,
) -> MediaBox:
    resolved = resolve_media_placement(placement)
    dimensions = _validate_positive_dimensions(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        media_source_width=media_source_width,
        media_source_height=media_source_height,
    )
    canvas_width = dimensions["canvas_width"]
    canvas_height = dimensions["canvas_height"]
    media_source_width = dimensions["media_source_width"]
    media_source_height = dimensions["media_source_height"]

    if resolved.fit == "contain":
        fit_width = media_source_width * min(
            canvas_width / media_source_width,
            canvas_height / media_source_height,
        )
        fit_height = media_source_height * min(
            canvas_width / media_source_width,
            canvas_height / media_source_height,
        )
    elif resolved.fit == "cover":
        cover_scale = max(
            canvas_width / media_source_width,
            canvas_height / media_source_height,
        )
        fit_width = media_source_width * cover_scale
        fit_height = media_source_height * cover_scale
    elif resolved.fit == "stretch":
        fit_width = canvas_width
        fit_height = canvas_height
    else:
        fit_width = media_source_width
        fit_height = media_source_height
    placement_scale = resolved.scale_percent / 100
    width = fit_width * placement_scale
    height = fit_height * placement_scale
    if (
        width * height
        > canvas_width * canvas_height * MAX_MEDIA_BOX_AREA_MULTIPLIER
        or width > canvas_width * MAX_MEDIA_BOX_EDGE_MULTIPLIER
        or height > canvas_height * MAX_MEDIA_BOX_EDGE_MULTIPLIER
    ):
        raise ValueError(
            "resolved media box exceeds the renderer resource-safety limit"
        )
    if resolved.anchor is not None:
        left = _anchor_left(resolved.anchor, canvas_width, width)
        top = _anchor_top(resolved.anchor, canvas_height, height)
    else:
        left = ((canvas_width - width) / 2) + resolved.offset_x
        top = ((canvas_height - height) / 2) + resolved.offset_y

    return MediaBox(width=width, height=height, left=left, top=top)


def project_canvas_box_to_template(
    canvas_box: MediaBox,
    *,
    canvas_width: float,
    canvas_height: float,
    template_width: float,
    template_height: float,
    canvas_fit: Literal["contain"] = "contain",
) -> MediaBox:
    if canvas_fit not in VALID_CANVAS_PROJECTION_FIT:
        raise ValueError(
            f"canvas_fit must be one of {VALID_CANVAS_PROJECTION_FIT}; "
            "projection consumes an already-resolved canvas box"
        )
    dimensions = _validate_positive_dimensions(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        template_width=template_width,
        template_height=template_height,
    )
    canvas_width = dimensions["canvas_width"]
    canvas_height = dimensions["canvas_height"]
    template_width = dimensions["template_width"]
    template_height = dimensions["template_height"]
    if not _same_aspect_ratio(canvas_width, canvas_height, template_width, template_height):
        raise ValueError("template and canvas aspect ratio must match")

    scale = template_width / canvas_width
    return MediaBox(
        width=canvas_box.width * scale,
        height=canvas_box.height * scale,
        left=canvas_box.left * scale,
        top=canvas_box.top * scale,
    )


def _anchor_left(anchor: MediaPlacementAnchor, canvas_width: float, box_width: float) -> float:
    if anchor in ("top_left", "left", "bottom_left"):
        return 0
    if anchor in ("top_right", "right", "bottom_right"):
        return canvas_width - box_width
    return (canvas_width - box_width) / 2


def _anchor_top(anchor: MediaPlacementAnchor, canvas_height: float, box_height: float) -> float:
    if anchor in ("top_left", "top", "top_right"):
        return 0
    if anchor in ("bottom_left", "bottom", "bottom_right"):
        return canvas_height - box_height
    return (canvas_height - box_height) / 2


def _same_aspect_ratio(
    width_a: float,
    height_a: float,
    width_b: float,
    height_b: float,
) -> bool:
    return isclose(width_a * height_b, width_b * height_a, rel_tol=1e-9, abs_tol=1e-9)


def _normalize_scale_percent(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("scale_percent must be an integer between 10 and 100")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("scale_percent must be an integer between 10 and 100") from exc
    if not isfinite(numeric_value) or not numeric_value.is_integer():
        raise ValueError("scale_percent must be an integer between 10 and 100")
    scale_percent = int(numeric_value)
    if not 10 <= scale_percent <= 100:
        raise ValueError("scale_percent must be between 10 and 100")
    return scale_percent


def _normalize_offset(name: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not isfinite(numeric_value) or not numeric_value.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(numeric_value)


def _normalize_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(numeric_value):
        raise ValueError(f"{name} must be a finite number")
    return numeric_value


def _validate_positive_dimensions(**dimensions: float) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for name, value in dimensions.items():
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite positive number")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be a finite positive number") from exc
        if not isfinite(numeric_value) or numeric_value <= 0:
            raise ValueError(f"{name} must be a finite positive number")
        normalized[name] = numeric_value
    return normalized
