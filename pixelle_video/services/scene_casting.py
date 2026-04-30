from __future__ import annotations

from dataclasses import dataclass

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast


@dataclass(frozen=True)
class SceneCastValidationError(ValueError):
    field_name: str
    invalid_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.field_name}: {self.invalid_id} ({self.message})"


def validate_scene_cast(scene_cast: SceneCast, asset_bible: AssetBible) -> SceneCast:
    if scene_cast.workspace_id != asset_bible.workspace_id:
        raise SceneCastValidationError(
            field_name="workspace_id",
            invalid_id=scene_cast.workspace_id,
            message="scene cast workspace does not match asset bible",
        )
    if scene_cast.project_id != asset_bible.project_id:
        raise SceneCastValidationError(
            field_name="project_id",
            invalid_id=scene_cast.project_id,
            message="scene cast project does not match asset bible",
        )
    if scene_cast.asset_bible_id != asset_bible.asset_bible_id:
        raise SceneCastValidationError(
            field_name="asset_bible_id",
            invalid_id=scene_cast.asset_bible_id,
            message="scene cast asset bible ID does not match",
        )

    character_ids = {profile.character_id for profile in asset_bible.character_profiles}
    scene_ids = {asset.scene_id for asset in asset_bible.scene_assets}
    prop_ids = {asset.prop_id for asset in asset_bible.prop_assets}
    style_ids = {profile.style_id for profile in asset_bible.style_profiles}

    for character_id in scene_cast.character_ids:
        _require_known_id("character_ids", character_id, character_ids)
    if scene_cast.scene_id is not None:
        _require_known_id("scene_id", scene_cast.scene_id, scene_ids)
    for prop_id in scene_cast.prop_ids:
        _require_known_id("prop_ids", prop_id, prop_ids)
    if scene_cast.style_id is not None:
        _require_known_id("style_id", scene_cast.style_id, style_ids)
    return scene_cast


def _require_known_id(field_name: str, asset_id: str, known_ids: set[str]) -> None:
    if asset_id not in known_ids:
        raise SceneCastValidationError(
            field_name=field_name,
            invalid_id=asset_id,
            message="asset ID is not defined in the current asset bible",
        )


__all__ = [
    "SceneCastValidationError",
    "validate_scene_cast",
]
