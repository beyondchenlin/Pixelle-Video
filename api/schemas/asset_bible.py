from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.storyboard_workbench import validate_public_reference_id
from pixelle_video.models.asset_bible import (
    AssetBible,
    CharacterProfile,
    IPProfile,
    PropAsset,
    SceneAsset,
    StyleProfile,
)
from pixelle_video.models.scene_cast import SceneCast


class PublicMetadataModel(BaseModel):
    @field_validator("metadata", check_fields=False)
    @classmethod
    def validate_public_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_path_like_metadata("metadata", value)
        _reject_text_rendering_metadata("metadata", value)
        return value


class CharacterProfileDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    display_name: str
    role: str | None = None
    visual_description: str | None = None
    personality: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("character_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class SceneAssetDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    display_name: str
    visual_description: str | None = None
    environment_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scene_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class PropAssetDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    prop_id: str
    display_name: str
    visual_description: str | None = None
    usage_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prop_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class StyleProfileDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    style_id: str
    display_name: str
    visual_style: str
    world_style: str | None = None
    provider_prompt: str | None = None
    negative_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("style_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class IPProfileDraft(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    ip_profile_id: str
    name: str
    logline: str | None = None
    world_hint: str | None = None
    style_hint: str | None = None
    identity_lock: list[str] = Field(default_factory=list)
    identity_anchors: list[str] = Field(default_factory=list)
    identity_suppression_rules: list[str] = Field(default_factory=list)
    variable_slots: list[str] = Field(default_factory=list)
    semantic_boundary: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    color_palette: dict[str, Any] = Field(default_factory=dict)
    image_text_palette: dict[str, Any] = Field(default_factory=dict)
    visible_text_whitelist: list[str] = Field(default_factory=list)
    ip_type: str | None = None
    visual_summary: str | None = None
    minimal_traits: list[str] = Field(default_factory=list)
    default_slot_preference: str | None = None
    role_presets: list[str] = Field(default_factory=list)
    presence_spectrum: list[str] = Field(default_factory=list)
    adaptable_slots: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_profile_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator(
        "identity_lock",
        "identity_anchors",
        "identity_suppression_rules",
        "variable_slots",
        "semantic_boundary",
        "negative_constraints",
        "visible_text_whitelist",
        "minimal_traits",
        "role_presets",
        "presence_spectrum",
        "adaptable_slots",
    )
    @classmethod
    def validate_text_list(cls, value: list[str], info) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if len(cleaned) != len(value):
            raise ValueError(f"{info.field_name} must not include blank values")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"{info.field_name} must not include duplicate values")
        return cleaned

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value

    def to_model(self, *, workspace_id: str, project_id: str) -> IPProfile:
        return IPProfile(
            ip_profile_id=self.ip_profile_id,
            workspace_id=workspace_id,
            project_id=project_id,
            name=self.name,
            logline=self.logline,
            world_hint=self.world_hint,
            style_hint=self.style_hint,
            identity_lock=tuple(self.identity_lock),
            identity_anchors=tuple(self.identity_anchors),
            identity_suppression_rules=tuple(self.identity_suppression_rules),
            variable_slots=tuple(self.variable_slots),
            semantic_boundary=tuple(self.semantic_boundary),
            negative_constraints=tuple(self.negative_constraints),
            ip_type=self.ip_type,
            visual_summary=self.visual_summary,
            minimal_traits=tuple(self.minimal_traits),
            default_slot_preference=self.default_slot_preference,
            role_presets=tuple(self.role_presets),
            presence_spectrum=tuple(self.presence_spectrum),
            adaptable_slots=tuple(self.adaptable_slots),
            color_palette=self.color_palette,
            image_text_palette=self.image_text_palette,
            visible_text_whitelist=tuple(self.visible_text_whitelist),
            metadata=self.metadata,
        )


class AssetBibleDraftRequest(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    asset_bible_id: str
    ip_profiles: list[IPProfileDraft] = Field(min_length=1)
    character_profiles: list[CharacterProfileDraft] = Field(default_factory=list)
    scene_assets: list[SceneAssetDraft] = Field(default_factory=list)
    prop_assets: list[PropAssetDraft] = Field(default_factory=list)
    style_profiles: list[StyleProfileDraft] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workspace_id", "asset_bible_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("ip_profiles")
    @classmethod
    def validate_ip_profiles(cls, value: list[IPProfileDraft]) -> list[IPProfileDraft]:
        ids = [item.ip_profile_id for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("ip_profiles must not include duplicate ip_profile_id")
        return value

    def to_model(self, *, project_id: str) -> AssetBible:
        ip_profiles = tuple(
            profile.to_model(workspace_id=self.workspace_id, project_id=project_id)
            for profile in self.ip_profiles
        )
        return AssetBible(
            asset_bible_id=self.asset_bible_id,
            workspace_id=self.workspace_id,
            project_id=project_id,
            ip_profiles=ip_profiles,
            character_profiles=tuple(
                CharacterProfile(
                    character_id=profile.character_id,
                    workspace_id=self.workspace_id,
                    project_id=project_id,
                    display_name=profile.display_name,
                    role=profile.role,
                    visual_description=profile.visual_description,
                    personality=profile.personality,
                    continuity_notes=tuple(profile.continuity_notes),
                    metadata=profile.metadata,
                )
                for profile in self.character_profiles
            ),
            scene_assets=tuple(
                SceneAsset(
                    scene_id=asset.scene_id,
                    workspace_id=self.workspace_id,
                    project_id=project_id,
                    display_name=asset.display_name,
                    visual_description=asset.visual_description,
                    environment_notes=tuple(asset.environment_notes),
                    metadata=asset.metadata,
                )
                for asset in self.scene_assets
            ),
            prop_assets=tuple(
                PropAsset(
                    prop_id=asset.prop_id,
                    workspace_id=self.workspace_id,
                    project_id=project_id,
                    display_name=asset.display_name,
                    visual_description=asset.visual_description,
                    usage_notes=tuple(asset.usage_notes),
                    metadata=asset.metadata,
                )
                for asset in self.prop_assets
            ),
            style_profiles=tuple(
                StyleProfile(
                    style_id=profile.style_id,
                    workspace_id=self.workspace_id,
                    project_id=project_id,
                    display_name=profile.display_name,
                    visual_style=profile.visual_style,
                    world_style=profile.world_style,
                    provider_prompt=profile.provider_prompt,
                    negative_prompt=profile.negative_prompt,
                    metadata=profile.metadata,
                )
                for profile in self.style_profiles
            ),
            metadata=self.metadata,
        )


class AssetBibleResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    asset_bible: "AssetBiblePayloadResponse"


class AssetBibleListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    asset_bibles: list["AssetBiblePayloadResponse"]


class SceneCastDraftRequest(PublicMetadataModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    scene_cast_id: str
    storyboard_plan_id: str
    frame_id: str
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prop_ids: list[str] = Field(default_factory=list)
    style_id: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workspace_id", "scene_cast_id", "storyboard_plan_id", "frame_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("scene_id", "style_id")
    @classmethod
    def validate_optional_ids(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id(info.field_name, value)

    @field_validator("character_ids", "prop_ids")
    @classmethod
    def validate_reference_id_lists(cls, value: list[str], info) -> list[str]:
        return [
            validate_public_reference_id(info.field_name, item)
            for item in value
        ]

    def to_model(self, *, project_id: str, asset_bible_id: str) -> SceneCast:
        return SceneCast(
            scene_cast_id=self.scene_cast_id,
            workspace_id=self.workspace_id,
            project_id=project_id,
            storyboard_plan_id=self.storyboard_plan_id,
            frame_id=self.frame_id,
            asset_bible_id=asset_bible_id,
            character_ids=tuple(self.character_ids),
            scene_id=self.scene_id,
            prop_ids=tuple(self.prop_ids),
            style_id=self.style_id,
            continuity_notes=tuple(self.continuity_notes),
            metadata=self.metadata,
        )


class SceneCastResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    scene_cast: "SceneCastPayloadResponse"


class SceneCastListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    scene_casts: list["SceneCastPayloadResponse"]


class IPProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip_profile_id: str
    workspace_id: str
    project_id: str
    name: str
    logline: str | None = None
    world_hint: str | None = None
    style_hint: str | None = None
    identity_lock: list[str] = Field(default_factory=list)
    identity_anchors: list[str] = Field(default_factory=list)
    identity_suppression_rules: list[str] = Field(default_factory=list)
    variable_slots: list[str] = Field(default_factory=list)
    semantic_boundary: list[str] = Field(default_factory=list)
    negative_constraints: list[str] = Field(default_factory=list)
    ip_type: str | None = None
    visual_summary: str | None = None
    minimal_traits: list[str] = Field(default_factory=list)
    default_slot_preference: str | None = None
    role_presets: list[str] = Field(default_factory=list)
    presence_spectrum: list[str] = Field(default_factory=list)
    adaptable_slots: list[str] = Field(default_factory=list)
    color_palette: dict[str, Any] = Field(default_factory=dict)
    image_text_palette: dict[str, Any] = Field(default_factory=dict)
    visible_text_whitelist: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_profile_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class CharacterProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    workspace_id: str
    project_id: str
    display_name: str
    role: str | None = None
    visual_description: str | None = None
    personality: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("character_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class SceneAssetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_description: str | None = None
    environment_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scene_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class PropAssetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prop_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_description: str | None = None
    usage_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prop_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class StyleProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_id: str
    workspace_id: str
    project_id: str
    display_name: str
    visual_style: str
    world_style: str | None = None
    provider_prompt: str | None = None
    negative_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("style_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class AssetBiblePayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_bible_id: str
    workspace_id: str
    project_id: str
    ip_profiles: list[IPProfileResponse] = Field(default_factory=list)
    character_profiles: list[CharacterProfileResponse] = Field(default_factory=list)
    scene_assets: list[SceneAssetResponse] = Field(default_factory=list)
    prop_assets: list[PropAssetResponse] = Field(default_factory=list)
    style_profiles: list[StyleProfileResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset_bible_id", "workspace_id", "project_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class SceneCastPayloadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_cast_id: str
    workspace_id: str
    project_id: str
    storyboard_plan_id: str
    frame_id: str
    asset_bible_id: str
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prop_ids: list[str] = Field(default_factory=list)
    style_id: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "scene_cast_id",
        "workspace_id",
        "project_id",
        "storyboard_plan_id",
        "frame_id",
        "asset_bible_id",
    )
    @classmethod
    def validate_required_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("scene_id", "style_id")
    @classmethod
    def validate_optional_ids(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id(info.field_name, value)

    @field_validator("character_ids", "prop_ids")
    @classmethod
    def validate_reference_id_lists(cls, value: list[str], info) -> list[str]:
        return [
            validate_public_reference_id(info.field_name, item)
            for item in value
        ]

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class PromptPlanProjectionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    storyboard_plan_id: str
    frame_id: str

    @field_validator("workspace_id", "storyboard_plan_id", "frame_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class PromptPlanApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    storyboard_plan_id: str
    frame_id: str
    actor_id: str | None = None

    @field_validator("workspace_id", "storyboard_plan_id", "frame_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("actor_id")
    @classmethod
    def validate_optional_actor_id(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id(info.field_name, value)


class PromptPlanProjectionSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_bible_id: str
    scene_cast_id: str
    prompt_plan_id: str

    @field_validator("asset_bible_id", "scene_cast_id", "prompt_plan_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)


class PromptPlanProjectionPromptPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_plan_id: str
    storyboard_plan_id: str
    frame_id: str
    image_prompt_draft_id: str
    prompt_sections: dict[str, str]
    final_prompt: str
    source_trace_id: str | None = None
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    prop_ids: list[str] = Field(default_factory=list)
    style_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt_plan_id", "storyboard_plan_id", "frame_id", "image_prompt_draft_id")
    @classmethod
    def validate_required_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    @field_validator("prompt_sections")
    @classmethod
    def validate_prompt_sections(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if _contains_path_or_url_reference(key) or _contains_path_or_url_reference(item):
                raise ValueError("prompt_sections must not contain path-like references")
        return value

    @field_validator("final_prompt")
    @classmethod
    def validate_final_prompt(cls, value: str) -> str:
        if _contains_path_or_url_reference(value):
            raise ValueError("final_prompt must not contain path-like references")
        return value

    @field_validator("source_trace_id", "scene_id", "style_id")
    @classmethod
    def validate_optional_ids(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_public_reference_id(info.field_name, value)

    @field_validator("character_ids", "prop_ids")
    @classmethod
    def validate_reference_id_lists(cls, value: list[str], info) -> list[str]:
        return [
            validate_public_reference_id(info.field_name, item)
            for item in value
        ]

    @field_validator("metadata")
    @classmethod
    def validate_projection_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_unsafe_public_metadata("metadata", value)
        return value


class PromptPlanProjectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_plan: PromptPlanProjectionPromptPlanResponse
    source: PromptPlanProjectionSourceResponse


class PromptPlanProjectionPreviewResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    projection: PromptPlanProjectionPayload


class PromptPlanApplySourceResponse(PromptPlanProjectionSourceResponse):
    pass


class PromptPlanApplyWriteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_tokens: list[str] = Field(default_factory=list)
    dependency_edge_count: int = 0
    stale_mark_count: int = 0

    @field_validator("version_tokens")
    @classmethod
    def validate_version_tokens(cls, value: list[str], info) -> list[str]:
        return [
            validate_public_reference_id(info.field_name, item)
            for item in value
        ]


class PromptPlanApplyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_plan: PromptPlanProjectionPromptPlanResponse
    source: PromptPlanApplySourceResponse
    write: PromptPlanApplyWriteResponse


class PromptPlanApplyResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    application: PromptPlanApplyPayload


def _reject_path_like_metadata(path: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    for raw_key, item in value.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError(f"{path} keys must not be empty")
        child_path = f"{path}.{key}"
        if _looks_like_path_or_url(key):
            raise ValueError(f"{path} keys must not be local paths, URLs, or storage references")
        if _is_path_metadata_key(key):
            raise ValueError(f"{child_path} must not carry local paths, URLs, or storage references")
        if isinstance(item, dict):
            _reject_path_like_metadata(child_path, item)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                _reject_path_like_metadata_value(f"{child_path}[{index}]", child)
        else:
            _reject_path_like_metadata_value(child_path, item)


def reject_unsafe_public_metadata(path: str, value: dict[str, Any]) -> None:
    _reject_path_like_metadata(path, value)
    _reject_text_rendering_metadata(path, value)


def _reject_path_like_metadata_value(path: str, value: Any) -> None:
    if isinstance(value, dict):
        _reject_path_like_metadata(path, value)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_path_like_metadata_value(f"{path}[{index}]", child)
    elif isinstance(value, str) and _looks_like_path_or_url(value):
        raise ValueError(f"{path} must not contain path-like string values")


def _is_path_metadata_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in {"path", "url", "uri", "file", "storage_key"}
        or lowered.endswith("_path")
        or lowered.endswith("_url")
        or lowered.endswith("_uri")
    )


def _reject_text_rendering_metadata(path: str, value: Any) -> None:
    if not isinstance(value, dict):
        return
    for raw_key, item in value.items():
        key = str(raw_key).strip()
        child_path = f"{path}.{key}"
        if _is_text_rendering_metadata_key(key):
            raise ValueError(f"{child_path} must not carry text-rendering style fields")
        if isinstance(item, dict):
            _reject_text_rendering_metadata(child_path, item)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                _reject_text_rendering_metadata(f"{child_path}[{index}]", child)


def _is_text_rendering_metadata_key(key: str) -> bool:
    lowered = key.lower()
    normalized = lowered.replace("-", "_")
    compact = normalized.replace("_", "")
    return (
        normalized in {
            "background_color",
            "caption_style",
            "font",
            "fontcolor",
            "fontsize",
            "overlay_style",
            "subtitle_style",
            "text_rendering_style",
            "title_style",
        }
        or compact in {
            "backgroundcolor",
            "captionstyle",
            "font",
            "fontcolor",
            "fontsize",
            "overlaystyle",
            "subtitlestyle",
            "textrenderingstyle",
            "titlefont",
            "titlestyle",
        }
        or compact.startswith("font")
        or normalized.startswith("font_")
        or normalized.startswith("caption_")
        or normalized.startswith("subtitle_")
        or normalized.startswith("title_")
        or normalized.startswith("text_rendering_")
        or normalized.endswith("_font")
        or normalized.endswith("_font_size")
        or normalized.endswith("_font_color")
    )


def _looks_like_path_or_url(value: str) -> bool:
    stripped = value.strip()
    return (
        "\\" in stripped
        or "/" in stripped
        or "://" in stripped
        or stripped in {".", ".."}
        or stripped.startswith("~")
        or (len(stripped) >= 2 and stripped[1] == ":" and stripped[0].isalpha())
    )


_PATH_OR_URL_REFERENCE_RE = re.compile(
    r"(?ix)"
    r"(://|\\|"
    r"(?:^|[\s\"'`(])"
    r"(?:"
    r"[A-Za-z]:[\\/]|"
    r"~[\\/]|"
    r"\.{1,2}[\\/]|"
    r"/[\w.-]+|"
    r"[\w.-]+[\\/][\w./-]*\.[A-Za-z0-9]{2,8}"
    r"))"
)


def _contains_path_or_url_reference(value: str) -> bool:
    return bool(_PATH_OR_URL_REFERENCE_RE.search(value.strip()))


__all__ = [
    "AssetBibleDraftRequest",
    "AssetBibleListResponse",
    "AssetBibleResponse",
    "CharacterProfileDraft",
    "IPProfileDraft",
    "PromptPlanApplyPayload",
    "PromptPlanApplyRequest",
    "PromptPlanApplyResponse",
    "PromptPlanApplySourceResponse",
    "PromptPlanApplyWriteResponse",
    "PromptPlanProjectionPayload",
    "PromptPlanProjectionPromptPlanResponse",
    "PromptPlanProjectionPreviewRequest",
    "PromptPlanProjectionPreviewResponse",
    "PromptPlanProjectionSourceResponse",
    "PropAssetDraft",
    "reject_unsafe_public_metadata",
    "SceneAssetDraft",
    "SceneCastDraftRequest",
    "SceneCastListResponse",
    "SceneCastResponse",
    "StyleProfileDraft",
]
