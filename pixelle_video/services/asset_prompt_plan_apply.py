from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptPlanBundle
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.prompt_plans import PromptPlanRepository
from pixelle_video.services.prompt_composer import apply_scene_cast_to_prompt_plan
from pixelle_video.services.public_ids import validate_public_reference_id
from pixelle_video.services.scene_casting import (
    SceneCastValidationError,
    validate_scene_cast,
)
from pixelle_video.services.stale_write_integration import (
    StaleAwarePromptPlanWriteService,
    StaleWriteDependencyNotFoundError,
    StaleWriteIntegrationError,
)


class PromptPlanApplyError(ValueError):
    """Base class for safe public PromptPlan apply errors."""


class PromptPlanApplyDependencyError(PromptPlanApplyError):
    pass


class PromptPlanApplyNotFoundError(PromptPlanApplyError):
    pass


class PromptPlanApplyValidationError(PromptPlanApplyError):
    pass


class PromptPlanApplyRepositoryIdentityError(PromptPlanApplyError):
    pass


@dataclass(frozen=True)
class PromptPlanApplySource:
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
class PromptPlanApplyWriteSummary:
    version_tokens: tuple[str, ...]
    dependency_edge_count: int
    stale_mark_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_tokens": list(self.version_tokens),
            "dependency_edge_count": self.dependency_edge_count,
            "stale_mark_count": self.stale_mark_count,
        }


@dataclass(frozen=True)
class PromptPlanApplyResult:
    prompt_plan: PromptPlan
    source: PromptPlanApplySource
    write: PromptPlanApplyWriteSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan": self.prompt_plan.to_dict(),
            "source": self.source.to_dict(),
            "write": self.write.to_dict(),
        }


