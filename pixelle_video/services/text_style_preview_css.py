from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal, Mapping

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_TEXT_POSITIONS = {
    "top",
    "center",
    "bottom",
    "lower_third",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
}
_TEXT_ALIGNMENTS = {"left", "center", "right"}
_UNSAFE_FONT_CHARS = ("\"", "'", "`", ";", "{", "}", "\\", "/", "*", ":", "(", ")")


@dataclass(frozen=True)
class TextPreviewRegion:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @classmethod
    def from_fraction(
        cls,
        region: Mapping[str, Any],
        *,
        canvas_width: int,
        canvas_height: int,
    ) -> "TextPreviewRegion":
        x = _region_fraction(region.get("x"), 0.0)
        y = _region_fraction(region.get("y"), 0.0)
        width = min(_region_fraction(region.get("width"), 1.0), max(0.0, 1.0 - x))
        height = min(_region_fraction(region.get("height"), 1.0), max(0.0, 1.0 - y))
        return cls(
            x=float(max(canvas_width, 1)) * x,
            y=float(max(canvas_height, 1)) * y,
            width=max(1.0, float(max(canvas_width, 1)) * width),
            height=max(1.0, float(max(canvas_height, 1)) * height),
        )


def render_text_style_preview_css(
    style: Mapping[str, Any] | None,
    *,
    canvas_width: int,
    canvas_height: int,
    region: TextPreviewRegion,
    units: Literal["px", "percent"],
    default_font_size: int,
    rotation_degrees: float = 0.0,
) -> str:
    """Render safe inline CSS for browser previews from the text style contract."""
    style = style or {}
    canvas_width = max(int(canvas_width), 1)
    canvas_height = max(int(canvas_height), 1)
    fields = _resolve_text_style_fields(style, default_font_size=default_font_size)
    layout = _layout_css(
        style,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        region=region,
        units=units,
        rotation_degrees=rotation_degrees,
    )
    declarations = [
        f"font-size:{fields['font_size']}px",
        f"color:{fields['primary_color']}",
        f"text-align:{fields['alignment']}",
        f"justify-content:{_justify_content(fields['alignment'])}",
        f"font-family:{fields['font_family']}",
        f"font-weight:{fields['font_weight']}",
        f"line-height:{fields['line_height']}",
        f"background:{fields['background']}",
        f"-webkit-text-stroke:{fields['stroke_width']}px {fields['stroke_color']}",
        *layout,
    ]
    return ";".join(declarations) + ";"


def text_preview_lines(text: Any, style: Mapping[str, Any] | None) -> list[str]:
    value = str(text or "")
    max_chars = _optional_positive_int((style or {}).get("max_chars_per_line"))
    if max_chars is None:
        return value.splitlines() or [value]

    lines: list[str] = []
    for source_line in value.splitlines() or [value]:
        if not source_line:
            lines.append("")
            continue
        lines.extend(
            source_line[index : index + max_chars]
            for index in range(0, len(source_line), max_chars)
        )
    return lines or [""]


def _resolve_text_style_fields(
    style: Mapping[str, Any],
    *,
    default_font_size: int,
) -> dict[str, Any]:
    primary_color = _safe_color(
        style.get("primary_color") or style.get("color"),
        "#FFFFFF",
    )
    background_color = _safe_color(style.get("background_color"), None)
    background_opacity = _safe_float(
        style.get("background_opacity"),
        0.0,
        minimum=0.0,
        maximum=1.0,
    )
    alignment = _safe_choice(
        style.get("alignment") or style.get("text_align"),
        "center",
        _TEXT_ALIGNMENTS,
    )
    return {
        "font_family": _safe_font_family(style.get("font_family")),
        "font_size": _safe_int(
            style.get("font_size"),
            default_font_size,
            minimum=8,
            maximum=240,
        ),
        "font_weight": _safe_int(
            style.get("font_weight"),
            500,
            minimum=100,
            maximum=1000,
        ),
        "primary_color": primary_color,
        "stroke_color": _safe_color(style.get("stroke_color"), "#000000"),
        "stroke_width": _safe_int(
            style.get("stroke_width"),
            0,
            minimum=0,
            maximum=16,
        ),
        "background": _rgba_background(background_color, background_opacity),
        "alignment": alignment,
        "line_height": _safe_float(
            style.get("line_height"),
            1.18,
            minimum=0.5,
            maximum=3.0,
        ),
    }


