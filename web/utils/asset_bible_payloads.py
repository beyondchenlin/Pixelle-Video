from __future__ import annotations

from typing import Any

from api.schemas.storyboard_workbench import validate_public_reference_id


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
    target_id = normalized_profile["series_visual_signature_profile_id"]
    profiles = _dict_items(normalized.get("ip_profiles"))
    for index, profile in enumerate(profiles):
        if profile.get("series_visual_signature_profile_id") == target_id:
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
    profile["series_visual_signature_profile_id"] = _validate_public_reference_id(
        "series_visual_signature_profile_id",
        str(profile.get("series_visual_signature_profile_id", "")),
    )
    profile["name"] = _require_text("name", str(profile.get("name", "")))
    for field_name in ("logline", "world_hint", "style_hint"):
        if field_name in profile:
            value = profile[field_name]
            profile[field_name] = _optional_text(str(value) if value else "")
    return _without_blank_values(profile)


def _project_ip_profile_response(value: dict[str, Any]) -> dict[str, Any]:
    return _copy_allowed_fields(
        value,
        (
            "series_visual_signature_profile_id",
            "name",
            "logline",
            "world_hint",
            "style_hint",
            "rendering_style",
            "style_scope",
            "exclusive_visual_layer",
            "style_boundary_rules",
            "identity_lock",
            "identity_anchors",
            "identity_suppression_rules",
            "variable_slots",
            "semantic_boundary",
            "negative_constraints",
            "color_palette",
            "image_text_palette",
            "visible_text_whitelist",
            "forbidden_elements",
            "ip_type",
            "visual_summary",
            "minimal_traits",
            "default_slot_preference",
            "role_presets",
            "presence_spectrum",
            "adaptable_slots",
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


def _without_blank_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value != ""}


def _require_text(field_name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_text(value: str) -> str:
    return value.strip()


def _validate_public_reference_id(field_name: str, value: str) -> str:
    return validate_public_reference_id(field_name, value)


__all__ = [
    "build_asset_bible_draft_payload_from_response",
    "build_asset_bible_payload",
    "upsert_ip_profile_draft",
]
