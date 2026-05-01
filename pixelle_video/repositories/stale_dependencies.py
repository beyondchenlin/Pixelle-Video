from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class DependencyEdgeRepository(Protocol):
    async def save_dependency_edge(
        self,
        workspace_id: str,
        edge: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, object]]:
        raise NotImplementedError


@runtime_checkable
class StaleMarkRepository(Protocol):
    async def mark_stale(
        self,
        workspace_id: str,
        mark: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        raise NotImplementedError

    async def list_stale_marks(
        self,
        workspace_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, object]]:
        raise NotImplementedError
