from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.utils.os_util import get_output_path


def load_latest_storyboard_snapshot_from_disk() -> dict[str, Any] | None:
    """Scan output/ for the latest storyboard.json and extract its planning_snapshot.

    Returns None if no storyboard files exist on disk or if any read/parse error occurs.
    """
    try:
        output_dir = get_output_path()
        output_path = Path(output_dir)
    except Exception:
        logger.warning("Could not resolve output path for storyboard disk fallback")
        return None

    if not output_path.is_dir():
        return None

    entries: list[tuple[float, Path]] = []
    try:
        for entry in output_path.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            storyboard_file = entry / "storyboard.json"
            if storyboard_file.is_file():
                entries.append((storyboard_file.stat().st_mtime, storyboard_file))
    except OSError:
        logger.warning("Failed to scan output directory for storyboard files")
        return None

    if not entries:
        return None

    entries.sort(key=lambda item: item[0], reverse=True)
    latest_path = entries[0][1]

    try:
        with open(latest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.warning(f"Failed to read storyboard JSON from {latest_path}")
        return None

    planning_snapshot = data.get("planning_snapshot")
    if not isinstance(planning_snapshot, dict):
        return None

    return planning_snapshot
