from __future__ import annotations

import asyncio
from typing import Any


def test_http_ip_design_client_wraps_asset_bible_helpers():
    from web.ip_design.http_client import HttpIPDesignClient

    calls: list[tuple[str, dict[str, Any]]] = []

    def list_asset_bible_presets(**kwargs):
        calls.append(("list_asset_bible_presets", kwargs))
        return [{"preset_id": "builtin_asset_bible_demo"}]

    def import_asset_bible_preset(**kwargs):
        calls.append(("import_asset_bible_preset", kwargs))
        return {"asset_bible": {"asset_bible_id": kwargs["asset_bible_id"]}}

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
        api_base_url="http://localhost:8888/api/",
        asset_bible_loader=list_asset_bibles,
        asset_bible_getter=load_asset_bible,
        asset_bible_saver=save_asset_bible,
        asset_bible_preset_loader=list_asset_bible_presets,
        asset_bible_preset_importer=import_asset_bible_preset,
        scene_cast_loader=list_scene_casts,
        scene_cast_getter=load_scene_cast,
        scene_cast_saver=save_scene_cast,
    )

    assert client.list_asset_bible_presets() == [{"preset_id": "builtin_asset_bible_demo"}]
    assert client.import_asset_bible_preset(
        workspace_id="workspace_1",
        project_id="project_1",
        preset_id="builtin_asset_bible_demo",
        asset_bible_id="demo_bible",
    )["asset_bible"]["asset_bible_id"] == "demo_bible"
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
        "list_asset_bible_presets",
        "import_asset_bible_preset",
        "list_asset_bibles",
        "load_asset_bible",
        "save_asset_bible",
        "list_scene_casts",
        "load_scene_cast",
        "save_scene_cast",
    ]
    assert all(call["api_base_url"] == "http://localhost:8888/api" for _, call in calls)


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
            payload = dict(asset_bible)
            payload["ip_profiles"] = [
                {**dict(profile), "forbidden_elements": ["private"]}
                for profile in payload.get("ip_profiles", [])
            ]
            self.asset_bibles[(workspace_id, payload["asset_bible_id"])] = payload
            return payload

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
    assert saved_asset["asset_bible"]["ip_profiles"][0].get("forbidden_elements") == ["private"]
    assert client.list_asset_bibles(
        workspace_id="workspace_1",
        project_id="project_1",
    )["asset_bibles"][0]["ip_profiles"][0]["name"] == "Demo IP"
    listed_asset = client.list_asset_bibles(
        workspace_id="workspace_1",
        project_id="project_1",
    )["asset_bibles"][0]
    loaded_asset = client.load_asset_bible(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
    )["asset_bible"]
    assert listed_asset["ip_profiles"][0].get("forbidden_elements") == ["private"]
    assert loaded_asset["ip_profiles"][0].get("forbidden_elements") == ["private"]

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


def test_inprocess_ip_design_client_save_marks_imported_asset_bible_customized():
    from web.ip_design.inprocess_client import InProcessIPDesignClient

    class AssetRepository:
        def __init__(self):
            self.asset_bibles: dict[tuple[str, str], dict[str, Any]] = {
                (
                    "workspace_1",
                    "bible_demo",
                ): {
                    "asset_bible_id": "bible_demo",
                    "workspace_id": "workspace_1",
                    "project_id": "project_1",
                    "ip_profiles": [
                        {
                            "ip_profile_id": "ip_main",
                            "workspace_id": "workspace_1",
                            "project_id": "project_1",
                            "name": "Demo IP",
                            "forbidden_elements": ["private"],
                        }
                    ],
                    "character_profiles": [],
                    "scene_assets": [],
                    "prop_assets": [],
                    "style_profiles": [],
                    "metadata": {
                        "source_kind": "imported",
                        "origin_preset_id": "builtin_asset_bible_demo",
                        "origin_revision": "2026-05-04.1",
                        "imported_at": "2026-05-04T00:00:00Z",
                        "customized": False,
                    },
                }
            }

        async def load_asset_bible(self, workspace_id, asset_bible_id):
            return self.asset_bibles.get((workspace_id, asset_bible_id))

        async def save_asset_bible(self, workspace_id, asset_bible):
            payload = dict(asset_bible)
            self.asset_bibles[(workspace_id, payload["asset_bible_id"])] = payload
            return payload

    repository = AssetRepository()
    core = type("Core", (), {"asset_bible_repository": repository})()
    client = InProcessIPDesignClient(pixelle_video=core, async_runner=asyncio.run)

    response = client.save_asset_bible(
        workspace_id="workspace_1",
        project_id="project_1",
        asset_bible_id="bible_demo",
        payload={
            "ip_profiles": [{"ip_profile_id": "ip_main", "name": "Updated IP"}],
            "metadata": {"source_kind": "imported", "customized": False},
        },
    )

    saved = repository.asset_bibles[("workspace_1", "bible_demo")]
    assert saved["metadata"] == {
        "source_kind": "imported",
        "origin_preset_id": "builtin_asset_bible_demo",
        "origin_revision": "2026-05-04.1",
        "imported_at": "2026-05-04T00:00:00Z",
        "customized": True,
    }
    assert response["asset_bible"]["metadata"] == saved["metadata"]
    assert response["asset_bible"]["ip_profiles"][0].get("forbidden_elements") == []


