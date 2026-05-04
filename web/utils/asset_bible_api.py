from __future__ import annotations

from typing import Any

import httpx

from api.schemas.storyboard_workbench import validate_public_reference_id


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


def build_asset_bible_payload(
    payload: dict[str, Any],
    *,
    require_ids: bool = True,
) -> dict[str, Any]:
    normalized = dict(payload)
    if require_ids:
        normalized["workspace_id"] = _validate_public_reference_id(
            "workspace_id",
            str(normalized.get("workspace_id", "")),
        )
        normalized["asset_bible_id"] = _validate_public_reference_id(
            "asset_bible_id",
            str(normalized.get("asset_bible_id", "")),
        )
    else:
        normalized.pop("workspace_id", None)
        normalized.pop("asset_bible_id", None)
    ip_profiles = normalized.get("ip_profiles")
    if not isinstance(ip_profiles, list) or not ip_profiles:
        raise ValueError("ip_profiles must include at least one IP profile")
    normalized["ip_profiles"] = [
        _build_ip_profile_payload(item, index=index)
        for index, item in enumerate(ip_profiles)
    ]
    return _without_blank_values(normalized)


def build_asset_bible_draft_payload_from_response(
    asset_bible: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "ip_profiles": [
            _project_ip_profile_response(item)
            for item in _dict_items(asset_bible.get("ip_profiles"))
        ],
        "character_profiles": [
            _project_character_profile_response(item)
            for item in _dict_items(asset_bible.get("character_profiles"))
        ],
        "scene_assets": [
            _project_scene_asset_response(item)
            for item in _dict_items(asset_bible.get("scene_assets"))
        ],
        "prop_assets": [
            _project_prop_asset_response(item)
            for item in _dict_items(asset_bible.get("prop_assets"))
        ],
        "style_profiles": [
            _project_style_profile_response(item)
            for item in _dict_items(asset_bible.get("style_profiles"))
        ],
    }
    metadata = asset_bible.get("metadata")
    if isinstance(metadata, dict):
        payload["metadata"] = dict(metadata)
    return _without_blank_values(payload)


def upsert_ip_profile_draft(
    asset_bible_payload: dict[str, Any],
    ip_profile: dict[str, Any],
) -> dict[str, Any]:
    normalized_profile = _build_ip_profile_payload(ip_profile, index=0)
    normalized = dict(asset_bible_payload)
    normalized.pop("workspace_id", None)
    normalized.pop("asset_bible_id", None)
    target_id = normalized_profile["ip_profile_id"]
    profiles = _dict_items(normalized.get("ip_profiles"))
    for index, profile in enumerate(profiles):
        if profile.get("ip_profile_id") == target_id:
            profiles[index] = normalized_profile
            break
    else:
        profiles.append(normalized_profile)
    normalized["ip_profiles"] = profiles
    return build_asset_bible_payload(normalized, require_ids=False)


def _build_ip_profile_payload(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"ip_profiles[{index}] must be a JSON object")
    profile = dict(value)
    profile["ip_profile_id"] = _validate_public_reference_id(
        "ip_profile_id",
        str(profile.get("ip_profile_id", "")),
    )
    profile["name"] = _require_text("name", str(profile.get("name", "")))
    for field_name in ("logline", "world_hint", "style_hint"):
        if field_name in profile:
            profile[field_name] = _optional_text(str(profile[field_name]))
    return _without_blank_values(profile)


def _project_ip_profile_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "ip_profile_id",
            "name",
            "logline",
            "world_hint",
            "style_hint",
            "identity_lock",
            "identity_anchors",
            "identity_suppression_rules",
            "variable_slots",
            "semantic_boundary",
            "negative_constraints",
            "color_palette",
            "image_text_palette",
            "visible_text_whitelist",
            "metadata",
        ),
    )


def _project_character_profile_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "character_id",
            "display_name",
            "role",
            "visual_description",
            "personality",
            "continuity_notes",
            "metadata",
        ),
    )


def _project_scene_asset_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "scene_id",
            "display_name",
            "visual_description",
            "environment_notes",
            "metadata",
        ),
    )


def _project_prop_asset_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "prop_id",
            "display_name",
            "visual_description",
            "usage_notes",
            "metadata",
        ),
    )


def _project_style_profile_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "style_id",
            "display_name",
            "visual_style",
            "world_style",
            "provider_prompt",
            "negative_prompt",
            "metadata",
        ),
    )


def _copy_allowed_fields(
    value: dict[str, Any],
    allowed_fields: tuple[str, ...],
) -> dict[str, Any]:
    return {field_name: value[field_name] for field_name in allowed_fields if field_name in value}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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
    return {key: value for key, value in payload.items() if value != "" and value != []}


def _require_text(field_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_text(value: str) -> str:
    return value.strip()


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
