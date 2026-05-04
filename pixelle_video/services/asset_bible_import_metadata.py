from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_IMPORT_ORIGIN_METADATA_KEYS = (
    "source_kind",
    "origin_preset_id",
    "origin_revision",
    "imported_at",
)


def mark_imported_asset_bible_customized(
    next_payload: Mapping[str, Any],
    existing_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(next_payload)
    if not isinstance(existing_payload, Mapping):
        return payload
    existing_metadata = existing_payload.get("metadata")
    if not isinstance(existing_metadata, Mapping):
        return payload
    if existing_metadata.get("source_kind") != "imported":
        return payload

    metadata = dict(payload.get("metadata") or {})
    for key in _IMPORT_ORIGIN_METADATA_KEYS:
        if key in existing_metadata:
            metadata[key] = existing_metadata[key]
    metadata["customized"] = True
    payload["metadata"] = metadata
    return payload


__all__ = ["mark_imported_asset_bible_customized"]
