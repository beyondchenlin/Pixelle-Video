from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from pixelle_video.platform_context import (
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    first_explicit_text,
)
from web.i18n import tr
from web.utils.streamlit_helpers import find_item, first_text, list_of_dicts, text_list

Translate = Callable[..., str]


def render_ip_workbench_panel(
    *,
    ip_workbench_client,
    workspace_id: str | None,
    project_id: str | None,
    storyboard_plan_id: str | None,
    frame_id: str | None,
    actor_id: str | None = None,
    ui=st,
    translate: Translate = tr,
) -> None:
    context = _build_ip_context(
        getattr(ui, "session_state", None),
        workspace_id=workspace_id,
        project_id=project_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if not _has_required_context(context):
        ui.caption(translate("ip_workbench.panel.missing_context"))
        return
    if ip_workbench_client is None:
        ui.caption(translate("ip_workbench.panel.unavailable"))
        return

    ui.markdown(f"##### {translate('ip_workbench.panel.title')}")
    ui.caption(translate("ip_workbench.panel.help"))

    try:
        asset_response = ip_workbench_client.list_asset_bibles(
            workspace_id=context["workspace_id"],
            project_id=context["project_id"],
        )
    except Exception:
        ui.caption(translate("ip_workbench.panel.unavailable"))
        return

    asset_bibles = list_of_dicts(asset_response.get("asset_bibles"))
    if not asset_bibles:
        ui.caption(translate("ip_workbench.panel.empty_asset_bibles"))
        return

    asset_bible_id = _select_asset_bible(asset_bibles, frame_id=context["frame_id"], ui=ui, translate=translate)
    if not asset_bible_id:
        ui.caption(translate("ip_workbench.panel.empty_asset_bibles"))
        return
    selected_asset_bible = find_item(asset_bibles, "asset_bible_id", asset_bible_id) or {}

    try:
        scene_response = ip_workbench_client.list_scene_casts(
            workspace_id=context["workspace_id"],
            project_id=context["project_id"],
            asset_bible_id=asset_bible_id,
        )
    except Exception:
        ui.caption(translate("ip_workbench.panel.unavailable"))
        return
    scene_casts = list_of_dicts(scene_response.get("scene_casts"))
    if not scene_casts:
        ui.caption(translate("ip_workbench.panel.empty_scene_casts"))
        return

    scene_cast_id = _select_scene_cast(
        scene_casts,
        storyboard_plan_id=context["storyboard_plan_id"],
        frame_id=context["frame_id"],
        ui=ui,
        translate=translate,
    )
    selected_scene_cast = find_item(scene_casts, "scene_cast_id", scene_cast_id) or {}
    _render_asset_summary(selected_asset_bible, ui=ui)
    _render_scene_cast_summary(selected_scene_cast, ui=ui)

    matches_frame = (
        first_text(selected_scene_cast.get("storyboard_plan_id")) == context["storyboard_plan_id"]
        and first_text(selected_scene_cast.get("frame_id")) == context["frame_id"]
    )
    if not matches_frame:
        ui.caption(translate("ip_workbench.panel.frame_mismatch"))

    if not ui.button(
        translate("ip_workbench.panel.apply"),
        key=f"ip_workbench_apply_{context['frame_id']}",
        disabled=not matches_frame,
    ):
        return

    try:
        response = ip_workbench_client.apply_scene_cast_to_prompt_plan(
            workspace_id=context["workspace_id"],
            project_id=context["project_id"],
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=context["storyboard_plan_id"],
            frame_id=context["frame_id"],
            actor_id=first_text(actor_id) or None,
        )
    except Exception:
        ui.error(translate("ip_workbench.panel.apply_failed"))
        return
    application = response.get("application")
    if isinstance(application, Mapping):
        ui.session_state["ip_workbench_last_application"] = dict(application)
    ui.success(translate("ip_workbench.panel.apply_success"))


def _build_ip_context(
    session_state: Mapping[str, Any] | None,
    *,
    workspace_id: str | None,
    project_id: str | None,
    storyboard_plan_id: str | None,
    frame_id: str | None,
) -> dict[str, str]:
    state = session_state or {}
    return {
        "workspace_id": first_explicit_text(workspace_id, state.get("workspace_id"), DEFAULT_WORKSPACE_ID),
        "project_id": first_explicit_text(project_id, state.get("project_id"), DEFAULT_PROJECT_ID),
        "storyboard_plan_id": first_explicit_text(storyboard_plan_id, state.get("storyboard_plan_id")),
        "frame_id": first_explicit_text(frame_id),
    }


def _has_required_context(context: Mapping[str, str]) -> bool:
    return all(
        context.get(field_name)
        for field_name in (
            "workspace_id",
            "project_id",
            "storyboard_plan_id",
            "frame_id",
        )
    )


def _select_asset_bible(
    asset_bibles: list[dict[str, Any]],
    *,
    frame_id: str,
    ui,
    translate: Translate,
) -> str:
    options = [first_text(item.get("asset_bible_id")) for item in asset_bibles]
    options = [option for option in options if option]
    selected = ui.selectbox(
        translate("ip_workbench.panel.asset_bible"),
        options,
        key=f"ip_workbench_asset_bible_select_{frame_id}",
    )
    return first_text(selected)


def _select_scene_cast(
    scene_casts: list[dict[str, Any]],
    *,
    storyboard_plan_id: str,
    frame_id: str,
    ui,
    translate: Translate,
) -> str:
    options = [first_text(item.get("scene_cast_id")) for item in scene_casts]
    options = [option for option in options if option]
    preferred_index = 0
    for index, item in enumerate(scene_casts):
        if (
            first_text(item.get("storyboard_plan_id")) == storyboard_plan_id
            and first_text(item.get("frame_id")) == frame_id
        ):
            preferred_index = index
            break
    selected = ui.selectbox(
        translate("ip_workbench.panel.scene_cast"),
        options,
        index=min(preferred_index, max(0, len(options) - 1)),
        key=f"ip_workbench_scene_cast_select_{frame_id}",
    )
    return first_text(selected)


def _render_asset_summary(asset_bible: Mapping[str, Any], *, ui) -> None:
    asset_bible_id = first_text(asset_bible.get("asset_bible_id"))
    ip_names = [
        first_text(profile.get("name"))
        for profile in list_of_dicts(asset_bible.get("ip_profiles"))
    ]
    summary = " / ".join(item for item in (asset_bible_id, *ip_names) if item)
    if summary:
        ui.caption(summary)


def _render_scene_cast_summary(scene_cast: Mapping[str, Any], *, ui) -> None:
    lines = [
        first_text(scene_cast.get("scene_cast_id")),
        "characters: " + ", ".join(text_list(scene_cast.get("character_ids"))),
        "scene: " + first_text(scene_cast.get("scene_id")),
        "props: " + ", ".join(text_list(scene_cast.get("prop_ids"))),
        "style: " + first_text(scene_cast.get("style_id")),
    ]
    for line in lines:
        if line and not line.endswith(": "):
            ui.caption(line)


def _find_item(items: list[dict[str, Any]], field_name: str, value: str) -> dict[str, Any] | None:
    return find_item(items, field_name, value)


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return list_of_dicts(value)


def _text_list(value: Any) -> list[str]:
    return text_list(value)


def _first_text(*values: Any) -> str:
    return first_text(*values)


__all__ = ["render_ip_workbench_panel"]
