from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def validate_task_id(task_id: str) -> str:
    """Return a canonical task identifier that is safe as one path component."""

    if not isinstance(task_id, str):
        raise TypeError("task_id must be a string")
    if task_id != task_id.strip():
        raise ValueError("task_id must not contain surrounding whitespace")
    windows_stem = task_id.split(".", 1)[0].upper()
    if (
        task_id in {"", ".", ".."}
        or task_id.endswith(".")
        or windows_stem in _WINDOWS_RESERVED_NAMES
        or _SAFE_TASK_ID_RE.fullmatch(task_id) is None
    ):
        raise ValueError("task_id contains unsafe path characters")
    return task_id


def resolve_path_within(root: str | Path, *parts: str | Path) -> Path:
    """Resolve a descendant path and reject absolute or escaping components."""

    resolved_root = Path(root).resolve()
    for part in parts:
        part_text = str(part)
        if Path(part_text).is_absolute() or PureWindowsPath(part_text).is_absolute():
            raise ValueError("path components must be relative")
    candidate = resolved_root.joinpath(*parts).resolve()
    if candidate != resolved_root and not candidate.is_relative_to(resolved_root):
        raise ValueError("path escapes its configured root")
    return candidate


def resolve_task_dir(root: str | Path, task_id: str) -> Path:
    """Resolve one validated task directory below the configured output root."""

    return resolve_path_within(root, validate_task_id(task_id))


__all__ = ["resolve_path_within", "resolve_task_dir", "validate_task_id"]
