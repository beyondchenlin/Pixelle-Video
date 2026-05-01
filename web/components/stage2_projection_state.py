from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

SessionState = MutableMapping[str, Any]


def build_projection_context_source(
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


def clear_projection_preview_result(session_state: SessionState) -> None:
    session_state.pop("projection_preview_result", None)
    session_state.pop("projection_preview_result_source", None)


def clear_projection_scene_cast_selection(session_state: SessionState) -> None:
    for key in (
        "projection_scene_cast_id",
        "projection_scene_cast_select",
        "projection_storyboard_plan_id",
        "projection_frame_id",
    ):
        session_state.pop(key, None)


def clear_projection_asset_selection(session_state: SessionState) -> None:
    session_state["projection_scene_casts"] = []
    session_state.pop("projection_asset_bible_id", None)
    session_state.pop("projection_asset_bible_select", None)
    session_state.pop("projection_scene_cast_asset_bible_id", None)
    clear_projection_preview_result(session_state)
    clear_projection_scene_cast_selection(session_state)


def clear_loaded_projection_context(session_state: SessionState) -> None:
    session_state.pop("projection_context_source", None)
    session_state["projection_asset_bibles"] = []
    clear_projection_asset_selection(session_state)
