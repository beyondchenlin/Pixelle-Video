from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class FakeAssetBibleRepository:
    saved: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

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
        return self.asset_bibles.get((workspace_id, asset_bible_id))


def _client(repository: FakeAssetBibleRepository | None = None) -> TestClient:
    from api.routers.asset_bible import router as asset_bible_router

    app = FastAPI()
    if repository is not None:
        app.state.asset_bible_repository = repository
    app.include_router(asset_bible_router)
    return TestClient(app)


def _asset_bible_payload(**overrides) -> dict[str, Any]:
    payload = {
        "workspace_id": "workspace_1",
        "asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "ip_name": "Pixelle Demo",
        "world_hint": "Soft futuristic city.",
        "style_hint": "clean comic panels",
        "forbidden_elements": ["brand logos"],
        "character_profiles": [
            {
                "character_id": "char_luna",
                "display_name": "Luna",
                "role": "lead inventor",
                "visual_description": "short silver hair",
                "continuity_notes": ["round goggles"],
            }
        ],
        "scene_assets": [
            {
                "scene_id": "scene_lab",
                "display_name": "Sky Lab",
                "visual_description": "floating workshop",
            }
        ],
        "prop_assets": [
            {
                "prop_id": "prop_compass",
                "display_name": "Star Compass",
                "visual_description": "brass compass",
            }
        ],
        "style_profiles": [
            {
                "style_id": "style_warm_comic",
                "display_name": "Warm Comic",
                "visual_style": "warm comic",
                "provider_prompt": "warm comic, clean line art",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_asset_bible_api_creates_draft_through_repository_without_local_paths():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert body["asset_bible"]["project_id"] == "project_1"
    assert body["asset_bible"]["ip_profiles"][0]["name"] == "Pixelle Demo"
    assert body["asset_bible"]["ip_profiles"][0]["forbidden_elements"] == [
        "brand logos"
    ]
    assert body["asset_bible"]["character_profiles"][0]["character_id"] == "char_luna"
    assert "local_path" not in str(body)
    assert "C:\\" not in str(body)
    assert repository.saved[0][0] == "workspace_1"


def test_asset_bible_api_loads_draft_from_repository():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    create_response = client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    )
    assert create_response.status_code == 201

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert body["asset_bible"]["style_profiles"][0]["style_id"] == "style_warm_comic"


def test_asset_bible_api_updates_draft_through_repository():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.put(
        "/projects/project_1/asset-bible/bible_demo",
        json=_asset_bible_payload(ip_name="Updated IP"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["asset_bible"]["ip_profiles"][0]["name"] == "Updated IP"
    assert repository.saved[-1][1]["asset_bible_id"] == "bible_demo"


def test_asset_bible_api_rejects_path_like_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/C:project/asset-bible",
        json=_asset_bible_payload(),
    )

    assert response.status_code == 422
    assert repository.saved == []


def test_asset_bible_api_maps_domain_validation_errors_to_422():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(forbidden_elements=[""]),
    )

    assert response.status_code == 422
    assert "forbidden_elements" in response.json()["detail"]
    assert repository.saved == []


def test_asset_bible_api_fails_fast_without_repository():
    response = _client().post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    )

    assert response.status_code == 503
    assert "asset bible repository is not configured" in response.json()["detail"]
