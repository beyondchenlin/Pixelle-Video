from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Any, Literal, Mapping

MediaPlacementBasis = Literal["canvas"]
MediaPlacementFit = Literal["contain"]
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
VALID_MEDIA_PLACEMENT_FIT = ("contain",)
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
    scale_percent: int = 80
    anchor: MediaPlacementAnchor = "center"

    def __post_init__(self) -> None:
        scale_percent = _normalize_scale_percent(self.scale_percent)

        if self.basis not in VALID_MEDIA_PLACEMENT_BASIS:
            raise ValueError(f"basis must be one of {VALID_MEDIA_PLACEMENT_BASIS}")
        if self.fit not in VALID_MEDIA_PLACEMENT_FIT:
            raise ValueError(f"fit must be one of {VALID_MEDIA_PLACEMENT_FIT}")
        if not 10 <= scale_percent <= 100:
            raise ValueError("scale_percent must be between 10 and 100")
        if self.anchor not in VALID_MEDIA_PLACEMENT_ANCHORS:
            raise ValueError(f"anchor must be one of {VALID_MEDIA_PLACEMENT_ANCHORS}")
        object.__setattr__(self, "scale_percent", scale_percent)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MediaPlacement:
        fields = ("basis", "fit", "scale_percent", "anchor")
        return cls(**{field: value[field] for field in fields if field in value})

    def to_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "fit": self.fit,
            "scale_percent": self.scale_percent,
            "anchor": self.anchor,
        }


@dataclass(frozen=True)
class MediaBox:
    width: float
    height: float
    left: float
    top: float


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

    contain_scale = min(
        canvas_width / media_source_width,
        canvas_height / media_source_height,
    )
    placement_scale = resolved.scale_percent / 100
    width = media_source_width * contain_scale * placement_scale
    height = media_source_height * contain_scale * placement_scale
    left = _anchor_left(resolved.anchor, canvas_width, width)
    top = _anchor_top(resolved.anchor, canvas_height, height)

    return MediaBox(width=width, height=height, left=left, top=top)


def project_canvas_box_to_template(
    canvas_box: MediaBox,
    *,
    canvas_width: float,
    canvas_height: float,
    template_width: float,
    template_height: float,
    canvas_fit: MediaPlacementFit = "contain",
) -> MediaBox:
    if canvas_fit not in VALID_MEDIA_PLACEMENT_FIT:
        raise ValueError(f"canvas_fit must be one of {VALID_MEDIA_PLACEMENT_FIT}")
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
