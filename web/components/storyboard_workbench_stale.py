from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
    first_text,
)
from web.components.stale_panel import render_stale_target_panel
from web.i18n import tr

Translate = Callable[..., str]
StalePanelRenderer = Callable[..., None]


def build_stale_panel_context(
    session_state: Mapping[str, Any] | None = None,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, str]:
    """Resolve public stale-query context for a frontend panel."""
    state = session_state or {}
    return {
        "workspace_id": first_explicit_text(workspace_id, state.get("workspace_id"), DEFAULT_WORKSPACE_ID),
        "project_id": first_explicit_text(project_id, state.get("project_id"), DEFAULT_PROJECT_ID),
    }


def render_prompt_plan_stale_panel(
    prompt_plan_id: str | None,
    *,
    ui=st,
    translate: Translate = tr,
    panel_renderer: StalePanelRenderer = render_stale_target_panel,
    workspace_id: str | None = None,
    project_id: str | None = None,
    workbench_client=None,
) -> None:
    """Render a read-only stale radar for one frame's PromptPlan."""
    context = build_stale_panel_context(
        getattr(ui, "session_state", None),
        workspace_id=workspace_id,
        project_id=project_id,
    )
    normalized_prompt_plan_id = first_text(prompt_plan_id)
    if not context["workspace_id"] or not context["project_id"] or not normalized_prompt_plan_id:
        ui.caption(translate("stale.workbench.missing_context"))
        return
    if workbench_client is None:
        ui.caption(translate("stale.workbench.unavailable"))
        return

    try:
        response = workbench_client.get_prompt_plan_stale_summary(
            workspace_id=context["workspace_id"],
            project_id=context["project_id"],
            prompt_plan_id=normalized_prompt_plan_id,
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
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "build_stale_panel_context",
    "render_prompt_plan_stale_panel",
]
