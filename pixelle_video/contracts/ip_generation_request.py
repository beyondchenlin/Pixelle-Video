from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.visual_role_request import VisualRoleControlsContract


FORMAL_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "ip_enabled",
        "ip_asset_bible_id",
        "ip_profile_id",
        "generation_world_hint",
        "visual_expression_mode",
        "visual_structure_mode",
        "visual_participation_mode",
        "visual_role_mode",
        "visual_consistency_mode",
    }
)
HELPER_ONLY_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "ip_profile_world_hint",
        "generation_world_hint_source",
        "generation_world_hint_last_value",
    }
)
REMOVED_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "generation_notes",
        "slot_preference_override",
        "presence_strength",
    }
)


def build_formal_content_ip_world_payload(source: Mapping[str, Any] | None) -> dict[str, Any]:
    values = dict(source or {})
    payload: dict[str, Any] = {"ip_enabled": bool(values.get("ip_enabled"))}
    if payload["ip_enabled"]:
        asset_bible_id = _first_text(values.get("ip_asset_bible_id"))
        profile_id = _first_text(values.get("ip_profile_id"))
        if asset_bible_id:
            payload["ip_asset_bible_id"] = asset_bible_id
        if profile_id:
            payload["ip_profile_id"] = profile_id
        payload.update(VisualRoleControlsContract.from_mapping(values).to_generation_dict())
    world_hint = _first_text(values.get("generation_world_hint"))
    if world_hint:
        payload["generation_world_hint"] = world_hint
    return payload


def dropped_content_ip_world_fields(source: Mapping[str, Any] | None) -> set[str]:
    keys = set(dict(source or {}))
    return keys & (HELPER_ONLY_CONTENT_IP_WORLD_FIELDS | REMOVED_CONTENT_IP_WORLD_FIELDS)


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text
