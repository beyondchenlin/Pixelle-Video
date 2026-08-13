from __future__ import annotations

import os
from pathlib import Path

from pixelle_video.utils.project_identity import resolve_project_root


def resolve_configured_path(
    configured_path: str | os.PathLike[str],
    *,
    project_root: str | os.PathLike[str],
    setting_name: str,
) -> Path:
    """Resolve a configured path with an explicit project-relative contract.

    Absolute paths remain supported for external storage. Relative paths are anchored
    to the configured project root and may not escape it through parent traversal.
    This function only resolves paths; it never creates filesystem entries.
    """
    raw_value = os.fspath(configured_path).strip()
    if not raw_value:
        raise ValueError(f"{setting_name} must not be blank")

    root = resolve_project_root(project_root)
    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{setting_name} relative path must stay inside the project root")
    return resolved


__all__ = ["resolve_configured_path"]
