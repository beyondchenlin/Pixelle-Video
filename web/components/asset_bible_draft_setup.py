from __future__ import annotations

from typing import Any, Callable

import httpx
import streamlit as st

from web.components.stage2_projection_state import (
    build_projection_context_source,
    clear_projection_preview_result,
    clear_projection_scene_cast_selection,
)
from web.utils.asset_bible_api import create_asset_bible, create_scene_cast

Translate = Callable[..., str]


def render_asset_bible_draft_setup(
    *,
    ui=st,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    translate: Translate | None = None,
) -> None:
    t = translate or (lambda key, **_kwargs: key)

    with ui.container(border=True):
        ui.markdown(f"### {t('stage2.draft_setup.title')}")
        ui.caption(t("stage2.draft_setup.description"))

        asset_col, cast_col = ui.columns(2)
        with asset_col:
            _render_asset_bible_create_form(
                ui=ui,
                api_base_url=api_base_url,
                project_id=project_id,
                workspace_id=workspace_id,
                translate=t,
            )
        with cast_col:
            _render_scene_cast_create_form(
                ui=ui,
                api_base_url=api_base_url,
                project_id=project_id,
                workspace_id=workspace_id,
                translate=t,
            )


def _render_asset_bible_create_form(
    *,
    ui,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    translate: Translate,
) -> None:
    ui.markdown(f"#### {translate('stage2.asset_bible.section')}")
    asset_bible_id = _text_input(
        ui,
        translate("stage2.asset_bible.id_label"),
        key="stage2_asset_bible_id",
    )
    ip_name = _text_input(
        ui,
        translate("stage2.asset_bible.ip_name_label"),
        key="stage2_ip_name",
    )
    world_hint = _text_input(
        ui,
        translate("stage2.asset_bible.world_hint_label"),
        key="stage2_world_hint",
    )
    style_hint = _text_input(
        ui,
        translate("stage2.asset_bible.style_hint_label"),
        key="stage2_style_hint",
    )

    if not ui.button(
        translate("stage2.asset_bible.create"),
        key="stage2_create_asset_bible_submit",
    ):
        return
    if _missing(project_id, workspace_id, asset_bible_id, ip_name):
        ui.error(translate("stage2.asset_bible.missing_required"))
        return

    try:
        result = create_asset_bible(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_bible_id=asset_bible_id,
            ip_name=ip_name,
            world_hint=world_hint,
            style_hint=style_hint,
        )
    except httpx.HTTPStatusError as exc:
        ui.error(
            translate(
                "stage2.asset_bible.create_failed_http",
                status_code=exc.response.status_code,
            )
        )
        return
    except (httpx.HTTPError, ValueError) as exc:
        ui.error(translate("stage2.asset_bible.create_failed", error=exc))
        return

    asset_bible = _as_dict(result.get("asset_bible"))
    if not asset_bible:
        ui.error(translate("stage2.asset_bible.response_missing_object"))
        return
    try:
        asset_bible_id = _required_response_id(asset_bible, "asset_bible_id")
    except ValueError as exc:
        ui.error(translate("stage2.asset_bible.create_failed", error=exc))
        return
    _stage_asset_bible(
        ui,
        asset_bible,
        asset_bible_id=asset_bible_id,
        context_source=build_projection_context_source(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
        ),
    )
    ui.success(translate("stage2.asset_bible.created"))


