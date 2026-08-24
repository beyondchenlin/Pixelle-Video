from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

IMAGE_STYLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
IMAGE_STYLE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ImageStyleSelection:
    """Immutable identity of one selected image-style definition."""

    style_id: str
    revision: str


def normalize_image_style_id(style_id: Any, *, allow_none: bool = False) -> str | None:
    if style_id is None and allow_none:
        return None
    if not isinstance(style_id, str):
        raise TypeError("image style id must be a string")
    if style_id != style_id.strip() or IMAGE_STYLE_ID_PATTERN.fullmatch(style_id) is None:
        raise ValueError(
            "image style id must start with a letter or number and contain only "
            "letters, numbers, underscores, and hyphens"
        )
    return style_id


def image_style_revision(content: Any) -> str:
    if not isinstance(content, str):
        raise TypeError("image style content must be a string")
    normalized_content = content.strip()
    if not normalized_content:
        raise ValueError("image style content must not be empty")
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def normalize_image_style_revision(
    revision: Any,
    *,
    allow_none: bool = False,
) -> str | None:
    if revision is None and allow_none:
        return None
    if not isinstance(revision, str):
        raise TypeError("image style revision must be a string")
    if (
        revision != revision.strip()
        or IMAGE_STYLE_REVISION_PATTERN.fullmatch(revision) is None
    ):
        raise ValueError("image style revision must be a lowercase SHA-256 digest")
    return revision


def normalize_image_style_selection(
    image_style_id: Any,
    image_style_revision: Any,
    *,
    prompt_prefix: Any = None,
) -> ImageStyleSelection | None:
    """Validate the complete request contract for a versioned style selection."""

    if prompt_prefix is not None and not isinstance(prompt_prefix, str):
        raise TypeError("prompt_prefix must be a string")
    normalized_prompt_prefix = (prompt_prefix or "").strip()
    normalized_id = normalize_image_style_id(image_style_id, allow_none=True)
    normalized_revision = normalize_image_style_revision(
        image_style_revision,
        allow_none=True,
    )
    if normalized_prompt_prefix and normalized_id is not None:
        raise ValueError("prompt_prefix and image_style_id are mutually exclusive")
    if (normalized_id is None) != (normalized_revision is None):
        raise ValueError(
            "image_style_id and image_style_revision must be provided together"
        )
    if normalized_id is None or normalized_revision is None:
        return None
    return ImageStyleSelection(
        style_id=normalized_id,
        revision=normalized_revision,
    )


__all__ = [
    "IMAGE_STYLE_ID_PATTERN",
    "IMAGE_STYLE_REVISION_PATTERN",
    "ImageStyleSelection",
    "image_style_revision",
    "normalize_image_style_id",
    "normalize_image_style_revision",
    "normalize_image_style_selection",
]
