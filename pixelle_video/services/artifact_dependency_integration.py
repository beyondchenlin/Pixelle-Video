from __future__ import annotations

from pixelle_video.models.artifact import ArtifactVersion
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.stale_dependency import DependencyEdge
from pixelle_video.repositories.stale_dependencies import DependencyEdgeRepository
from pixelle_video.services.dependency_versions import DependencyVersionService


class ArtifactDependencyIntegrationError(ValueError):
    pass


class ArtifactDependencyWriteService:
    def __init__(
        self,
        *,
        edge_repository: DependencyEdgeRepository,
        version_service: DependencyVersionService | None = None,
    ) -> None:
        self.edge_repository = edge_repository
        self.version_service = version_service or DependencyVersionService()

    async def record_image_artifact_dependency(
        self,
        *,
        workspace_id: str,
        project_id: str,
        artifact_version: ArtifactVersion,
        prompt_plan: PromptPlan,
    ) -> DependencyEdge:
        if artifact_version.source_prompt_plan_id != prompt_plan.prompt_plan_id:
            raise ArtifactDependencyIntegrationError(
                "artifact version source prompt plan does not match prompt plan"
            )

        edge = DependencyEdge(
            edge_id=(
                f"dep_image_artifact_{artifact_version.artifact_id}_"
                f"prompt_plan_{prompt_plan.prompt_plan_id}"
            ),
            workspace_id=workspace_id,
            project_id=project_id,
            upstream_type="prompt_plan",
            upstream_id=prompt_plan.prompt_plan_id,
            upstream_version=self.version_service.version_for_prompt_plan(prompt_plan),
            downstream_type="image_artifact",
            downstream_id=artifact_version.artifact_id,
            relation="image_artifact.generated_from_prompt_plan",
        )
        saved = await self.edge_repository.save_dependency_edge(workspace_id, edge.to_dict())
        return DependencyEdge.from_dict(saved)