class AssetPromptPlanApplyService:
    def __init__(
        self,
        *,
        asset_bible_repository: AssetBibleRepository | None,
        prompt_plan_repository: PromptPlanRepository | None,
        stale_prompt_plan_writer: StaleAwarePromptPlanWriteService | None,
    ) -> None:
        if asset_bible_repository is None:
            raise PromptPlanApplyDependencyError("asset bible repository is not configured")
        if prompt_plan_repository is None:
            raise PromptPlanApplyDependencyError("prompt plan repository is not configured")
        if stale_prompt_plan_writer is None:
            raise PromptPlanApplyDependencyError("stale-aware prompt plan writer is not configured")
        self.asset_bible_repository = asset_bible_repository
        self.prompt_plan_repository = prompt_plan_repository
        self.stale_prompt_plan_writer = stale_prompt_plan_writer

    async def apply_scene_cast_to_prompt_plan_bundle(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
        actor_id: str | None = None,
    ) -> PromptPlanApplyResult:
        _ = actor_id
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
            raise PromptPlanApplyValidationError(str(exc)) from exc

        bundle = await self._load_prompt_plan_bundle(
            workspace_id=workspace_id,
            storyboard_plan_id=storyboard_plan_id,
        )
        updated_plans: list[PromptPlan] = []
        applied_plan: PromptPlan | None = None
        for prompt_plan in bundle.prompt_plans:
            if prompt_plan.frame_id == frame_id:
                try:
                    applied_plan = apply_scene_cast_to_prompt_plan(prompt_plan, scene_cast)
                except ValueError as exc:
                    raise PromptPlanApplyValidationError(str(exc)) from exc
                updated_plans.append(applied_plan)
            else:
                updated_plans.append(prompt_plan)
        if applied_plan is None:
            raise PromptPlanApplyNotFoundError("prompt plan was not found for storyboard frame")

        updated_bundle = PromptPlanBundle(
            storyboard_plan_id=bundle.storyboard_plan_id,
            image_prompt_drafts=bundle.image_prompt_drafts,
            prompt_plans=tuple(updated_plans),
            source_trace_id=bundle.source_trace_id,
            metadata=bundle.metadata,
        )
        try:
            write_result = await self.stale_prompt_plan_writer.save_prompt_plan_bundle(
                workspace_id,
                project_id,
                updated_bundle,
            )
        except StaleWriteDependencyNotFoundError as exc:
            raise PromptPlanApplyNotFoundError(str(exc)) from exc
        except StaleWriteIntegrationError as exc:
            raise PromptPlanApplyDependencyError(str(exc)) from exc

        return PromptPlanApplyResult(
            prompt_plan=applied_plan,
            source=PromptPlanApplySource(
                asset_bible_id=asset_bible.asset_bible_id,
                scene_cast_id=scene_cast.scene_cast_id,
                prompt_plan_id=applied_plan.prompt_plan_id,
            ),
            write=_write_summary_from_result(write_result),
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
            raise PromptPlanApplyNotFoundError("asset bible draft was not found")
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
            raise PromptPlanApplyNotFoundError("scene cast draft was not found")
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
        _require_apply_identity(
            value=scene_cast.storyboard_plan_id,
            expected=storyboard_plan_id,
            field_name="storyboard_plan_id",
        )
        _require_apply_identity(
            value=scene_cast.frame_id,
            expected=frame_id,
            field_name="frame_id",
        )
        return scene_cast

    async def _load_prompt_plan_bundle(
        self,
        *,
        workspace_id: str,
        storyboard_plan_id: str,
    ) -> PromptPlanBundle:
        loaded_plans = await self.prompt_plan_repository.load_prompt_plans_by_storyboard(
            workspace_id,
            storyboard_plan_id,
        )
        prompt_plans = tuple(_parse_prompt_plan(loaded) for loaded in loaded_plans)
        if not prompt_plans:
            raise PromptPlanApplyNotFoundError("prompt plans were not found for storyboard")
        for prompt_plan in prompt_plans:
            _require_identity(
                value=prompt_plan.storyboard_plan_id,
                expected=storyboard_plan_id,
                message="prompt plan storyboard does not match request",
            )
        return PromptPlanBundle(
            storyboard_plan_id=storyboard_plan_id,
            image_prompt_drafts=tuple(_draft_from_prompt_plan(plan) for plan in prompt_plans),
            prompt_plans=prompt_plans,
        )


def _write_summary_from_result(result: Any) -> PromptPlanApplyWriteSummary:
    return PromptPlanApplyWriteSummary(
        version_tokens=tuple(getattr(result, "version_tokens", ())),
        dependency_edge_count=len(tuple(getattr(result, "dependency_edges", ()))),
        stale_mark_count=sum(
            int(getattr(summary, "stale_mark_count", 0))
            for summary in tuple(getattr(result, "propagation_summaries", ()))
        ),
    )


def _draft_from_prompt_plan(prompt_plan: PromptPlan) -> ImagePromptDraft:
    return ImagePromptDraft(
        image_prompt_draft_id=prompt_plan.image_prompt_draft_id,
        storyboard_plan_id=prompt_plan.storyboard_plan_id,
        frame_id=prompt_plan.frame_id,
        prompt_text=prompt_plan.final_prompt,
        source_trace_id=prompt_plan.source_trace_id,
        metadata={"reconstructed_from_prompt_plan_id": prompt_plan.prompt_plan_id},
    )


def _parse_asset_bible(payload: Mapping[str, Any]) -> AssetBible:
    try:
        return AssetBible.from_dict(payload)
    except ValueError as exc:
        raise PromptPlanApplyRepositoryIdentityError(
            "asset bible repository payload is invalid"
        ) from exc


def _parse_scene_cast(payload: Mapping[str, Any]) -> SceneCast:
    try:
        return SceneCast.from_dict(payload)
    except ValueError as exc:
        raise PromptPlanApplyRepositoryIdentityError(
            "scene cast repository payload is invalid"
        ) from exc


def _parse_prompt_plan(payload: Mapping[str, Any]) -> PromptPlan:
    try:
        return PromptPlan.from_dict(payload)
    except ValueError as exc:
        raise PromptPlanApplyRepositoryIdentityError(
            "prompt plan repository payload is invalid"
        ) from exc


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
        raise PromptPlanApplyRepositoryIdentityError(
            f"{field_name} in repository payload is invalid"
        ) from exc


def _require_identity(*, value: str, expected: str, message: str) -> None:
    if value != expected:
        raise PromptPlanApplyRepositoryIdentityError(message)


def _require_apply_identity(*, value: str, expected: str, field_name: str) -> None:
    if value != expected:
        raise PromptPlanApplyValidationError(
            f"{field_name} must match apply request"
        )


__all__ = [
    "AssetPromptPlanApplyService",
    "PromptPlanApplyDependencyError",
    "PromptPlanApplyError",
    "PromptPlanApplyNotFoundError",
    "PromptPlanApplyRepositoryIdentityError",
    "PromptPlanApplyResult",
    "PromptPlanApplySource",
    "PromptPlanApplyValidationError",
    "PromptPlanApplyWriteSummary",
]
