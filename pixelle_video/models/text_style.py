from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

DEFAULT_CAPTION_STYLE_ID = "caption-default"
DEFAULT_OVERLAY_STYLE_ID = "overlay-default"
DEFAULT_CAPTION_FONT_SIZE = 42
DEFAULT_CAPTION_FONT_WEIGHT = 500
DEFAULT_CAPTION_PRIMARY_COLOR = "#2C3E50"
DEFAULT_CAPTION_STROKE_WIDTH = 0
DEFAULT_OVERLAY_FONT_SIZE = 76
DEFAULT_OVERLAY_PRIMARY_COLOR = "#FFFFFF"
DEFAULT_OVERLAY_STROKE_WIDTH = 2

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_POSITIONS = {
    "top",
    "center",
    "bottom",
    "lower_third",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
}
_ALIGNMENTS = {"left", "center", "right"}
_PUNCTUATION_MODES = {"strip_all", "strip_terminal", "preserve"}


def normalize_hex_color(
    value: str | None, field_name: str = "color"
) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not _HEX_COLOR_RE.match(cleaned):
        raise ValueError(f"{field_name} must be a #RRGGBB hex color")
    return cleaned.upper()


@dataclass(frozen=True)
class TextStyleProfile:
    id: str
    name: str
    version: str = "text_style_profile.v1"
    font_family: str = "Noto Sans CJK SC"
    font_file: str | None = None
    font_size: int = DEFAULT_CAPTION_FONT_SIZE
    font_weight: int = DEFAULT_CAPTION_FONT_WEIGHT
    primary_color: str = DEFAULT_CAPTION_PRIMARY_COLOR
    background_color: str | None = None
    background_opacity: float = 0.0
    stroke_color: str = "#000000"
    stroke_width: int = DEFAULT_CAPTION_STROKE_WIDTH
    shadow_color: str | None = None
    shadow_blur: int = 0
    position: str = "bottom"
    alignment: str = "center"
    margin_x: int = 80
    margin_y: int = 140
    max_width_ratio: float = 0.86
    line_height: float = 1.18
    max_chars_per_line: int | None = None
    punctuation_mode: str = "strip_all"
    scale_basis_width: int = 1080
    scale_basis_height: int = 1920

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ValueError("TextStyleProfile id cannot be empty")
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if self.stroke_width < 0:
            raise ValueError("stroke_width must be non-negative")
        if self.shadow_blur < 0:
            raise ValueError("shadow_blur must be non-negative")
        if self.margin_x < 0 or self.margin_y < 0:
            raise ValueError("margins must be non-negative")
        if not 0.0 <= float(self.background_opacity) <= 1.0:
            raise ValueError("background_opacity must be between 0 and 1")
        if self.position not in _POSITIONS:
            raise ValueError(f"Unsupported text position: {self.position}")
        if self.alignment not in _ALIGNMENTS:
            raise ValueError(f"Unsupported text alignment: {self.alignment}")
        if self.punctuation_mode not in _PUNCTUATION_MODES:
            raise ValueError(f"Unsupported punctuation_mode: {self.punctuation_mode}")
        if self.scale_basis_width <= 0 or self.scale_basis_height <= 0:
            raise ValueError("scale basis dimensions must be positive")

        object.__setattr__(
            self,
            "primary_color",
            normalize_hex_color(self.primary_color, "primary_color"),
        )
        object.__setattr__(
            self,
            "background_color",
            normalize_hex_color(self.background_color, "background_color"),
        )
        object.__setattr__(
            self,
            "stroke_color",
            normalize_hex_color(self.stroke_color, "stroke_color"),
        )
        object.__setattr__(
            self,
            "shadow_color",
            normalize_hex_color(self.shadow_color, "shadow_color"),
        )

    def scale_for_canvas(self, width: int, height: int) -> float:
        safe_width = max(1, int(width))
        safe_height = max(1, int(height))
        return min(
            safe_width / self.scale_basis_width,
            safe_height / self.scale_basis_height,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "font_family": self.font_family,
            "font_file": self.font_file,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "primary_color": self.primary_color,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "stroke_color": self.stroke_color,
            "stroke_width": self.stroke_width,
            "shadow_color": self.shadow_color,
            "shadow_blur": self.shadow_blur,
            "position": self.position,
            "alignment": self.alignment,
            "margin_x": self.margin_x,
            "margin_y": self.margin_y,
            "max_width_ratio": self.max_width_ratio,
            "line_height": self.line_height,
            "max_chars_per_line": self.max_chars_per_line,
            "punctuation_mode": self.punctuation_mode,
            "scale_basis_width": self.scale_basis_width,
            "scale_basis_height": self.scale_basis_height,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TextStyleProfile":
        return cls(
            version=str(data.get("version", "text_style_profile.v1")),
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            font_family=str(data.get("font_family", "Noto Sans CJK SC")),
            font_file=data.get("font_file"),
            font_size=int(data.get("font_size", DEFAULT_CAPTION_FONT_SIZE)),
            font_weight=int(data.get("font_weight", DEFAULT_CAPTION_FONT_WEIGHT)),
            primary_color=str(
                data.get("primary_color", DEFAULT_CAPTION_PRIMARY_COLOR)
            ),
            background_color=data.get("background_color"),
            background_opacity=float(data.get("background_opacity", 0.0)),
            stroke_color=str(data.get("stroke_color", "#000000")),
            stroke_width=int(data.get("stroke_width", DEFAULT_CAPTION_STROKE_WIDTH)),
            shadow_color=data.get("shadow_color"),
            shadow_blur=int(data.get("shadow_blur", 0)),
            position=str(data.get("position", "bottom")),
            alignment=str(data.get("alignment", "center")),
            margin_x=int(data.get("margin_x", 80)),
            margin_y=int(data.get("margin_y", 140)),
            max_width_ratio=float(data.get("max_width_ratio", 0.86)),
            line_height=float(data.get("line_height", 1.18)),
            max_chars_per_line=(
                int(data["max_chars_per_line"])
                if data.get("max_chars_per_line") is not None
                else None
            ),
            punctuation_mode=str(data.get("punctuation_mode", "strip_all")),
            scale_basis_width=int(data.get("scale_basis_width", 1080)),
            scale_basis_height=int(data.get("scale_basis_height", 1920)),
        )


def build_default_text_style_profiles() -> list[TextStyleProfile]:
    return [
        TextStyleProfile(id=DEFAULT_CAPTION_STYLE_ID, name="Caption Default"),
        TextStyleProfile(
            id=DEFAULT_OVERLAY_STYLE_ID,
            name="Overlay Default",
            font_size=DEFAULT_OVERLAY_FONT_SIZE,
            font_weight=700,
            primary_color=DEFAULT_OVERLAY_PRIMARY_COLOR,
            stroke_width=DEFAULT_OVERLAY_STROKE_WIDTH,
            position="center",
            margin_y=80,
        ),
    ]
