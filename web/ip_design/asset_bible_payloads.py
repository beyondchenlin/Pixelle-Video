from __future__ import annotations

from typing import Any

from pixelle_video.models.asset_bible import resolve_series_visual_signature_profile_id_from_payload

from .models import (
    AssetBibleDraft,
    CharacterProfileDraft,
    IPProfileDraft,
    PropAssetDraft,
    SceneAssetDraft,
    SceneCastDraft,
    StyleProfileDraft,
)

# ── 新增 _to_model 函数族 ──

def _to_ip_profile_draft(data: dict[str, Any]) -> IPProfileDraft:
    return IPProfileDraft(
        series_visual_signature_profile_id=resolve_series_visual_signature_profile_id_from_payload(data),
        name=data.get("name", ""),
        ip_type=data.get("ip_type") or "cartoon_animal",
        logline=data.get("logline", ""),
        visual_summary=data.get("visual_summary", ""),
        identity_lock=_ensure_str_list(data.get("identity_lock", [])),
        color_palette=data.get("color_palette", {}),
        minimal_traits=_ensure_str_list(data.get("minimal_traits", [])),
        adaptable_slots=_ensure_str_list(data.get("adaptable_slots", [])),
        default_slot_preference=data.get("default_slot_preference") or "prefer_supporting",
        presence_spectrum=_ensure_str_list(data.get("presence_spectrum", [])),
        role_presets=_ensure_str_list(data.get("role_presets", [])),
        negative_constraints=_ensure_str_list(data.get("negative_constraints", [])),
        semantic_boundary=_ensure_str_list(data.get("semantic_boundary", [])),
        identity_suppression_rules=_ensure_str_list(data.get("identity_suppression_rules", [])),
        forbidden_elements=_ensure_str_list(data.get("forbidden_elements", [])),
        visible_text_whitelist=_ensure_str_list(data.get("visible_text_whitelist", [])),
        identity_anchors=_ensure_str_list(data.get("identity_anchors", [])),
        variable_slots=_ensure_str_list(data.get("variable_slots", [])),
        world_hint=data.get("world_hint") or "",
        style_hint=data.get("style_hint") or "",
        image_text_palette=data.get("image_text_palette", {}),
        metadata=data.get("metadata", {}),
    )


def _to_character_profile_draft(data: dict[str, Any]) -> CharacterProfileDraft:
    return CharacterProfileDraft(
        character_id=data.get("character_id", ""),
        display_name=data.get("display_name", ""),
        role=data.get("role", ""),
        visual_description=data.get("visual_description", ""),
        personality=data.get("personality", ""),
        continuity_notes=_ensure_str_list(data.get("continuity_notes", [])),
    )


def _to_scene_asset_draft(data: dict[str, Any]) -> SceneAssetDraft:
    return SceneAssetDraft(
        scene_id=data.get("scene_id", ""),
        display_name=data.get("display_name", ""),
        visual_description=data.get("visual_description", ""),
        environment_notes=data.get("environment_notes", ""),
    )


def _to_prop_asset_draft(data: dict[str, Any]) -> PropAssetDraft:
    return PropAssetDraft(
        prop_id=data.get("prop_id", ""),
        display_name=data.get("display_name", ""),
        visual_description=data.get("visual_description", ""),
        usage_notes=data.get("usage_notes", ""),
    )


def _to_style_profile_draft(data: dict[str, Any]) -> StyleProfileDraft:
    return StyleProfileDraft(
        style_id=data.get("style_id", ""),
        display_name=data.get("display_name", ""),
        visual_style=data.get("visual_style", ""),
        world_style=data.get("world_style", ""),
        provider_prompt=data.get("provider_prompt", ""),
        negative_prompt=data.get("negative_prompt", ""),
    )


def _to_asset_bible_draft(data: dict[str, Any]) -> AssetBibleDraft:
    return AssetBibleDraft(
        asset_bible_id=data.get("asset_bible_id", ""),
        ip_profiles=[_to_ip_profile_draft(p) for p in _ensure_list_of_dicts(data.get("ip_profiles", []))],
        character_profiles=[_to_character_profile_draft(c) for c in _ensure_list_of_dicts(data.get("character_profiles", []))],
        scene_assets=[_to_scene_asset_draft(s) for s in _ensure_list_of_dicts(data.get("scene_assets", []))],
        prop_assets=[_to_prop_asset_draft(p) for p in _ensure_list_of_dicts(data.get("prop_assets", []))],
        style_profiles=[_to_style_profile_draft(s) for s in _ensure_list_of_dicts(data.get("style_profiles", []))],
    )


def _to_scene_cast_draft(data: dict[str, Any]) -> SceneCastDraft:
    return SceneCastDraft(
        scene_cast_id=data.get("scene_cast_id", ""),
        storyboard_plan_id=data.get("storyboard_plan_id", ""),
        frame_id=data.get("frame_id", ""),
        character_ids=_ensure_str_list(data.get("character_ids", [])),
        scene_id=data.get("scene_id", ""),
        prop_ids=_ensure_str_list(data.get("prop_ids", [])),
        style_id=data.get("style_id", ""),
        continuity_notes=_ensure_str_list(data.get("continuity_notes", [])),
    )


def _ensure_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _ensure_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
