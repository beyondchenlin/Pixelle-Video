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
    load_asset_bible_calls: list[tuple[str, str]] = field(default_factory=list)
    load_scene_cast_calls: list[tuple[str, str]] = field(default_factory=list)
    list_asset_bible_calls: list[tuple[str, str]] = field(default_factory=list)
    list_scene_cast_calls: list[tuple[str, str, str]] = field(default_factory=list)
    saved_asset_bible_id_override: str | None = None
    saved_scene_cast_id_override: str | None = None

    async def save_asset_bible(
        self,
        workspace_id: str,
        asset_bible: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(asset_bible)
        if self.saved_asset_bible_id_override is not None:
            payload["asset_bible_id"] = self.saved_asset_bible_id_override
        self.saved.append((workspace_id, payload))
        self.asset_bibles[(workspace_id, payload["asset_bible_id"])] = payload
        return payload

    async def load_asset_bible(
        self,
        workspace_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any] | None:
        self.load_asset_bible_calls.append((workspace_id, asset_bible_id))
        return self.asset_bibles.get((workspace_id, asset_bible_id))

    async def list_asset_bibles(
        self,
        workspace_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        self.list_asset_bible_calls.append((workspace_id, project_id))
        return [
            payload
            for (stored_workspace_id, _), payload in self.asset_bibles.items()
            if stored_workspace_id == workspace_id
            and payload.get("project_id") == project_id
        ]

    async def save_scene_cast(
        self,
        workspace_id: str,
        scene_cast: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(scene_cast)
        if self.saved_scene_cast_id_override is not None:
            payload["scene_cast_id"] = self.saved_scene_cast_id_override
        self.saved_scene_casts.append((workspace_id, payload))
        self.scene_casts[(workspace_id, payload["scene_cast_id"])] = payload
        return payload

    async def load_scene_cast(
        self,
        workspace_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any] | None:
        self.load_scene_cast_calls.append((workspace_id, scene_cast_id))
        return self.scene_casts.get((workspace_id, scene_cast_id))

    async def list_scene_casts(
        self,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> list[dict[str, Any]]:
        self.list_scene_cast_calls.append((workspace_id, project_id, asset_bible_id))
        return [
            payload
            for (stored_workspace_id, _), payload in self.scene_casts.items()
            if stored_workspace_id == workspace_id
            and payload.get("project_id") == project_id
            and payload.get("asset_bible_id") == asset_bible_id
        ]


@dataclass
class FakePromptPlanRepository:
    prompt_plans: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    load_calls: list[tuple[str, str]] = field(default_factory=list)

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, Any]]:
        self.load_calls.append((workspace_id, storyboard_id))
        return self.prompt_plans.get((workspace_id, storyboard_id), [])


def _client(
    repository: FakeAssetBibleRepository | None = None,
    *,
    prompt_plan_repository: FakePromptPlanRepository | None = None,
) -> TestClient:
    from api.routers.asset_bible import router as asset_bible_router

    app = FastAPI()
    if repository is not None:
        app.state.asset_bible_repository = repository
    if prompt_plan_repository is not None:
        app.state.prompt_plan_repository = prompt_plan_repository
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


def _prompt_plan_payload(**overrides) -> dict[str, Any]:
    payload = {
        "prompt_plan_id": "prompt_plan_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "image_prompt_draft_id": "draft_1",
        "prompt_sections": {"visual_goal": "Show Luna in the lab."},
        "final_prompt": "Show Luna in the lab.",
        "source_trace_id": "trace_1",
        "metadata": {"source": "stage1a"},
    }
    payload.update(overrides)
    return payload


def _projection_request_payload(**overrides) -> dict[str, Any]:
    payload = {
        "workspace_id": "workspace_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
    }
    payload.update(overrides)
    return payload


def _client_with_projection_dependencies() -> tuple[TestClient, FakeAssetBibleRepository, FakePromptPlanRepository]:
    repository = FakeAssetBibleRepository()
    prompt_plan_repository = FakePromptPlanRepository()
    client = _client(
        repository,
        prompt_plan_repository=prompt_plan_repository,
    )
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(),
    ).status_code == 201
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload()
    ]
    repository.load_asset_bible_calls.clear()
    repository.load_scene_cast_calls.clear()
    return client, repository, prompt_plan_repository


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


def test_asset_bible_api_create_rejects_mismatched_repository_id():
    repository = FakeAssetBibleRepository(saved_asset_bible_id_override="other_bible")
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    )

    assert response.status_code == 502
    assert "asset bible ID" in response.json()["detail"]


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


