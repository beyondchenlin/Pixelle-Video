from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.stale_dependency import DependencyEdge, StaleMark
from pixelle_video.services.stale_dependency_read_model import StaleDependencyReadService


@dataclass
class InMemoryDependencyEdgeRepository:
    edges: list[dict[str, Any]] = field(default_factory=list)

    async def save_dependency_edge(self, workspace_id: str, edge: dict[str, Any]) -> dict[str, Any]:
        self.edges.append(dict(edge))
        return dict(edge)

    async def list_downstream_edges(
        self,
        workspace_id: str,
        project_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, Any]]:
        return [
            edge
            for edge in self.edges
            if edge["workspace_id"] == workspace_id
            and edge["project_id"] == project_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class InMemoryStaleMarkRepository:
    marks: list[dict[str, Any]] = field(default_factory=list)
    list_calls: list[tuple[str, str, str]] = field(default_factory=list)

    async def mark_stale(self, workspace_id: str, mark: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        self.marks.append(dict(mark))
        return dict(mark), True

    async def list_stale_marks(
        self,
        workspace_id: str,
        project_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        self.list_calls.append((workspace_id, project_id, target_type, target_id))
        return [
            mark
            for mark in self.marks
            if mark["workspace_id"] == workspace_id
            and mark["project_id"] == project_id
            and mark["target_type"] == target_type
            and mark["target_id"] == target_id
        ]


@pytest.mark.asyncio
async def test_target_stale_summary_reports_reasons_and_upstream_refs():
    stale_repository = InMemoryStaleMarkRepository()
    mark = StaleMark(
        stale_id="stale_prompt_plan_1",
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
        reason_code="scene_cast_changed",
        upstream_type="scene_cast",
        upstream_id="cast_frame_001",
        upstream_version="scene_cast_rev_2",
        marked_at="2026-05-01T10:00:00Z",
        metadata={
            "source_edge_id": "dep_prompt_plan_prompt_plan_001_scene_cast_cast_frame_001",
            "via_relation": "prompt_plan.uses_scene_cast",
            "auto_rewrite_allowed": False,
        },
    )
    await stale_repository.mark_stale("workspace_1", mark.to_dict())
    service = StaleDependencyReadService(
        edge_repository=InMemoryDependencyEdgeRepository(),
        stale_repository=stale_repository,
    )

    summary = await service.get_target_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
    )

    assert summary.is_stale is True
    assert summary.primary_reasons == ("scene_cast_changed",)
    assert summary.upstream_refs == (
        {
            "upstream_type": "scene_cast",
            "upstream_id": "cast_frame_001",
            "upstream_version": "scene_cast_rev_2",
            "reason_code": "scene_cast_changed",
            "source_edge_id": "dep_prompt_plan_prompt_plan_001_scene_cast_cast_frame_001",
            "via_relation": "prompt_plan.uses_scene_cast",
        },
    )
    assert summary.stale_marks == (mark,)


@pytest.mark.asyncio
async def test_target_stale_summary_is_clean_when_no_marks_exist():
    service = StaleDependencyReadService(
        edge_repository=InMemoryDependencyEdgeRepository(),
        stale_repository=InMemoryStaleMarkRepository(),
    )

    summary = await service.get_target_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="image_artifact",
        target_id="image_artifact_001",
    )

    assert summary.is_stale is False
    assert summary.stale_marks == ()
    assert summary.upstream_refs == ()
    assert summary.primary_reasons == ()


@pytest.mark.asyncio
async def test_downstream_summary_lists_dependency_edges_and_public_refs():
    edge_repository = InMemoryDependencyEdgeRepository()
    edge = DependencyEdge(
        edge_id="dep_image_artifact_prompt_plan_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
        upstream_version="prompt_plan_rev_5",
        downstream_type="image_artifact",
        downstream_id="image_artifact_001",
        relation="image_artifact.generated_from_prompt_plan",
    )
    await edge_repository.save_dependency_edge("workspace_1", edge.to_dict())
    service = StaleDependencyReadService(
        edge_repository=edge_repository,
        stale_repository=InMemoryStaleMarkRepository(),
    )

    summary = await service.get_downstream_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_001",
    )

    assert summary.dependency_edges == (edge,)
    assert summary.downstream_refs == (
        {
            "downstream_type": "image_artifact",
            "downstream_id": "image_artifact_001",
            "relation": "image_artifact.generated_from_prompt_plan",
            "upstream_version": "prompt_plan_rev_5",
        },
    )


