from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.prompt_plans import PromptPlanRepository
from pixelle_video.services.prompt_composer import apply_scene_cast_to_prompt_plan
from pixelle_video.services.public_ids import validate_public_reference_id
from pixelle_video.services.scene_casting import (
    SceneCastValidationError,
    validate_scene_cast,
)


class PromptPlanProjectionError(ValueError):
    """Base class for safe public projection errors."""


class ProjectionDependencyError(PromptPlanProjectionError):
    pass


class AssetBibleNotFoundError(PromptPlanProjectionError):
    pass


class SceneCastNotFoundError(PromptPlanProjectionError):
    pass


class PromptPlanNotFoundError(PromptPlanProjectionError):
    pass


class RepositoryIdentityError(PromptPlanProjectionError):
    pass


class PromptPlanProjectionValidationError(PromptPlanProjectionError):
    pass


@dataclass(frozen=True)
class PromptPlanProjectionSource:
    asset_bible_id: str
    scene_cast_id: str
    prompt_plan_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "asset_bible_id": self.asset_bible_id,
            "scene_cast_id": self.scene_cast_id,
            "prompt_plan_id": self.prompt_plan_id,
        }


@dataclass(frozen=True)
class PromptPlanProjectionPreview:
    prompt_plan: PromptPlan
    source: PromptPlanProjectionSource

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan": self.prompt_plan.to_dict(),
            "source": self.source.to_dict(),
        }


class AssetPromptPlanComposerService:
    def __init__(
        self,
        *,
        asset_bible_repository: AssetBibleRepository | None,
        prompt_plan_repository: PromptPlanRepository | None,
    ) -> None:
        if asset_bible_repository is None:
            raise ProjectionDependencyError("asset bible repository is not configured")
        if prompt_plan_repository is None:
            raise ProjectionDependencyError("prompt plan repository is not configured")
        self.asset_bible_repository = asset_bible_repository
        self.prompt_plan_repository = prompt_plan_repository

    async def preview_prompt_plan_projection(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
    ) -> PromptPlanProjectionPreview:
        asset_bible = await self._load_asset_bible(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        scene_cast = await self._load_scene_cast(
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
        )
        try:
            validate_scene_cast(scene_cast, asset_bible)
        except SceneCastValidationError as exc:
            raise PromptPlanProjectionValidationError(str(exc)) from exc

        prompt_plan = await self._load_prompt_plan(
            workspace_id=workspace_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
        )
        try:
            projected = apply_scene_cast_to_prompt_plan(prompt_plan, scene_cast)
        except ValueError as exc:
            raise PromptPlanProjectionValidationError(str(exc)) from exc
        return PromptPlanProjectionPreview(
            prompt_plan=projected,
            source=PromptPlanProjectionSource(
                asset_bible_id=asset_bible.asset_bible_id,
                scene_cast_id=scene_cast.scene_cast_id,
                prompt_plan_id=projected.prompt_plan_id,
            ),
        )

    async def _load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> AssetBible:
        loaded = await self.asset_bible_repository.load_asset_bible(
            workspace_id,
            asset_bible_id,
        )
        if loaded is None:
            raise AssetBibleNotFoundError("asset bible draft was not found")
        asset_bible = _parse_asset_bible(loaded)
        _require_identity(
            value=asset_bible.workspace_id,
            expected=workspace_id,
            message="asset bible workspace does not match request",
        )
        _require_identity(
            value=asset_bible.project_id,
            expected=project_id,
            message="asset bible project does not match request",
        )
        _require_identity(
            value=asset_bible.asset_bible_id,
            expected=asset_bible_id,
            message="asset bible ID does not match request",
        )
        return asset_bible

    async def _load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
    ) -> SceneCast:
        loaded = await self.asset_bible_repository.load_scene_cast(
            workspace_id,
            scene_cast_id,
        )
        if loaded is None:
            raise SceneCastNotFoundError("scene cast draft was not found")
        scene_cast = _parse_scene_cast(loaded)
        _validate_scene_cast_public_references(scene_cast)
        _require_identity(
            value=scene_cast.workspace_id,
            expected=workspace_id,
            message="scene cast workspace does not match request",
        )
        _require_identity(
            value=scene_cast.project_id,
            expected=project_id,
            message="scene cast project does not match request",
        )
        _require_identity(
            value=scene_cast.asset_bible_id,
            expected=asset_bible_id,
            message="scene cast asset bible does not match request",
        )
        _require_identity(
            value=scene_cast.scene_cast_id,
            expected=scene_cast_id,
            message="scene cast ID does not match request",
        )
        _require_projection_identity(
            value=scene_cast.storyboard_plan_id,
            expected=storyboard_plan_id,
            field_name="storyboard_plan_id",
        )
        _require_projection_identity(
            value=scene_cast.frame_id,
            expected=frame_id,
            field_name="frame_id",
        )
        return scene_cast

    async def _load_prompt_plan(
        self,
        *,
        workspace_id: str,
        storyboard_plan_id: str,
        frame_id: str,
    ) -> PromptPlan:
        loaded_plans = await self.prompt_plan_repository.load_prompt_plans_by_storyboard(
            workspace_id,
            storyboard_plan_id,
        )
        for loaded in loaded_plans:
            prompt_plan = _parse_prompt_plan(loaded)
            _require_identity(
                value=prompt_plan.storyboard_plan_id,
                expected=storyboard_plan_id,
                message="prompt plan storyboard does not match request",
            )
            if prompt_plan.frame_id == frame_id:
                return prompt_plan
        raise PromptPlanNotFoundError("prompt plan was not found for storyboard frame")


