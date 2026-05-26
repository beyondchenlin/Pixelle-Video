from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from web.utils.streamlit_helpers import list_of_dicts

Translate = Callable[..., str]

_PRIVATE_FIELDS = {
    "workflow_path",
    "provider_url",
    "local_path",
}


def render_stale_target_panel(
    *,
    stale_summary: dict[str, Any],
    ui=st,
    translate: Translate | None = None,
) -> None:
    t = translate or (lambda key, **_kwargs: key)
    target_type = _safe_text(stale_summary.get("target_type"))
    target_id = _safe_text(stale_summary.get("target_id"))
    is_stale = stale_summary.get("is_stale") is True

    with ui.container(border=True):
        ui.markdown(_build_panel_header(t, target_type=target_type, target_id=target_id))
        ui.caption(t("stale.read_only.caption"))

        if is_stale:
            ui.warning(t("stale.needs_refresh"))
        else:
            ui.success(t("stale.clean"))

        _render_primary_reasons(
            ui,
            t=t,
            reasons=_as_text_list(stale_summary.get("primary_reasons")),
        )
        _render_upstream_refs(
            ui,
            t=t,
            upstream_refs=list_of_dicts(stale_summary.get("upstream_refs")),
        )
        _render_stale_marks(
            ui,
            t=t,
            stale_marks=list_of_dicts(stale_summary.get("stale_marks")),
        )


def _build_panel_header(t: Translate, *, target_type: str, target_id: str) -> str:
    target_label = " / ".join(item for item in (target_type, target_id) if item)
    if not target_label:
        target_label = t("stale.target.unknown")
    return (
        "<div style='padding: 0.15rem 0 0.35rem 0;'>"
        "<div style='font-size: 0.76rem; letter-spacing: 0.14em; "
        "text-transform: uppercase; color: #7c6f57;'>Dependency Radar</div>"
        f"<div style='font-size: 1.15rem; font-weight: 700;'>{_escape_html(target_label)}</div>"
        "</div>"
    )


def _render_primary_reasons(ui, *, t: Translate, reasons: list[str]) -> None:
    if not reasons:
        ui.info(t("stale.reasons.empty"))
        return
    ui.markdown(f"**{t('stale.reasons.title')}**")
    for reason in reasons:
        ui.markdown(f"- `{_safe_text(reason)}`")


def _render_upstream_refs(ui, *, t: Translate, upstream_refs: list[dict[str, Any]]) -> None:
    ui.markdown(f"**{t('stale.upstream.title')}**")
    if not upstream_refs:
        ui.caption(t("stale.upstream.empty"))
        return
    for ref in upstream_refs:
        public_ref = _public_subset(ref)
        relation = _join_parts(
            [
                public_ref.get("upstream_type"),
                public_ref.get("upstream_id"),
                _format_version(public_ref.get("upstream_version")),
            ]
        )
        ui.markdown(f"- {relation}")


def _render_stale_marks(ui, *, t: Translate, stale_marks: list[dict[str, Any]]) -> None:
    ui.markdown(f"**{t('stale.marks.title')}**")
    if not stale_marks:
        ui.caption(t("stale.marks.empty"))
        return
    for mark in stale_marks:
        public_mark = _public_subset(mark)
        items = [
            ("reason", public_mark.get("reason") or public_mark.get("reason_code")),
            ("upstream", _join_parts([public_mark.get("upstream_type"), public_mark.get("upstream_id")])),
            ("source_relation", public_mark.get("source_relation") or _metadata_text(public_mark, "via_relation")),
        ]
        text = " | ".join(
            f"{label}: `{_safe_text(value)}`"
            for label, value in items
            if _safe_text(value)
        )
        if text:
            ui.markdown(f"- {text}")


def _public_subset(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in _PRIVATE_FIELDS}


def _metadata_text(value: dict[str, Any], key: str) -> str:
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return _safe_text(metadata.get(key))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return list_of_dicts(value)


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(item) for item in value if _safe_text(item)]


def _format_version(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"v{value}"


def _join_parts(parts: list[Any]) -> str:
    return " / ".join(_safe_text(part) for part in parts if _safe_text(part))


def _safe_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
