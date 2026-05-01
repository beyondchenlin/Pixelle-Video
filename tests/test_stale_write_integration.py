from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptPlanBundle
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.stale_write_integration import (
    StaleAwareAssetBibleWriteService,
    StaleAwarePromptPlanWriteService,
)


@dataclass
class FakeAssetBibleRepository:
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_asset_bible(self, workspace_id: str, asset_bible: dict[str, Any]) -> dict[str, Any]:
        self.asset_bibles[(workspace_id, asset_bible["asset_bible_id"])] = dict(asset_bible)
        return dict(asset_bible)

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any] | None:
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def list_asset_bibles(self, workspace_id: str, project_id: str) -> list[dict[str, Any]]:
        return []

    async def save_scene_cast(self, workspace_id: str, scene_cast: dict[str, Any]) -> dict[str, Any]:
        self.scene_casts[(workspace_id, scene_cast["scene_cast_id"])] = dict(scene_cast)
        return dict(scene_cast)

    async def load_scene_cast(self, workspace_id: str, scene_cast_id: str) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))

    async def list_scene_casts(
        self,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> list[dict[str, Any]]:
        return []


@dataclass
class FakeDependencyEdgeRepository:
    edges: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges[(workspace_id, edge["edge_id"])] = dict(edge)
        return dict(edge)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, Any]]:
        return [
            edge
            for (stored_workspace_id, _), edge in self.edges.items()
            if stored_workspace_id == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class FakeStaleMarkRepository:
    marks: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = field(
        default_factory=dict
    )

    async def mark_stale(self, workspace_id: str, mark: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        key = (
            workspace_id,
            mark["target_type"],
            mark["target_id"],
            mark["reason_code"],
            mark["upstream_type"],
            mark["upstream_id"],
            mark["upstream_version"],
        )
        if key in self.marks:
            return dict(self.marks[key]), False
        self.marks[key] = dict(mark)
        return dict(mark), True

    async def list_stale_marks(
        self,
        workspace_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        return []


@dataclass
class FakePromptPlanRepository:
    bundles: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def save_prompt_plan_bundle(self, workspace_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        self.bundles.append((workspace_id, dict(bundle)))
        return dict(bundle)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, Any]]:
        return []

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"prompt_plan_id": prompt_plan_id, "stale": True}


def _asset_bible() -> AssetBible:
    return AssetBible(
        asset_bible_id="bible_demo",
        workspace_id="workspace_1",
        project_id="project_1",
        ip_profiles=(
            IPProfile(
                ip_profile_id="ip_main",
                workspace_id="workspace_1",
                project_id="project_1",
                name="Pixelle Demo",
            ),
        ),
        character_profiles=(
            CharacterProfile(
                character_id="char_luna",
                workspace_id="workspace_1",
                project_id="project_1",
                display_name="Luna",
            ),
        ),
    )


def _scene_cast() -> SceneCast:
    return SceneCast(
        scene_cast_id="cast_frame_0001",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        asset_bible_id="bible_demo",
        character_ids=("char_luna",),
    )


def _prompt_plan_bundle_with_scene_cast() -> PromptPlanBundle:
    draft = ImagePromptDraft(
        image_prompt_draft_id="draft_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        prompt_text="Show Luna in the lab.",
    )
    plan = PromptPlan(
        prompt_plan_id="prompt_plan_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_1",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    return PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(draft,),
        prompt_plans=(plan,),
    )


@pytest.mark.asyncio
async def test_save_asset_bible_triggers_asset_bible_stale_propagation():
    assets = FakeAssetBibleRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwareAssetBibleWriteService(
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_asset_bible("workspace_1", _asset_bible())

    assert result.saved_payload["asset_bible_id"] == "bible_demo"
    assert result.version_token.startswith("asset_bible_rev_")
    assert result.propagation_summary.upstream_type == "asset_bible"
    assert result.propagation_summary.upstream_id == "bible_demo"
    assert result.propagation_summary.upstream_version == result.version_token


@pytest.mark.asyncio
async def test_save_scene_cast_writes_asset_bible_dependency_edge_and_triggers_scene_cast_propagation():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwareAssetBibleWriteService(
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_scene_cast("workspace_1", _scene_cast())

    edge = next(iter(edges.edges.values()))
    assert edge["edge_id"] == "dep_scene_cast_cast_frame_0001_asset_bible_bible_demo"
    assert edge["upstream_type"] == "asset_bible"
    assert edge["upstream_id"] == "bible_demo"
    assert edge["upstream_version"].startswith("asset_bible_rev_")
    assert edge["downstream_type"] == "scene_cast"
    assert edge["downstream_id"] == "cast_frame_0001"
    assert edge["relation"] == "scene_cast.references_asset_bible"
    assert result.propagation_summary.upstream_type == "scene_cast"
    assert result.propagation_summary.upstream_id == "cast_frame_0001"
    assert result.version_token.startswith("scene_cast_rev_")


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_writes_scene_cast_dependency_edge_and_triggers_prompt_plan_propagation():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    await assets.save_scene_cast("workspace_1", _scene_cast().to_dict())
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle(
        "workspace_1",
        "project_1",
        _prompt_plan_bundle_with_scene_cast(),
    )

    edge = next(iter(edges.edges.values()))
    assert edge["edge_id"] == "dep_prompt_plan_prompt_plan_1_scene_cast_cast_frame_0001"
    assert edge["upstream_type"] == "scene_cast"
    assert edge["upstream_id"] == "cast_frame_0001"
    assert edge["upstream_version"].startswith("scene_cast_rev_")
    assert edge["downstream_type"] == "prompt_plan"
    assert edge["downstream_id"] == "prompt_plan_1"
    assert edge["relation"] == "prompt_plan.uses_scene_cast"
    assert result.propagation_summary.upstream_type == "prompt_plan"
    assert result.propagation_summary.upstream_id == "prompt_plan_1"


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_without_public_dependency_source_does_not_guess_edges():
    assets = FakeAssetBibleRepository()
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    bundle = _prompt_plan_bundle_with_scene_cast()
    plan_payload = bundle.prompt_plans[0].to_dict()
    plan_payload["metadata"] = {}
    no_source_bundle = PromptPlanBundle(
        storyboard_plan_id=bundle.storyboard_plan_id,
        image_prompt_drafts=bundle.image_prompt_drafts,
        prompt_plans=(PromptPlan.from_dict(plan_payload),),
    )
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle(
        "workspace_1",
        "project_1",
        no_source_bundle,
    )

    assert edges.edges == {}
    assert result.propagation_summary.upstream_type == "prompt_plan"
    assert result.propagation_summary.upstream_id == "prompt_plan_1"


@pytest.mark.asyncio
async def test_save_prompt_plan_bundle_preserves_every_prompt_plan_propagation_summary():
    assets = FakeAssetBibleRepository()
    await assets.save_asset_bible("workspace_1", _asset_bible().to_dict())
    await assets.save_scene_cast("workspace_1", _scene_cast().to_dict())
    prompts = FakePromptPlanRepository()
    edges = FakeDependencyEdgeRepository()
    stale = FakeStaleMarkRepository()
    first_bundle = _prompt_plan_bundle_with_scene_cast()
    second_draft = ImagePromptDraft(
        image_prompt_draft_id="draft_2",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0002",
        prompt_text="Show Luna entering the observatory.",
    )
    second_plan = PromptPlan(
        prompt_plan_id="prompt_plan_2",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0002",
        image_prompt_draft_id="draft_2",
        prompt_sections={"visual_goal": "Show Luna entering the observatory."},
        final_prompt="Show Luna entering the observatory.",
        metadata={"scene_cast_id": "cast_frame_0001"},
    )
    bundle = PromptPlanBundle(
        storyboard_plan_id="storyboard_plan_1",
        image_prompt_drafts=(*first_bundle.image_prompt_drafts, second_draft),
        prompt_plans=(*first_bundle.prompt_plans, second_plan),
    )
    service = StaleAwarePromptPlanWriteService(
        prompt_plan_repository=prompts,
        asset_bible_repository=assets,
        edge_repository=edges,
        stale_repository=stale,
    )

    result = await service.save_prompt_plan_bundle("workspace_1", "project_1", bundle)

    assert tuple(summary.upstream_id for summary in result.propagation_summaries) == (
        "prompt_plan_1",
        "prompt_plan_2",
    )
    assert len(result.version_tokens) == 2
    assert all(version.startswith("prompt_plan_rev_") for version in result.version_tokens)
    assert len(result.dependency_edges) == 2
