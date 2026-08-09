"""
Helpers for loading preview media in the Streamlit UI.
"""

import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pixelle_video.config import config_manager
from pixelle_video.services.remote_media import (
    configured_workflow_output_origins,
    configured_workflow_output_roots,
    materialize_media_source,
)
from pixelle_video.utils.os_util import get_root_path, get_temp_path
from web.utils.async_helpers import run_async


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
    preview_root = Path(get_temp_path("preview_media"))
    preview_root.mkdir(parents=True, exist_ok=True)
    suffix = ".png" if media_type == "image" else ".mp4"
    config_holder = type(
        "PreviewConfig",
        (),
        {"config": config_manager.config.to_dict()},
    )()
    with tempfile.TemporaryDirectory(dir=preview_root) as temp_dir:
        target = Path(temp_dir) / f"preview{suffix}"
        materialized = run_async(
            materialize_media_source(
                preview_media_path,
                target,
                media_type=media_type,
                trusted_private_origins=configured_workflow_output_origins(config_holder),
                trusted_local_roots=(
                    Path(get_root_path()).resolve(),
                    *configured_workflow_output_roots(),
                ),
                request_timeout_seconds=timeout,
            )
        )
        content = materialized.read_bytes()

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
