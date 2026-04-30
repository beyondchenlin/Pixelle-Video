from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from pixelle_video.models.text_style import DEFAULT_TITLE_STYLE_ID


@dataclass(frozen=True)
class TemplateTextStylePreset:
    template_id: str
    has_title_region: bool
    title_style: Mapping[str, Any]
    title_region: Mapping[str, float]
    caption_safe_area: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "title_style",
            MappingProxyType(dict(self.title_style)),
        )
        object.__setattr__(
            self,
            "title_region",
            MappingProxyType(dict(self.title_region)),
        )
        object.__setattr__(
            self,
            "caption_safe_area",
            MappingProxyType(dict(self.caption_safe_area)),
        )

    def title_style_dict(self) -> dict[str, Any]:
        return dict(self.title_style)

    def title_region_dict(self) -> dict[str, float]:
        return dict(self.title_region)

    def caption_safe_area_dict(self) -> dict[str, float]:
        return dict(self.caption_safe_area)


GENERIC_TEMPLATE_TEXT_STYLE_PRESET = TemplateTextStylePreset(
    template_id="generic",
    has_title_region=False,
    title_style={
        "id": DEFAULT_TITLE_STYLE_ID,
        "name": "Title Default",
        "font_family": "Noto Sans CJK SC",
        "font_size": 72,
        "font_weight": 700,
        "primary_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 2,
        "background_color": None,
        "background_opacity": 0.0,
        "position": "top",
        "alignment": "center",
        "margin_x": 80,
        "margin_y": 96,
        "max_width_ratio": 0.84,
        "line_height": 1.16,
        "max_chars_per_line": 14,
        "punctuation_mode": "preserve",
    },
    title_region={"x": 0.08, "y": 0.04, "width": 0.84, "height": 0.16},
    caption_safe_area={"x": 0.08, "y": 0.76, "width": 0.84, "height": 0.16},
)


TEMPLATE_TEXT_STYLE_PRESETS: dict[str, TemplateTextStylePreset] = {
    "image_default": TemplateTextStylePreset(
        template_id="image_default",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 84,
            "font_weight": 800,
            "primary_color": "#2C3E50",
            "stroke_width": 0,
            "background_color": "#FFFFFF",
            "background_opacity": 0.92,
            "position": "top",
            "margin_y": 84,
            "max_chars_per_line": 10,
        },
        title_region={"x": 0.09, "y": 0.045, "width": 0.82, "height": 0.16},
        caption_safe_area={"x": 0.10, "y": 0.73, "width": 0.80, "height": 0.16},
    ),
    "image_life_insights_light": TemplateTextStylePreset(
        template_id="image_life_insights_light",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 78,
            "font_weight": 800,
            "primary_color": "#5B4631",
            "stroke_color": "#F8EDDC",
            "stroke_width": 1,
            "background_color": "#FFF6E8",
            "background_opacity": 0.82,
            "position": "top",
            "margin_y": 92,
            "max_chars_per_line": 11,
        },
        title_region={"x": 0.10, "y": 0.05, "width": 0.80, "height": 0.15},
        caption_safe_area={"x": 0.12, "y": 0.74, "width": 0.76, "height": 0.15},
    ),
    "image_landscape_full": TemplateTextStylePreset(
        template_id="image_landscape_full",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 80,
            "font_weight": 700,
            "font_family": "Ma Shan Zheng",
            "primary_color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 2,
            "background_color": "#000000",
            "background_opacity": 0.24,
            "position": "top",
            "margin_y": 84,
            "max_chars_per_line": 16,
        },
        title_region={"x": 0.06, "y": 0.075, "width": 0.88, "height": 0.18},
        caption_safe_area={"x": 0.16, "y": 0.68, "width": 0.68, "height": 0.18},
    ),
    "image_landscape_minimal": TemplateTextStylePreset(
        template_id="image_landscape_minimal",
        has_title_region=True,
        title_style={
            **GENERIC_TEMPLATE_TEXT_STYLE_PRESET.title_style,
            "font_size": 76,
            "font_weight": 900,
            "primary_color": "#171410",
            "stroke_width": 0,
            "background_color": "#FFFFFF",
            "background_opacity": 0.88,
            "position": "top_left",
            "alignment": "left",
            "margin_x": 110,
            "margin_y": 92,
            "max_width_ratio": 0.44,
            "max_chars_per_line": 12,
        },
        title_region={"x": 0.055, "y": 0.085, "width": 0.44, "height": 0.20},
        caption_safe_area={"x": 0.18, "y": 0.69, "width": 0.64, "height": 0.17},
    ),
}


def normalize_template_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace("\\", "/")
    if not cleaned:
        return None
    stem = Path(cleaned).stem if "/" in cleaned or "." in cleaned else cleaned
    return stem or None


def resolve_template_text_style_preset(
    template_id: str | None,
) -> TemplateTextStylePreset:
    normalized = normalize_template_id(template_id)
    if normalized and normalized in TEMPLATE_TEXT_STYLE_PRESETS:
        return TEMPLATE_TEXT_STYLE_PRESETS[normalized]
    return GENERIC_TEMPLATE_TEXT_STYLE_PRESET


def require_template_text_style_preset(
    template_id: str | None,
) -> TemplateTextStylePreset:
    normalized = normalize_template_id(template_id)
    if normalized and normalized in TEMPLATE_TEXT_STYLE_PRESETS:
        return TEMPLATE_TEXT_STYLE_PRESETS[normalized]
    raise ValueError(f"template {template_id!r} has no title preset")
