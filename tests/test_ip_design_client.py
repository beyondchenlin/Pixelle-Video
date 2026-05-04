from __future__ import annotations

import asyncio
from typing import Any


def test_http_ip_design_client_wraps_asset_bible_helpers():
    from web.ip_design.http_client import HttpIPDesignClient

    calls: list[tuple[str, dict[str, Any]]] = []

    def list_asset_bibles(**kwargs):
        calls.append(("list_asset_bibles", kwargs))
        return [{"asset_bible_id": "bible_demo"}]

    def load_asset_bible(**kwargs):
        calls.append(("load_asset_bible", kwargs))
        return {"asset_bible": {"asset_bible_id": kwargs["asset_bible_id"]}}

    def save_asset_bible(**kwargs):
        calls.append(("save_asset_bible", kwargs))
        return {"asset_bible": {"asset_bible_id": kwargs["asset_bible_id"]}}

    def list_scene_casts(**kwargs):
        calls.append(("list_scene_casts", kwargs))
        return [{"scene_cast_id": "cast_frame_1"}]

    def load_scene_cast(**kwargs):
        calls.append(("load_scene_cast", kwargs))
        return {"scene_cast": {"scene_cast_id": kwargs["scene_cast_id"]}}

    def save_scene_cast(**kwargs):
        calls.append(("save_scene_cast", kwargs))
        return {"scene_cast": {"scene_cast_id": kwargs["scene_cast_id"]}}

    client = HttpIPDesignClient(
        api_base_url="http://localhost:8001/api/",
        asset_bible_loader=list_asset_bibles,
        asset_bible_getter=load_asset_bible,
        asset_bible_saver=save_asset_bible,
        scene_cast_loader=list_scene_casts,
        scene_cast_getter=load_scene_cast,
        scene_cast_saver=save_scene_cast,
    )

    assert client.list_asset_bibles(workspace_id="workspace_1", project_id="project_1")[
        "asset_bibles"
    ] == [{"asset_bible_id": "bible_demo"}]
    assert client.load_asset_bible(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    )["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert client.save_asset_bible(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        payload={"ip_profiles": [{"ip_profile_id": "ip_main", "name": "Demo IP"}]},
    )["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert client.list_scene_casts(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    )["scene_casts"] == [{"scene_cast_id": "cast_frame_1"}]
    assert client.load_scene_cast(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
    )["scene_cast"]["scene_cast_id"] == "cast_frame_1"
    assert client.save_scene_cast(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        payload={"frame_id": "frame_0001"},
    )["scene_cast"]["scene_cast_id"] == "cast_frame_1"
    assert [name for name, _ in calls] == [
        "list_asset_bibles",
        "load_asset_bible",
        "save_asset_bible",
        "list_scene_casts",
        "load_scene_cast",
        "save_scene_cast",
    ]
    assert all(call["api_base_url"] == "http://localhost:8001/api" for _, call in calls)


def test_inprocess_ip_design_client_uses_asset_repository_without_http():
    from web.ip_design.inprocess_client import InProcessIPDesignClient

    class AssetRepository:
        def __init__(self):
            self.asset_bibles: dict[tuple[str, str], dict[str, Any]] = {}
            self.scene_casts: dict[tuple[str, str], dict[str, Any]] = {}

        async def list_asset_bibles(self, workspace_id, project_id):
            return [
                payload
                for (stored_workspace, _), payload in self.asset_bibles.items()
                if stored_workspace == workspace_id and payload["project_id"] == project_id
            ]

        async def load_asset_bible(self, workspace_id, asset_bible_id):
            return self.asset_bibles.get((workspace_id, asset_bible_id))

        async def save_asset_bible(self, workspace_id, asset_bible):
            self.asset_bibles[(workspace_id, asset_bible["asset_bible_id"])] = dict(asset_bible)
            return dict(asset_bible)

        async def list_scene_casts(self, workspace_id, project_id, asset_bible_id):
            return [
                payload
                for (stored_workspace, _), payload in self.scene_casts.items()
                if stored_workspace == workspace_id
                and payload["project_id"] == project_id
                and payload["asset_bible_id"] == asset_bible_id
            ]

        async def load_scene_cast(self, workspace_id, scene_cast_id):
            return self.scene_casts.get((workspace_id, scene_cast_id))

        async def save_scene_cast(self, workspace_id, scene_cast):
            self.scene_casts[(workspace_id, scene_cast["scene_cast_id"])] = dict(scene_cast)
            return dict(scene_cast)

    repository = AssetRepository()
    core = type("Core", (), {"asset_bible_repository": repository})()
    client = InProcessIPDesignClient(pixelle_video=core, async_runner=asyncio.run)

    saved_asset = client.save_asset_bible(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        payload={
            "ip_profiles": [
                {
                    "ip_profile_id": "ip_main",
                    "name": "Demo IP",
                }
            ],
            "character_profiles": [
                {
                    "character_id": "char_luna",
                    "display_name": "Luna",
                }
            ],
            "scene_assets": [
                {
                    "scene_id": "scene_lab",
                    "display_name": "Sky Lab",
                }
            ],
            "prop_assets": [
                {
                    "prop_id": "prop_compass",
                    "display_name": "Star Compass",
                }
            ],
            "style_profiles": [
                {
                    "style_id": "style_warm_comic",
                    "display_name": "Warm Comic",
                    "visual_style": "warm comic",
                }
            ],
        },
    )
    assert saved_asset["asset_bible"]["asset_bible_id"] == "bible_demo"
    assert client.list_asset_bibles(
        workspace_id="workspace_1",
        project_id="project_1",
    )["asset_bibles"][0]["ip_profiles"][0]["name"] == "Demo IP"

    saved_cast = client.save_scene_cast(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        payload={
            "storyboard_plan_id": "storyboard_plan_1",
            "frame_id": "frame_0001",
            "character_ids": ["char_luna"],
            "scene_id": "scene_lab",
            "prop_ids": ["prop_compass"],
            "style_id": "style_warm_comic",
        },
    )
    assert saved_cast["scene_cast"]["asset_bible_id"] == "bible_demo"
    assert client.list_scene_casts(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    )["scene_casts"][0]["scene_cast_id"] == "cast_frame_1"


def test_ip_design_client_factory_does_not_cache_unconfigured_inprocess_client(
    monkeypatch,
):
    from web.state.ip_design_client import resolve_ip_design_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_ip_design_client(session_state, pixelle_video=None)

    assert client is None
    assert "ip_design_client" not in session_state


def test_ip_design_client_factory_caches_http_by_api_base_url(monkeypatch):
    from web.state.ip_design_client import resolve_ip_design_client

    monkeypatch.setenv("PIXELLE_WORKBENCH_CLIENT_MODE", "http")
    session_state = {"api_base_url": "http://localhost:8001/api"}

    first = resolve_ip_design_client(session_state, pixelle_video=None)
    second = resolve_ip_design_client(session_state, pixelle_video=None)

    assert first is second
    assert session_state["ip_design_client_cache_key"] == (
        "http",
        "http://localhost:8001/api",
    )
