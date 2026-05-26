from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FieldId(str, Enum):
    NAME = "name"
    IP_TYPE = "ip_type"
    LOGLINE = "logline"
    VISUAL_SUMMARY = "visual_summary"
    IDENTITY_LOCK = "identity_lock"
    MINIMAL_TRAITS = "minimal_traits"
    ADAPTABLE_SLOTS = "adaptable_slots"
    DEFAULT_SLOT_PREF = "default_slot_preference"
    PRESENCE_SPECTRUM = "presence_spectrum"
    ROLE_PRESETS = "role_presets"
    NEGATIVE_CONSTRAINTS = "negative_constraints"
    SEMANTIC_BOUNDARY = "semantic_boundary"
    ID_SUPPRESSION = "identity_suppression_rules"
    FORBIDDEN = "forbidden_elements"
    VISIBLE_TEXT = "visible_text_whitelist"


class TypedResponse(BaseModel):
    success: bool
    message: str = ""
    errors: list[str] = []


class SaveResponse(TypedResponse):
    pass


class DeleteResponse(TypedResponse):
    pass


class AssetBibleSummary(BaseModel):
    asset_bible_id: str
    character_profiles: list[dict[str, Any]] = []
    scene_assets: list[dict[str, Any]] = []
    prop_assets: list[dict[str, Any]] = []
    style_profiles: list[dict[str, Any]] = []
    ip_profiles: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class ListAssetBiblesResponse(BaseModel):
    success: bool = True
    asset_bibles: list[AssetBibleSummary] = []
    errors: list[str] = []


class ListSceneCastsResponse(BaseModel):
    success: bool = True
    scene_casts: list[dict[str, Any]] = []
    errors: list[str] = []


class PresetSummary(BaseModel):
    preset_id: str
    display_name: str = ""
    description: str = ""


class ListPresetsResponse(BaseModel):
    success: bool = True
    presets: list[PresetSummary] = []
    errors: list[str] = []


class ImportPresetResponse(TypedResponse):
    asset_bible_id: str = ""
    asset_bible: dict[str, Any] = {}


class IPProfileDraft(BaseModel):
    ip_profile_id: str
    name: str
    ip_type: str = "cartoon_animal"
    logline: str = ""
    visual_summary: str = ""
    identity_lock: list[str] = []
    color_palette: dict[str, Any] = Field(default_factory=dict)
    minimal_traits: list[str] = []
    adaptable_slots: list[str] = []
    default_slot_preference: str = "prefer_supporting"
    presence_spectrum: list[str] = []
    role_presets: list[str] = []
    negative_constraints: list[str] = []
    semantic_boundary: list[str] = []
    identity_suppression_rules: list[str] = []
    forbidden_elements: list[str] = []
    visible_text_whitelist: list[str] = []
    identity_anchors: list[str] = Field(default_factory=list)
    variable_slots: list[str] = Field(default_factory=list)
    world_hint: str = ""
    style_hint: str = ""
    image_text_palette: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterProfileDraft(BaseModel):
    character_id: str
    display_name: str = ""
    role: str = ""
    visual_description: str = ""
    personality: str = ""
    continuity_notes: list[str] = []


class SceneAssetDraft(BaseModel):
    scene_id: str
    display_name: str = ""
    visual_description: str = ""
    environment_notes: str = ""


class PropAssetDraft(BaseModel):
    prop_id: str
    display_name: str = ""
    visual_description: str = ""
    usage_notes: str = ""


class StyleProfileDraft(BaseModel):
    style_id: str
    display_name: str = ""
    visual_style: str = ""
    world_style: str = ""
    provider_prompt: str = ""
    negative_prompt: str = ""


class AssetBibleDraft(BaseModel):
    asset_bible_id: str
    ip_profiles: list[IPProfileDraft] = []
    character_profiles: list[CharacterProfileDraft] = []
    scene_assets: list[SceneAssetDraft] = []
    prop_assets: list[PropAssetDraft] = []
    style_profiles: list[StyleProfileDraft] = []


class SceneCastDraft(BaseModel):
    scene_cast_id: str
    storyboard_plan_id: str = ""
    frame_id: str = ""
    character_ids: list[str] = []
    scene_id: str = ""
    prop_ids: list[str] = []
    style_id: str = ""
    continuity_notes: list[str] = []


class ReadinessReport(BaseModel):
    ready: bool
    missing: list[FieldId] = []
    warnings: list[FieldId] = []


__all__ = [
    "FieldId", "TypedResponse", "SaveResponse", "DeleteResponse",
    "AssetBibleSummary", "ListAssetBiblesResponse", "ListSceneCastsResponse",
    "PresetSummary", "ListPresetsResponse", "ImportPresetResponse",
    "IPProfileDraft", "CharacterProfileDraft", "SceneAssetDraft",
    "PropAssetDraft", "StyleProfileDraft", "AssetBibleDraft",
    "SceneCastDraft", "ReadinessReport",
]
