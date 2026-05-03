"""
Minimal storyboard preview helpers for collecting per-frame override payloads.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Mapping, Sequence

import streamlit as st

from pixelle_video.platform_context import first_text
from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel
from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel
from web.i18n import tr
from web.state.storyboard_overrides import build_storyboard_override_snapshot_identity

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
    return build_storyboard_override_snapshot_identity(planning_snapshot)


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
    plan_id: str,
    plan_revision: int,
    frame_id: str,
    source_digest: str,
    locked_fields: Sequence[str] | None,
    values: Mapping[str, Any] | None,
    override_source: str = "user_preview",
) -> dict[str, Any] | None:
    """Build one frame override payload and keep only explicitly locked fields."""
    normalized_locked_fields = _normalize_locked_fields(locked_fields)
    normalized_plan_id = str(plan_id or "").strip()
    normalized_frame_id = str(frame_id or "").strip()
    normalized_source_digest = str(source_digest or "").strip()
    if (
        not normalized_plan_id
        or type(plan_revision) is not int
        or plan_revision < 1
        or not normalized_frame_id
        or len(normalized_source_digest) != 64
        or any(char not in "0123456789abcdef" for char in normalized_source_digest)
        or not normalized_locked_fields
    ):
        return None

    payload: dict[str, Any] = {
        "plan_id": normalized_plan_id,
        "plan_revision": plan_revision,
        "frame_id": normalized_frame_id,
        "source_digest": normalized_source_digest,
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
    override_source: str = "user_preview",
) -> list[dict[str, Any]]:
    """Collect non-empty frame overrides from preview state entries."""
    overrides: list[dict[str, Any]] = []
    for entry in entries or ():
        payload = build_frame_override_payload(
            plan_id=str(entry.get("plan_id", "")).strip(),
            plan_revision=entry.get("plan_revision"),
            frame_id=str(entry.get("frame_id", "")).strip(),
            source_digest=str(entry.get("source_digest", "")).strip(),
            locked_fields=entry.get("locked_fields"),
            values=entry.get("values"),
            override_source=override_source,
        )
        if payload:
            overrides.append(payload)
    return overrides


def build_storyboard_preview_rows(planning_snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snapshot = planning_snapshot or {}
    generation = snapshot.get("storyboard_generation")
    if not isinstance(generation, Mapping):
        return rows

    plan_id = str(generation.get("plan_id") or "").strip()
    plan_revision = generation.get("revision")
    source_digest = str(generation.get("source_digest") or "").strip()
    if (
        not plan_id
        or type(plan_revision) is not int
        or plan_revision < 1
        or len(source_digest) != 64
        or any(char not in "0123456789abcdef" for char in source_digest)
    ):
        return rows

    identity_frames = generation.get("frames") or ()
    if not isinstance(identity_frames, Sequence) or isinstance(identity_frames, (str, bytes)):
        return rows
    display_frames = snapshot.get("frames") or ()
    if not isinstance(display_frames, Sequence) or isinstance(display_frames, (str, bytes)):
        display_frames = ()
    for index, identity_frame in enumerate(identity_frames):
        if not isinstance(identity_frame, Mapping):
            continue
        frame_id = str(identity_frame.get("frame_id") or "").strip()
        if not frame_id:
            continue
        display_frame = (
            display_frames[index]
            if index < len(display_frames) and isinstance(display_frames[index], Mapping)
            else {}
        )
        frame = {**dict(identity_frame), **dict(display_frame)}
        scene_id = str(frame.get("scene_id") or frame.get("index") or index + 1)
        values: dict[str, Any] = {}
        for field_name in EDITABLE_STORYBOARD_FIELDS:
            raw_value = frame.get(field_name)
            if field_name in LIST_LIKE_STORYBOARD_FIELDS and isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
                values[field_name] = ", ".join(str(item) for item in raw_value if str(item).strip())
            else:
                values[field_name] = "" if raw_value is None else str(raw_value)
        rows.append(
            {
                "plan_id": plan_id,
                "plan_revision": plan_revision,
                "frame_id": frame_id,
                "source_digest": source_digest,
                "scene_id": scene_id,
                "workbench": _extract_frame_workbench_context(frame),
                "locked_fields": list(frame.get("locked_fields") or []),
                "values": values,
            }
        )
    return rows


def render_storyboard_preview(
    planning_snapshot: Mapping[str, Any] | None,
    *,
    stale_context: Mapping[str, str] | None = None,
    workbench_client=None,
    stale_renderer: Callable[..., None] | None = render_prompt_plan_stale_panel,
    workbench_renderer: Callable[..., None] | None = render_storyboard_workbench_panel,
) -> list[dict[str, Any]]:
    """Render a minimal frame override editor from the latest planning snapshot."""
    rows = build_storyboard_preview_rows(planning_snapshot)
    if not rows:
        st.caption(tr("storyboard.preview.empty"))
        return []

    state_namespace = build_storyboard_preview_state_namespace(planning_snapshot)
    draft_entries: list[dict[str, Any]] = []
    with st.expander(tr("storyboard.preview.title"), expanded=False):
        st.caption(tr("storyboard.preview.help"))
        if stale_renderer is not None:
            context = stale_context or {}
            stale_renderer(
                prompt_plan_id=rows[0]["plan_id"],
                ui=st,
                translate=tr,
                workspace_id=context.get("workspace_id"),
                project_id=context.get("project_id"),
                workbench_client=workbench_client,
            )
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
                        "plan_id": row["plan_id"],
                        "plan_revision": row["plan_revision"],
                        "frame_id": row["frame_id"],
                        "source_digest": row["source_digest"],
                        "scene_id": scene_id,
                        "locked_fields": locked_fields,
                        "values": values,
                    }
                )
                if workbench_renderer is not None:
                    workbench_context = dict(row.get("workbench") or {})
                    if workbench_context.get("artifact_id"):
                        context = stale_context or {}
                        workbench_renderer(
                            workspace_id=context.get("workspace_id"),
                            storyboard_id=workbench_context.get("storyboard_id")
                            or context.get("storyboard_id")
                            or row["plan_id"],
                            frame_id=row["frame_id"],
                            artifact_id=workbench_context.get("artifact_id"),
                            selected_version_id=workbench_context.get("selected_version_id"),
                            workbench_client=workbench_client,
                            ui=st,
                            translate=tr,
                        )

    return collect_storyboard_preview_overrides(
        draft_entries,
    )


def _extract_frame_workbench_context(frame: Mapping[str, Any]) -> dict[str, str]:
    workbench_state = frame.get("workbench_state")
    state = workbench_state if isinstance(workbench_state, Mapping) else {}
    return {
        "storyboard_id": first_text(
            frame.get("storyboard_id"),
            frame.get("source_storyboard_id"),
        ),
        "artifact_id": first_text(
            frame.get("selected_image_artifact_id"),
            frame.get("image_artifact_id"),
            frame.get("artifact_id"),
            state.get("selected_image_artifact_id"),
        ),
        "selected_version_id": first_text(
            frame.get("selected_image_version_id"),
            state.get("selected_image_version_id"),
        ),
    }
