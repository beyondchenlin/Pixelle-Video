from __future__ import annotations

from dataclasses import dataclass

from pixelle_video.models.stale_dependency import (
    ALLOWED_DEPENDENCY_TYPES,
    DependencyEdge,
    StaleMark,
)
from pixelle_video.repositories.stale_dependencies import (
    DependencyEdgeRepository,
    StaleMarkRepository,
)


class StaleDependencyReadError(ValueError):
    pass


class StaleDependencyReadRepositoryNotConfiguredError(StaleDependencyReadError):
    pass


@dataclass(frozen=True)
class TargetStaleSummary:
    workspace_id: str
    project_id: str
    target_type: str
    target_id: str
    is_stale: bool
    stale_marks: tuple[StaleMark, ...]
    upstream_refs: tuple[dict[str, str | None], ...]
    primary_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "is_stale": self.is_stale,
            "stale_marks": [mark.to_dict() for mark in self.stale_marks],
            "upstream_refs": [dict(ref) for ref in self.upstream_refs],
            "primary_reasons": list(self.primary_reasons),
        }


@dataclass(frozen=True)
class UpstreamDownstreamSummary:
    workspace_id: str
    project_id: str
    upstream_type: str
    upstream_id: str
    dependency_edges: tuple[DependencyEdge, ...]
    downstream_refs: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "upstream_type": self.upstream_type,
            "upstream_id": self.upstream_id,
            "dependency_edges": [edge.to_dict() for edge in self.dependency_edges],
            "downstream_refs": [dict(ref) for ref in self.downstream_refs],
        }


class StaleDependencyReadService:
    def __init__(
        self,
        *,
        edge_repository: DependencyEdgeRepository | None,
        stale_repository: StaleMarkRepository | None,
    ) -> None:
        self.edge_repository = edge_repository
        self.stale_repository = stale_repository

    async def get_target_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        target_type: str,
        target_id: str,
    ) -> TargetStaleSummary:
        _validate_dependency_type("target_type", target_type)
        if self.stale_repository is None:
            raise StaleDependencyReadRepositoryNotConfiguredError(
                "stale mark repository is not configured"
            )
        payloads = await self.stale_repository.list_stale_marks(
            workspace_id,
            target_type,
            target_id,
        )
        marks = tuple(StaleMark.from_dict(payload) for payload in payloads)
        return TargetStaleSummary(
            workspace_id=workspace_id,
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            is_stale=bool(marks),
            stale_marks=marks,
            upstream_refs=tuple(_upstream_ref(mark) for mark in marks),
            primary_reasons=tuple(dict.fromkeys(mark.reason_code for mark in marks)),
        )

    async def get_downstream_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> UpstreamDownstreamSummary:
        _validate_dependency_type("upstream_type", upstream_type)
        if self.edge_repository is None:
            raise StaleDependencyReadRepositoryNotConfiguredError(
                "dependency edge repository is not configured"
            )
        payloads = await self.edge_repository.list_downstream_edges(
            workspace_id,
            upstream_type,
            upstream_id,
        )
        edges = tuple(DependencyEdge.from_dict(payload) for payload in payloads)
        return UpstreamDownstreamSummary(
            workspace_id=workspace_id,
            project_id=project_id,
            upstream_type=upstream_type,
            upstream_id=upstream_id,
            dependency_edges=edges,
            downstream_refs=tuple(_downstream_ref(edge) for edge in edges),
        )


def _upstream_ref(mark: StaleMark) -> dict[str, str | None]:
    source_edge_id = mark.metadata.get("source_edge_id")
    via_relation = mark.metadata.get("via_relation")
    return {
        "upstream_type": mark.upstream_type,
        "upstream_id": mark.upstream_id,
        "upstream_version": mark.upstream_version,
        "reason_code": mark.reason_code,
        "source_edge_id": source_edge_id if isinstance(source_edge_id, str) else None,
        "via_relation": via_relation if isinstance(via_relation, str) else None,
    }


def _downstream_ref(edge: DependencyEdge) -> dict[str, str]:
    return {
        "downstream_type": edge.downstream_type,
        "downstream_id": edge.downstream_id,
        "relation": edge.relation,
        "upstream_version": edge.upstream_version,
    }


def _validate_dependency_type(field_name: str, value: str) -> None:
    if value not in ALLOWED_DEPENDENCY_TYPES:
        raise ValueError(f"{field_name} must be one of {sorted(ALLOWED_DEPENDENCY_TYPES)}")
