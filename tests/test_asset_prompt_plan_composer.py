from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.services.asset_prompt_plan_composer import (
    AssetBibleNotFoundError,
    AssetPromptPlanComposerService,
    PromptPlanNotFoundError,
    PromptPlanProjectionValidationError,
    RepositoryIdentityError,
    SceneCastNotFoundError,
)


@dataclass
class FakeAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def load_asset_bible(self, workspace_id: str, asset_bible_id: str) -> dict[str, Any] | None:
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def load_scene_cast(self, workspace_id: str, scene_cast_id: str) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))


@dataclass
class FakePromptPlanRepository:
    prompt_plans: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    async def load_prompt_plans_by_storyboard(self, workspace_id: str, storyboard_id: str) -> list[dict[str, Any]]:
        return self.prompt_plans.get((workspace_id, storyboard_id), [])


def asset_bible_payload(**overrides: Any) -> dict[str, Any]:
    workspace_id = overrides.get("workspace_id", "workspace_1")
    project_id = overrides.get("project_id", "project_1")
    payload = {
        "asset_bible_id": "bible_demo",
        "workspace_id": workspace_id,
        "project_id": project_id,
        "character_profiles": [
            {
                "character_id": "char_luna",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "display_name": "Luna",
            }
        ],
        "scene_assets": [
            {
                "scene_id": "scene_lab",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "display_name": "Sky Lab",
            }
        ],
        "prop_assets": [
            {
                "prop_id": "prop_compass",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "display_name": "Star Compass",
            }
        ],
        "style_profiles": [
            {
                "style_id": "style_warm_comic",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "display_name": "Warm Comic",
                "visual_style": "warm comic",
            }
        ],
    }
    payload.update(overrides)
    return payload


def scene_cast_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "scene_cast_id": "cast_frame_1",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "asset_bible_id": "bible_demo",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    payload.update(overrides)
    return payload


def prompt_plan_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "prompt_plan_id": "prompt_plan_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_1",
        "prompt_sections": {"visual_goal": "Show Luna in the lab."},
        "final_prompt": "Show Luna in the lab.",
        "source_trace_id": "trace_1",
        "metadata": {"source": "stage1a"},
    }
    payload.update(overrides)
    return payload


def service_with_defaults() -> tuple[AssetPromptPlanComposerService, FakeAssetBibleRepository, FakePromptPlanRepository]:
    asset_repository = FakeAssetBibleRepository()
    prompt_repository = FakePromptPlanRepository()
    asset_repository.asset_bibles[("workspace_1", "bible_demo")] = asset_bible_payload()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [prompt_plan_payload()]
    return (
        AssetPromptPlanComposerService(
            asset_bible_repository=asset_repository,
            prompt_plan_repository=prompt_repository,
        ),
        asset_repository,
        prompt_repository,
    )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_projects_scene_cast_without_mutating_source_plan():
    service, _, prompt_repository = service_with_defaults()
    source_plan = prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")][0]

    preview = await service.preview_prompt_plan_projection(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
    )

    assert preview.prompt_plan.prompt_plan_id == "prompt_plan_1"
    assert preview.prompt_plan.character_ids == ("char_luna",)
    assert preview.prompt_plan.scene_id == "scene_lab"
    assert preview.prompt_plan.prop_ids == ("prop_compass",)
    assert preview.prompt_plan.style_id == "style_warm_comic"
    assert preview.prompt_plan.metadata["scene_cast_id"] == "cast_frame_1"
    assert preview.source.asset_bible_id == "bible_demo"
    assert preview.source.scene_cast_id == "cast_frame_1"
    assert preview.source.prompt_plan_id == "prompt_plan_1"
    assert "character_ids" not in source_plan
    assert source_plan["metadata"] == {"source": "stage1a"}


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_asset_bible():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.asset_bibles.clear()

    with pytest.raises(AssetBibleNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_scene_cast():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts.clear()

    with pytest.raises(SceneCastNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_unknown_scene_cast_asset_reference():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload(
        character_ids=["char_missing"]
    )

    with pytest.raises(PromptPlanProjectionValidationError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "char_missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_missing_prompt_plan_for_frame():
    service, _, prompt_repository = service_with_defaults()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        prompt_plan_payload(frame_id="frame_0002")
    ]

    with pytest.raises(PromptPlanNotFoundError):
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_repository_identity_mismatch():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.asset_bibles[("workspace_1", "bible_demo")] = asset_bible_payload(project_id="other_project")

    with pytest.raises(RepositoryIdentityError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "project" in str(exc_info.value)


@pytest.mark.asyncio
async def test_preview_prompt_plan_projection_rejects_scene_cast_frame_mismatch():
    service, asset_repository, _ = service_with_defaults()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload(frame_id="frame_0002")

    with pytest.raises(PromptPlanProjectionValidationError) as exc_info:
        await service.preview_prompt_plan_projection(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "frame_id" in str(exc_info.value)
