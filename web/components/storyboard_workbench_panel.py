from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_API_BASE_URL,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
)
from web.i18n import tr
from web.utils.storyboard_workbench_api import (
    list_storyboard_image_candidates,
    regenerate_storyboard_frame_image,
    select_storyboard_image_candidate,
)

Translate = Callable[..., str]
CandidateLoader = Callable[..., dict[str, Any]]
CandidateSelector = Callable[..., dict[str, Any]]
FrameRegenerator = Callable[..., dict[str, Any]]


def render_storyboard_workbench_panel(
    *,
    workspace_id: str | None,
    storyboard_id: str | None,
    frame_id: str | None,
    artifact_id: str | None,
    selected_version_id: str | None = None,
    api_base_url: str | None = None,
    actor_id: str | None = None,
    ui=st,
    translate: Translate = tr,
    candidate_loader: CandidateLoader = list_storyboard_image_candidates,
    candidate_selector: CandidateSelector = select_storyboard_image_candidate,
    frame_regenerator: FrameRegenerator = regenerate_storyboard_frame_image,
) -> None:
    """Render the Stage 1B image workbench for one storyboard frame."""
    context = _build_workbench_context(
        getattr(ui, "session_state", None),
        api_base_url=api_base_url,
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        artifact_id=artifact_id,
    )
    if not _has_required_context(context):
        ui.caption(translate("workbench.panel.missing_context"))
        return

    ui.markdown(f"##### {translate('workbench.panel.title')}")
    ui.caption(translate("workbench.panel.help"))

    try:
        response = candidate_loader(**context)
    except Exception:
        ui.caption(translate("workbench.panel.unavailable"))
        return

    candidates = _list_of_dicts(response.get("candidates"))
    if not candidates:
        ui.caption(translate("workbench.panel.empty"))
    else:
        _render_candidate_grid(
            candidates,
            context=context,
            selected_version_id=_resolve_selected_version_id(
                ui.session_state,
                frame_id=context["frame_id"],
                fallback=selected_version_id,
            ),
            actor_id=actor_id,
            ui=ui,
            translate=translate,
            candidate_selector=candidate_selector,
        )

    if ui.button(
        translate("workbench.panel.regenerate"),
        key=f"workbench_regenerate_{context['frame_id']}",
    ):
        try:
            result = frame_regenerator(**context)
        except Exception:
            ui.error(translate("workbench.panel.regenerate_failed"))
            return
        task_id = _first_text(result.get("task_id"))
        if task_id:
            _remember_last_task(ui.session_state, frame_id=context["frame_id"], task_id=task_id)
        ui.info(translate("workbench.panel.regenerate_started"))


def _render_candidate_grid(
    candidates: list[dict[str, Any]],
    *,
    context: dict[str, str],
    selected_version_id: str,
    actor_id: str | None,
    ui,
    translate: Translate,
    candidate_selector: CandidateSelector,
) -> None:
    columns = ui.columns(min(3, max(1, len(candidates))))
    for index, candidate in enumerate(candidates):
        version_id = _first_text(candidate.get("version_id"))
        with columns[index % len(columns)]:
            with ui.container(border=True):
                _render_candidate_image(candidate, version_id=version_id, ui=ui)
                _render_candidate_summary(
                    candidate,
                    version_id=version_id,
                    selected_version_id=selected_version_id,
                    translate=translate,
                    ui=ui,
                )
                if version_id != selected_version_id:
                    _render_select_button(
                        context=context,
                        version_id=version_id,
                        actor_id=actor_id,
                        ui=ui,
                        translate=translate,
                        candidate_selector=candidate_selector,
                    )


def _render_candidate_image(candidate: Mapping[str, Any], *, version_id: str, ui) -> None:
    url = _first_text(candidate.get("url"))
    if url:
        ui.image(url, caption=version_id, width="stretch")
    else:
        ui.caption(version_id)


def _render_candidate_summary(
    candidate: Mapping[str, Any],
    *,
    version_id: str,
    selected_version_id: str,
    translate: Translate,
    ui,
) -> None:
    status = _first_text(candidate.get("status"))
    provider = _first_text(candidate.get("provider"))
    trace_event_id = _first_text(candidate.get("trace_event_id"))
    badge = f" - {translate('workbench.panel.selected_badge')}" if version_id == selected_version_id else ""
    ui.markdown(f"**{version_id}**{badge}")
    if status or provider:
        ui.caption(" / ".join(item for item in (status, provider) if item))
    if trace_event_id:
        ui.caption(f"{translate('workbench.panel.trace_label')}: {trace_event_id}")


def _render_select_button(
    *,
    context: dict[str, str],
    version_id: str,
    actor_id: str | None,
    ui,
    translate: Translate,
    candidate_selector: CandidateSelector,
) -> None:
    if not version_id:
        return
    if not ui.button(
        translate("workbench.panel.select"),
        key=f"workbench_select_{context['frame_id']}_{version_id}",
    ):
        return
    try:
        result = candidate_selector(
            **context,
            version_id=version_id,
            actor_id=_first_text(actor_id),
        )
    except Exception:
        ui.error(translate("workbench.panel.select_failed"))
        return

    state = result.get("state")
    if isinstance(state, Mapping):
        selected = _first_text(state.get("selected_image_version_id"))
        if selected:
            _remember_selected_version(
                ui.session_state,
                frame_id=context["frame_id"],
                version_id=selected,
            )
    ui.success(translate("workbench.panel.select_success"))


def _build_workbench_context(
    session_state: Mapping[str, Any] | None,
    *,
    api_base_url: str | None,
    workspace_id: str | None,
    storyboard_id: str | None,
    frame_id: str | None,
    artifact_id: str | None,
) -> dict[str, str]:
    state = session_state or {}
    return {
        "api_base_url": _first_text(api_base_url, state.get("api_base_url"), DEFAULT_API_BASE_URL).rstrip("/"),
        "workspace_id": first_explicit_text(workspace_id, state.get("workspace_id"), DEFAULT_WORKSPACE_ID),
        "storyboard_id": first_explicit_text(storyboard_id, state.get("storyboard_id")),
        "frame_id": first_explicit_text(frame_id),
        "artifact_id": first_explicit_text(artifact_id),
    }


def _has_required_context(context: Mapping[str, str]) -> bool:
    return all(
        context.get(field_name)
        for field_name in (
            "api_base_url",
            "workspace_id",
            "storyboard_id",
            "frame_id",
            "artifact_id",
        )
    )


def _resolve_selected_version_id(
    session_state: Mapping[str, Any],
    *,
    frame_id: str,
    fallback: str | None,
) -> str:
    selected_versions = session_state.get("workbench_selected_versions")
    if isinstance(selected_versions, Mapping):
        selected = _first_text(selected_versions.get(frame_id))
        if selected:
            return selected
    return _first_text(fallback)


def _remember_selected_version(session_state: dict[str, Any], *, frame_id: str, version_id: str) -> None:
    selected_versions = session_state.setdefault("workbench_selected_versions", {})
    if isinstance(selected_versions, dict):
        selected_versions[frame_id] = version_id


def _remember_last_task(session_state: dict[str, Any], *, frame_id: str, task_id: str) -> None:
    last_tasks = session_state.setdefault("workbench_last_regeneration_tasks", {})
    if isinstance(last_tasks, dict):
        last_tasks[frame_id] = task_id


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


__all__ = ["render_storyboard_workbench_panel"]
