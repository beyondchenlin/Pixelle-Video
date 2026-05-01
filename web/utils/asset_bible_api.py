from __future__ import annotations

from typing import Any

import httpx


def build_prompt_plan_projection_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
) -> str:
    project_id = _validate_public_reference_id("project_id", project_id)
    asset_bible_id = _validate_public_reference_id("asset_bible_id", asset_bible_id)
    scene_cast_id = _validate_public_reference_id("scene_cast_id", scene_cast_id)
    return (
        f"{api_base_url.rstrip('/')}/{project_id}/asset-bible/"
        f"{asset_bible_id}/scene-casts/{scene_cast_id}/"
        "prompt-plan-projection"
    )


def build_prompt_plan_projection_payload(
    *,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> dict[str, str]:
    return {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
        "storyboard_plan_id": _validate_public_reference_id(
            "storyboard_plan_id",
            storyboard_plan_id,
        ),
        "frame_id": _validate_public_reference_id("frame_id", frame_id),
    }


def preview_prompt_plan_projection(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_prompt_plan_projection_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
    )
    payload = build_prompt_plan_projection_payload(
        workspace_id=workspace_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("prompt plan projection response must be a JSON object")
    return data


def _validate_public_reference_id(field_name: str, value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    if _looks_path_like(stripped):
        raise ValueError(f"{field_name} must not be a local path, URL, or storage reference")
    return stripped


def _looks_path_like(value: str) -> bool:
    return (
        "\\" in value
        or "/" in value
        or "://" in value
        or value in {".", ".."}
        or value.startswith("~")
        or (len(value) >= 2 and value[1] == ":" and value[0].isalpha())
    )
