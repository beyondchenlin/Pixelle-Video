from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import Any

STORYBOARD_PREVIEW_SNAPSHOT_KEY = "storyboard_preview_snapshot"


def get_storyboard_preview_snapshot(
    session_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the storyboard preview snapshot stored in session state."""
    snapshot = session_state.get(STORYBOARD_PREVIEW_SNAPSHOT_KEY)
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    return None


def set_storyboard_preview_snapshot(
    session_state: MutableMapping[str, Any],
    snapshot: Mapping[str, Any] | None,
) -> bool:
    """Persist a storyboard preview snapshot and report whether the value changed."""
    next_snapshot = deepcopy(dict(snapshot)) if isinstance(snapshot, Mapping) else None
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
