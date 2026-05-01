from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.stale_dependency import (
    DependencyEdge,
    StalePropagationSummary,
    UpstreamChangeEvent,
)
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)
from pixelle_video.services.dependency_versions import DependencyVersionService
from pixelle_video.services.stale_dependency_propagation import StaleDependencyPropagationService


class StaleWriteIntegrationError(ValueError):
    pass


class StaleWriteDependencyNotFoundError(StaleWriteIntegrationError):
    pass


@dataclass(frozen=True)
class StaleAwareWriteResult:
    saved_payload: Mapping[str, Any]
    version_tokens: tuple[str, ...]
    propagation_summaries: tuple[StalePropagationSummary, ...]
    dependency_edges: tuple[DependencyEdge, ...] = field(default_factory=tuple)

    @property
    def version_token(self) -> str:
        if len(self.version_tokens) != 1:
            raise StaleWriteIntegrationError("write result contains multiple version tokens")
        return self.version_tokens[0]

    @property
    def propagation_summary(self) -> StalePropagationSummary:
        if len(self.propagation_summaries) != 1:
            raise StaleWriteIntegrationError("write result contains multiple propagation summaries")
        return self.propagation_summaries[0]


class StaleAwareAssetBibleWriteService:
    def __init__(
        self,
        *,
        asset_bible_repository: AssetBibleRepository,
        edge_repository: DependencyEdgeRepository,
        stale_repository: StaleMarkRepository,
        version_service: DependencyVersionService | None = None,
    ) -> None:
        self.asset_bible_repository = asset_bible_repository
        self.edge_repository = edge_repository
        self.stale_repository = stale_repository
        self.version_service = version_service or DependencyVersionService()
        self.propagation_service = StaleDependencyPropagationService(
            edge_repository=edge_repository,
            stale_repository=stale_repository,
        )

    async def save_asset_bible(self, workspace_id: str, asset_bible: AssetBible) -> StaleAwareWriteResult:
        saved = await self.asset_bible_repository.save_asset_bible(workspace_id, asset_bible.to_dict())
        saved_model = AssetBible.from_dict(saved)
        version_token = self.version_service.version_for_asset_bible(saved_model)
        summary = await self.propagation_service.propagate_upstream_change(
            UpstreamChangeEvent(
                workspace_id=workspace_id,
                project_id=saved_model.project_id,
                upstream_type="asset_bible",
                upstream_id=saved_model.asset_bible_id,
                upstream_version=version_token,
                reason_code="asset_bible_changed",
            )
        )
        return StaleAwareWriteResult(
            saved_payload=saved_model.to_dict(),
            version_tokens=(version_token,),
            propagation_summaries=(summary,),
        )

    async def save_scene_cast(self, workspace_id: str, scene_cast: SceneCast) -> StaleAwareWriteResult:
        asset_bible_payload = await self.asset_bible_repository.load_asset_bible(
            workspace_id,
            scene_cast.asset_bible_id,
        )
        if asset_bible_payload is None:
            raise StaleWriteDependencyNotFoundError("asset bible draft was not found")
        asset_bible = AssetBible.from_dict(asset_bible_payload)
        asset_bible_version = self.version_service.version_for_asset_bible(asset_bible)
        saved = await self.asset_bible_repository.save_scene_cast(workspace_id, scene_cast.to_dict())
        saved_model = SceneCast.from_dict(saved)
        scene_cast_version = self.version_service.version_for_scene_cast(saved_model)
        edge = DependencyEdge(
            edge_id=f"dep_scene_cast_{saved_model.scene_cast_id}_asset_bible_{saved_model.asset_bible_id}",
            workspace_id=workspace_id,
            project_id=saved_model.project_id,
            upstream_type="asset_bible",
            upstream_id=saved_model.asset_bible_id,
            upstream_version=asset_bible_version,
            downstream_type="scene_cast",
            downstream_id=saved_model.scene_cast_id,
            relation="scene_cast.references_asset_bible",
        )
        await self.edge_repository.save_dependency_edge(workspace_id, edge.to_dict())
        summary = await self.propagation_service.propagate_upstream_change(
            UpstreamChangeEvent(
                workspace_id=workspace_id,
                project_id=saved_model.project_id,
                upstream_type="scene_cast",
                upstream_id=saved_model.scene_cast_id,
                upstream_version=scene_cast_version,
                reason_code="scene_cast_changed",
            )
        )
        return StaleAwareWriteResult(
            saved_payload=saved_model.to_dict(),
            version_tokens=(scene_cast_version,),
            propagation_summaries=(summary,),
            dependency_edges=(edge,),
        )
