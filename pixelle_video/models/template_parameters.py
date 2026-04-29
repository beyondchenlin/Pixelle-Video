from __future__ import annotations

from typing import Final


RESERVED_TEMPLATE_PARAM_NAMES: Final[frozenset[str]] = frozenset(
    {
        "title",
        "text",
        "image",
        "index",
        "media_layout_mode",
    }
)


def is_reserved_template_param(name: str) -> bool:
    return name in RESERVED_TEMPLATE_PARAM_NAMES
