from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path

PROJECT_ROOT_ID_PREFIX = "pixelle-root-v1:"
_PROJECT_ROOT_ID_PATTERN = re.compile(r"^pixelle-root-v1:[0-9a-f]{64}$")
_PROJECT_ROOT_HASH_DOMAIN = b"Pixelle-Video project root identity v1\0"
PATH_ID_PREFIX = "pixelle-path-v1:"
_PATH_ID_PATTERN = re.compile(r"^pixelle-path-v1:[0-9a-f]{64}$")
_PATH_HASH_DOMAIN = b"Pixelle-Video configured path identity v1\0"


def resolve_project_root(project_root: str | os.PathLike[str]) -> Path:
    """Resolve and validate an application project root without creating files."""
    resolved = Path(project_root).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Project root is not a directory: {resolved}")
    return resolved


def build_project_root_id(project_root: str | os.PathLike[str]) -> str:
    """Build a stable, non-path project identity for local process matching."""
    resolved = resolve_project_root(project_root)
    canonical_path = unicodedata.normalize("NFC", os.path.normcase(str(resolved)))
    digest = hashlib.sha256(
        _PROJECT_ROOT_HASH_DOMAIN + canonical_path.encode("utf-8")
    ).hexdigest()
    return f"{PROJECT_ROOT_ID_PREFIX}{digest}"


def build_path_id(path: str | os.PathLike[str]) -> str:
    """Build a stable identity for a configured path without requiring it to exist."""
    configured_path = Path(path).expanduser()
    if not configured_path.is_absolute():
        raise ValueError("Configured path identity requires an absolute path")
    resolved = configured_path.resolve()
    canonical_path = unicodedata.normalize("NFC", os.path.normcase(str(resolved)))
    digest = hashlib.sha256(_PATH_HASH_DOMAIN + canonical_path.encode("utf-8")).hexdigest()
    return f"{PATH_ID_PREFIX}{digest}"


def is_project_root_id(value: object) -> bool:
    """Return whether a value follows the versioned project-root identity contract."""
    return isinstance(value, str) and _PROJECT_ROOT_ID_PATTERN.fullmatch(value) is not None


def is_path_id(value: object) -> bool:
    """Return whether a value follows the versioned configured-path identity contract."""
    return isinstance(value, str) and _PATH_ID_PATTERN.fullmatch(value) is not None


__all__ = [
    "PATH_ID_PREFIX",
    "PROJECT_ROOT_ID_PREFIX",
    "build_path_id",
    "build_project_root_id",
    "is_path_id",
    "is_project_root_id",
    "resolve_project_root",
]
