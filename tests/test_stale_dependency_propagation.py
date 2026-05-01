from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.stale_dependency import DependencyEdge, UpstreamChangeEvent
from pixelle_video.services.stale_dependency_propagation import StaleDependencyPropagationService


@dataclass
class InMemoryDependencyEdgeRepository:
    edges: list[dict[str, Any]] = field(default_factory=list)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges.append(dict(edge))
        return dict(edge)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, Any]]:
        return [
            edge
            for edge in self.edges
            if edge["workspace_id"] == workspace_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class InMemoryStaleMarkRepository:
    marks: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = field(default_factory=dict)

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
        return [
            mark
            for key, mark in self.marks.items()
            if key[0] == workspace_id and key[1] == target_type and key[2] == target_id
        ]


async def seed_edge(repository: InMemoryDependencyEdgeRepository, **overrides: Any) -> None:
    payload = {
        "edge_id": f"dep_edge_{len(repository.edges) + 1}",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "upstream_type": "asset_bible",
        "upstream_id": "bible_demo",
        "upstream_version": "asset_bible_rev_3",
        "downstream_type": "scene_cast",
        "downstream_id": "cast_frame_0001",
        "relation": "scene_cast.references_asset_bible",
    }
    payload.update(overrides)
    await repository.save_dependency_edge("workspace_1", DependencyEdge(**payload).to_dict())


@pytest.mark.asyncio
async def test_asset_bible_change_marks_scene_cast_prompt_plan_and_image_artifact_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(edges)
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )
    )

    assert summary.visited_edge_count == 3
    assert summary.stale_created_count == 3
    assert summary.stale_existing_count == 0
    assert set(summary.marked_target_ids) == {
        "cast_frame_0001",
        "prompt_plan_001",
        "image_artifact_001",
    }
    assert stale.marks[
        (
            "workspace_1",
            "prompt_plan",
            "prompt_plan_001",
            "asset_bible_changed_via_scene_cast",
            "asset_bible",
            "bible_demo",
            "asset_bible_rev_4",
        )
    ]["upstream_version"] == "asset_bible_rev_4"


@pytest.mark.asyncio
async def test_scene_cast_change_marks_prompt_plan_and_image_artifact_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="scene_cast",
            upstream_id="cast_frame_0001",
            upstream_version="scene_cast_rev_3",
            reason_code="scene_cast_changed",
        )
    )

    assert summary.visited_edge_count == 2
    assert summary.stale_created_count == 2
    assert set(summary.marked_target_ids) == {"prompt_plan_001", "image_artifact_001"}


@pytest.mark.asyncio
async def test_direct_asset_bible_to_prompt_plan_edge_uses_direct_reason():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_3",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_direct",
        relation="prompt_plan.references_asset_bible",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )
    )

    assert summary.stale_created_count == 1
    mark = next(iter(stale.marks.values()))
    assert mark["target_type"] == "prompt_plan"
    assert mark["target_id"] == "prompt_plan_direct"
    assert mark["reason_code"] == "asset_bible_changed"
    assert mark["metadata"]["source_edge_id"] == "dep_edge_1"
    assert mark["metadata"]["source_edge_version"] == "asset_bible_rev_3"
    assert mark["metadata"]["is_direct_event_upstream"] is True


@pytest.mark.asyncio
async def test_direct_edge_on_current_upstream_version_is_not_marked_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_current",
        relation="prompt_plan.uses_scene_cast",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="scene_cast",
            upstream_id="cast_frame_0001",
            upstream_version="scene_cast_rev_3",
            reason_code="scene_cast_changed",
        )
    )

    assert summary.visited_edge_count == 0
    assert summary.stale_created_count == 0
    assert summary.stale_existing_count == 0
    assert summary.marked_target_ids == ()
    assert stale.marks == {}