@pytest.mark.asyncio
async def test_downstream_summary_is_scoped_to_project_id():
    edge_repository = InMemoryDependencyEdgeRepository()
    await edge_repository.save_dependency_edge(
        "workspace_1",
        DependencyEdge(
            edge_id="dep_project_1",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_shared",
            upstream_version="prompt_plan_rev_1",
            downstream_type="image_artifact",
            downstream_id="artifact_project_1",
            relation="image_artifact.generated_from_prompt_plan",
        ).to_dict(),
    )
    await edge_repository.save_dependency_edge(
        "workspace_1",
        DependencyEdge(
            edge_id="dep_project_2",
            workspace_id="workspace_1",
            project_id="project_2",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_shared",
            upstream_version="prompt_plan_rev_2",
            downstream_type="image_artifact",
            downstream_id="artifact_project_2",
            relation="image_artifact.generated_from_prompt_plan",
        ).to_dict(),
    )
    service = StaleDependencyReadService(
        edge_repository=edge_repository,
        stale_repository=InMemoryStaleMarkRepository(),
    )

    summary = await service.get_downstream_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="prompt_plan",
        upstream_id="prompt_plan_shared",
    )

    assert summary.project_id == "project_1"
    assert tuple(edge.edge_id for edge in summary.dependency_edges) == ("dep_project_1",)
    assert summary.downstream_refs == (
        {
            "downstream_type": "image_artifact",
            "downstream_id": "artifact_project_1",
            "relation": "image_artifact.generated_from_prompt_plan",
            "upstream_version": "prompt_plan_rev_1",
        },
    )


@pytest.mark.asyncio
async def test_target_summary_rejects_unknown_target_type_before_repository_call():
    stale_repository = InMemoryStaleMarkRepository()
    service = StaleDependencyReadService(
        edge_repository=InMemoryDependencyEdgeRepository(),
        stale_repository=stale_repository,
    )

    with pytest.raises(ValueError, match="target_type"):
        await service.get_target_summary(
            workspace_id="workspace_1",
            project_id="project_1",
            target_type="workflow_path",
            target_id="prompt_plan_001",
        )

    assert stale_repository.list_calls == []


@pytest.mark.asyncio
async def test_target_stale_summary_is_scoped_to_project_id():
    stale_repository = InMemoryStaleMarkRepository()
    await stale_repository.mark_stale(
        "workspace_1",
        StaleMark(
            stale_id="stale_project_1",
            workspace_id="workspace_1",
            project_id="project_1",
            target_type="prompt_plan",
            target_id="prompt_plan_shared",
            reason_code="scene_cast_changed",
            upstream_type="scene_cast",
            upstream_id="cast_project_1",
            upstream_version="scene_cast_rev_1",
            marked_at="2026-05-01T10:00:00Z",
        ).to_dict(),
    )
    await stale_repository.mark_stale(
        "workspace_1",
        StaleMark(
            stale_id="stale_project_2",
            workspace_id="workspace_1",
            project_id="project_2",
            target_type="prompt_plan",
            target_id="prompt_plan_shared",
            reason_code="asset_bible_changed",
            upstream_type="asset_bible",
            upstream_id="bible_project_2",
            upstream_version="asset_bible_rev_2",
            marked_at="2026-05-01T10:01:00Z",
        ).to_dict(),
    )
    service = StaleDependencyReadService(
        edge_repository=InMemoryDependencyEdgeRepository(),
        stale_repository=stale_repository,
    )

    summary = await service.get_target_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="prompt_plan",
        target_id="prompt_plan_shared",
    )

    assert summary.project_id == "project_1"
    assert tuple(mark.stale_id for mark in summary.stale_marks) == ("stale_project_1",)
    assert summary.primary_reasons == ("scene_cast_changed",)


@pytest.mark.asyncio
async def test_downstream_summary_rejects_unknown_upstream_type_before_repository_call():
    edge_repository = InMemoryDependencyEdgeRepository()
    service = StaleDependencyReadService(
        edge_repository=edge_repository,
        stale_repository=InMemoryStaleMarkRepository(),
    )

    with pytest.raises(ValueError, match="upstream_type"):
        await service.get_downstream_summary(
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="provider_url",
            upstream_id="prompt_plan_001",
        )

    assert edge_repository.edges == []
