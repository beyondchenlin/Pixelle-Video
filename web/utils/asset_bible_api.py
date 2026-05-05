from __future__ import annotations

from typing import Any

import httpx

from api.schemas.storyboard_workbench import validate_public_reference_id
from web.utils.asset_bible_payloads import (
    build_asset_bible_payload,
)


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


def build_prompt_plan_apply_endpoint(
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
        "prompt-plan-apply"
    )


def build_asset_bible_list_endpoint(
    *,
    api_base_url: str,
    project_id: str,
) -> str:
    project_id = _validate_public_reference_id("project_id", project_id)
    return f"{api_base_url.rstrip('/')}/{project_id}/asset-bible"


def build_asset_bible_detail_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
) -> str:
    project_id = _validate_public_reference_id("project_id", project_id)
    asset_bible_id = _validate_public_reference_id("asset_bible_id", asset_bible_id)
    return f"{api_base_url.rstrip('/')}/{project_id}/asset-bible/{asset_bible_id}"


def build_asset_bible_preset_list_endpoint(*, api_base_url: str) -> str:
    return f"{api_base_url.rstrip('/')}/presets/asset-bibles"


def build_asset_bible_preset_detail_endpoint(
    *,
    api_base_url: str,
    preset_id: str,
) -> str:
    preset_id = _validate_public_reference_id("preset_id", preset_id)
    return f"{api_base_url.rstrip('/')}/presets/asset-bibles/{preset_id}"


def build_asset_bible_preset_import_endpoint(
    *,
    api_base_url: str,
    project_id: str,
) -> str:
    project_id = _validate_public_reference_id("project_id", project_id)
    return f"{api_base_url.rstrip('/')}/projects/{project_id}/asset-bible/import-from-preset"


def build_scene_cast_list_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
) -> str:
    project_id = _validate_public_reference_id("project_id", project_id)
    asset_bible_id = _validate_public_reference_id("asset_bible_id", asset_bible_id)
    return f"{api_base_url.rstrip('/')}/{project_id}/asset-bible/{asset_bible_id}/scene-casts"


