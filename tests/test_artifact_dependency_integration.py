from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.services.artifact_dependency_integration import (
    ArtifactDependencyWriteService,
)
from pixelle_video.services.dependency_versions import DependencyVersionService


@dataclass
class FakeDependencyEdgeRepository:
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
        return []


@pytest.mark.asyncio
async def test_record_image_artifact_dependency_writes_prompt_plan_edge_without_storage_path_identity():
    repository = FakeDependencyEdgeRepository()
    service = ArtifactDependencyWriteService(edge_repository=repository)
    prompt_plan = PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_plan_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
        metadata={"workflow_path": "workflows/selfhost/image_qwen.json"},
    )
    artifact_version = ArtifactVersion(
        version_id="artifact_version_001",
        artifact_id="artifact_frame_0001_image",
        workspace_id="workspace_1",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_001",
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_001.png",
        status=ArtifactVersionStatus.SUCCEEDED,
        provider="comfyui",
        provider_metadata={"provider_url": "https://example.test/output.png"},
    )

    edge = await service.record_image_artifact_dependency(
        workspace_id="workspace_1",
        project_id="project_1",
        artifact_version=artifact_version,
        prompt_plan=prompt_plan,
    )

    expected_upstream_version = DependencyVersionService().version_for_prompt_plan(prompt_plan)
    assert edge.edge_id == "dep_image_artifact_artifact_frame_0001_image_prompt_plan_prompt_plan_001"
    assert edge.workspace_id == "workspace_1"
    assert edge.project_id == "project_1"
    assert edge.upstream_type == "prompt_plan"
    assert edge.upstream_id == "prompt_plan_001"
    assert edge.upstream_version == expected_upstream_version
    assert edge.downstream_type == "image_artifact"
    assert edge.downstream_id == "artifact_frame_0001_image"
    assert edge.relation == "image_artifact.generated_from_prompt_plan"
    assert edge.metadata == {}
    assert repository.edges == [edge.to_dict()]

    saved_text = repr(repository.edges[0])
    assert "artifacts/workspace_1" not in saved_text
    assert "https://example.test" not in saved_text
    assert "workflows/selfhost" not in saved_text
    assert "comfyui" not in saved_text
