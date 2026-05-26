from __future__ import annotations

from typing import Any, Callable

import httpx
import streamlit as st

from pixelle_video.platform_context import DEFAULT_API_BASE_URL
from web.components.asset_bible_draft_setup import render_asset_bible_draft_setup
from web.components.stage2_projection_state import (
    build_projection_context_source,
    clear_loaded_projection_context,
    clear_projection_asset_selection,
    clear_projection_preview_result,
    clear_projection_scene_cast_selection,
)
from web.utils.asset_bible_api import (
    build_prompt_plan_projection_payload,
    list_asset_bibles,
    list_scene_casts,
    preview_prompt_plan_projection,
)
from web.utils.streamlit_helpers import list_of_dicts, find_item

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
    ui.caption("PromptPlan 投影预览 / 不保存投影结果 / 不触发生成")

    with ui.container(border=True):
        ui.markdown("**Preview-only guardrails**")
        ui.caption(
            "这个入口只用于验证 SceneCast -> PromptPlan 预留字段投影。"
            "它不会保存投影后的 PromptPlan，不会标记 stale，也不会触发图片或视频生成。"
        )

    _render_step_header(
        ui,
        1,
        "Context",
        "Load project/workspace context before selecting Stage2 assets.",
    )

    api_base_url = _text_input(
        ui,
        "API Base URL",
        key="api_base_url",
        value=DEFAULT_API_BASE_URL,
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

    context_loaded = _is_context_loaded(
        ui.session_state,
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    if not context_loaded:
        clear_projection_preview_result(ui.session_state)
        _render_locked_step(
            ui,
            2,
            "AssetBible",
            "Load context before selecting AssetBible.",
        )
        _render_locked_step(
            ui,
            3,
            "SceneCast",
            "Load context before selecting SceneCast.",
        )
        _render_locked_step(
            ui,
            4,
            "Storyboard Frame",
            "Load context before choosing a storyboard frame.",
        )
        _render_locked_step(
            ui,
            5,
            "Preview",
            "Preview is locked until context, AssetBible, SceneCast, storyboard, and frame are ready.",
        )
        return None

    _render_step_header(ui, 2, "AssetBible", "Select or create the AssetBible draft.")
    render_asset_bible_draft_setup(
        ui=ui,
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        translate=t,
    )

    asset_bibles = list_of_dicts(ui.session_state.get("projection_asset_bibles"))
    asset_bible_id = _render_asset_bible_selector(ui, asset_bibles)
    if not asset_bible_id:
        asset_bible_id = _existing_projection_id(ui.session_state, "projection_asset_bible_id")
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

    scene_casts = list_of_dicts(ui.session_state.get("projection_scene_casts"))
    scene_cast_id = _render_scene_cast_selector(ui, scene_casts)
    if not scene_cast_id:
        scene_cast_id = _existing_projection_id(ui.session_state, "projection_scene_cast_id")
    if not asset_bible_id or not scene_cast_id:
        debug_ids = _render_advanced_debug_ids(
            ui,
            current_asset_bible_id=asset_bible_id,
            current_scene_cast_id=scene_cast_id,
        )
        asset_bible_id = asset_bible_id or debug_ids["asset_bible_id"]
        scene_cast_id = scene_cast_id or debug_ids["scene_cast_id"]
        if not asset_bible_id or not scene_cast_id:
            ui.caption(
                "普通预览流程需要先加载或创建 AssetBible / SceneCast 草稿；"
                "手动 ID 只保留在 Advanced Debug 中。"
            )

    selected_scene_cast = find_item(scene_casts, "scene_cast_id", scene_cast_id) or {}
    frame_status, _frame_ready = _frame_status_for_scene_cast(
        selected_scene_cast,
        storyboard_plan_id=_existing_projection_id(
            ui.session_state,
            "projection_storyboard_plan_id",
        ),
        frame_id=_existing_projection_id(ui.session_state, "projection_frame_id"),
    )
    _render_step_header(ui, 4, "Storyboard Frame", frame_status)
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
        "只调用后端 projection preview endpoint；不会保存投影后的 PromptPlan，"
        "不会标记 stale，也不会接入主生成链路。"
    )
    _clear_preview_result_if_request_source_changed(
        ui=ui,
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )

    _render_step_header(ui, 5, "Preview", "Send a preview-only projection request.")
    _render_request_summary(
        ui,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if not ui.button(t("projection.preview.submit"), key="projection_preview_submit"):
        cached_result = ui.session_state.get("projection_preview_result")
        if isinstance(cached_result, dict):
            _render_projection_result(cached_result, ui=ui)
            return cached_result
        return None

    validation_error = _validate_projection_flow(
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
        scene_cast=selected_scene_cast,
    )
    if validation_error:
        ui.error(validation_error)
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
    ui.session_state["projection_preview_result_source"] = _preview_result_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
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
    ui.session_state["projection_context_source"] = build_projection_context_source(
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
        clear_projection_asset_selection(ui.session_state)
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
    clear_projection_scene_cast_selection(ui.session_state)
    clear_projection_preview_result(ui.session_state)

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
    _sync_scene_cast_selection(ui, find_item(scene_casts, "scene_cast_id", scene_cast_id) or {})


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
            find_item(asset_bibles, "asset_bible_id", item_id) or {}
        ),
    )
    if not selected_id:
        return ""
    ui.session_state["projection_asset_bible_id"] = selected_id
    selected = find_item(asset_bibles, "asset_bible_id", selected_id) or {}
    ui.caption(_format_asset_bible_summary(selected))
    return selected_id


def _render_scene_cast_selector(ui, scene_casts: list[dict[str, Any]]) -> str:
    _render_step_header(ui, 3, "SceneCast", "Select the SceneCast draft for this preview.")
    options = _item_ids(scene_casts, "scene_cast_id")
    if not options:
        return ""
    previous_selected_id = _existing_projection_id(ui.session_state, "projection_scene_cast_id")
    selected_id = ui.selectbox(
        "SceneCast Draft",
        options,
        index=_selected_index(options, ui.session_state.get("projection_scene_cast_id")),
        key="projection_scene_cast_select",
        format_func=lambda item_id: _format_scene_cast_option(
            find_item(scene_casts, "scene_cast_id", item_id) or {}
        ),
    )
    if not selected_id:
        return ""
    selected = find_item(scene_casts, "scene_cast_id", selected_id) or {}
    _sync_scene_cast_selection(
        ui,
        selected,
        force_frame_sync=selected_id != previous_selected_id,
    )
    ui.caption(_format_scene_cast_summary(selected))
    return selected_id


def _render_step_header(ui, number: int, title: str, status: str) -> None:
    ui.markdown(f"#### {number}. {title}")
    if status:
        ui.caption(status)


def _render_locked_step(ui, number: int, title: str, message: str) -> None:
    _render_step_header(ui, number, title, "Locked")
    ui.caption(message)


def _frame_status_for_scene_cast(
    scene_cast: dict[str, Any],
    *,
    storyboard_plan_id: str,
    frame_id: str,
) -> tuple[str, bool]:
    expected_storyboard = _safe_text(scene_cast.get("storyboard_plan_id"))
    expected_frame = _safe_text(scene_cast.get("frame_id"))
    current_storyboard = storyboard_plan_id.strip()
    current_frame = frame_id.strip()
    if expected_storyboard and expected_frame:
        if current_storyboard == expected_storyboard and current_frame == expected_frame:
            return (
                "Storyboard/frame derived from selected SceneCast: "
                f"{current_storyboard} / {current_frame}",
                True,
            )
        return ("Storyboard/frame no longer matches selected SceneCast.", False)
    if current_storyboard and current_frame:
        return (
            "Storyboard/frame manually completed because SceneCast did not provide both values.",
            True,
        )
    return ("Storyboard/frame is required before preview.", False)


def _validate_projection_flow(
    *,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    scene_cast: dict[str, Any],
) -> str | None:
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
        return f"缺少必填字段: {', '.join(missing)}"
    _message, is_valid = _frame_status_for_scene_cast(
        scene_cast,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if not is_valid:
        return "Storyboard/frame no longer matches selected SceneCast."
    return None


def _render_request_summary(
    ui,
    *,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> None:
    ui.markdown("##### Current request summary")
    ui.markdown(f"- Context: {project_id.strip()} / {workspace_id.strip()}")
    ui.markdown(f"- AssetBible: {asset_bible_id.strip()}")
    ui.markdown(f"- SceneCast: {scene_cast_id.strip()}")
    ui.markdown(
        f"- Storyboard Frame: {storyboard_plan_id.strip()} / {frame_id.strip()}"
    )
    ui.caption(
        "Preview-only: no PromptPlan save, no stale marking, no image/video generation."
    )


def _render_advanced_debug_ids(
    ui,
    *,
    current_asset_bible_id: str,
    current_scene_cast_id: str,
) -> dict[str, str]:
    if not ui.session_state.get("projection_advanced_debug"):
        return {"asset_bible_id": "", "scene_cast_id": ""}
    with ui.expander("Advanced Debug", expanded=False):
        ui.caption("仅用于调试已有后端资源 ID；普通预览应通过加载或创建草稿获得选择项。")
        asset_bible_id = current_asset_bible_id or _text_input(
            ui,
            "Asset Bible ID",
            key="projection_asset_bible_id",
        )
        scene_cast_id = current_scene_cast_id or _text_input(
            ui,
            "Scene Cast ID",
            key="projection_scene_cast_id",
        )
    return {
        "asset_bible_id": asset_bible_id,
        "scene_cast_id": scene_cast_id,
    }


def _render_projection_result(result: dict[str, Any], *, ui=st) -> None:
    projection = _as_dict(result.get("projection"))
    prompt_plan = _as_dict(projection.get("prompt_plan"))
    source = _as_dict(projection.get("source"))
    prompt_sections = _as_dict(prompt_plan.get("prompt_sections"))

    ui.success("Projection preview 已返回；投影后的 PromptPlan 仅用于预览，不保存，不触发生成。")
    ui.markdown("#### Projection Lab")
    ui.caption("只读投影预览：确认 SceneCast 是否正确落到 PromptPlan 预留资产字段。")
    left, right = ui.columns(2)
    with left:
        ui.markdown("##### IP Context")
        ui.markdown(f"- AssetBible: {_safe_text(source.get('asset_bible_id'))}")
        ui.markdown(f"- SceneCast: {_safe_text(source.get('scene_cast_id'))}")
        ui.markdown(f"- PromptPlan: {_safe_text(source.get('prompt_plan_id'))}")
        ui.markdown("##### Prompt Output")
        ui.markdown(_format_prompt_preview(prompt_plan.get("final_prompt")))
    with right:
        ui.markdown("##### Asset Locks")
        ui.markdown(f"- Characters: {_format_list(prompt_plan.get('character_ids'))}")
        ui.markdown(f"- Scene: {_safe_text(prompt_plan.get('scene_id'))}")
        ui.markdown(f"- Props: {_format_list(prompt_plan.get('prop_ids'))}")
        ui.markdown(f"- Style: {_safe_text(prompt_plan.get('style_id'))}")
        ui.markdown("##### Source Trace")
        ui.markdown(
            "- "
            + " / ".join(
                item
                for item in (
                    _safe_text(source.get("asset_bible_id")),
                    _safe_text(source.get("scene_cast_id")),
                    _safe_text(source.get("prompt_plan_id")),
                )
                if item
            )
        )

    if prompt_sections:
        ui.markdown("##### Prompt Sections")
        for key, value in prompt_sections.items():
            ui.markdown(f"- {_safe_text(key)}: {_safe_text(value)}")


def _text_input(ui, label: str, *, key: str, value: str = "") -> str:
    if key in ui.session_state:
        return ui.text_input(label, key=key)
    return ui.text_input(label, value=value, key=key)


def _existing_projection_id(session_state: dict[str, Any], key: str) -> str:
    value = session_state.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _has_missing_context(*, project_id: str, workspace_id: str) -> bool:
    return not project_id.strip() or not workspace_id.strip()


def _is_context_loaded(
    session_state: dict[str, Any],
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
) -> bool:
    loaded_source = session_state.get("projection_context_source")
    if not loaded_source:
        return False
    return loaded_source == build_projection_context_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )


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
    current_source = build_projection_context_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    if loaded_source != current_source:
        clear_loaded_projection_context(ui.session_state)


def _clear_preview_result_if_request_source_changed(
    *,
    ui,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> None:
    result_source = ui.session_state.get("projection_preview_result_source")
    if not result_source:
        if "projection_preview_result" in ui.session_state:
            clear_projection_preview_result(ui.session_state)
        return
    current_source = _preview_result_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if result_source != current_source:
        clear_projection_preview_result(ui.session_state)


def _preview_result_source(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> dict[str, str]:
    return {
        **build_projection_context_source(
            api_base_url=api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
        ),
        "asset_bible_id": asset_bible_id.strip(),
        "scene_cast_id": scene_cast_id.strip(),
        "storyboard_plan_id": storyboard_plan_id.strip(),
        "frame_id": frame_id.strip(),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    return list_of_dicts(value)


def _format_list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def _safe_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _format_prompt_preview(value: Any) -> str:
    prompt = _safe_text(value)
    if not prompt:
        return "_No final prompt returned._"
    return f"> {prompt}"


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
    return find_item(items, id_field, item_id) or {}


def _sync_scene_cast_selection(
    ui,
    scene_cast: dict[str, Any],
    *,
    force_frame_sync: bool = True,
) -> None:
    scene_cast_id = scene_cast.get("scene_cast_id")
    storyboard_plan_id = scene_cast.get("storyboard_plan_id")
    frame_id = scene_cast.get("frame_id")
    if isinstance(scene_cast_id, str):
        ui.session_state["projection_scene_cast_id"] = scene_cast_id
    if isinstance(storyboard_plan_id, str) and (
        force_frame_sync
        or not _existing_projection_id(ui.session_state, "projection_storyboard_plan_id")
    ):
        ui.session_state["projection_storyboard_plan_id"] = storyboard_plan_id
    if isinstance(frame_id, str) and (
        force_frame_sync or not _existing_projection_id(ui.session_state, "projection_frame_id")
    ):
        ui.session_state["projection_frame_id"] = frame_id


def _format_asset_bible_option(asset_bible: dict[str, Any]) -> str:
    asset_bible_id = str(asset_bible.get("asset_bible_id") or "")
    ip_name = _first_ip_name(asset_bible)
    if ip_name:
        return f"{asset_bible_id} · {ip_name}"
    return asset_bible_id


def _format_asset_bible_summary(asset_bible: dict[str, Any]) -> str:
    return (
        "AssetBible 摘要: "
        f"characters={len(list_of_dicts(asset_bible.get('character_profiles')))}, "
        f"scenes={len(list_of_dicts(asset_bible.get('scene_assets')))}, "
        f"props={len(list_of_dicts(asset_bible.get('prop_assets')))}, "
        f"styles={len(list_of_dicts(asset_bible.get('style_profiles')))}"
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
    ip_profiles = list_of_dicts(asset_bible.get("ip_profiles"))
    if not ip_profiles:
        return ""
    name = ip_profiles[0].get("name")
    return name if isinstance(name, str) else ""
