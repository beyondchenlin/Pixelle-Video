from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


def test_http_ip_workbench_client_wraps_asset_bible_helpers():
    from web.ip_workbench.http_client import HttpStoryboardIPWorkbenchClient

    calls: list[tuple[str, dict[str, Any]]] = []

    def list_asset_bibles(**kwargs):
        calls.append(("list_asset_bibles", kwargs))
        return [{"asset_bible_id": "bible_demo"}]

    def list_scene_casts(**kwargs):
        calls.append(("list_scene_casts", kwargs))
        return [{"scene_cast_id": "cast_frame_1"}]

    def apply_scene_cast_to_prompt_plan(**kwargs):
        calls.append(("apply", kwargs))
        return {"success": True, "application": {"prompt_plan": {"prompt_plan_id": "plan_1"}}}

    client = HttpStoryboardIPWorkbenchClient(
        api_base_url="http://localhost:8001/api/",
        asset_bible_loader=list_asset_bibles,
        scene_cast_loader=list_scene_casts,
        scene_cast_applier=apply_scene_cast_to_prompt_plan,
    )

    assert client.list_asset_bibles(
        workspace_id="workspace_1",
        project_id="project_1",
    ) == {"success": True, "asset_bibles": [{"asset_bible_id": "bible_demo"}]}
    assert client.list_scene_casts(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    ) == {"success": True, "scene_casts": [{"scene_cast_id": "cast_frame_1"}]}
    assert client.apply_scene_cast_to_prompt_plan(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        actor_id="user_1",
    )["success"] is True
    assert calls == [
        (
            "list_asset_bibles",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
            },
        ),
        (
            "list_scene_casts",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "asset_bible_id": "bible_demo",
            },
        ),
        (
            "apply",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "asset_bible_id": "bible_demo",
                "scene_cast_id": "cast_frame_1",
                "storyboard_plan_id": "storyboard_plan_1",
                "frame_id": "frame_0001",
                "actor_id": "user_1",
            },
        ),
    ]


def test_inprocess_ip_workbench_client_uses_local_services_without_http():
    from web.ip_workbench.inprocess_client import InProcessStoryboardIPWorkbenchClient

    class AssetRepository:
        async def list_asset_bibles(self, workspace_id, project_id):
            return [{"asset_bible_id": "bible_demo"}]

        async def list_scene_casts(self, workspace_id, project_id, asset_bible_id):
            return [{"scene_cast_id": "cast_frame_1", "asset_bible_id": asset_bible_id}]

    class ApplyService:
        async def apply_scene_cast_to_prompt_plan_bundle(self, **kwargs):
            return type(
                "Result",
                (),
                {
                    "to_dict": lambda _self: {
                        "prompt_plan": {"prompt_plan_id": "prompt_plan_1"},
                        "source": {
                            "asset_bible_id": kwargs["asset_bible_id"],
                            "scene_cast_id": kwargs["scene_cast_id"],
                            "prompt_plan_id": "prompt_plan_1",
                        },
                        "write": {
                            "version_tokens": ["prompt_plan_rev_1"],
                            "dependency_edge_count": 1,
                            "stale_mark_count": 0,
                        },
                    }
                },
            )()

    core = type(
        "Core",
        (),
        {
            "asset_bible_repository": AssetRepository(),
            "asset_prompt_plan_apply_service": ApplyService(),
        },
    )()

    client = InProcessStoryboardIPWorkbenchClient(
        pixelle_video=core,
        async_runner=asyncio.run,
    )

    assert client.list_asset_bibles(
        workspace_id="workspace_1",
        project_id="project_1",
    ) == {"success": True, "asset_bibles": [{"asset_bible_id": "bible_demo"}]}
    assert client.list_scene_casts(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    )["scene_casts"][0]["scene_cast_id"] == "cast_frame_1"
    assert client.apply_scene_cast_to_prompt_plan(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        scene_cast_id="cast_frame_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
    )["application"]["source"]["scene_cast_id"] == "cast_frame_1"


def test_ip_workbench_client_factory_does_not_cache_unconfigured_inprocess_client(
    monkeypatch,
):
    from web.state.ip_workbench_client import resolve_storyboard_ip_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_storyboard_ip_workbench_client(session_state, pixelle_video=None)

    assert client is None
    assert "storyboard_ip_workbench_client" not in session_state


def test_ip_workbench_client_factory_caches_http_by_api_base_url(monkeypatch):
    from web.state.ip_workbench_client import resolve_storyboard_ip_workbench_client

    monkeypatch.setenv("PIXELLE_WORKBENCH_CLIENT_MODE", "http")
    session_state = {"api_base_url": "http://localhost:8001/api"}

    first = resolve_storyboard_ip_workbench_client(session_state, pixelle_video=None)
    second = resolve_storyboard_ip_workbench_client(session_state, pixelle_video=None)

    assert first is second
    assert session_state["storyboard_ip_workbench_client_cache_key"] == (
        "http",
        "http://localhost:8001/api",
    )


def test_formal_ip_workbench_ui_sources_do_not_import_http_helpers():
    for path in [
        Path("web/components/ip_workbench_panel.py"),
        Path("web/components/storyboard_preview.py"),
        Path("web/pages/3_🧭_Storyboard_Workbench.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        for token in (
            "web.utils.asset_bible_api",
            "httpx",
            "DEFAULT_API_BASE_URL",
            "localhost:8001",
        ):
            assert token not in source
