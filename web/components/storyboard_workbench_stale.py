from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from web.components.stale_panel import render_stale_target_panel
from web.i18n import tr
from web.utils.stale_api import get_stale_target_summary

DEFAULT_API_BASE_URL = "http://localhost:8000/api"
Translate = Callable[..., str]
StaleSummaryLoader = Callable[..., dict[str, Any]]
StalePanelRenderer = Callable[..., None]


def build_stale_panel_context(
    session_state: Mapping[str, Any] | None = None,
    *,
    api_base_url: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, str]:
    """Resolve public stale-query context for a frontend panel."""
    state = session_state or {}
    resolved_api_base_url = _first_text(api_base_url, state.get("api_base_url"), DEFAULT_API_BASE_URL)
    return {
        "api_base_url": resolved_api_base_url.rstrip("/"),
        "workspace_id": _first_text(workspace_id, state.get("workspace_id")),
        "project_id": _first_text(project_id, state.get("project_id")),
    }


def render_prompt_plan_stale_panel(
    prompt_plan_id: str | None,
    *,
    ui=st,
    translate: Translate = tr,
    stale_summary_loader: StaleSummaryLoader = get_stale_target_summary,
    panel_renderer: StalePanelRenderer = render_stale_target_panel,
    api_base_url: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> None:
    """Render a read-only stale radar for one frame's PromptPlan."""
    context = build_stale_panel_context(
        getattr(ui, "session_state", None),
        api_base_url=api_base_url,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    normalized_prompt_plan_id = _first_text(prompt_plan_id)
    if not context["workspace_id"] or not context["project_id"] or not normalized_prompt_plan_id:
        ui.caption(translate("stale.workbench.missing_context"))
        return

    try:
        response = stale_summary_loader(
            api_base_url=context["api_base_url"],
            project_id=context["project_id"],
            workspace_id=context["workspace_id"],
            target_type="prompt_plan",
            target_id=normalized_prompt_plan_id,
        )
    except Exception:
        ui.caption(translate("stale.workbench.unavailable"))
        return

    stale_summary = response.get("stale_summary")
    if not isinstance(stale_summary, dict):
        ui.caption(translate("stale.workbench.unavailable"))
        return

    panel_renderer(
        stale_summary=stale_summary,
        ui=ui,
        translate=translate,
    )


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = [
    "DEFAULT_API_BASE_URL",
    "build_stale_panel_context",
    "render_prompt_plan_stale_panel",
]