def _layout_css(
    style: Mapping[str, Any],
    *,
    canvas_width: int,
    canvas_height: int,
    region: TextPreviewRegion,
    units: Literal["px", "percent"],
    rotation_degrees: float,
) -> list[str]:
    position = _safe_choice(style.get("position"), "", _TEXT_POSITIONS)
    margin_x = _safe_float(style.get("margin_x"), 80.0, minimum=0.0, maximum=2000.0)
    margin_y = _safe_float(style.get("margin_y"), 140.0, minimum=0.0, maximum=2000.0)
    max_width_ratio = min(
        _safe_float(
            style.get("max_width_ratio"),
            region.width / float(canvas_width),
            minimum=0.05,
            maximum=1.0,
        ),
        max(region.width / float(canvas_width), 0.05),
    )

    layout = _resolve_layout_box(
        position=position,
        canvas_width=float(canvas_width),
        canvas_height=float(canvas_height),
        region=region,
        margin_x=margin_x,
        margin_y=margin_y,
        max_width_ratio=max_width_ratio,
    )
    transform = _compose_transform(layout["transform"], rotation_degrees)
    if units == "percent":
        left_bound = layout["left_bound"] / float(canvas_width) * 100.0
        right_bound = layout["right_bound"] / float(canvas_width) * 100.0
        return [
            f"left:{_position_percent(layout['left'], canvas_width)}",
            f"right:{_position_percent(layout['right'], canvas_width)}",
            f"top:{_position_percent(layout['top'], canvas_height)}",
            f"bottom:{_position_percent(layout['bottom'], canvas_height)}",
            f"transform:{transform}",
            f"width:{layout['width'] / float(canvas_width) * 100.0:.3f}%",
            (
                "max-width:"
                f"min({layout['width'] / float(canvas_width) * 100.0:.3f}%, "
                f"calc(100% - {left_bound:.3f}% - {right_bound:.3f}%))"
            ),
            f"height:{region.height / float(canvas_height) * 100.0:.3f}%",
        ]

    left_bound = _format_px(layout["left_bound"])
    right_bound = _format_px(layout["right_bound"])
    width = _format_px(layout["width"])
    return [
        f"left:{_position_px(layout['left'])}",
        f"right:{_position_px(layout['right'])}",
        f"top:{_position_px(layout['top'])}",
        f"bottom:{_position_px(layout['bottom'])}",
        f"transform:{transform}",
        f"width:{width}",
        f"max-width:min({width}, calc(100% - {left_bound} - {right_bound}))",
        f"height:{_format_px(region.height)}",
    ]