def _parse_asset_bible(payload: Mapping[str, Any]) -> AssetBible:
    try:
        return AssetBible.from_dict(payload)
    except ValueError as exc:
        raise RepositoryIdentityError("asset bible repository payload is invalid") from exc


def _parse_scene_cast(payload: Mapping[str, Any]) -> SceneCast:
    try:
        return SceneCast.from_dict(payload)
    except ValueError as exc:
        raise RepositoryIdentityError("scene cast repository payload is invalid") from exc


def _parse_prompt_plan(payload: Mapping[str, Any]) -> PromptPlan:
    try:
        return PromptPlan.from_dict(payload)
    except ValueError as exc:
        raise RepositoryIdentityError("prompt plan repository payload is invalid") from exc


def _validate_scene_cast_public_references(scene_cast: SceneCast) -> None:
    _require_public_reference("scene cast workspace_id", scene_cast.workspace_id)
    _require_public_reference("scene cast project_id", scene_cast.project_id)
    _require_public_reference("scene cast asset_bible_id", scene_cast.asset_bible_id)
    _require_public_reference("scene cast scene_cast_id", scene_cast.scene_cast_id)
    _require_public_reference("scene cast storyboard_plan_id", scene_cast.storyboard_plan_id)
    _require_public_reference("scene cast frame_id", scene_cast.frame_id)
    for character_id in scene_cast.character_ids:
        _require_public_reference("scene cast character_ids", character_id)
    if scene_cast.scene_id is not None:
        _require_public_reference("scene cast scene_id", scene_cast.scene_id)
    for prop_id in scene_cast.prop_ids:
        _require_public_reference("scene cast prop_ids", prop_id)
    if scene_cast.style_id is not None:
        _require_public_reference("scene cast style_id", scene_cast.style_id)


def _require_public_reference(field_name: str, value: str) -> None:
    try:
        validate_public_reference_id(field_name, value)
    except ValueError as exc:
        raise RepositoryIdentityError(
            f"{field_name} in repository payload is invalid"
        ) from exc


def _require_identity(*, value: str, expected: str, message: str) -> None:
    if value != expected:
        raise RepositoryIdentityError(message)


def _require_projection_identity(*, value: str, expected: str, field_name: str) -> None:
    if value != expected:
        raise PromptPlanProjectionValidationError(
            f"{field_name} must match projection request"
        )


__all__ = [
    "AssetBibleNotFoundError",
    "AssetPromptPlanComposerService",
    "ProjectionDependencyError",
    "PromptPlanNotFoundError",
    "PromptPlanProjectionError",
    "PromptPlanProjectionPreview",
    "PromptPlanProjectionSource",
    "PromptPlanProjectionValidationError",
    "RepositoryIdentityError",
    "SceneCastNotFoundError",
]