@pytest.mark.asyncio
async def test_recursive_propagation_does_not_compare_original_version_to_intermediate_edges():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="asset_bible",
        upstream_id="bible_demo",
        upstream_version="asset_bible_rev_3",
        downstream_type="scene_cast",
        downstream_id="cast_frame_0001",
        relation="scene_cast.references_asset_bible",
    )
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="asset_bible_rev_4",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="asset_bible",
            upstream_id="bible_demo",
            upstream_version="asset_bible_rev_4",
            reason_code="asset_bible_changed",
        )
    )

    assert summary.visited_edge_count == 2
    assert summary.stale_created_count == 2
    assert set(summary.marked_target_ids) == {"cast_frame_0001", "prompt_plan_001"}
    assert (
        "workspace_1",
        "prompt_plan",
        "prompt_plan_001",
        "asset_bible_changed_via_scene_cast",
        "asset_bible",
        "bible_demo",
        "asset_bible_rev_4",
    ) in stale.marks


def test_stale_service_module_does_not_import_stage2_projection_or_provider_routing():
    import inspect

    import pixelle_video.services.stale_dependency_propagation as module

    source = inspect.getsource(module)

    assert "stage2_projection" not in source
    assert "asset_prompt_plan_composer" not in source
    assert "comfyui" not in source.lower()
    assert "provider routing" not in source.lower()
    assert "workflow_path" not in source
    assert "save_prompt_plan_bundle" not in source


@pytest.mark.asyncio
async def test_prompt_plan_change_marks_image_artifact_video_segment_and_final_video_stale():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    await seed_edge(
        edges,
        upstream_type="image_artifact",
        upstream_id="image_artifact_001",
        upstream_version="image_artifact_rev_1",
        downstream_type="video_segment",
        downstream_id="video_segment_001",
        relation="video_segment.uses_image_artifact",
    )
    await seed_edge(
        edges,
        upstream_type="video_segment",
        upstream_id="video_segment_001",
        upstream_version="video_segment_rev_1",
        downstream_type="final_video",
        downstream_id="final_video_001",
        relation="final_video.uses_video_segment",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_6",
            reason_code="prompt_plan_changed",
        )
    )

    assert summary.visited_edge_count == 3
    assert summary.stale_created_count == 3
    assert set(summary.marked_target_ids) == {
        "image_artifact_001",
        "video_segment_001",
        "final_video_001",
    }
    assert stale.marks[
        (
            "workspace_1",
            "video_segment",
            "video_segment_001",
            "prompt_plan_changed_via_image_artifact",
            "prompt_plan",
            "prompt_plan_001",
            "prompt_plan_rev_6",
        )
    ]["reason_code"] == "prompt_plan_changed_via_image_artifact"
    assert stale.marks[
        (
            "workspace_1",
            "final_video",
            "final_video_001",
            "prompt_plan_changed_via_video_segment",
            "prompt_plan",
            "prompt_plan_001",
            "prompt_plan_rev_6",
        )
    ]["reason_code"] == "prompt_plan_changed_via_video_segment"


@pytest.mark.asyncio
async def test_lock_policy_does_not_block_stale_marking():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
        metadata={"lock_policy": "locked_artifact"},
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)

    summary = await service.propagate_upstream_change(
        UpstreamChangeEvent(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_6",
            reason_code="prompt_plan_changed",
        )
    )

    assert summary.stale_created_count == 1
    mark = next(iter(stale.marks.values()))
    assert mark["target_id"] == "image_artifact_001"
    assert mark["metadata"]["lock_policy"] == "locked_artifact"
    assert mark["metadata"]["auto_rewrite_allowed"] is False


@pytest.mark.asyncio
async def test_repeating_same_upstream_version_is_idempotent_and_auditable():
    edges = InMemoryDependencyEdgeRepository()
    stale = InMemoryStaleMarkRepository()
    await seed_edge(
        edges,
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_2",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )
    service = StaleDependencyPropagationService(edge_repository=edges, stale_repository=stale)
    event = UpstreamChangeEvent(
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        reason_code="scene_cast_changed",
    )

    first = await service.propagate_upstream_change(event)
    second = await service.propagate_upstream_change(event)

    assert first.stale_created_count == 1
    assert first.stale_existing_count == 0
    assert second.stale_created_count == 0
    assert second.stale_existing_count == 1
    assert len(stale.marks) == 1
    mark = next(iter(stale.marks.values()))
    assert mark["reason_code"] == "scene_cast_changed"
    assert mark["upstream_version"] == "scene_cast_rev_3"
    assert mark["marked_at"].endswith("Z")
    assert mark["metadata"]["auto_rewrite_allowed"] is False
