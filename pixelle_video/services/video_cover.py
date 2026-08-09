"""Create and reuse bounded homepage cover artifacts for generated videos."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path

from loguru import logger
from PIL import Image, ImageFilter, ImageOps

from pixelle_video.utils.os_util import get_output_path

COVER_RELATIVE_PATH = Path("preview") / "home-cover.jpg"
COVER_SIZE = (480, 270)
MAX_SOURCE_IMAGE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 40_000_000
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
_cover_locks = tuple(threading.Lock() for _index in range(32))
_generation_slots = threading.BoundedSemaphore(2)


def ensure_video_cover(
    video_path: str | os.PathLike[str],
    *,
    frame_paths: Iterable[str | os.PathLike[str] | None] = (),
    output_root: str | os.PathLike[str] | None = None,
) -> Path | None:
    """Return a cached cover, creating it once from a safe frame or the video.

    The video and every source frame must resolve below the configured output
    root. Covers are fixed-size JPEG files written atomically inside the task
    directory, so homepage reruns never decode the video themselves.
    """
    root = Path(output_root or get_output_path()).resolve()
    video = _resolve_regular_file(video_path, root=root)
    if video is None or video.suffix.casefold() not in _VIDEO_SUFFIXES:
        return None

    try:
        relative_video = video.relative_to(root)
    except ValueError:
        return None
    if len(relative_video.parts) < 2:
        return None

    task_dir = (root / relative_video.parts[0]).resolve()
    if not task_dir.is_dir() or not task_dir.is_relative_to(root):
        return None
    cover_directory = _safe_cover_directory(task_dir)
    if cover_directory is None:
        return None
    cover_path = cover_directory / COVER_RELATIVE_PATH.name
    if _is_nonempty_regular_file(cover_path, task_dir=task_dir):
        return cover_path

    lock = _cover_lock(cover_path)
    with lock:
        if _is_nonempty_regular_file(cover_path, task_dir=task_dir):
            return cover_path
        with _generation_slots:
            try:
                source = _select_source_image(
                    task_dir,
                    frame_paths=frame_paths,
                )
                if source is not None:
                    _write_cover_from_image(source, cover_path)
                else:
                    _write_cover_from_video(video, cover_path)
            except Exception as exc:
                logger.warning(f"Unable to create homepage video cover: {type(exc).__name__}")
                return None
    return cover_path if _is_nonempty_regular_file(cover_path, task_dir=task_dir) else None


def _cover_lock(path: Path) -> threading.Lock:
    return _cover_locks[hash(path) % len(_cover_locks)]


def _safe_cover_directory(task_dir: Path) -> Path | None:
    directory = task_dir / COVER_RELATIVE_PATH.parent
    try:
        directory.mkdir(parents=False, exist_ok=True)
        resolved = directory.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if directory.is_symlink() or not resolved.is_dir() or not resolved.is_relative_to(task_dir):
        return None
    return resolved


def _resolve_regular_file(
    value: str | os.PathLike[str],
    *,
    root: Path,
) -> Path | None:
    raw_path = Path(str(value))
    if not raw_path.is_absolute():
        parts = raw_path.parts
        if parts and parts[0].casefold() == "output":
            raw_path = Path(*parts[1:])
        raw_path = root / raw_path
    try:
        resolved = raw_path.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if not resolved.is_file() or not resolved.is_relative_to(root):
        return None
    return resolved


def _is_nonempty_regular_file(path: Path, *, task_dir: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
        return resolved.is_file() and resolved.is_relative_to(task_dir) and resolved.stat().st_size > 0
    except (FileNotFoundError, OSError, RuntimeError):
        return False


def _select_source_image(
    task_dir: Path,
    *,
    frame_paths: Iterable[str | os.PathLike[str] | None],
) -> Path | None:
    explicit = [Path(str(path)) for path in frame_paths if path]
    discovered = sorted((task_dir / "frames").glob("*")) if (task_dir / "frames").is_dir() else []
    for candidate in [*explicit, *discovered]:
        if not candidate.is_absolute():
            candidate = task_dir / candidate
        try:
            resolved = candidate.resolve(strict=True)
            size = resolved.stat().st_size
        except (FileNotFoundError, OSError, RuntimeError):
            continue
        if (
            resolved.is_file()
            and resolved.is_relative_to(task_dir)
            and resolved.suffix.casefold() in _IMAGE_SUFFIXES
            and 0 < size <= MAX_SOURCE_IMAGE_BYTES
        ):
            return resolved
    return None


def _write_cover_from_image(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        if image.width * image.height > MAX_SOURCE_IMAGE_PIXELS:
            raise ValueError("source image exceeds the cover pixel limit")
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        cover = ImageOps.fit(normalized, COVER_SIZE, method=Image.Resampling.LANCZOS)
        cover = cover.filter(ImageFilter.GaussianBlur(radius=12))
        foreground = normalized.copy()
        foreground.thumbnail(COVER_SIZE, Image.Resampling.LANCZOS)
        offset = (
            (COVER_SIZE[0] - foreground.width) // 2,
            (COVER_SIZE[1] - foreground.height) // 2,
        )
        cover.paste(foreground, offset)
        _save_cover_atomic(cover, target)


def _write_cover_from_video(video: Path, target: Path) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("ffmpeg executable is unavailable")
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix="cover-frame-",
        suffix=".png",
        dir=target.parent,
        delete=False,
    )
    extracted_frame = Path(handle.name)
    handle.close()
    try:
        completed = subprocess.run(
            [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-y",
                str(extracted_frame),
            ],
            check=False,
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not extracted_frame.is_file():
            raise RuntimeError("video frame extraction failed")
        _write_cover_from_image(extracted_frame, target)
    finally:
        extracted_frame.unlink(missing_ok=True)


def _save_cover_atomic(image: Image.Image, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}-",
        suffix=".jpg",
        dir=target.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        image.save(temporary, format="JPEG", quality=78, optimize=True, progressive=True)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["COVER_RELATIVE_PATH", "COVER_SIZE", "ensure_video_cover"]
