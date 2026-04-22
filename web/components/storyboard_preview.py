"""
Minimal storyboard preview helpers for collecting per-frame override payloads.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import streamlit as st

from web.i18n import tr

EDITABLE_STORYBOARD_FIELDS: tuple[str, ...] = (
    "shot_type",
    "shot_purpose",
    "primary_subject",
    "world_elements",
    "continuity_anchors",
    "focus_detail",
    "prompt_intent",
)
LIST_LIKE_STORYBOARD_FIELDS = {"world_elements", "continuity_anchors"}


def build_storyboard_preview_snapshot_identity(
    planning_snapshot: Mapping[str, Any] | None,
) -> str:
    """Build a stable identity for the snapshot frames currently shown in preview."""
    canonical_payload = json.dumps(
        (planning_snapshot or {}).get("frames") or [],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    fingerprint = hashlib.sha1(canonical_payload.encode("utf-8")).hexdigest()
    return f"storyboard_snapshot_{fingerprint}"


def build_storyboard_preview_state_namespace(
    planning_snapshot: Mapping[str, Any] | None,
) -> str:
    """Build a stable widget namespace for one planning snapshot."""
    canonical_payload = json.dumps(
        planning_snapshot or {},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    fingerprint = hashlib.sha1(canonical_payload.encode("utf-8")).hexdigest()[:12]
    return f"storyboard_preview_{fingerprint}"


def _normalize_locked_fields(locked_fields: Sequence[str] | None) -> list[str]:
    normalized: list[str] = []
    for field in locked_fields or ():
        field_name = str(field).strip()
        if field_name and field_name in EDITABLE_STORYBOARD_FIELDS and field_name not in normalized:
            normalized.append(field_name)
    return normalized


def _normalize_override_value(field_name: str, value: Any) -> Any:
    if field_name in LIST_LIKE_STORYBOARD_FIELDS:
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            parts = [str(item).strip() for item in value]
        else:
            parts = []
        return [item for item in parts if item]

    if value is None:
        return None
    return str(value).strip()


def build_frame_override_payload(
    *,
    scene_id: str,
    snapshot_identity: str | None,
    locked_fields: Sequence[str] | None,
    values: Mapping[str, Any] | None,
    override_source: str = "user_preview",
) -> dict[str, Any] | None:
    """Build one frame override payload and keep only explicitly locked fields."""
    normalized_locked_fields = _normalize_locked_fields(locked_fields)
    normalized_snapshot_identity = str(snapshot_identity or "").strip()
    if not scene_id or not normalized_snapshot_identity or not normalized_locked_fields:
        return None

    payload: dict[str, Any] = {
        "scene_id": scene_id,
        "snapshot_identity": normalized_snapshot_identity,
        "locked_fields": normalized_locked_fields,
    }
    if override_source:
        payload["override_source"] = override_source

    source_values = dict(values or {})
    for field_name in normalized_locked_fields:
        normalized_value = _normalize_override_value(field_name, source_values.get(field_name))
        if normalized_value in (None, "", []):
            continue
        payload[field_name] = normalized_value

    value_keys = [field_name for field_name in normalized_locked_fields if field_name in payload]
    if not value_keys:
        return None
    return payload


def collect_storyboard_preview_overrides(
    entries: Sequence[Mapping[str, Any]] | None,
    *,
    snapshot_identity: str | None,
    override_source: str = "user_preview",
) -> list[dict[str, Any]]:
    """Collect non-empty frame overrides from preview state entries."""
    overrides: list[dict[str, Any]] = []
    for entry in entries or ():
        payload = build_frame_override_payload(
            scene_id=str(entry.get("scene_id", "")).strip(),
            snapshot_identity=snapshot_identity,
            locked_fields=entry.get("locked_fields"),
            values=entry.get("values"),
            override_source=override_source,
        )
        if payload:
            overrides.append(payload)
    return overrides


def _build_preview_rows(planning_snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, frame in enumerate((planning_snapshot or {}).get("frames") or ()):
        scene_id = str(frame.get("scene_id") or f"scene-{index + 1}")
        values: dict[str, Any] = {}
        for field_name in EDITABLE_STORYBOARD_FIELDS:
            raw_value = frame.get(field_name)
            if field_name in LIST_LIKE_STORYBOARD_FIELDS and isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
                values[field_name] = ", ".join(str(item) for item in raw_value if str(item).strip())
            else:
                values[field_name] = "" if raw_value is None else str(raw_value)
        rows.append(
            {
                "scene_id": scene_id,
                "locked_fields": list(frame.get("locked_fields") or []),
                "values": values,
            }
        )
    return rows


def render_storyboard_preview(planning_snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Render a minimal frame override editor from the latest planning snapshot."""
    rows = _build_preview_rows(planning_snapshot)
    if not rows:
        st.caption(tr("storyboard.preview.empty"))
        return []

    snapshot_identity = build_storyboard_preview_snapshot_identity(planning_snapshot)
    state_namespace = build_storyboard_preview_state_namespace(planning_snapshot)
    draft_entries: list[dict[str, Any]] = []
    with st.expander(tr("storyboard.preview.title"), expanded=False):
        st.caption(tr("storyboard.preview.help"))
        for row in rows:
            scene_id = row["scene_id"]
            with st.container(border=True):
                st.markdown(
                    f"**{tr('storyboard.preview.scene_label', scene_id=scene_id)}**"
                )
                locked_fields: list[str] = []
                values: dict[str, Any] = {}
                for field_name in EDITABLE_STORYBOARD_FIELDS:
                    default_value = row["values"].get(field_name, "")
                    lock_key = (
                        f"{state_namespace}_lock_{scene_id}_{field_name}"
                    )
                    value_key = (
                        f"{state_namespace}_value_{scene_id}_{field_name}"
                    )
                    is_locked = st.checkbox(
                        tr(f"storyboard.preview.field.{field_name}"),
                        value=field_name in row["locked_fields"],
                        key=lock_key,
                    )
                    if field_name in LIST_LIKE_STORYBOARD_FIELDS:
                        field_value = st.text_area(
                            tr(f"storyboard.preview.field_value.{field_name}"),
                            value=default_value,
                            key=value_key,
                            height=68,
                        )
                    else:
                        field_value = st.text_input(
                            tr(f"storyboard.preview.field_value.{field_name}"),
                            value=default_value,
                            key=value_key,
                        )
                    values[field_name] = field_value
                    if is_locked:
                        locked_fields.append(field_name)

                draft_entries.append(
                    {
                        "scene_id": scene_id,
                        "locked_fields": locked_fields,
                        "values": values,
                    }
                )

    return collect_storyboard_preview_overrides(
        draft_entries,
        snapshot_identity=snapshot_identity,
    )
