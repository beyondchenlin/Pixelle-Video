from __future__ import annotations

from typing import Any

import pytest


def test_list_storyboard_image_candidates_builds_public_endpoint(monkeypatch):
    from web.utils import storyboard_workbench_api

    captured: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "artifact_id": "artifact_frame_0001_image",
                "candidates": [
                    {
                        "artifact_id": "artifact_frame_0001_image",
                        "version_id": "artifact_version_001",
                        "frame_id": "frame_0001",
                        "prompt_plan_id": "prompt_plan_001",
                        "storage_key": "artifacts/workspace_1/frame_0001/artifact_version_001.png",
                        "status": "succeeded",
                        "url": "https://cdn.pixelle.test/artifacts/frame_0001.png",
                    }
                ],
            }

    def fake_get(endpoint, params, timeout):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(storyboard_workbench_api.httpx, "get", fake_get)

    result = storyboard_workbench_api.list_storyboard_image_candidates(
        api_base_url="http://localhost:8000/api/",
        workspace_id=" workspace_1 ",
        storyboard_id=" storyboard_001 ",
        frame_id=" frame_0001 ",
        artifact_id=" artifact_frame_0001_image ",
    )

    assert captured["endpoint"] == (
        "http://localhost:8000/api/storyboards/storyboard_001/"
        "frames/frame_0001/images"
    )
    assert captured["params"] == {
        "workspace_id": "workspace_1",
        "artifact_id": "artifact_frame_0001_image",
    }
    assert captured["timeout"] == 30.0
    assert result["candidates"][0]["version_id"] == "artifact_version_001"


def test_list_storyboard_image_candidates_accepts_controlled_relative_urls(monkeypatch):
    from web.utils import storyboard_workbench_api

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "artifact_id": "artifact_frame_0001_image",
                "candidates": [
                    {
                        "artifact_id": "artifact_frame_0001_image",
                        "version_id": "artifact_version_001",
                        "frame_id": "frame_0001",
                        "prompt_plan_id": "prompt_plan_001",
                        "storage_key": "artifacts/workspace_1/frame_0001/artifact_version_001.png",
                        "status": "succeeded",
                        "url": "/api/files/artifacts/workspace_1/frame_0001/artifact_version_001.png",
                    }
                ],
            }

    monkeypatch.setattr(
        storyboard_workbench_api.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(),
    )

    result = storyboard_workbench_api.list_storyboard_image_candidates(
        api_base_url="http://localhost:8000/api",
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
    )

    assert result["candidates"][0]["url"] == (
        "/api/files/artifacts/workspace_1/frame_0001/artifact_version_001.png"
    )


def test_storyboard_workbench_api_rejects_path_like_ids_before_http(monkeypatch):
    from web.utils import storyboard_workbench_api

    def fail_get(*_args, **_kwargs):
        raise AssertionError("httpx.get must not be called for path-like IDs")

    monkeypatch.setattr(storyboard_workbench_api.httpx, "get", fail_get)

    with pytest.raises(ValueError, match="artifact_id"):
        storyboard_workbench_api.list_storyboard_image_candidates(
            api_base_url="http://localhost:8000/api",
            workspace_id="workspace_1",
            storyboard_id="storyboard_001",
            frame_id="frame_0001",
            artifact_id=r"D:\output\frame.png",
        )


def test_storyboard_workbench_api_rejects_local_or_provider_leaks(monkeypatch):
    from web.utils import storyboard_workbench_api

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "artifact_id": "artifact_frame_0001_image",
                "candidates": [
                    {
                        "artifact_id": "artifact_frame_0001_image",
                        "version_id": "artifact_version_001",
                        "frame_id": "frame_0001",
                        "prompt_plan_id": "prompt_plan_001",
                        "storage_key": "artifacts/workspace_1/frame_0001/artifact_version_001.png",
                        "status": "succeeded",
                        "url": r"D:\private\frame.png",
                        "metadata": {
                            "provider_url": "https://provider.example/private"
                        },
                    }
                ],
            }

    monkeypatch.setattr(
        storyboard_workbench_api.httpx,
        "get",
        lambda *_args, **_kwargs: _Response(),
    )

    with pytest.raises(ValueError, match="candidate"):
        storyboard_workbench_api.list_storyboard_image_candidates(
            api_base_url="http://localhost:8000/api",
            workspace_id="workspace_1",
            storyboard_id="storyboard_001",
            frame_id="frame_0001",
            artifact_id="artifact_frame_0001_image",
        )


def test_select_and_regenerate_storyboard_image_use_existing_workbench_endpoints(monkeypatch):
    from web.utils import storyboard_workbench_api

    calls: list[dict[str, Any]] = []

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(endpoint, json, timeout):
        calls.append({"endpoint": endpoint, "json": json, "timeout": timeout})
        if endpoint.endswith("/select-image"):
            return _Response(
                {
                    "success": True,
                    "workspace_id": "workspace_1",
                    "storyboard_id": "storyboard_001",
                    "frame_id": "frame_0001",
                    "state": {
                        "frame_id": "frame_0001",
                        "prompt_plan_id": "prompt_plan_001",
                        "selected_image_artifact_id": "artifact_frame_0001_image",
                        "selected_image_version_id": "artifact_version_002",
                        "candidate_image_version_ids": ["artifact_version_002"],
                        "lock_policy": "unlocked",
                        "stale_flags": ["video_segment"],
                    },
                }
            )
        return _Response(
            {
                "success": True,
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "artifact_id": "artifact_frame_0001_image",
                "task_id": "regen-task-1",
                "task_type": "frame_image_regeneration",
                "created": True,
                "generation_fingerprint": "fingerprint-frame-0001",
            }
        )

    monkeypatch.setattr(storyboard_workbench_api.httpx, "post", fake_post)

    selection = storyboard_workbench_api.select_storyboard_image_candidate(
        api_base_url="http://localhost:8000/api",
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        version_id="artifact_version_002",
        actor_id="user_1",
    )
    regeneration = storyboard_workbench_api.regenerate_storyboard_frame_image(
        api_base_url="http://localhost:8000/api",
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
    )

    assert calls == [
        {
            "endpoint": (
                "http://localhost:8000/api/storyboards/storyboard_001/"
                "frames/frame_0001/select-image"
            ),
            "json": {
                "workspace_id": "workspace_1",
                "artifact_id": "artifact_frame_0001_image",
                "version_id": "artifact_version_002",
                "actor_id": "user_1",
            },
            "timeout": 30.0,
        },
        {
            "endpoint": (
                "http://localhost:8000/api/storyboards/storyboard_001/"
                "frames/frame_0001/regenerate-image"
            ),
            "json": {
                "workspace_id": "workspace_1",
                "artifact_id": "artifact_frame_0001_image",
            },
            "timeout": 30.0,
        },
    ]
    assert selection["state"]["selected_image_version_id"] == "artifact_version_002"
    assert regeneration["task_id"] == "regen-task-1"
