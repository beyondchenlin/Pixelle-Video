from __future__ import annotations

import operator
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote, urlparse
from urllib.request import url2pathname

LayoutPreviewMediaKind = Literal["provided", "placeholder"]

_DIRECT_MEDIA_KEYS = (
    "layout_preview_media_path",
    "layout_preview_image_path",
    "preview_media_ref",
    "preview_media_path",
    "image_path",
    "media_path",
    "composed_image_path",
)
_TEMPLATE_MEDIA_KEYS = ("image", "media", "media_path", "image_path")
_ASSET_COLLECTION_KEYS = ("assets", "image_assets", "character_assets", "goods_assets")
_STRUCTURED_ASSET_PATH_KEYS = (
    "asset_path",
    "local_path",
    "media_path",
    "image_path",
    "path",
    "uri",
    "url",
)
_SAFE_DATA_IMAGE_MIME_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/webp",
}
_MAX_DATA_IMAGE_URI_LENGTH = 8 * 1024 * 1024
_MAX_REMOTE_MEDIA_URI_LENGTH = 8192
_MAX_PLACEHOLDER_EDGE = 4096


@dataclass(frozen=True)
class LayoutPreviewMediaSource:
    """A preview source plus the dimensions used when natural geometry is unavailable."""

    uri: str
    fallback_width: int
    fallback_height: int
    kind: LayoutPreviewMediaKind

    def __post_init__(self) -> None:
        normalized_uri = str(self.uri).strip()
        if not normalized_uri:
            raise ValueError("layout preview media URI must not be empty")
        object.__setattr__(self, "uri", normalized_uri)
        object.__setattr__(
            self,
            "fallback_width",
            _positive_dimension(self.fallback_width, field_name="fallback_width"),
        )
        object.__setattr__(
            self,
            "fallback_height",
            _positive_dimension(self.fallback_height, field_name="fallback_height"),
        )
        if self.kind not in {"provided", "placeholder"}:
            raise ValueError("layout preview media kind must be provided or placeholder")


def resolve_layout_preview_media_source(
    video_params: Mapping[str, Any],
    *,
    fallback_width: int,
    fallback_height: int,
) -> LayoutPreviewMediaSource:
    """Resolve real preview media or create an aspect-correct generated placeholder."""

    width = _positive_dimension(fallback_width, field_name="fallback_width")
    height = _positive_dimension(fallback_height, field_name="fallback_height")
    for candidate in _iter_layout_preview_media_candidates(video_params):
        uri = _safe_preview_media_uri(candidate)
        if uri is not None:
            return LayoutPreviewMediaSource(
                uri=uri,
                fallback_width=width,
                fallback_height=height,
                kind="provided",
            )

    return LayoutPreviewMediaSource(
        uri=build_layout_preview_placeholder_uri(width=width, height=height),
        fallback_width=width,
        fallback_height=height,
        kind="placeholder",
    )


