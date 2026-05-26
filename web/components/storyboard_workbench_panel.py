from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import DEFAULT_WORKSPACE_ID, first_explicit_text
from web.i18n import tr
from web.utils.streamlit_helpers import first_text, list_of_dicts

Translate = Callable[..., str]


def render_storyboard_workbench_panel(
    *,
    workspace_id: str | None,
    storyboard_id: str | None,
    frame_id: str | None,
    artifact_id: str | None,
    selected_version_id: str | None = None,
    actor_id: str | None = None,
    ui=st,
    translate: Translate = tr,
    workbench_client=None,
) -> None:
    """Render the Stage 1B image workbench for one storyboard frame."""
    context = _build_workbench_context(
        getattr(ui, "session_state", None),
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        frame_id=frame_id,
        artifact_id=artifact_id,
    )
    if not _has_required_context(context):
        ui.caption(translate("workbench.panel.missing_context"))
        return
    if workbench_client is None:
        ui.caption(translate("workbench.panel.unavailable"))
        return

    ui.markdown(f"##### {translate('workbench.panel.title')}")
    ui.caption(translate("workbench.panel.help"))

    try:
        response = workbench_client.list_image_candidates(**context)
    except Exception:
        ui.caption(translate("workbench.panel.unavailable"))
        return

    candidates = list_of_dicts(response.get("candidates"))
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
            workbench_client=workbench_client,
        )

    capabilities = _get_capabilities(workbench_client)
    can_regenerate = capabilities.get("can_regenerate_frame_image") is True
    if ui.button(
        translate("workbench.panel.regenerate"),
        key=f"workbench_regenerate_{context['frame_id']}",
        disabled=not can_regenerate,
    ):
        try:
            result = workbench_client.regenerate_frame_image(**context)
        except Exception:
            ui.error(translate("workbench.panel.regenerate_failed"))
            return
        if result.get("success") is False:
            ui.error(translate("workbench.panel.regenerate_failed"))
            return
        task_id = first_text(result.get("task_id"))
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
    workbench_client,
) -> None:
    columns = ui.columns(min(3, max(1, len(candidates))))
    for index, candidate in enumerate(candidates):
        version_id = first_text(candidate.get("version_id"))
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
                        workbench_client=workbench_client,
                    )


def _render_candidate_image(
    candidate: Mapping[str, Any],
    *,
    version_id: str,
    ui,
) -> None:
    image_display = candidate.get("image_display")
    if isinstance(image_display, Mapping):
        if image_display.get("kind") == "url" and first_text(image_display.get("url")):
            ui.image(first_text(image_display.get("url")), caption=version_id, width="stretch")
            return
        if image_display.get("kind") == "bytes" and isinstance(image_display.get("data"), bytes):
            ui.image(image_display["data"], caption=version_id, width="stretch")
            return
    ui.caption(version_id)


def _render_candidate_summary(
    candidate: Mapping[str, Any],
    *,
    version_id: str,
    selected_version_id: str,
    translate: Translate,
    ui,
) -> None:
    status = first_text(candidate.get("status"))
    provider = first_text(candidate.get("provider"))
    trace_event_id = first_text(candidate.get("trace_event_id"))
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
    workbench_client,
) -> None:
    if not version_id:
        return
    if not ui.button(
        translate("workbench.panel.select"),
        key=f"workbench_select_{context['frame_id']}_{version_id}",
    ):
        return
    try:
        result = workbench_client.select_image_candidate(
            **context,
            version_id=version_id,
            actor_id=first_text(actor_id),
        )
    except Exception:
        ui.error(translate("workbench.panel.select_failed"))
        return

    state = result.get("state")
    if isinstance(state, Mapping):
        selected = first_text(state.get("selected_image_version_id"))
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
    workspace_id: str | None,
    storyboard_id: str | None,
    frame_id: str | None,
    artifact_id: str | None,
) -> dict[str, str]:
    state = session_state or {}
    return {
        "workspace_id": first_explicit_text(workspace_id, state.get("workspace_id"), DEFAULT_WORKSPACE_ID),
        "storyboard_id": first_explicit_text(storyboard_id, state.get("storyboard_id")),
        "frame_id": first_explicit_text(frame_id),
        "artifact_id": first_explicit_text(artifact_id),
    }


def _has_required_context(context: Mapping[str, str]) -> bool:
    return all(
        context.get(field_name)
        for field_name in (
            "workspace_id",
            "storyboard_id",
            "frame_id",
            "artifact_id",
        )
    )


def _get_capabilities(workbench_client) -> dict[str, Any]:
    try:
        capabilities = workbench_client.get_capabilities()
    except Exception:
        return {
            "can_regenerate_frame_image": False,
            "regenerate_unavailable_reason": "capability check failed",
        }
    return capabilities if isinstance(capabilities, dict) else {}


def _resolve_selected_version_id(
    session_state: Mapping[str, Any],
    *,
    frame_id: str,
    fallback: str | None,
) -> str:
    selected_versions = session_state.get("workbench_selected_versions")
    if isinstance(selected_versions, Mapping):
        selected = first_text(selected_versions.get(frame_id))
        if selected:
            return selected
    return first_text(fallback)


def _remember_selected_version(session_state: dict[str, Any], *, frame_id: str, version_id: str) -> None:
    selected_versions = session_state.setdefault("workbench_selected_versions", {})
    if isinstance(selected_versions, dict):
        selected_versions[frame_id] = version_id


def _remember_last_task(session_state: dict[str, Any], *, frame_id: str, task_id: str) -> None:
    last_tasks = session_state.setdefault("workbench_last_regeneration_tasks", {})
    if isinstance(last_tasks, dict):
        last_tasks[frame_id] = task_id


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return list_of_dicts(value)


def _first_text(*values: Any) -> str:
    return first_text(*values)


__all__ = ["render_storyboard_workbench_panel"]
