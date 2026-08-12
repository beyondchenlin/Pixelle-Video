from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import ffmpeg
from PIL import Image, UnidentifiedImageError

from pixelle_video.models.media_placement import (
    MediaBox,
    MediaPlacement,
    calculate_media_box,
)


class MediaGeometryResolver:
    """Resolve source dimensions once and derive the canonical canvas rectangle."""

    def resolve_box(
        self,
        *,
        media_path: str,
        media_type: str,
        canvas_width: int,
        canvas_height: int,
        fallback_width: int | None,
        fallback_height: int | None,
        placement: MediaPlacement,
        base_dir: Path | None = None,
    ) -> MediaBox:
        source_width, source_height = self.resolve_source_size(
            media_path=media_path,
            media_type=media_type,
            fallback_width=fallback_width or canvas_width,
            fallback_height=fallback_height or canvas_height,
            base_dir=base_dir,
        )
        return calculate_media_box(
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            media_source_width=source_width,
            media_source_height=source_height,
            placement=placement,
        )

    def resolve_source_size(
        self,
        *,
        media_path: str,
        media_type: str,
        fallback_width: int,
        fallback_height: int,
        base_dir: Path | None = None,
    ) -> tuple[int, int]:
        local_path = self.local_path(media_path, base_dir=base_dir)
        if local_path is not None and local_path.is_file():
            if str(media_type).strip().lower() == "video":
                size = self._probe_video_size(local_path)
            else:
                size = self._probe_image_size(local_path)
            if size is not None:
                return size
        return max(1, int(fallback_width)), max(1, int(fallback_height))

    @staticmethod
    def local_path(media_path: str, *, base_dir: Path | None = None) -> Path | None:
        if not media_path:
            return None
        if media_path.startswith("file://"):
            parsed = urlparse(media_path)
            path = unquote(parsed.path)
            if os.name == "nt" and path.startswith("/") and re.match(r"^/[a-zA-Z]:", path):
                path = path[1:]
            return Path(path).resolve()
        if media_path.startswith(("http://", "https://", "data:")):
            return None
        path = Path(media_path)
        if not path.is_absolute():
            path = (base_dir or Path.cwd()) / path
        return path.resolve()

    @staticmethod
    def _probe_image_size(path: Path) -> tuple[int, int] | None:
        try:
            with Image.open(path) as image:
                return int(image.width), int(image.height)
        except (OSError, UnidentifiedImageError):
            return None

    @staticmethod
    def _probe_video_size(path: Path) -> tuple[int, int] | None:
        try:
            payload = ffmpeg.probe(str(path), select_streams="v:0")
        except (ffmpeg.Error, OSError):
            return None
        stream = next(
            (
                item
                for item in payload.get("streams", [])
                if item.get("codec_type") == "video"
            ),
            None,
        )
        if stream is None:
            return None
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        return (width, height) if width > 0 and height > 0 else None


__all__ = ["MediaGeometryResolver"]
