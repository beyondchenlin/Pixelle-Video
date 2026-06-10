from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from loguru import logger


def load_json_with_quarantine(path: Path, default: Any) -> Any:
    """Load JSON and quarantine corrupt files instead of crashing the caller.

    Local dev trace/history stores are observability infrastructure. A partially
    written or manually edited JSON file must not prevent content generation.
    """
    if not path.exists():
        return deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        corrupt_path = path.with_name(f"{path.name}.corrupt.{int(time.time())}.bak")
        try:
            path.replace(corrupt_path)
        except OSError:
            logger.exception("Failed to quarantine corrupt JSON file: %s", path)
            raise
        logger.warning(
            "JSON store file is corrupt; quarantined and reset: %s -> %s (%s)",
            path,
            corrupt_path,
            exc,
        )
        return deepcopy(default)


def save_json_atomic(
    path: Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 2,
    sort_keys: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys)
        handle.write("\n")
    temp_path.replace(path)


__all__ = ["load_json_with_quarantine", "save_json_atomic"]
