from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.services.asset_prompt_plan_apply import (
    AssetPromptPlanApplyService,
    PromptPlanApplyDependencyError,
    PromptPlanApplyNotFoundError,
    PromptPlanApplyValidationError,
)


@dataclass
class FakeAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any] | None:
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))


@dataclass
class FakePromptPlanRepository:
    prompt_plans: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, Any]]:
        return self.prompt_plans.get((workspace_id, storyboard_id), [])


@dataclass
class FakeStaleAwarePromptPlanWriteService:
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    version_tokens: tuple[str, ...] = ("prompt_plan_rev_1", "prompt_plan_rev_2")
    dependency_edge_count: int = 1
    stale_mark_count: int = 0

    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        project_id: str,
        bundle,
    ):
        payload = bundle.to_dict()
        self.calls.append((workspace_id, project_id, payload))
        return FakeStaleAwareWriteResult(
            saved_payload=payload,
            version_tokens=self.version_tokens,
            dependency_edges=tuple({} for _ in range(self.dependency_edge_count)),
            propagation_summaries=(
                FakePropagationSummary(stale_mark_count=self.stale_mark_count),
            ),
        )


@dataclass(frozen=True)
class FakePropagationSummary:
    stale_mark_count: int


@dataclass(frozen=True)
class FakeStaleAwareWriteResult:
    saved_payload: dict[str, Any]
    version_tokens: tuple[str, ...]
    dependency_edges: tuple[dict[str, Any], ...]
    propagation_summaries: tuple[FakePropagationSummary, ...]


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


def service_with_defaults(
    *,
    writer: FakeStaleAwarePromptPlanWriteService | None = None,
) -> tuple[
    AssetPromptPlanApplyService,
    FakeAssetBibleRepository,
    FakePromptPlanRepository,
    FakeStaleAwarePromptPlanWriteService | None,
]:
    asset_repository = FakeAssetBibleRepository()
    prompt_repository = FakePromptPlanRepository()
    asset_repository.asset_bibles[("workspace_1", "bible_demo")] = asset_bible_payload()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        prompt_plan_payload(),
        prompt_plan_payload(
            prompt_plan_id="prompt_plan_2",
            frame_id="frame_0002",
            image_prompt_draft_id="draft_2",
            prompt_sections={"visual_goal": "Show Luna entering the observatory."},
            final_prompt="Show Luna entering the observatory.",
            metadata={"source": "stage1a_second"},
        ),
    ]
    stale_writer = writer if writer is not None else FakeStaleAwarePromptPlanWriteService()
    return (
        AssetPromptPlanApplyService(
            asset_bible_repository=asset_repository,
            prompt_plan_repository=prompt_repository,
            stale_prompt_plan_writer=stale_writer,
        ),
        asset_repository,
        prompt_repository,
        stale_writer,
    )


@pytest.mark.asyncio
async def test_apply_scene_cast_replaces_only_target_prompt_plan_and_saves_bundle():
    service, _, _, writer = service_with_defaults()
    assert writer is not None

    result = await service.apply_scene_cast_to_prompt_plan_bundle(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        actor_id="user_1",
    )

    assert result.prompt_plan.prompt_plan_id == "prompt_plan_1"
    assert result.prompt_plan.character_ids == ("char_luna",)
    assert result.prompt_plan.scene_id == "scene_lab"
    assert result.prompt_plan.prop_ids == ("prop_compass",)
    assert result.prompt_plan.style_id == "style_warm_comic"
    assert result.prompt_plan.metadata["scene_cast_id"] == "cast_frame_1"
    assert result.prompt_plan.metadata["asset_bible_id"] == "bible_demo"
    assert result.source.asset_bible_id == "bible_demo"
    assert result.source.scene_cast_id == "cast_frame_1"
    assert result.source.prompt_plan_id == "prompt_plan_1"
    assert result.write.version_tokens == ("prompt_plan_rev_1", "prompt_plan_rev_2")
    assert result.write.dependency_edge_count == 1
    assert result.write.stale_mark_count == 0
    assert len(writer.calls) == 1
    workspace_id, project_id, saved_bundle = writer.calls[0]
    assert (workspace_id, project_id) == ("workspace_1", "project_1")
    saved_plans = saved_bundle["prompt_plans"]
    assert saved_plans[0]["character_ids"] == ["char_luna"]
    assert saved_plans[0]["metadata"]["scene_cast_id"] == "cast_frame_1"
    assert saved_plans[1]["prompt_plan_id"] == "prompt_plan_2"
    assert saved_plans[1]["character_ids"] == []
    assert saved_plans[1]["metadata"] == {"source": "stage1a_second"}
    assert [draft["image_prompt_draft_id"] for draft in saved_bundle["image_prompt_drafts"]] == [
        "draft_1",
        "draft_2",
    ]


@pytest.mark.asyncio
async def test_apply_scene_cast_rejects_missing_prompt_plan_frame():
    service, _, prompt_repository, _ = service_with_defaults()
    prompt_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        prompt_plan_payload(frame_id="frame_0002")
    ]

    with pytest.raises(PromptPlanApplyNotFoundError):
        await service.apply_scene_cast_to_prompt_plan_bundle(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )


@pytest.mark.asyncio
async def test_apply_scene_cast_rejects_invalid_scene_cast_reference():
    service, asset_repository, _, _ = service_with_defaults()
    asset_repository.scene_casts[("workspace_1", "cast_frame_1")] = scene_cast_payload(
        character_ids=["char_missing"]
    )

    with pytest.raises(PromptPlanApplyValidationError) as exc_info:
        await service.apply_scene_cast_to_prompt_plan_bundle(
            workspace_id="workspace_1",
            project_id="project_1",
            asset_bible_id="bible_demo",
            scene_cast_id="cast_frame_1",
            storyboard_plan_id="storyboard_plan_1",
            frame_id="frame_0001",
        )

    assert "char_missing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_apply_scene_cast_requires_stale_aware_writer():
    asset_repository = FakeAssetBibleRepository()
    prompt_repository = FakePromptPlanRepository()

    with pytest.raises(PromptPlanApplyDependencyError):
        AssetPromptPlanApplyService(
            asset_bible_repository=asset_repository,
            prompt_plan_repository=prompt_repository,
            stale_prompt_plan_writer=None,
        )
