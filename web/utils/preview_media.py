"""
Helpers for loading preview media in the Streamlit UI.
"""

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx


@dataclass(frozen=True)
class PreviewMediaData:
    """Normalized preview payload for Streamlit media components."""

    data: bytes
    format: str | None = None


def load_preview_media(
    preview_media_path: str,
    media_type: Literal["image", "video"],
    timeout: float = 10.0,
) -> PreviewMediaData:
    """
    Load preview media bytes from either a local file path or an HTTP(S) URL.
    """
    if preview_media_path.startswith(("http://", "https://")):
        response = httpx.get(preview_media_path, follow_redirects=True, timeout=timeout)
        response.raise_for_status()
        content = response.content
    else:
        content = Path(preview_media_path).read_bytes()

    return PreviewMediaData(
        data=content,
        format=_guess_media_format(preview_media_path, media_type),
    )


def _guess_media_format(
    preview_media_path: str,
    media_type: Literal["image", "video"],
) -> str | None:
    """Infer MIME type from local paths or ComfyUI-style URLs with filename query params."""
    candidates = []

    if preview_media_path.startswith(("http://", "https://")):
        parsed = urlparse(preview_media_path)
        query = parse_qs(parsed.query)
        filename = query.get("filename", [None])[0]
        if filename:
            candidates.append(filename)
        if parsed.path:
            candidates.append(parsed.path)
    else:
        candidates.append(preview_media_path)

    for candidate in candidates:
        mime_type, _ = mimetypes.guess_type(candidate)
        if mime_type:
            if media_type == "image":
                return None
            return mime_type

    if media_type == "video":
        return "video/mp4"

    return None
