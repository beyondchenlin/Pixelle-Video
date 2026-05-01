from __future__ import annotations

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


class CharacterProfileDraft(BaseModel):
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


class SceneAssetDraft(BaseModel):
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


class PropAssetDraft(BaseModel):
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


class StyleProfileDraft(BaseModel):
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


class AssetBibleDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    asset_bible_id: str
    ip_profile_id: str = "ip_default"
    ip_name: str
    logline: str | None = None
    world_hint: str | None = None
    style_hint: str | None = None
    forbidden_elements: list[str] = Field(default_factory=list)
    character_profiles: list[CharacterProfileDraft] = Field(default_factory=list)
    scene_assets: list[SceneAssetDraft] = Field(default_factory=list)
    prop_assets: list[PropAssetDraft] = Field(default_factory=list)
    style_profiles: list[StyleProfileDraft] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workspace_id", "asset_bible_id", "ip_profile_id")
    @classmethod
    def validate_ids(cls, value: str, info) -> str:
        return validate_public_reference_id(info.field_name, value)

    def to_model(self, *, project_id: str) -> AssetBible:
        return AssetBible(
            asset_bible_id=self.asset_bible_id,
            workspace_id=self.workspace_id,
            project_id=project_id,
            ip_profiles=(
                IPProfile(
                    ip_profile_id=self.ip_profile_id,
                    workspace_id=self.workspace_id,
                    project_id=project_id,
                    name=self.ip_name,
                    logline=self.logline,
                    world_hint=self.world_hint,
                    style_hint=self.style_hint,
                    forbidden_elements=tuple(self.forbidden_elements),
                ),
            ),
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
    asset_bible: dict[str, Any]


class SceneCastDraftRequest(BaseModel):
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
    scene_cast: dict[str, Any]


__all__ = [
    "AssetBibleDraftRequest",
    "AssetBibleResponse",
    "CharacterProfileDraft",
    "PropAssetDraft",
    "SceneAssetDraft",
    "SceneCastDraftRequest",
    "SceneCastResponse",
    "StyleProfileDraft",
]
