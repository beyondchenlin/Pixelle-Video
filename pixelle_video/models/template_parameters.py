from __future__ import annotations

from typing import Any, Final, Mapping

from pixelle_video.models.template_display import TEMPLATE_DISPLAY_CONTROL_PARAM_NAMES

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
    | set(TEMPLATE_DISPLAY_CONTROL_PARAM_NAMES)
)


def is_reserved_template_param(name: str) -> bool:
    return name in RESERVED_TEMPLATE_PARAM_NAMES


def validate_template_params(
    template_params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    params = dict(template_params or {})
    reserved = sorted(
        str(key) for key in params if key in RESERVED_TEMPLATE_PARAM_NAMES
    )
    if reserved:
        joined = ", ".join(reserved)
        raise ValueError(f"reserved template parameter(s) are not allowed: {joined}")
    return params