def test_asset_bible_api_lists_drafts_by_workspace_and_project():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(asset_bible_id="bible_demo"),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(asset_bible_id="bible_alt"),
    ).status_code == 201
    assert client.post(
        "/projects/project_2/asset-bible",
        json=_asset_bible_payload(asset_bible_id="bible_other_project"),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(
            workspace_id="workspace_2",
            asset_bible_id="bible_other_workspace",
        ),
    ).status_code == 201

    response = client.get(
        "/projects/project_1/asset-bible",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["asset_bible_id"] for item in body["asset_bibles"]] == [
        "bible_demo",
        "bible_alt",
    ]
    assert repository.list_asset_bible_calls == [("workspace_1", "project_1")]
    assert "C:\\" not in str(body)
    assert "local_path" not in str(body)


def test_asset_bible_api_list_rejects_path_like_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.get(
        "/projects/project_1/asset-bible",
        params={"workspace_id": "C:\\workspace"},
    )

    assert response.status_code == 422
    assert repository.list_asset_bible_calls == []


def test_asset_bible_api_list_rejects_path_like_repository_metadata():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    stored = dict(repository.asset_bibles[("workspace_1", "bible_demo")])
    stored["metadata"] = {"local_path": "C:\\assets\\bible.json"}
    repository.asset_bibles[("workspace_1", "bible_demo")] = stored

    response = client.get(
        "/projects/project_1/asset-bible",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 502
    assert "metadata.local_path" in response.json()["detail"]
    assert "C:\\" not in response.json()["detail"]


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


def test_asset_bible_api_rejects_path_like_metadata_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    payload = _asset_bible_payload()
    payload["character_profiles"][0]["metadata"] = {"local_path": "C:\\assets\\luna.png"}
    response = client.post(
        "/projects/project_1/asset-bible",
        json=payload,
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
    assert "caption_style" in str(response.json()["detail"])
    assert repository.saved == []


def test_asset_bible_api_rejects_font_prefixed_metadata():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(metadata={"font_color": "#fff"}),
    )

    assert response.status_code == 422
    assert "font_color" in str(response.json()["detail"])
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


def test_scene_cast_api_create_rejects_mismatched_repository_id():
    repository = FakeAssetBibleRepository(saved_scene_cast_id_override="other_cast")
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(),
    )

    assert response.status_code == 502
    assert "scene cast ID" in response.json()["detail"]


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


def test_scene_cast_api_lists_drafts_by_asset_bible():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(scene_cast_id="cast_frame_1"),
    ).status_code == 201
    assert client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(
            scene_cast_id="cast_frame_2",
            frame_id="frame_0002",
        ),
    ).status_code == 201
    repository.scene_casts[("workspace_1", "cast_other_bible")] = {
        **_scene_cast_payload(scene_cast_id="cast_other_bible"),
        "project_id": "project_1",
        "asset_bible_id": "bible_other",
    }

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["scene_cast_id"] for item in body["scene_casts"]] == [
        "cast_frame_1",
        "cast_frame_2",
    ]
    assert repository.list_scene_cast_calls == [
        ("workspace_1", "project_1", "bible_demo")
    ]
    assert "C:\\" not in str(body)
    assert "local_path" not in str(body)


def test_scene_cast_api_list_rejects_path_like_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.get(
        "/projects/project_1/asset-bible/C:\\bibles\\1/scene-casts",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 422
    assert repository.list_scene_cast_calls == []


def test_scene_cast_api_list_rejects_path_like_repository_metadata():
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
    stored = dict(repository.scene_casts[("workspace_1", "cast_frame_1")])
    stored["metadata"] = {"local_path": "C:\\casts\\cast.json"}
    repository.scene_casts[("workspace_1", "cast_frame_1")] = stored

    response = client.get(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        params={"workspace_id": "workspace_1"},
    )

    assert response.status_code == 502
    assert "metadata.local_path" in response.json()["detail"]
    assert "C:\\" not in response.json()["detail"]


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


def test_scene_cast_api_rejects_path_like_metadata_before_repository_call():
    repository = FakeAssetBibleRepository()
    client = _client(repository)
    assert client.post(
        "/projects/project_1/asset-bible",
        json=_asset_bible_payload(),
    ).status_code == 201

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts",
        json=_scene_cast_payload(metadata={"source_url": "https://example.test/ref"}),
    )

    assert response.status_code == 422
    assert repository.saved_scene_casts == []


