from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

from pixelle_video.utils.json_safety import to_json_compatible

STORYBOARD_PREVIEW_SNAPSHOT_KEY = "storyboard_preview_snapshot"


def get_storyboard_preview_snapshot(
    session_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the storyboard preview snapshot stored in session state."""
    snapshot = session_state.get(STORYBOARD_PREVIEW_SNAPSHOT_KEY)
    if isinstance(snapshot, Mapping):
        copied_snapshot = to_json_compatible(
            snapshot,
            field_name=STORYBOARD_PREVIEW_SNAPSHOT_KEY,
        )
        return copied_snapshot if isinstance(copied_snapshot, dict) else None
    return None


def set_storyboard_preview_snapshot(
    session_state: MutableMapping[str, Any],
    snapshot: Mapping[str, Any] | None,
) -> bool:
    """Persist a storyboard preview snapshot and report whether the value changed."""
    next_snapshot = (
        to_json_compatible(snapshot, field_name=STORYBOARD_PREVIEW_SNAPSHOT_KEY)
        if isinstance(snapshot, Mapping)
        else None
    )
    current_snapshot = session_state.get(STORYBOARD_PREVIEW_SNAPSHOT_KEY)
    if current_snapshot == next_snapshot:
        return False

    session_state[STORYBOARD_PREVIEW_SNAPSHOT_KEY] = next_snapshot
    return True


__all__ = [
    "STORYBOARD_PREVIEW_SNAPSHOT_KEY",
    "get_storyboard_preview_snapshot",
    "set_storyboard_preview_snapshot",
]
