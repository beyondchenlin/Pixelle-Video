from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pixelle_video.models.asset_bible import AssetBible, CharacterProfile, IPProfile
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.services.stale_write_integration import StaleAwareAssetBibleWriteService


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