@lru_cache(maxsize=32, typed=True)
def build_layout_preview_placeholder_uri(*, width: int, height: int) -> str:
    """Build a small deterministic SVG placeholder with the requested media aspect ratio."""

    source_width = _positive_dimension(width, field_name="width")
    source_height = _positive_dimension(height, field_name="height")
    width, height = _bounded_placeholder_dimensions(source_width, source_height)
    short_edge = min(width, height)
    inset = short_edge * 0.06
    stroke_width = max(0.01, short_edge * 0.006)
    corner_radius = short_edge * 0.025
    center_x = width / 2.0
    center_y = height / 2.0
    icon_width = min(width * 0.22, height * 0.32)
    icon_height = icon_width * 0.68
    icon_left = center_x - (icon_width / 2.0)
    icon_top = center_y - (icon_height / 2.0)
    mountain_y = icon_top + (icon_height * 0.72)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
      <rect width="{width}" height="{height}" fill="#f8f5ef"/>
      <rect x="{inset:.3f}" y="{inset:.3f}" width="{width - (2 * inset):.3f}" height="{height - (2 * inset):.3f}" rx="{corner_radius:.3f}" fill="none" stroke="#b9aa96" stroke-width="{stroke_width:.3f}" stroke-dasharray="{stroke_width * 4:.3f} {stroke_width * 3:.3f}" opacity=".55"/>
      <rect x="{icon_left:.3f}" y="{icon_top:.3f}" width="{icon_width:.3f}" height="{icon_height:.3f}" rx="{corner_radius:.3f}" fill="none" stroke="#8b785e" stroke-width="{stroke_width:.3f}" opacity=".55"/>
      <circle cx="{icon_left + (icon_width * 0.72):.3f}" cy="{icon_top + (icon_height * 0.28):.3f}" r="{icon_width * 0.055:.3f}" fill="#b98242" opacity=".45"/>
      <path d="M {icon_left + (icon_width * 0.12):.3f} {mountain_y:.3f} L {icon_left + (icon_width * 0.38):.3f} {icon_top + (icon_height * 0.43):.3f} L {icon_left + (icon_width * 0.55):.3f} {icon_top + (icon_height * 0.62):.3f} L {icon_left + (icon_width * 0.72):.3f} {icon_top + (icon_height * 0.48):.3f} L {icon_left + (icon_width * 0.88):.3f} {mountain_y:.3f}" fill="none" stroke="#8b785e" stroke-width="{stroke_width:.3f}" stroke-linecap="round" stroke-linejoin="round" opacity=".6"/>
    </svg>
    """.strip()
    return f"data:image/svg+xml;charset=utf-8,{quote(svg, safe='')}"


def _iter_layout_preview_media_candidates(
    video_params: Mapping[str, Any],
) -> Iterator[object]:
    for key in _DIRECT_MEDIA_KEYS:
        yield video_params.get(key)

    template_params = video_params.get("template_params")
    if isinstance(template_params, Mapping):
        for key in _TEMPLATE_MEDIA_KEYS:
            yield template_params.get(key)

    for key in _ASSET_COLLECTION_KEYS:
        collection = video_params.get(key)
        if not isinstance(collection, Sequence) or isinstance(collection, (str, bytes)):
            continue
        for item in collection:
            if isinstance(item, Mapping):
                for path_key in _STRUCTURED_ASSET_PATH_KEYS:
                    yield item.get(path_key)
            else:
                yield item


def _safe_preview_media_uri(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, str):
        return None
    source = str(value).strip()
    if not source:
        return None

    lowered = source.lower()
    if lowered.startswith(("http://", "https://")):
        if len(source) > _MAX_REMOTE_MEDIA_URI_LENGTH:
            return None
        parsed = urlparse(source)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            return source
        return None
    if lowered.startswith("data:"):
        return source if _is_safe_data_image_uri(source) else None
    if lowered.startswith("file:"):
        return _validated_file_uri(source)
    try:
        absolute_path = Path(source)
        if absolute_path.is_absolute():
            return absolute_path.resolve().as_uri() if absolute_path.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None
    if urlparse(source).scheme:
        return None

    try:
        path = Path(source)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve().as_uri() if path.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def _validated_file_uri(source: str) -> str | None:
    try:
        parsed = urlparse(source)
        if parsed.scheme.lower() != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        path_value = url2pathname(unquote(parsed.path))
        if os.name == "nt" and re.match(r"^/[a-zA-Z]:", path_value):
            path_value = path_value[1:]
        path = Path(path_value)
        return path.resolve().as_uri() if path.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None


def _is_safe_data_image_uri(source: str) -> bool:
    if len(source) > _MAX_DATA_IMAGE_URI_LENGTH:
        return False
    header, separator, _payload = source.partition(",")
    if not separator:
        return False
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    return mime_type in _SAFE_DATA_IMAGE_MIME_TYPES


def _positive_dimension(value: object, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        normalized = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if normalized <= 0:
        raise ValueError(f"{field_name} must be positive")
    return normalized


def _bounded_placeholder_dimensions(width: int, height: int) -> tuple[int, int]:
    longest_edge = max(width, height)
    if longest_edge <= _MAX_PLACEHOLDER_EDGE:
        return width, height
    if width >= height:
        bounded_height = max(
            1,
            (height * _MAX_PLACEHOLDER_EDGE + (width // 2)) // width,
        )
        return _MAX_PLACEHOLDER_EDGE, bounded_height
    bounded_width = max(
        1,
        (width * _MAX_PLACEHOLDER_EDGE + (height // 2)) // height,
    )
    return bounded_width, _MAX_PLACEHOLDER_EDGE


__all__ = [
    "LayoutPreviewMediaSource",
    "build_layout_preview_placeholder_uri",
    "resolve_layout_preview_media_source",
]
