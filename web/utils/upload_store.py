from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from loguru import logger
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
    max_image_frames: int = 500
    max_video_pixels: int = 67_108_864
    max_video_duration_seconds: float = 14_400.0
    max_video_streams: int = 16

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("upload max_bytes must be positive")
        if not self.allowed_extensions:
            raise ValueError("upload policy must allow at least one extension")
        if self.max_image_frames < 1 or self.max_video_streams < 1:
            raise ValueError("upload frame and stream limits must be positive")
        if self.max_video_pixels < 1 or self.max_video_duration_seconds <= 0:
            raise ValueError("upload video limits must be positive")


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


def store_uploaded_files_with_feedback(
    uploaded_files: Iterable[Any],
    destination_dir: str | Path,
    *,
    policy: UploadPolicy,
    report_error: Callable[[str], Any],
) -> list[str]:
    """Store UI uploads without letting validation failures crash the page."""

    try:
        return store_uploaded_files(
            uploaded_files,
            destination_dir,
            policy=policy,
        )
    except (ValueError, RuntimeError) as error:
        report_error(f"Upload rejected: {error}")
    except OSError as error:
        logger.exception(f"Failed to persist uploaded media: {error}")
        report_error("Upload could not be saved; verify temporary storage availability")
    return []


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
        _validate_image(
            byte_view,
            extension=extension,
            max_pixels=policy.max_image_pixels,
            max_frames=policy.max_image_frames,
        )
    else:
        _validate_video_signature(byte_view, extension=extension)

    content_digest = sha256(byte_view).hexdigest()
    final_path = resolve_path_within(destination_dir, f"upload_{content_digest}{extension}")
    if (
        final_path.is_file()
        and final_path.stat().st_size == byte_size
        and _file_sha256(final_path) == content_digest
    ):
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
        if extension in VIDEO_UPLOAD_EXTENSIONS:
            _validate_video_container(temporary_path, policy=policy)
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
    max_frames: int,
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
                if int(getattr(image, "n_frames", 1)) > max_frames:
                    raise ValueError("uploaded image contains too many animation frames")
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


def _validate_video_container(path: Path, *, policy: UploadPolicy) -> None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("video upload validation requires ffprobe")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creation_flags,
        )
        probe = json.loads(completed.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("uploaded video container is invalid") from exc

    if not isinstance(probe, dict):
        raise ValueError("uploaded video probe result is invalid")
    streams = probe.get("streams", [])
    if not isinstance(streams, list) or len(streams) > policy.max_video_streams:
        raise ValueError("uploaded video contains too many media streams")
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise ValueError("uploaded video does not contain a video stream")
    for stream in video_streams:
        width = _bounded_integer(stream.get("width"))
        height = _bounded_integer(stream.get("height"))
        if width < 1 or height < 1 or width * height > policy.max_video_pixels:
            raise ValueError("uploaded video dimensions exceed safe limits")

    format_data = probe.get("format")
    if not isinstance(format_data, dict):
        raise ValueError("uploaded video format metadata is invalid")
    try:
        duration = float(format_data.get("duration"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("uploaded video duration is invalid") from exc
    if not math.isfinite(duration) or duration <= 0 or duration > policy.max_video_duration_seconds:
        raise ValueError("uploaded video duration exceeds safe limits")


def _bounded_integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if 0 < parsed <= 1_000_000 else 0


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "IMAGE_UPLOAD_POLICY",
    "MIXED_MEDIA_UPLOAD_POLICY",
    "UploadPolicy",
    "VIDEO_UPLOAD_POLICY",
    "store_uploaded_files",
    "store_uploaded_files_with_feedback",
]
