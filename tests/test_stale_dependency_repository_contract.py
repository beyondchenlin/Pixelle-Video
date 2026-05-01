from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.stale_dependency import DependencyEdge, StaleMark
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)


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
    marks: dict[tuple[str, str, str, str, str, str, str, str], dict[str, Any]] = field(default_factory=dict)

    async def mark_stale(self, workspace_id: str, mark: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        key = (
            workspace_id,
            mark["project_id"],
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
        project_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        return [
            mark
            for key, mark in self.marks.items()
            if key[0] == workspace_id
            and key[1] == project_id
            and key[2] == target_type
            and key[3] == target_id
        ]


def test_fake_repositories_satisfy_protocols():
    edge_repository = InMemoryDependencyEdgeRepository()
    stale_repository = InMemoryStaleMarkRepository()

    assert isinstance(edge_repository, DependencyEdgeRepository)
    assert isinstance(stale_repository, StaleMarkRepository)


@pytest.mark.asyncio
async def test_dependency_edge_repository_lists_downstream_edges_by_public_upstream():
    repository = InMemoryDependencyEdgeRepository()
    edge = DependencyEdge(
        edge_id="dep_edge_001",
        workspace_id="workspace_1",
        project_id="project_1",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_3",
        downstream_type="prompt_plan",
        downstream_id="prompt_plan_001",
        relation="prompt_plan.uses_scene_cast",
    )

    await repository.save_dependency_edge("workspace_1", edge.to_dict())

    assert await repository.list_downstream_edges(
        "workspace_1",
        "project_1",
        "scene_cast",
        "cast_frame_0001",
    ) == [edge.to_dict()]
    assert await repository.list_downstream_edges("workspace_1", "project_1", "asset_bible", "bible_demo") == []


@pytest.mark.asyncio
async def test_stale_mark_repository_is_idempotent_for_same_reason_and_upstream_version():
    repository = InMemoryStaleMarkRepository()
    mark = StaleMark(
        stale_id="stale_001",
        workspace_id="workspace_1",
        project_id="project_1",
        target_type="prompt_plan",
        target_id="prompt_plan_001",
        reason_code="scene_cast_changed",
        upstream_type="scene_cast",
        upstream_id="cast_frame_0001",
        upstream_version="scene_cast_rev_4",
        marked_at="2026-05-01T10:03:00Z",
    )

    first, first_created = await repository.mark_stale("workspace_1", mark.to_dict())
    second, second_created = await repository.mark_stale("workspace_1", mark.to_dict())

    assert first == second
    assert first_created is True
    assert second_created is False
    assert len(await repository.list_stale_marks("workspace_1", "project_1", "prompt_plan", "prompt_plan_001")) == 1