def test_inprocess_ip_design_client_imports_builtin_asset_bible_without_leaking_private_fields():
    from web.ip_design.inprocess_client import InProcessIPDesignClient

    class AssetRepository:
        def __init__(self):
            self.asset_bibles: dict[tuple[str, str], dict[str, Any]] = {}
            self.load_calls: list[tuple[str, str]] = []
            self.saved: list[tuple[str, dict[str, Any]]] = []

        async def load_asset_bible(self, workspace_id, asset_bible_id):
            self.load_calls.append((workspace_id, asset_bible_id))
            return self.asset_bibles.get((workspace_id, asset_bible_id))

        async def save_asset_bible(self, workspace_id, asset_bible):
            payload = dict(asset_bible)
            self.saved.append((workspace_id, payload))
            self.asset_bibles[(workspace_id, payload["asset_bible_id"])] = payload
            return payload

    class PresetRegistry:
        def list_summaries(self):
            return [{"preset_id": "builtin_asset_bible_demo", "display_name": "Demo IP"}]

        def build_project_asset_bible(self, **kwargs):
            assert kwargs == {
                "preset_id": "builtin_asset_bible_demo",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "asset_bible_id": "demo_bible",
            }

            class AssetBible:
                def to_dict(self):
                    return {
                        "asset_bible_id": "demo_bible",
                        "workspace_id": "workspace_1",
                        "project_id": "project_1",
                        "ip_profiles": [
                            {
                                "ip_profile_id": "ip_main",
                                "workspace_id": "workspace_1",
                                "project_id": "project_1",
                                "name": "Demo IP",
                                "forbidden_elements": ["private"],
                            }
                        ],
                        "character_profiles": [],
                        "scene_assets": [],
                        "prop_assets": [],
                        "style_profiles": [],
                        "metadata": {"origin_preset_id": "builtin_asset_bible_demo"},
                    }

            return AssetBible()

    repository = AssetRepository()
    core = type(
        "Core",
        (),
        {
            "asset_bible_repository": repository,
            "asset_bible_preset_registry": PresetRegistry(),
        },
    )()
    client = InProcessIPDesignClient(pixelle_video=core, async_runner=asyncio.run)

    assert client.list_asset_bible_presets() == [
        {"preset_id": "builtin_asset_bible_demo", "display_name": "Demo IP"}
    ]

    response = client.import_asset_bible_preset(
        workspace_id="workspace_1",
        project_id="project_1",
        preset_id="builtin_asset_bible_demo",
        asset_bible_id="demo_bible",
    )

    assert response["asset_bible"]["asset_bible_id"] == "demo_bible"
    assert response["asset_bible"]["ip_profiles"][0].get("forbidden_elements") == ["private"]
    assert repository.load_calls == [("workspace_1", "demo_bible")]
    assert repository.saved[0][0] == "workspace_1"

    try:
        client.import_asset_bible_preset(
            workspace_id="workspace_1",
            project_id="project_1",
            preset_id="builtin_asset_bible_demo",
            asset_bible_id="demo_bible",
        )
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected import conflict to fail")


def test_inprocess_ip_design_client_import_rejects_invalid_public_ids():
    from web.ip_design.inprocess_client import InProcessIPDesignClient

    class AssetRepository:
        async def load_asset_bible(self, *_args, **_kwargs):
            raise AssertionError("repository should not be called for invalid IDs")

        async def save_asset_bible(self, *_args, **_kwargs):
            raise AssertionError("repository should not be called for invalid IDs")

    class PresetRegistry:
        def build_project_asset_bible(self, **_kwargs):
            raise AssertionError("registry should not be called for invalid IDs")

    core = type(
        "Core",
        (),
        {
            "asset_bible_repository": AssetRepository(),
            "asset_bible_preset_registry": PresetRegistry(),
        },
    )()
    client = InProcessIPDesignClient(pixelle_video=core, async_runner=asyncio.run)

    try:
        client.import_asset_bible_preset(
            workspace_id="workspace_1",
            project_id="C:\\projects\\1",
            preset_id="builtin_asset_bible_demo",
            asset_bible_id="demo_bible",
        )
    except ValueError as exc:
        assert "project_id" in str(exc)
    else:
        raise AssertionError("expected invalid project_id to fail")


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
    session_state = {"api_base_url": "http://localhost:8888/api"}

    first = resolve_ip_design_client(session_state, pixelle_video=None)
    second = resolve_ip_design_client(session_state, pixelle_video=None)

    assert first is second
    assert session_state["ip_design_client_cache_key"] == (
        "http",
        "http://localhost:8888/api",
    )
