"""Shared storyboard snapshot capture — called by every pipeline after video generation.

Provides two entry points:
- capture_snapshot_from_result()  — for pipelines that return VideoGenerationResult or similar
- capture_snapshot_from_task_dir() — for pipelines that write storyboard.json to a task dir
"""

from __future__ import annotations

import json
import os
from collections.abc import MutableMapping
from typing import Any

from loguru import logger

from web.state.storyboard_preview import set_storyboard_preview_snapshot


def capture_snapshot_from_result(
    result: Any,
    session_state: MutableMapping[str, Any],
) -> bool:
    """Extract planning_snapshot from a generation result and store in session state.

    Tries result.storyboard.planning_snapshot first.  Falls back to loading
    storyboard.json from the directory containing the output video file.
    """
    if result is None:
        return False

    storyboard = getattr(result, "storyboard", None)
    snapshot = (
        getattr(storyboard, "planning_snapshot", None)
        if storyboard is not None
        else None
    )
    if isinstance(snapshot, dict):
        return set_storyboard_preview_snapshot(session_state, snapshot)

    video_path = (
        getattr(result, "video_path", None)
        or getattr(result, "final_video_path", None)
    )
    if video_path and isinstance(video_path, str):
        return capture_snapshot_from_task_dir(
            os.path.dirname(video_path),
            session_state,
        )

    return False


def capture_snapshot_from_task_dir(
    task_dir: str,
    session_state: MutableMapping[str, Any],
) -> bool:
    """Load storyboard.json from *task_dir* and store its planning_snapshot.

    Returns False when the file is missing, unreadable, or has no planning_snapshot.
    """
    storyboard_path = os.path.join(task_dir, "storyboard.json")
    if not os.path.isfile(storyboard_path):
        return False

    try:
        with open(storyboard_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "Failed to read storyboard.json for snapshot capture",
            extra={"storyboard_path": storyboard_path},
        )
        return False

    snapshot = data.get("planning_snapshot")
    if not isinstance(snapshot, dict):
        return False

    return set_storyboard_preview_snapshot(session_state, snapshot)


__all__ = [
    "capture_snapshot_from_result",
    "capture_snapshot_from_task_dir",
]
