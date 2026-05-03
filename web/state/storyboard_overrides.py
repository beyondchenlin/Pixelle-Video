from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from typing import Any

STORYBOARD_OVERRIDE_DRAFT_KEY = "storyboard_override_draft"


def build_storyboard_override_snapshot_identity(
    planning_snapshot: Mapping[str, Any] | None,
) -> str:
    """Build a stable identity for the storyboard frames that an override draft targets."""
    canonical_payload = json.dumps(
        (planning_snapshot or {}).get("frames") or [],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    fingerprint = hashlib.sha1(canonical_payload.encode("utf-8")).hexdigest()
    return f"storyboard_snapshot_{fingerprint}"


def get_storyboard_override_draft(
    session_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the stored storyboard override draft if it is well-formed."""
    draft = session_state.get(STORYBOARD_OVERRIDE_DRAFT_KEY)
    if not isinstance(draft, Mapping):
        return None
    return dict(draft)


def get_storyboard_override_values_for_snapshot(
    session_state: Mapping[str, Any],
    *,
    snapshot_identity: str,
) -> list[dict[str, Any]]:
    """Return override payloads only when the stored draft matches the active snapshot."""
    normalized_identity = str(snapshot_identity or "").strip()
    if not normalized_identity:
        return []

    draft = get_storyboard_override_draft(session_state)
    if not isinstance(draft, Mapping):
        return []
    if str(draft.get("snapshot_identity") or "").strip() != normalized_identity:
        return []

    overrides = draft.get("frame_overrides")
    if not isinstance(overrides, Sequence) or isinstance(overrides, (str, bytes)):
        return []
    return [dict(item) for item in overrides if isinstance(item, Mapping)]


def set_storyboard_override_draft(
    session_state: MutableMapping[str, Any],
    draft: Mapping[str, Any] | None,
) -> bool:
    """Persist storyboard override draft state and report whether it changed."""
    next_draft = deepcopy(dict(draft)) if isinstance(draft, Mapping) else None
    current_draft = session_state.get(STORYBOARD_OVERRIDE_DRAFT_KEY)
    if current_draft == next_draft:
        return False

    session_state[STORYBOARD_OVERRIDE_DRAFT_KEY] = next_draft
    return True


__all__ = [
    "STORYBOARD_OVERRIDE_DRAFT_KEY",
    "build_storyboard_override_snapshot_identity",
    "get_storyboard_override_draft",
    "get_storyboard_override_values_for_snapshot",
    "set_storyboard_override_draft",
]
