from __future__ import annotations

from typing import Any, Callable

import httpx
import streamlit as st

from web.utils.asset_bible_api import (
    build_prompt_plan_projection_payload,
    list_asset_bibles,
    list_scene_casts,
    preview_prompt_plan_projection,
)

Translate = Callable[..., str]


def build_projection_request_payload(
    *,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> dict[str, str]:
    return build_prompt_plan_projection_payload(
        workspace_id=workspace_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )


def render_asset_prompt_plan_projection_preview(
    *,
    ui=st,
    translate: Translate | None = None,
) -> dict[str, Any] | None:
    t = translate or (lambda key, **_kwargs: key)

    ui.markdown("### Stage 2 PromptPlan Projection")
    ui.caption("非持久化预览 / 不保存 / 不触发生成")

    with ui.container(border=True):
        ui.markdown("**Preview-only guardrails**")
        ui.caption(
            "这个入口只用于验证 SceneCast -> PromptPlan 预留字段投影。"
            "它不会保存 PromptPlan，不会标记 stale，也不会触发图片或视频生成。"
        )

    api_base_url = _text_input(
        ui,
        "API Base URL",
        key="api_base_url",
        value="http://localhost:8000/api",
    )

    left, right = ui.columns(2)
    with left:
        project_id = _text_input(ui, "Project ID", key="projection_project_id")
        workspace_id = _text_input(ui, "Workspace ID", key="projection_workspace_id")
        _clear_loaded_context_if_source_changed(
            ui=ui,
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
        )
    with right:
        ui.caption("先输入 Project / Workspace，再加载 AssetBible 和 SceneCast 草稿。")
        if ui.button(t("projection.context.load"), key="projection_context_load"):
            if _has_missing_context(project_id=project_id, workspace_id=workspace_id):
                ui.error("加载上下文前必须填写 project_id 和 workspace_id")
            else:
                _load_projection_context(
                    ui=ui,
                    api_base_url=api_base_url,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )

    asset_bibles = _list_of_dicts(ui.session_state.get("projection_asset_bibles"))
    asset_bible_id = _render_asset_bible_selector(ui, asset_bibles)
    if (
        asset_bibles
        and asset_bible_id
        and ui.session_state.get("projection_scene_cast_asset_bible_id") != asset_bible_id
        and not _has_missing_context(project_id=project_id, workspace_id=workspace_id)
    ):
        _load_scene_cast_context(
            ui=ui,
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_bible_id=asset_bible_id,
        )
    if not asset_bible_id:
        asset_bible_id = _text_input(
            ui,
            "Asset Bible ID",
            key="projection_asset_bible_id",
        )

    scene_casts = _list_of_dicts(ui.session_state.get("projection_scene_casts"))
    scene_cast_id = _render_scene_cast_selector(ui, scene_casts)
    if not scene_cast_id:
        scene_cast_id = _text_input(ui, "Scene Cast ID", key="projection_scene_cast_id")

    left, right = ui.columns(2)
    with left:
        storyboard_plan_id = _text_input(
            ui,
            "Storyboard Plan ID",
            key="projection_storyboard_plan_id",
        )
    with right:
        frame_id = _text_input(ui, "Frame ID", key="projection_frame_id")

    ui.caption(
        "只调用后端 projection preview endpoint；不会写入 AssetBible、PromptPlan，"
        "也不会接入主生成链路。"
    )

    if not ui.button(t("projection.preview.submit"), key="projection_preview_submit"):
        return ui.session_state.get("projection_preview_result")

    missing = [
        label
        for label, value in (
            ("project_id", project_id),
            ("workspace_id", workspace_id),
            ("asset_bible_id", asset_bible_id),
            ("scene_cast_id", scene_cast_id),
            ("storyboard_plan_id", storyboard_plan_id),
            ("frame_id", frame_id),
        )
        if not value.strip()
    ]
    if missing:
        ui.error(f"缺少必填字段: {', '.join(missing)}")
        return None

    try:
        result = preview_prompt_plan_projection(
            api_base_url=api_base_url,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            workspace_id=workspace_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
        )
    except httpx.HTTPStatusError as exc:
        ui.error(f"Projection preview 请求失败: HTTP {exc.response.status_code}")
        return None
    except (httpx.HTTPError, ValueError) as exc:
        ui.error(f"Projection preview 请求失败: {exc}")
        return None

    ui.session_state["projection_preview_result"] = result
    _render_projection_result(result, ui=ui)
    return result


def _load_projection_context(
    *,
    ui=st,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
) -> None:
    try:
        asset_bibles = list_asset_bibles(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
        )
    except httpx.HTTPStatusError as exc:
        ui.error(f"AssetBible 列表加载失败: HTTP {exc.response.status_code}")
        return
    except (httpx.HTTPError, ValueError) as exc:
        ui.error(f"AssetBible 列表加载失败: {exc}")
        return

    ui.session_state["projection_asset_bibles"] = asset_bibles
    ui.session_state["projection_context_source"] = _context_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    asset_bible_id = _select_existing_or_first_id(
        asset_bibles,
        id_field="asset_bible_id",
        current_id=ui.session_state.get("projection_asset_bible_id"),
    )
    if not asset_bible_id:
        ui.session_state["projection_scene_casts"] = []
        ui.caption("没有可用的 AssetBible 草稿；仍可手动输入 ID 调试。")
        return

    ui.session_state["projection_asset_bible_id"] = asset_bible_id
    _load_scene_cast_context(
        ui=ui,
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
    )


def _load_scene_cast_context(
    *,
    ui=st,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
) -> None:
    ui.session_state["projection_scene_casts"] = []
    ui.session_state["projection_scene_cast_asset_bible_id"] = asset_bible_id
    _clear_scene_cast_selection(ui)

    try:
        scene_casts = list_scene_casts(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_bible_id=asset_bible_id,
        )
    except httpx.HTTPStatusError as exc:
        ui.error(f"SceneCast 列表加载失败: HTTP {exc.response.status_code}")
        return
    except (httpx.HTTPError, ValueError) as exc:
        ui.error(f"SceneCast 列表加载失败: {exc}")
        return

    ui.session_state["projection_scene_casts"] = scene_casts
    ui.session_state["projection_scene_cast_asset_bible_id"] = asset_bible_id
    scene_cast_id = _select_existing_or_first_id(
        scene_casts,
        id_field="scene_cast_id",
        current_id=ui.session_state.get("projection_scene_cast_id"),
    )
    if not scene_cast_id:
        ui.caption("当前 AssetBible 下没有 SceneCast 草稿；仍可手动输入 ID 调试。")
        return
    _sync_scene_cast_selection(ui, _find_item(scene_casts, "scene_cast_id", scene_cast_id))


def _render_asset_bible_selector(ui, asset_bibles: list[dict[str, Any]]) -> str:
    options = _item_ids(asset_bibles, "asset_bible_id")
    if not options:
        return ""
    selected_id = ui.selectbox(
        "AssetBible Draft",
        options,
        index=_selected_index(options, ui.session_state.get("projection_asset_bible_id")),
        key="projection_asset_bible_select",
        format_func=lambda item_id: _format_asset_bible_option(
            _find_item(asset_bibles, "asset_bible_id", item_id)
        ),
    )
    if not selected_id:
        return ""
    ui.session_state["projection_asset_bible_id"] = selected_id
    selected = _find_item(asset_bibles, "asset_bible_id", selected_id)
    ui.caption(_format_asset_bible_summary(selected))
    return selected_id


def _render_scene_cast_selector(ui, scene_casts: list[dict[str, Any]]) -> str:
    options = _item_ids(scene_casts, "scene_cast_id")
    if not options:
        return ""
    selected_id = ui.selectbox(
        "SceneCast Draft",
        options,
        index=_selected_index(options, ui.session_state.get("projection_scene_cast_id")),
        key="projection_scene_cast_select",
        format_func=lambda item_id: _format_scene_cast_option(
            _find_item(scene_casts, "scene_cast_id", item_id)
        ),
    )
    if not selected_id:
        return ""
    selected = _find_item(scene_casts, "scene_cast_id", selected_id)
    _sync_scene_cast_selection(ui, selected)
    ui.caption(_format_scene_cast_summary(selected))
    return selected_id


def _render_projection_result(result: dict[str, Any], *, ui=st) -> None:
    projection = _as_dict(result.get("projection"))
    prompt_plan = _as_dict(projection.get("prompt_plan"))
    source = _as_dict(projection.get("source"))

    ui.success("Projection preview 已返回；结果仅用于调试预览，不保存，不触发生成。")
    ui.markdown("#### Projection Workbench")
    left, right = ui.columns(2)
    with left:
        ui.markdown("##### PromptPlan Output")
        ui.code(str(prompt_plan.get("final_prompt") or ""), language="text")
        ui.markdown("##### prompt_sections")
        ui.json(_as_dict(prompt_plan.get("prompt_sections")))
    with right:
        ui.markdown("##### Reserved Asset References")
        ui.markdown(f"- character_ids: {_format_list(prompt_plan.get('character_ids'))}")
        ui.markdown(f"- scene_id: {prompt_plan.get('scene_id') or ''}")
        ui.markdown(f"- prop_ids: {_format_list(prompt_plan.get('prop_ids'))}")
        ui.markdown(f"- style_id: {prompt_plan.get('style_id') or ''}")
        ui.markdown("##### Source Metadata")
        ui.json(source)


def _text_input(ui, label: str, *, key: str, value: str = "") -> str:
    if key in ui.session_state:
        return ui.text_input(label, key=key)
    return ui.text_input(label, value=value, key=key)


def _has_missing_context(*, project_id: str, workspace_id: str) -> bool:
    return not project_id.strip() or not workspace_id.strip()


def _clear_loaded_context_if_source_changed(
    *,
    ui,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
) -> None:
    loaded_source = ui.session_state.get("projection_context_source")
    if not loaded_source:
        return
    current_source = _context_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    if loaded_source != current_source:
        _clear_loaded_context(ui)


def _context_source(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
) -> dict[str, str]:
    return {
        "api_base_url": api_base_url.rstrip("/"),
        "project_id": project_id.strip(),
        "workspace_id": workspace_id.strip(),
    }


def _clear_loaded_context(ui) -> None:
    ui.session_state.pop("projection_context_source", None)
    ui.session_state["projection_asset_bibles"] = []
    ui.session_state["projection_scene_casts"] = []
    ui.session_state.pop("projection_asset_bible_id", None)
    ui.session_state.pop("projection_asset_bible_select", None)
    ui.session_state.pop("projection_scene_cast_asset_bible_id", None)
    ui.session_state.pop("projection_preview_result", None)
    _clear_scene_cast_selection(ui)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _format_list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def _item_ids(items: list[dict[str, Any]], id_field: str) -> list[str]:
    return [
        str(item[id_field])
        for item in items
        if isinstance(item.get(id_field), str) and item[id_field].strip()
    ]


def _selected_index(options: list[str], current_id: Any) -> int:
    if isinstance(current_id, str) and current_id in options:
        return options.index(current_id)
    return 0


def _select_existing_or_first_id(
    items: list[dict[str, Any]],
    *,
    id_field: str,
    current_id: Any,
) -> str:
    options = _item_ids(items, id_field)
    if isinstance(current_id, str) and current_id in options:
        return current_id
    return options[0] if options else ""


def _find_item(
    items: list[dict[str, Any]],
    id_field: str,
    item_id: str,
) -> dict[str, Any]:
    for item in items:
        if item.get(id_field) == item_id:
            return item
    return {}


def _sync_scene_cast_selection(ui, scene_cast: dict[str, Any]) -> None:
    scene_cast_id = scene_cast.get("scene_cast_id")
    storyboard_plan_id = scene_cast.get("storyboard_plan_id")
    frame_id = scene_cast.get("frame_id")
    if isinstance(scene_cast_id, str):
        ui.session_state["projection_scene_cast_id"] = scene_cast_id
    if isinstance(storyboard_plan_id, str):
        ui.session_state["projection_storyboard_plan_id"] = storyboard_plan_id
    if isinstance(frame_id, str):
        ui.session_state["projection_frame_id"] = frame_id


def _clear_scene_cast_selection(ui) -> None:
    for key in (
        "projection_scene_cast_id",
        "projection_scene_cast_select",
        "projection_storyboard_plan_id",
        "projection_frame_id",
    ):
        ui.session_state.pop(key, None)


def _format_asset_bible_option(asset_bible: dict[str, Any]) -> str:
    asset_bible_id = str(asset_bible.get("asset_bible_id") or "")
    ip_name = _first_ip_name(asset_bible)
    if ip_name:
        return f"{asset_bible_id} · {ip_name}"
    return asset_bible_id


def _format_asset_bible_summary(asset_bible: dict[str, Any]) -> str:
    return (
        "AssetBible 摘要: "
        f"characters={len(_list_of_dicts(asset_bible.get('character_profiles')))}, "
        f"scenes={len(_list_of_dicts(asset_bible.get('scene_assets')))}, "
        f"props={len(_list_of_dicts(asset_bible.get('prop_assets')))}, "
        f"styles={len(_list_of_dicts(asset_bible.get('style_profiles')))}"
    )


def _format_scene_cast_option(scene_cast: dict[str, Any]) -> str:
    scene_cast_id = str(scene_cast.get("scene_cast_id") or "")
    storyboard_plan_id = str(scene_cast.get("storyboard_plan_id") or "")
    frame_id = str(scene_cast.get("frame_id") or "")
    if storyboard_plan_id and frame_id:
        return f"{scene_cast_id} · {storyboard_plan_id}/{frame_id}"
    return scene_cast_id


def _format_scene_cast_summary(scene_cast: dict[str, Any]) -> str:
    return (
        "SceneCast 摘要: "
        f"characters={_format_list(scene_cast.get('character_ids'))}; "
        f"scene={scene_cast.get('scene_id') or ''}; "
        f"props={_format_list(scene_cast.get('prop_ids'))}; "
        f"style={scene_cast.get('style_id') or ''}"
    )


def _first_ip_name(asset_bible: dict[str, Any]) -> str:
    ip_profiles = _list_of_dicts(asset_bible.get("ip_profiles"))
    if not ip_profiles:
        return ""
    name = ip_profiles[0].get("name")
    return name if isinstance(name, str) else ""
