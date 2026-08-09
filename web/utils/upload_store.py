from __future__ import annotations

import os
import tempfile
import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Literal

from PIL import Image, UnidentifiedImageError

from pixelle_video.utils.path_safety import resolve_path_within

IMAGE_UPLOAD_EXTENSIONS = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})
VIDEO_UPLOAD_EXTENSIONS = frozenset({".avi", ".mkv", ".mov", ".mp4", ".webm"})


@dataclass(frozen=True)
class UploadPolicy:
    media_type: Literal["image", "video", "mixed"]
    allowed_extensions: frozenset[str]
    max_bytes: int
    max_image_pixels: int = 100_000_000

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("upload max_bytes must be positive")
        if not self.allowed_extensions:
            raise ValueError("upload policy must allow at least one extension")


IMAGE_UPLOAD_POLICY = UploadPolicy(
    media_type="image",
    allowed_extensions=IMAGE_UPLOAD_EXTENSIONS,
    max_bytes=25 * 1024 * 1024,
)
VIDEO_UPLOAD_POLICY = UploadPolicy(
    media_type="video",
    allowed_extensions=VIDEO_UPLOAD_EXTENSIONS,
    max_bytes=512 * 1024 * 1024,
)
MIXED_MEDIA_UPLOAD_POLICY = UploadPolicy(
    media_type="mixed",
    allowed_extensions=IMAGE_UPLOAD_EXTENSIONS | VIDEO_UPLOAD_EXTENSIONS,
    max_bytes=512 * 1024 * 1024,
)


def store_uploaded_files(
    uploaded_files: Iterable[Any],
    destination_dir: str | Path,
    *,
    policy: UploadPolicy,
) -> list[str]:
    """Validate uploaded media and atomically store it under one task-local directory."""

    resolved_dir = Path(destination_dir).resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    stored_paths: list[str] = []
    for uploaded_file in uploaded_files:
        stored_paths.append(str(_store_uploaded_file(uploaded_file, resolved_dir, policy=policy)))
    return stored_paths


def _store_uploaded_file(
    uploaded_file: Any,
    destination_dir: Path,
    *,
    policy: UploadPolicy,
) -> Path:
    original_name = str(getattr(uploaded_file, "name", "") or "")
    if (
        not original_name
        or original_name in {".", ".."}
        or "/" in original_name
        or "\\" in original_name
        or Path(original_name).name != original_name
    ):
        raise ValueError("uploaded filename must be a plain basename")

    extension = Path(original_name).suffix.lower()
    if extension not in policy.allowed_extensions:
        raise ValueError("uploaded file extension is not allowed")

    buffer = uploaded_file.getbuffer()
    byte_view = memoryview(buffer)
    byte_size = byte_view.nbytes
    if byte_size < 1:
        raise ValueError("uploaded file must not be empty")
    effective_limit = _effective_byte_limit(extension, policy)
    if byte_size > effective_limit:
        raise ValueError("uploaded file exceeds the configured size limit")

    if extension in IMAGE_UPLOAD_EXTENSIONS:
        _validate_image(byte_view, extension=extension, max_pixels=policy.max_image_pixels)
    else:
        _validate_video_signature(byte_view, extension=extension)

    content_digest = sha256(byte_view).hexdigest()
    final_path = resolve_path_within(destination_dir, f"upload_{content_digest}{extension}")
    if final_path.is_file() and final_path.stat().st_size == byte_size:
        return final_path
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".upload_",
            suffix=".tmp",
            dir=destination_dir,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(byte_view)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(final_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return final_path


def _effective_byte_limit(extension: str, policy: UploadPolicy) -> int:
    if policy.media_type == "mixed" and extension in IMAGE_UPLOAD_EXTENSIONS:
        return min(policy.max_bytes, IMAGE_UPLOAD_POLICY.max_bytes)
    return policy.max_bytes


def _validate_image(
    content: memoryview,
    *,
    extension: str,
    max_pixels: int,
) -> None:
    expected_formats = {
        ".gif": {"GIF"},
        ".jpeg": {"JPEG"},
        ".jpg": {"JPEG"},
        ".png": {"PNG"},
        ".webp": {"WEBP"},
    }[extension]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = str(image.format or "").upper()
                width, height = image.size
                if image_format not in expected_formats:
                    raise ValueError("uploaded image content does not match its extension")
                if width < 1 or height < 1 or width * height > max_pixels:
                    raise ValueError("uploaded image dimensions exceed safe limits")
                image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("uploaded image dimensions exceed safe limits") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("uploaded image content is invalid") from exc


def _validate_video_signature(content: memoryview, *, extension: str) -> None:
    header = bytes(content[:32])
    valid = False
    if extension in {".mp4", ".mov"}:
        valid = len(header) >= 12 and header[4:8] == b"ftyp"
    elif extension in {".mkv", ".webm"}:
        valid = header.startswith(b"\x1aE\xdf\xa3")
    elif extension == ".avi":
        valid = len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    if not valid:
        raise ValueError("uploaded video content does not match its extension")


__all__ = [
    "IMAGE_UPLOAD_POLICY",
    "MIXED_MEDIA_UPLOAD_POLICY",
    "UploadPolicy",
    "VIDEO_UPLOAD_POLICY",
    "store_uploaded_files",
]
