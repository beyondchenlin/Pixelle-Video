from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pixelle_video.models.stale_dependency import DependencyEdge, StaleMark
from tests.support.test_client import create_test_client


@dataclass
class FakeDependencyEdgeRepository:
    edges: list[dict[str, Any]] = field(default_factory=list)
    list_calls: list[tuple[str, str, str, str]] = field(default_factory=list)

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
        self.list_calls.append((workspace_id, project_id, upstream_type, upstream_id))
        return [
            edge
            for edge in self.edges
            if edge["workspace_id"] == workspace_id
            and edge["project_id"] == project_id
            and edge["upstream_type"] == upstream_type
            and edge["upstream_id"] == upstream_id
        ]


@dataclass
class FakeStaleMarkRepository:
    marks: list[dict[str, Any]] = field(default_factory=list)
    list_calls: list[tuple[str, str, str, str]] = field(default_factory=list)

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


def _client(
    *,
    edge_repository: FakeDependencyEdgeRepository | None = None,
    stale_repository: FakeStaleMarkRepository | None = None,
) -> TestClient:
    from api.routers.stale_dependencies import router

    app = FastAPI()
    if edge_repository is not None:
        app.state.dependency_edge_repository = edge_repository
    if stale_repository is not None:
        app.state.stale_mark_repository = stale_repository
    app.include_router(router)
    return create_test_client(app)


def test_target_stale_api_returns_readable_stale_summary():
    stale_repository = FakeStaleMarkRepository()
    stale_repository.marks.append(
        StaleMark(
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
        ).to_dict()
    )
    client = _client(stale_repository=stale_repository)

    response = client.get(
        "/projects/project_1/stale/targets/prompt_plan/prompt_plan_001",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["stale_summary"]["is_stale"] is True
    assert body["stale_summary"]["primary_reasons"] == ["scene_cast_changed"]
    assert body["stale_summary"]["upstream_refs"] == [
        {
            "upstream_type": "scene_cast",
            "upstream_id": "cast_frame_001",
            "upstream_version": "scene_cast_rev_2",
            "reason_code": "scene_cast_changed",
            "source_edge_id": "dep_prompt_plan_prompt_plan_001_scene_cast_cast_frame_001",
            "via_relation": "prompt_plan.uses_scene_cast",
        }
    ]
    assert "C:\\" not in str(body)
    assert "provider_url" not in str(body)


def test_target_stale_api_rejects_path_like_ids_before_repository_call():
    stale_repository = FakeStaleMarkRepository()
    client = _client(stale_repository=stale_repository)

    response = client.get(
        "/projects/project_1/stale/targets/prompt_plan/C:\\plans\\1",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert stale_repository.list_calls == []


def test_target_stale_api_rejects_unknown_target_type_before_repository_call():
    stale_repository = FakeStaleMarkRepository()
    client = _client(stale_repository=stale_repository)

    response = client.get(
        "/projects/project_1/stale/targets/workflow_path/prompt_plan_001",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert stale_repository.list_calls == []


def test_target_stale_api_fails_fast_without_stale_repository():
    client = _client()

    response = client.get(
        "/projects/project_1/stale/targets/prompt_plan/prompt_plan_001",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 503
    assert "stale mark repository is not configured" in response.json()["detail"]


def test_downstream_stale_api_returns_dependency_edges():
    edge_repository = FakeDependencyEdgeRepository()
    edge_repository.edges.append(
        DependencyEdge(
            edge_id="dep_image_artifact_prompt_plan_001",
            workspace_id="workspace_1",
            project_id="project_1",
            upstream_type="prompt_plan",
            upstream_id="prompt_plan_001",
            upstream_version="prompt_plan_rev_5",
            downstream_type="image_artifact",
            downstream_id="image_artifact_001",
            relation="image_artifact.generated_from_prompt_plan",
        ).to_dict()
    )
    client = _client(edge_repository=edge_repository)

    response = client.get(
        "/projects/project_1/stale/upstream/prompt_plan/prompt_plan_001/downstream",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["downstream"]["downstream_refs"] == [
        {
            "downstream_type": "image_artifact",
            "downstream_id": "image_artifact_001",
            "relation": "image_artifact.generated_from_prompt_plan",
            "upstream_version": "prompt_plan_rev_5",
        }
    ]
    assert body["downstream"]["dependency_edges"][0]["edge_id"] == "dep_image_artifact_prompt_plan_001"


def test_downstream_stale_api_rejects_path_like_ids_before_repository_call():
    edge_repository = FakeDependencyEdgeRepository()
    client = _client(edge_repository=edge_repository)

    response = client.get(
        "/projects/project_1/stale/upstream/prompt_plan/C:\\plans\\1/downstream",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert edge_repository.list_calls == []


def test_downstream_stale_api_rejects_unknown_upstream_type_before_repository_call():
    edge_repository = FakeDependencyEdgeRepository()
    client = _client(edge_repository=edge_repository)

    response = client.get(
        "/projects/project_1/stale/upstream/provider_url/prompt_plan_001/downstream",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert edge_repository.list_calls == []
