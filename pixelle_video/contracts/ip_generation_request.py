from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pixelle_video.models.series_visual_signature_request import (
    SeriesVisualSignatureControlsContract,
)
from pixelle_video.utils.bool_parsing import coerce_bool

FORMAL_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "series_visual_signature_enabled",
        "identity_reference_required",
        "series_visual_signature_asset_bible_id",
        "series_visual_signature_profile_id",
        "generation_world_hint",
        "series_visual_signature_expression_mode",
        "series_visual_signature_structure_mode",
        "series_visual_signature_participation_mode",
        "series_visual_signature_mode",
        "series_visual_signature_consistency_mode",
        "series_visual_signature_presentation_mode",
        "series_visual_signature_enforcement",
        "series_visual_signature_fallback_enabled",
        "series_visual_signature_fallback_mode",
        "series_visual_signature_min_visibility",
        "series_visual_signature_llm_prompt_assembly_enabled",
        "mandatory_content_bound_anchor",
        "series_visual_signature_contract_version",
        "series_visual_signature_output_validation_mode",
        "series_visual_signature_output_max_attempts",
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
    payload: dict[str, Any] = {
        "series_visual_signature_enabled": coerce_bool(
            values.get("series_visual_signature_enabled"),
            default=False,
        )
    }
    if payload["series_visual_signature_enabled"]:
        asset_bible_id = _first_text(values.get("series_visual_signature_asset_bible_id"))
        profile_id = _first_text(values.get("series_visual_signature_profile_id"))
        if asset_bible_id:
            payload["series_visual_signature_asset_bible_id"] = asset_bible_id
        if profile_id:
            payload["series_visual_signature_profile_id"] = profile_id
        payload.update(
            SeriesVisualSignatureControlsContract.single_pass_from_mapping(
                values
            ).to_generation_dict()
        )
    if payload["series_visual_signature_enabled"] and coerce_bool(values.get("identity_reference_required"), default=False):
        payload["identity_reference_required"] = True
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
