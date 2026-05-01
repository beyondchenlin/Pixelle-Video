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
    return (
        f"{api_base_url.rstrip('/')}/{project_id.strip()}/asset-bible/"
        f"{asset_bible_id.strip()}/scene-casts/{scene_cast_id.strip()}/"
        "prompt-plan-projection"
    )


def build_prompt_plan_projection_payload(
    *,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> dict[str, str]:
    return {
        "workspace_id": workspace_id.strip(),
        "storyboard_plan_id": storyboard_plan_id.strip(),
        "frame_id": frame_id.strip(),
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