def _resolve_layout_box(
    *,
    position: str,
    canvas_width: float,
    canvas_height: float,
    region: TextPreviewRegion,
    margin_x: float,
    margin_y: float,
    max_width_ratio: float,
) -> dict[str, float | None | str]:
    left: float | None = region.x
    right: float | None = None
    top: float | None = region.y
    bottom: float | None = None
    transform = "none"
    left_gap = max(0.0, region.x)
    right_gap = max(0.0, canvas_width - region.right)
    top_gap = max(0.0, region.y)
    bottom_gap = max(0.0, canvas_height - region.bottom)
    center_x = region.x + region.width / 2.0
    center_y = region.y + region.height / 2.0
    left_bound = left_gap
    right_bound = right_gap
    available_width = max(1.0, canvas_width - left_bound - right_bound)

    if position == "center":
        left = center_x
        top = center_y
        transform = "translate(-50%, -50%)"
        left_bound = left_gap
        right_bound = right_gap
        available_width = region.width
    elif position in {"bottom", "lower_third"}:
        left = center_x
        top = None
        bottom = max(bottom_gap, margin_y)
        transform = "translateX(-50%)"
        left_bound = left_gap
        right_bound = right_gap
        available_width = region.width
    elif position == "top":
        left = center_x
        top = max(top_gap, margin_y)
        transform = "translateX(-50%)"
        left_bound = left_gap
        right_bound = right_gap
        available_width = region.width
    elif position == "top_left":
        left = max(left_gap, margin_x)
        top = max(top_gap, margin_y)
        left_bound = left
        available_width = max(1.0, region.right - left)
    elif position == "top_right":
        left = None
        right = max(right_gap, margin_x)
        top = max(top_gap, margin_y)
        right_bound = right
        available_width = max(1.0, canvas_width - right - region.x)
    elif position == "bottom_left":
        left = max(left_gap, margin_x)
        top = None
        bottom = max(bottom_gap, margin_y)
        left_bound = left
        available_width = max(1.0, region.right - left)
    elif position == "bottom_right":
        left = None
        right = max(right_gap, margin_x)
        top = None
        bottom = max(bottom_gap, margin_y)
        right_bound = right
        available_width = max(1.0, canvas_width - right - region.x)

    width = min(region.width, canvas_width * max_width_ratio, available_width)
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "transform": transform,
        "left_bound": left_bound,
        "right_bound": right_bound,
        "width": max(1.0, width),
    }


def _safe_color(value: Any, default: str | None) -> str | None:
    cleaned = str(value or "").strip()
    if _HEX_COLOR_RE.fullmatch(cleaned):
        if len(cleaned) == 4:
            return "#" + "".join(char * 2 for char in cleaned[1:]).upper()
        return cleaned.upper()
    return default


def _safe_font_family(value: Any) -> str:
    raw_value = str(value or "").replace("\r", " ").replace("\n", " ")
    if not raw_value.strip() or any(char in raw_value for char in _UNSAFE_FONT_CHARS):
        return "sans-serif"

    cleaned_chars = []
    for char in raw_value:
        if char.isalnum() or char.isspace() or char in {"-", "_", ",", "."}:
            cleaned_chars.append(char)
    cleaned = " ".join("".join(cleaned_chars).split())
    families = [family.strip() for family in cleaned.split(",") if family.strip()]
    return ", ".join(families) or "sans-serif"


def _rgba_background(color: str | None, opacity: float) -> str:
    if not color or opacity <= 0:
        return "transparent"
    normalized = color[:7]
    red = int(normalized[1:3], 16)
    green = int(normalized[3:5], 16)
    blue = int(normalized[5:7], 16)
    return f"rgba({red}, {green}, {blue}, {opacity:g})"


def _safe_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        float_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not isfinite(float_value):
        return default
    parsed = int(float_value)
    return min(max(parsed, minimum), maximum)


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _safe_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not isfinite(parsed):
        return default
    return min(max(parsed, minimum), maximum)


def _safe_choice(value: Any, default: str, allowed: set[str]) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned in allowed else default


def _region_fraction(value: Any, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        numeric = default
    if not isfinite(numeric):
        numeric = default
    return min(max(numeric, 0.0), 1.0)


def _justify_content(alignment: str) -> str:
    return {"left": "flex-start", "right": "flex-end"}.get(alignment, "center")


def _compose_transform(transform: str, rotation_degrees: float) -> str:
    rotation = _safe_float(rotation_degrees, 0.0, minimum=-3600.0, maximum=3600.0)
    if rotation == 0.0:
        return transform
    rotate = f"rotate({_format_number(rotation)}deg)"
    return rotate if transform == "none" else f"{transform} {rotate}"


def _position_percent(value: float | None | str, basis: int) -> str:
    if value is None:
        return "auto"
    return f"{float(value) / float(max(basis, 1)) * 100.0:.3f}%"


def _position_px(value: float | None | str) -> str:
    if value is None:
        return "auto"
    return _format_px(float(value))


def _format_px(value: float) -> str:
    rounded = round(float(value))
    return f"{rounded}px"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")
