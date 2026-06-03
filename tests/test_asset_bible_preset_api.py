from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pixelle_video.services.asset_bible_preset_registry import AssetBiblePresetRegistry


@dataclass
class FakeAssetBibleRepository:
    saved: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    load_calls: list[tuple[str, str]] = field(default_factory=list)

    async def save_asset_bible(
        self,
        workspace_id: str,
        asset_bible: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(asset_bible)
        self.saved.append((workspace_id, payload))
        self.asset_bibles[(workspace_id, payload["asset_bible_id"])] = payload
        return payload

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any] | None:
        self.load_calls.append((workspace_id, asset_bible_id))
        return self.asset_bibles.get((workspace_id, asset_bible_id))


def _client(
    registry: AssetBiblePresetRegistry | None = None,
    repository: FakeAssetBibleRepository | None = None,
) -> TestClient:
    from api.routers.asset_bible_presets import router as asset_bible_presets_router

    app = FastAPI()
    if registry is not None:
        app.state.asset_bible_preset_registry = registry
    if repository is not None:
        app.state.asset_bible_repository = repository
    app.include_router(asset_bible_presets_router, prefix="/api")
    return TestClient(app)


def _registry(tmp_path: Path) -> AssetBiblePresetRegistry:
    root = tmp_path / "asset_bibles"
    root.mkdir()
    (root / "demo.json").write_text(json.dumps(_preset_payload()), encoding="utf-8")
    return AssetBiblePresetRegistry(root=root)


def _preset_payload() -> dict[str, Any]:
    return {
        "preset_id": "builtin_asset_bible_demo",
        "revision": "2026-05-04.1",
        "source": "builtin",
        "display_name": "Demo IP",
        "description": "Demo preset.",
        "tags": ["demo"],
        "preview_asset_path": "resources/presets/asset_bibles/previews/demo.png",
        "asset_bible": {
            "asset_bible_id": "demo_bible",
            "workspace_id": "__builtin__",
            "project_id": "__builtin__",
            "ip_profiles": [
                {
                    "series_visual_signature_profile_id": "ip_main",
                    "workspace_id": "__builtin__",
                    "project_id": "__builtin__",
                    "name": "Demo IP",
                    "identity_lock": ["white cartoon rabbit"],
                    "identity_anchors": ["blue bow tie"],
                    "forbidden_elements": ["private internal note"],
                }
            ],
            "character_profiles": [],
            "scene_assets": [],
            "prop_assets": [],
            "style_profiles": [],
            "metadata": {},
        },
    }


def test_asset_bible_preset_api_lists_presets(tmp_path: Path):
    client = _client(registry=_registry(tmp_path))

    response = client.get("/api/presets/asset-bibles")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [
            {
                "preset_id": "builtin_asset_bible_demo",
                "revision": "2026-05-04.1",
                "source": "builtin",
                "display_name": "Demo IP",
                "description": "Demo preset.",
                "tags": ["demo"],
                "preview_asset_path": "resources/presets/asset_bibles/previews/demo.png",
            }
        ]
    }


def test_asset_bible_preset_api_loads_detail(tmp_path: Path):
    client = _client(registry=_registry(tmp_path))

    response = client.get("/api/presets/asset-bibles/builtin_asset_bible_demo")

    assert response.status_code == 200
    body = response.json()
    assert body["preset"]["preset_id"] == "builtin_asset_bible_demo"
    assert body["preset"]["asset_bible"]["asset_bible_id"] == "demo_bible"
    assert body["preset"]["asset_bible"]["ip_profiles"][0].get("forbidden_elements") == ["private internal note"]


def test_asset_bible_preset_api_maps_unknown_detail_to_404(tmp_path: Path):
    client = _client(registry=_registry(tmp_path))

    response = client.get("/api/presets/asset-bibles/missing")

    assert response.status_code == 404
    assert "unknown asset bible preset" in response.json()["detail"]


def test_asset_bible_preset_api_imports_preset_to_project(tmp_path: Path):
    repository = FakeAssetBibleRepository()
    client = _client(registry=_registry(tmp_path), repository=repository)

    response = client.post(
        "/api/projects/project_1/asset-bible/import-from-preset",
        json={
            "workspace_id": "workspace_1",
            "preset_id": "builtin_asset_bible_demo",
            "asset_bible_id": "demo_project_bible",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["asset_bible"]["asset_bible_id"] == "demo_project_bible"
    assert body["asset_bible"]["workspace_id"] == "workspace_1"
    assert body["asset_bible"]["project_id"] == "project_1"
    assert body["asset_bible"]["metadata"]["origin_preset_id"] == (
        "builtin_asset_bible_demo"
    )
    assert body["asset_bible"]["ip_profiles"][0].get("forbidden_elements") == ["private internal note"]
    assert repository.saved[0][0] == "workspace_1"


def test_asset_bible_preset_api_import_overwrites_existing(tmp_path: Path):
    repository = FakeAssetBibleRepository()
    repository.asset_bibles[("workspace_1", "demo_project_bible")] = {
        **_preset_payload()["asset_bible"],
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "asset_bible_id": "demo_project_bible",
        "ip_profiles": [
            {
                "series_visual_signature_profile_id": "old_profile",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "name": "Old Profile",
            }
        ],
    }
    client = _client(registry=_registry(tmp_path), repository=repository)

    response = client.post(
        "/api/projects/project_1/asset-bible/import-from-preset",
        json={
            "workspace_id": "workspace_1",
            "preset_id": "builtin_asset_bible_demo",
            "asset_bible_id": "demo_project_bible",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["asset_bible"]["ip_profiles"][0]["name"] == "Demo IP"
    assert repository.saved[0][0] == "workspace_1"


def test_asset_bible_preset_api_list_fails_without_registry():
    client = _client()

    response = client.get("/api/presets/asset-bibles")

    assert response.status_code == 503
    assert "asset bible preset registry is not configured" in response.json()["detail"]


def test_asset_bible_preset_api_import_fails_without_repository(tmp_path: Path):
    client = _client(registry=_registry(tmp_path))

    response = client.post(
        "/api/projects/project_1/asset-bible/import-from-preset",
        json={
            "workspace_id": "workspace_1",
            "preset_id": "builtin_asset_bible_demo",
            "asset_bible_id": "demo_project_bible",
        },
    )

    assert response.status_code == 503
    assert "asset bible repository is not configured" in response.json()["detail"]
