from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class FakeAssetBibleRepository:
    saved: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    saved_scene_casts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    asset_bibles: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    scene_casts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

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

    async def save_scene_cast(
        self,
        workspace_id: str,
        scene_cast: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(scene_cast)
        self.saved_scene_casts.append((workspace_id, payload))
        self.scene_casts[(workspace_id, payload["scene_cast_id"])] = payload
        return payload

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any] | None:
        return self.scene_casts.get((workspace_id, scene_cast_id))


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


def _scene_cast_payload(**overrides) -> dict[str, Any]:
    payload = {
        "workspace_id": "workspace_1",
        "scene_cast_id": "cast_frame_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
        "continuity_notes": ["Keep Luna's round goggles visible."],
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


def test_asset_bible_api_load_rejects_mismatched_repository_id():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    stored = dict(repository.asset_bibles[("workspace_1", "bible_demo")])
    stored["asset_bible_id"] = "other_bible"
    repository.asset_bibles[("workspace_1", "bible_demo")] = stored

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 502
    assert "asset bible ID" in response.json()["detail"]


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


def test_asset_bible_api_rejects_text_rendering_style_metadata():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    payload = _asset_bible_payload()
    payload["style_profiles"][0]["metadata"] = {"caption_style": {"font_size": 24}}
    response = client.post(
        "/projects/project_1/asset-bible",
        json=payload,
    )

    assert response.status_code == 422
    assert "caption_style" in response.json()["detail"]
    assert repository.saved == []


def test_asset_bible_api_fails_fast_without_repository():
    response = _client().post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    )

    assert response.status_code == 503
    assert "asset bible repository is not configured" in response.json()["detail"]


def test_scene_cast_api_creates_draft_after_asset_bible_validation():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["scene_cast"]["scene_cast_id"] == "cast_frame_1"
    assert body["scene_cast"]["project_id"] == "project_1"
    assert body["scene_cast"]["asset_bible_id"] == "bible_demo"
    assert body["scene_cast"]["character_ids"] == ["char_luna"]
    assert "local_path" not in str(body)
    assert "C:\\" not in str(body)
    assert repository.saved_scene_casts[0][0] == "workspace_1"


def test_scene_cast_api_loads_draft_from_repository():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(),
    ).status_code == 201

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scene_cast"]["frame_id"] == "frame_0001"
    assert body["scene_cast"]["style_id"] == "style_warm_comic"


def test_scene_cast_api_load_revalidates_asset_references():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    repository.scene_casts[("workspace_1", "cast_frame_1")] = {
        **_scene_cast_payload(character_ids=["char_missing"]),
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
    }

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert "char_missing" in response.json()["detail"]


def test_scene_cast_api_updates_draft_through_repository():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.put(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1",
        json=_scene_cast_payload(continuity_notes=["Updated continuity."]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scene_cast"]["continuity_notes"] == ["Updated continuity."]
    assert repository.saved_scene_casts[-1][1]["scene_cast_id"] == "cast_frame_1"


def test_scene_cast_api_rejects_unknown_asset_references_before_save():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(character_ids=["char_missing"]),
    )

    assert response.status_code == 422
    assert "char_missing" in response.json()["detail"]
    assert repository.saved_scene_casts == []


def test_scene_cast_api_rejects_missing_asset_bible_before_save():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(),
    )

    assert response.status_code == 404
    assert "asset bible draft was not found" in response.json()["detail"]
    assert repository.saved_scene_casts == []


def test_scene_cast_api_rejects_mismatched_route_scene_cast_id():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.put(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/other_cast",
        json=_scene_cast_payload(),
    )

    assert response.status_code == 422
    assert "scene_cast_id" in response.json()["detail"]
    assert repository.saved_scene_casts == []


def test_scene_cast_api_rejects_path_like_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(frame_id="C:\\frames\\1"),
    )

    assert response.status_code == 422
    assert repository.saved_scene_casts == []
