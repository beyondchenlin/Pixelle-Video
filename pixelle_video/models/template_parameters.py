from __future__ import annotations

from typing import Final

RESERVED_TEMPLATE_PARAM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "title",
        "text",
        "image",
        "index",
        "media_layout_mode",
        "pixelle_media_layer",
        "pixelle_media_display_width",
        "pixelle_media_display_height",
        "pixelle_media_left",
        "pixelle_media_top",
    }
)


def is_reserved_template_param(name: str) -> bool:
    return name in RESERVED_TEMPLATE_PARAM_NAMES
