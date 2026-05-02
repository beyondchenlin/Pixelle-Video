from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_API_BASE_URL,
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
    first_text,
)
from web.components.stale_panel import render_stale_target_panel
from web.i18n import tr
from web.utils.stale_api import get_stale_target_summary

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
    resolved_api_base_url = first_text(api_base_url, state.get("api_base_url"), DEFAULT_API_BASE_URL)
    return {
        "api_base_url": resolved_api_base_url.rstrip("/"),
        "workspace_id": first_explicit_text(workspace_id, state.get("workspace_id"), DEFAULT_WORKSPACE_ID),
        "project_id": first_explicit_text(project_id, state.get("project_id"), DEFAULT_PROJECT_ID),
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
    normalized_prompt_plan_id = first_text(prompt_plan_id)
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

__all__ = [
    "DEFAULT_API_BASE_URL",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "build_stale_panel_context",
    "render_prompt_plan_stale_panel",
]