def _render_scene_cast_create_form(
    *,
    ui,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    translate: Translate,
) -> None:
    ui.markdown(f"#### {translate('stage2.scene_cast.section')}")
    asset_bible_id = _current_asset_bible_id(ui.session_state)
    if asset_bible_id:
        ui.caption(
            translate(
                "stage2.scene_cast.current_asset_bible",
                asset_bible_id=asset_bible_id,
            )
        )
    else:
        ui.caption(translate("stage2.scene_cast.requires_asset_bible"))

    scene_cast_id = _text_input(
        ui,
        translate("stage2.scene_cast.id_label"),
        key="stage2_scene_cast_id",
    )
    storyboard_plan_id = _text_input(
        ui,
        translate("stage2.scene_cast.storyboard_plan_id_label"),
        key="stage2_storyboard_plan_id",
    )
    frame_id = _text_input(
        ui,
        translate("stage2.scene_cast.frame_id_label"),
        key="stage2_frame_id",
    )
    character_ids = _text_input(
        ui,
        translate("stage2.scene_cast.character_ids_label"),
        key="stage2_character_ids",
    )
    scene_id = _text_input(
        ui,
        translate("stage2.scene_cast.scene_id_label"),
        key="stage2_scene_id",
    )
    prop_ids = _text_input(
        ui,
        translate("stage2.scene_cast.prop_ids_label"),
        key="stage2_prop_ids",
    )
    style_id = _text_input(
        ui,
        translate("stage2.scene_cast.style_id_label"),
        key="stage2_style_id",
    )

    if not ui.button(
        translate("stage2.scene_cast.create"),
        key="stage2_create_scene_cast_submit",
    ):
        return
    if _missing(
        project_id, workspace_id, asset_bible_id, scene_cast_id, storyboard_plan_id, frame_id
    ):
        ui.error(translate("stage2.scene_cast.missing_required"))
        return

    try:
        result = create_scene_cast(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
            character_ids=_split_csv(character_ids),
            scene_id=scene_id,
            prop_ids=_split_csv(prop_ids),
            style_id=style_id,
        )
    except httpx.HTTPStatusError as exc:
        ui.error(
            translate(
                "stage2.scene_cast.create_failed_http",
                status_code=exc.response.status_code,
            )
        )
        return
    except (httpx.HTTPError, ValueError) as exc:
        ui.error(translate("stage2.scene_cast.create_failed", error=exc))
        return

    scene_cast = _as_dict(result.get("scene_cast"))
    if not scene_cast:
        ui.error(translate("stage2.scene_cast.response_missing_object"))
        return
    try:
        scene_cast_ids = {
            field_name: _required_response_id(scene_cast, field_name)
            for field_name in (
                "scene_cast_id",
                "storyboard_plan_id",
                "frame_id",
                "asset_bible_id",
            )
        }
    except ValueError as exc:
        ui.error(translate("stage2.scene_cast.create_failed", error=exc))
        return
    _stage_scene_cast(
        ui,
        scene_cast,
        scene_cast_ids=scene_cast_ids,
        context_source=build_projection_context_source(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
        ),
    )
    ui.success(translate("stage2.scene_cast.created"))


def _stage_asset_bible(
    ui,
    asset_bible: dict[str, Any],
    *,
    asset_bible_id: str,
    context_source: dict[str, str],
) -> None:
    ui.session_state["projection_context_source"] = context_source
    ui.session_state["projection_asset_bible_id"] = asset_bible_id
    ui.session_state["projection_asset_bible_select"] = asset_bible_id
    ui.session_state["projection_asset_bibles"] = _upsert_by_id(
        _list_of_dicts(ui.session_state.get("projection_asset_bibles")),
        asset_bible,
        "asset_bible_id",
    )
    ui.session_state["projection_scene_casts"] = []
    ui.session_state.pop("projection_scene_cast_asset_bible_id", None)
    clear_projection_scene_cast_selection(ui.session_state)
    clear_projection_preview_result(ui.session_state)


def _stage_scene_cast(
    ui,
    scene_cast: dict[str, Any],
    *,
    scene_cast_ids: dict[str, str],
    context_source: dict[str, str],
) -> None:
    ui.session_state["projection_context_source"] = context_source
    ui.session_state["projection_asset_bible_id"] = scene_cast_ids["asset_bible_id"]
    ui.session_state["projection_asset_bible_select"] = scene_cast_ids["asset_bible_id"]
    ui.session_state["projection_scene_cast_id"] = scene_cast_ids["scene_cast_id"]
    ui.session_state["projection_scene_cast_select"] = scene_cast_ids["scene_cast_id"]
    ui.session_state["projection_storyboard_plan_id"] = scene_cast_ids["storyboard_plan_id"]
    ui.session_state["projection_frame_id"] = scene_cast_ids["frame_id"]
    ui.session_state["projection_scene_cast_asset_bible_id"] = scene_cast_ids["asset_bible_id"]
    ui.session_state["projection_scene_casts"] = _upsert_by_id(
        _list_of_dicts(ui.session_state.get("projection_scene_casts")),
        scene_cast,
        "scene_cast_id",
    )
    clear_projection_preview_result(ui.session_state)


def _text_input(ui, label: str, *, key: str, value: str = "") -> str:
    if key in ui.session_state:
        return ui.text_input(label, key=key)
    return ui.text_input(label, value=value, key=key)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _missing(*values: str) -> bool:
    return any(not value.strip() for value in values)


def _current_asset_bible_id(session_state: Any) -> str:
    selected_id = session_state.get("projection_asset_bible_select")
    if isinstance(selected_id, str) and selected_id.strip():
        return selected_id.strip()
    stored_id = session_state.get("projection_asset_bible_id")
    if isinstance(stored_id, str):
        return stored_id.strip()
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _required_response_id(item: dict[str, Any], field_name: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"response missing {field_name}")
    return value


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _upsert_by_id(
    items: list[dict[str, Any]],
    item: dict[str, Any],
    id_field: str,
) -> list[dict[str, Any]]:
    item_id = item.get(id_field)
    return [
        *(existing for existing in items if existing.get(id_field) != item_id),
        item,
    ]