def test_prompt_plan_projection_api_returns_preview_through_repositories():
    client, _, _ = _client_with_projection_dependencies()

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["projection"]["prompt_plan"]["prompt_plan_id"] == "prompt_plan_1"
    assert body["projection"]["prompt_plan"]["final_prompt"] == "Show Luna in the lab."
    assert body["projection"]["prompt_plan"]["character_ids"] == ["char_luna"]
    assert body["projection"]["prompt_plan"]["scene_id"] == "scene_lab"
    assert body["projection"]["prompt_plan"]["prop_ids"] == ["prop_compass"]
    assert body["projection"]["prompt_plan"]["style_id"] == "style_warm_comic"
    assert body["projection"]["prompt_plan"]["metadata"]["scene_cast_id"] == "cast_frame_1"
    assert body["projection"]["source"] == {
        "asset_bible_id": "bible_demo",
        "scene_cast_id": "cast_frame_1",
        "prompt_plan_id": "prompt_plan_1",
    }
    assert "C:\\" not in str(body)
    assert "local_path" not in str(body)


def test_prompt_plan_projection_api_rejects_text_rendering_metadata_from_repository():
    client, _, prompt_plan_repository = _client_with_projection_dependencies()
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload(metadata={"caption_style": {"font_size": 72}})
    ]

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "metadata.caption_style" in response.json()["detail"]


def test_prompt_plan_projection_api_fails_fast_without_prompt_plan_repository():
    repository = FakeAssetBibleRepository()
    client = _client(repository)

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 503
    assert "prompt plan repository is not configured" in response.json()["detail"]


def test_prompt_plan_projection_api_rejects_path_like_body_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    prompt_plan_repository = FakePromptPlanRepository()
    client = _client(
        repository,
        prompt_plan_repository=prompt_plan_repository,
    )

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(frame_id="C:\\frames\\1"),
    )

    assert response.status_code == 422
    assert repository.load_asset_bible_calls == []
    assert repository.load_scene_cast_calls == []
    assert prompt_plan_repository.load_calls == []


def test_prompt_plan_projection_api_rejects_path_like_route_ids_before_repository_call():
    repository = FakeAssetBibleRepository()
    prompt_plan_repository = FakePromptPlanRepository()
    client = _client(
        repository,
        prompt_plan_repository=prompt_plan_repository,
    )

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/C:\\casts\\1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 422
    assert repository.load_asset_bible_calls == []
    assert repository.load_scene_cast_calls == []
    assert prompt_plan_repository.load_calls == []


def test_prompt_plan_projection_api_maps_missing_prompt_plan_to_404():
    client, _, prompt_plan_repository = _client_with_projection_dependencies()
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload(frame_id="frame_0002")
    ]

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 404
    assert "prompt plan" in response.json()["detail"]


def test_prompt_plan_projection_api_maps_scene_cast_validation_to_422():
    client, repository, _ = _client_with_projection_dependencies()
    repository.scene_casts[("workspace_1", "cast_frame_1")] = {
        **_scene_cast_payload(character_ids=["char_missing"]),
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
    }

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 422
    assert "char_missing" in response.json()["detail"]


def test_prompt_plan_projection_api_maps_repository_identity_to_502():
    client, repository, _ = _client_with_projection_dependencies()
    stored = dict(repository.asset_bibles[("workspace_1", "bible_demo")])
    stored["asset_bible_id"] = "other_bible"
    repository.asset_bibles[("workspace_1", "bible_demo")] = stored

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "asset bible" in response.json()["detail"]


def test_prompt_plan_projection_api_maps_scene_cast_repository_identity_to_502():
    client, repository, _ = _client_with_projection_dependencies()
    repository.scene_casts[("workspace_1", "cast_frame_1")] = {
        **_scene_cast_payload(scene_cast_id="other_cast"),
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
    }

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "scene cast ID" in response.json()["detail"]


def test_prompt_plan_projection_api_maps_prompt_plan_repository_identity_to_502():
    client, _, prompt_plan_repository = _client_with_projection_dependencies()
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload(storyboard_plan_id="other_storyboard")
    ]

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "prompt plan storyboard" in response.json()["detail"]


def test_prompt_plan_projection_api_rejects_path_like_prompt_plan_response_ids():
    client, _, prompt_plan_repository = _client_with_projection_dependencies()
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload(prompt_plan_id="C:\\plans\\1")
    ]

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "prompt_plan_id" in response.json()["detail"]
    assert "C:\\" not in response.json()["detail"]


def test_prompt_plan_projection_api_rejects_path_like_prompt_plan_metadata():
    client, _, prompt_plan_repository = _client_with_projection_dependencies()
    prompt_plan_repository.prompt_plans[("workspace_1", "storyboard_plan_1")] = [
        _prompt_plan_payload(metadata={"local_path": "C:\\plans\\1.json"})
    ]

    response = client.post(
        "/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-projection",
        json=_projection_request_payload(),
    )

    assert response.status_code == 502
    assert "metadata.local_path" in response.json()["detail"]
    assert "C:\\" not in response.json()["detail"]
