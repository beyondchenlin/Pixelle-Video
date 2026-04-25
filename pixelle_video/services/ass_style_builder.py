from __future__ import annotations

import re
from dataclasses import dataclass

from pixelle_video.models.text_style import TextStyleProfile

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ASS_ALIGNMENT_BY_POSITION = {
    ("bottom", "center"): 2,
    ("lower_third", "center"): 2,
    ("top", "center"): 8,
    ("center", "center"): 5,
    ("top_left", "left"): 7,
    ("top_right", "right"): 9,
    ("bottom_left", "left"): 1,
    ("bottom_right", "right"): 3,
}


def ass_color(value: str, *, alpha: int = 0) -> str:
    """Convert #RRGGBB to ASS &HAABBGGRR color notation."""
    cleaned = str(value).strip()
    if not _HEX_COLOR_RE.match(cleaned):
        raise ValueError("ASS color value must be a #RRGGBB hex color")
    if type(alpha) is not int or not 0 <= alpha <= 255:
        raise ValueError("ASS color alpha must be between 0 and 255")

    red = cleaned[1:3]
    green = cleaned[3:5]
    blue = cleaned[5:7]
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


@dataclass(frozen=True)
class AssStyleBuilder:
    def build_style(
        self,
        name: str,
        profile: TextStyleProfile,
        canvas_width: int,
        canvas_height: int,
    ) -> str:
        if not isinstance(profile, TextStyleProfile):
            raise TypeError("profile must be a TextStyleProfile")
        _validate_ass_field(str(name), "style name")
        _validate_ass_field(profile.font_family, "font family")
        if canvas_width <= 0 or canvas_height <= 0:
            raise ValueError("canvas_width and canvas_height must be positive")

        scale = profile.scale_for_canvas(canvas_width, canvas_height)
        font_size = max(1, _scale_int(profile.font_size, scale))
        outline = _scale_int(profile.stroke_width, scale)
        shadow = _scale_int(profile.shadow_blur, scale) if profile.shadow_blur else 0
        margin_x = _scale_int(profile.margin_x, scale)
        margin_y = _scale_int(profile.margin_y, scale)
        background_alpha = int(round((1.0 - profile.background_opacity) * 255))

        fields = [
            f"Style: {name}",
            profile.font_family,
            str(font_size),
            ass_color(profile.primary_color),
            ass_color(profile.stroke_color),
            ass_color(profile.background_color or "#000000", alpha=background_alpha),
            "1" if profile.font_weight >= 600 else "0",
            "0",
            "1",
            str(outline),
            str(shadow),
            str(_ass_alignment(profile)),
            str(margin_x),
            str(margin_x),
            str(margin_y),
            "1",
        ]
        return ",".join(fields)


def _scale_int(value: int, scale: float) -> int:
    return int(round(value * scale))


def _validate_ass_field(value: str, field_name: str) -> None:
    if any(separator in value for separator in (",", "\r", "\n")):
        raise ValueError(f"ASS {field_name} cannot contain comma, CR, or LF")


def _ass_alignment(profile: TextStyleProfile) -> int:
    try:
        return _ASS_ALIGNMENT_BY_POSITION[(profile.position, profile.alignment)]
    except KeyError as exc:
        raise ValueError(
            "Unsupported ASS alignment for "
            f"position={profile.position!r}, alignment={profile.alignment!r}"
        ) from exc
