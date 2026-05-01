from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping

from pixelle_video.models.text_overlay import thaw_json_value
from pixelle_video.services.text_content_sanitizer import TextContentSanitizer

_CAPTION_SAFE_AREA_SLOTS = {"bottom", "lower_third"}
_TEXT_SAFE_AREA_SLOTS = {"center", "top", "top_left", "top_right", "bottom_left", "bottom_right"}


@dataclass(frozen=True)
class TextLayoutIntent:
    wrapped_lines: tuple[str, ...]
    safe_area: str
    slot: str
    layer: str
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wrapped_lines": list(self.wrapped_lines),
            "safe_area": self.safe_area,
            "slot": self.slot,
            "layer": self.layer,
            "diagnostics": thaw_json_value(self.diagnostics),
        }


class TextLayoutPlanner:
    def __init__(self, sanitizer: TextContentSanitizer | None = None) -> None:
        self.sanitizer = sanitizer or TextContentSanitizer()

    def plan_text(
        self,
        text: object,
        *,
        max_display_width: int = 24,
        slot: str = "bottom",
        layer: str = "caption",
    ) -> TextLayoutIntent:
        sanitized = self.sanitizer.sanitize(text)
        display_text = sanitized.display_text
        width_limit = max(1, int(max_display_width))
        wrapped_lines = _wrap_by_display_width(display_text, width_limit)
        line_widths = tuple(display_width(line) for line in wrapped_lines)

        return TextLayoutIntent(
            wrapped_lines=wrapped_lines,
            safe_area=_safe_area_for_slot(slot),
            slot=str(slot),
            layer=str(layer),
            diagnostics={
                "raw_display_width": display_width(display_text),
                "line_display_widths": line_widths,
                "max_display_width": width_limit,
                "sanitized_removed_token_count": len(sanitized.removed_tokens),
                "requires_html_escape": sanitized.requires_html_escape,
                "requires_ass_escape": sanitized.requires_ass_escape,
            },
        )


def display_width(text: str) -> int:
    return sum(_cluster_display_width(cluster) for cluster in _grapheme_clusters(text))


def _wrap_by_display_width(text: str, max_display_width: int) -> tuple[str, ...]:
    lines: list[str] = []
    current: list[str] = []
    current_width = 0

    for cluster in _grapheme_clusters(text):
        cluster_width = _cluster_display_width(cluster)
        if current and current_width + cluster_width > max_display_width:
            lines.append("".join(current).rstrip())
            current = []
            current_width = 0
        current.append(cluster)
        current_width += cluster_width

    if current or not lines:
        lines.append("".join(current).rstrip())
    return tuple(lines)


def _character_display_width(char: str) -> int:
    return 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1


def _cluster_display_width(cluster: str) -> int:
    width = sum(
        _character_display_width(char)
        for char in cluster
        if not _is_combining_mark(char)
    )
    return max(width, 1)


def _grapheme_clusters(text: str) -> tuple[str, ...]:
    clusters: list[str] = []
    current = ""
    for char in text:
        if current and _is_combining_mark(char):
            current += char
            continue
        if current:
            clusters.append(current)
        current = char
    if current:
        clusters.append(current)
    return tuple(clusters)


def _is_combining_mark(char: str) -> bool:
    return unicodedata.combining(char) != 0 or unicodedata.category(char) in {
        "Mn",
        "Mc",
        "Me",
    }


def _safe_area_for_slot(slot: str) -> str:
    normalized = str(slot).strip().lower()
    if normalized in _CAPTION_SAFE_AREA_SLOTS:
        return "caption_safe_area"
    if normalized in _TEXT_SAFE_AREA_SLOTS:
        return "text_safe_area"
    return "text_safe_area"
