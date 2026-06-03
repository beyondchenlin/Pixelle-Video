from __future__ import annotations

from collections.abc import Mapping
from typing import Any

LEGACY_IP_PROFILE_ID_FIELD = "ip_profile_id"
SERIES_VISUAL_SIGNATURE_PROFILE_ID_FIELD = "series_visual_signature_profile_id"


def resolve_series_visual_signature_profile_id_from_payload(payload: Mapping[str, Any]) -> str:
    """Read persisted AssetBible profile ids across schema versions."""
    if not isinstance(payload, Mapping):
        raise ValueError("IPProfile payload must be a mapping")
    return _first_text(
        payload.get(SERIES_VISUAL_SIGNATURE_PROFILE_ID_FIELD),
        payload.get(LEGACY_IP_PROFILE_ID_FIELD),
    )


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = [
    "LEGACY_IP_PROFILE_ID_FIELD",
    "SERIES_VISUAL_SIGNATURE_PROFILE_ID_FIELD",
    "resolve_series_visual_signature_profile_id_from_payload",
]