def build_scene_cast_detail_endpoint(
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
        f"{asset_bible_id}/scene-casts/{scene_cast_id}"
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


def build_prompt_plan_apply_payload(
    *,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    actor_id: str | None = None,
) -> dict[str, str]:
    payload = build_prompt_plan_projection_payload(
        workspace_id=workspace_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if actor_id is not None and actor_id.strip():
        payload["actor_id"] = _validate_public_reference_id("actor_id", actor_id)
    return payload


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


def apply_scene_cast_to_prompt_plan(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    workspace_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    actor_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_prompt_plan_apply_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
    )
    payload = build_prompt_plan_apply_payload(
        workspace_id=workspace_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
        actor_id=actor_id,
    )

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("prompt plan apply response must be a JSON object")
    return data


def create_asset_bible(
    *,
    api_base_url: str,
    project_id: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_asset_bible_list_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
    )

    response = httpx.post(endpoint, json=build_asset_bible_payload(payload), timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible create response must be a JSON object")
    if not isinstance(data.get("asset_bible"), dict):
        raise ValueError("asset bible create response must include asset_bible")
    return data


def load_asset_bible(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_asset_bible_detail_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    params = {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
    }

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible load response must be a JSON object")
    if not isinstance(data.get("asset_bible"), dict):
        raise ValueError("asset bible load response must include asset_bible")
    return data


def save_asset_bible(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_asset_bible_detail_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    request_payload = {
        **build_asset_bible_payload(payload, require_ids=False),
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
        "asset_bible_id": _validate_public_reference_id(
            "asset_bible_id",
            asset_bible_id,
        ),
    }

    response = httpx.put(endpoint, json=request_payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible save response must be a JSON object")
    if not isinstance(data.get("asset_bible"), dict):
        raise ValueError("asset bible save response must include asset_bible")
    return data


def list_asset_bible_presets(
    *,
    api_base_url: str,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    endpoint = build_asset_bible_preset_list_endpoint(api_base_url=api_base_url)

    response = httpx.get(endpoint, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible preset list response must be a JSON object")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("asset bible preset list response must include items")
    return _require_dict_items("items", items)


def import_asset_bible_preset(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    preset_id: str,
    asset_bible_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_asset_bible_preset_import_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
    )
    payload = {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
        "preset_id": _validate_public_reference_id("preset_id", preset_id),
        "conflict_policy": "fail",
    }
    if asset_bible_id is not None and asset_bible_id.strip():
        payload["asset_bible_id"] = _validate_public_reference_id(
            "asset_bible_id",
            asset_bible_id,
        )

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible preset import response must be a JSON object")
    if not isinstance(data.get("asset_bible"), dict):
        raise ValueError("asset bible preset import response must include asset_bible")
    return data


def create_scene_cast(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    character_ids: list[str] | None = None,
    scene_id: str = "",
    prop_ids: list[str] | None = None,
    style_id: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_scene_cast_list_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    payload = _without_blank_values(
        {
            "workspace_id": _validate_public_reference_id(
                "workspace_id",
                workspace_id,
            ),
            "scene_cast_id": _validate_public_reference_id(
                "scene_cast_id",
                scene_cast_id,
            ),
            "storyboard_plan_id": _validate_public_reference_id(
                "storyboard_plan_id",
                storyboard_plan_id,
            ),
            "frame_id": _validate_public_reference_id("frame_id", frame_id),
            "character_ids": _validate_optional_id_list(
                "character_ids",
                character_ids or [],
            ),
            "scene_id": _validate_optional_id("scene_id", scene_id),
            "prop_ids": _validate_optional_id_list("prop_ids", prop_ids or []),
            "style_id": _validate_optional_id("style_id", style_id),
        }
    )

    response = httpx.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("scene cast create response must be a JSON object")
    if not isinstance(data.get("scene_cast"), dict):
        raise ValueError("scene cast create response must include scene_cast")
    return data


def load_scene_cast(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_scene_cast_detail_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
    )
    params = {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
    }

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("scene cast load response must be a JSON object")
    if not isinstance(data.get("scene_cast"), dict):
        raise ValueError("scene cast load response must include scene_cast")
    return data


def save_scene_cast(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    endpoint = build_scene_cast_detail_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
    )
    request_payload = {
        **dict(payload),
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
        "scene_cast_id": _validate_public_reference_id(
            "scene_cast_id",
            scene_cast_id,
        ),
    }

    response = httpx.put(endpoint, json=request_payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("scene cast save response must be a JSON object")
    if not isinstance(data.get("scene_cast"), dict):
        raise ValueError("scene cast save response must include scene_cast")
    return data


def list_asset_bibles(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    endpoint = build_asset_bible_list_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
    )
    params = {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
    }

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("asset bible list response must be a JSON object")
    asset_bibles = data.get("asset_bibles")
    if not isinstance(asset_bibles, list):
        raise ValueError("asset bible list response must include asset_bibles")
    return _require_dict_items("asset_bibles", asset_bibles)


def list_scene_casts(
    *,
    api_base_url: str,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    endpoint = build_scene_cast_list_endpoint(
        api_base_url=api_base_url,
        project_id=project_id,
        asset_bible_id=asset_bible_id,
    )
    params = {
        "workspace_id": _validate_public_reference_id("workspace_id", workspace_id),
    }

    response = httpx.get(endpoint, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("scene cast list response must be a JSON object")
    scene_casts = data.get("scene_casts")
    if not isinstance(scene_casts, list):
        raise ValueError("scene cast list response must include scene_casts")
    return _require_dict_items("scene_casts", scene_casts)


def _require_dict_items(field_name: str, items: list[Any]) -> list[dict[str, Any]]:
    typed_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{field_name}[{index}] must be a JSON object")
        typed_items.append(item)
    return typed_items


def _without_blank_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value != ""}


def _validate_optional_id(field_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    return _validate_public_reference_id(field_name, normalized)


def _validate_optional_id_list(field_name: str, values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if item:
            normalized.append(_validate_public_reference_id(field_name, item))
    return normalized


def _validate_public_reference_id(field_name: str, value: str) -> str:
    return validate_public_reference_id(field_name, value)
