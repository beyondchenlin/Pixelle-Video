from __future__ import annotations

from typing import Any, Callable

import httpx
import streamlit as st

from web.utils.asset_bible_api import (
    build_prompt_plan_projection_payload,
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
        asset_bible_id = _text_input(
            ui,
            "Asset Bible ID",
            key="projection_asset_bible_id",
        )
    with right:
        scene_cast_id = _text_input(ui, "Scene Cast ID", key="projection_scene_cast_id")
        storyboard_plan_id = _text_input(
            ui,
            "Storyboard Plan ID",
            key="projection_storyboard_plan_id",
        )
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


def _render_projection_result(result: dict[str, Any], *, ui=st) -> None:
    projection = _as_dict(result.get("projection"))
    prompt_plan = _as_dict(projection.get("prompt_plan"))
    source = _as_dict(projection.get("source"))

    ui.success("Projection preview 已返回；结果仅用于调试预览，不保存，不触发生成。")
    ui.markdown("#### final_prompt")
    ui.code(str(prompt_plan.get("final_prompt") or ""), language="text")

    ui.markdown("#### prompt_sections")
    ui.json(_as_dict(prompt_plan.get("prompt_sections")))

    ui.markdown("#### Asset references")
    ui.markdown(f"- character_ids: {_format_list(prompt_plan.get('character_ids'))}")
    ui.markdown(f"- scene_id: {prompt_plan.get('scene_id') or ''}")
    ui.markdown(f"- prop_ids: {_format_list(prompt_plan.get('prop_ids'))}")
    ui.markdown(f"- style_id: {prompt_plan.get('style_id') or ''}")

    ui.markdown("#### source")
    ui.json(source)


def _text_input(ui, label: str, *, key: str, value: str = "") -> str:
    if key in ui.session_state:
        return ui.text_input(label, key=key)
    return ui.text_input(label, value=value, key=key)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _format_list(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)
