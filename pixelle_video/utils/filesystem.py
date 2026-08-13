from __future__ import annotations

import os
import shutil
from os import PathLike
from pathlib import Path
from typing import IO, Any


def extended_length_path(path: str | PathLike[str]) -> Path:
    """Return an absolute path that remains addressable beyond MAX_PATH on Windows."""

    resolved_path = Path(path).expanduser().resolve(strict=False)
    if os.name != "nt":
        return resolved_path

    raw_path = str(resolved_path)
    if raw_path.startswith("\\\\?\\"):
        return resolved_path
    if raw_path.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{raw_path[2:]}")
    return Path(f"\\\\?\\{raw_path}")


def copy_file(
    source: str | PathLike[str],
    target: str | PathLike[str],
) -> Path:
    """Copy one file while preserving metadata and supporting long Windows paths."""

    source_path = extended_length_path(source)
    target_path = extended_length_path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return Path(target)


def ensure_directory(path: str | PathLike[str]) -> Path:
    """Create a directory tree without inheriting the Windows MAX_PATH limit."""

    target_path = extended_length_path(path)
    target_path.mkdir(parents=True, exist_ok=True)
    return Path(path)


def path_exists(path: str | PathLike[str]) -> bool:
    """Check path existence without inheriting the Windows MAX_PATH limit."""

    return extended_length_path(path).exists()


def path_is_file(path: str | PathLike[str]) -> bool:
    """Check for a regular file without inheriting the Windows MAX_PATH limit."""

    return extended_length_path(path).is_file()


def path_is_dir(path: str | PathLike[str]) -> bool:
    """Check for a directory without inheriting the Windows MAX_PATH limit."""

    return extended_length_path(path).is_dir()


def open_file(
    path: str | PathLike[str],
    mode: str = "r",
    **kwargs: Any,
) -> IO[Any]:
    """Open a file through its extended-length path on Windows."""

    return extended_length_path(path).open(mode, **kwargs)


def read_text_file(
    path: str | PathLike[str],
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
) -> str:
    """Read text through its extended-length path on Windows."""

    return extended_length_path(path).read_text(encoding=encoding, errors=errors)


def write_text_file(
    path: str | PathLike[str],
    content: str,
    *,
    encoding: str = "utf-8",
    errors: str | None = None,
) -> int:
    """Write text through its extended-length path on Windows."""

    target_path = extended_length_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return target_path.write_text(content, encoding=encoding, errors=errors)
