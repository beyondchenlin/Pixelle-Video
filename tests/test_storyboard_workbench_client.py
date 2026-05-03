from __future__ import annotations

from pathlib import Path
from typing import Any


def test_http_workbench_client_reads_capabilities_from_backend():
    from web.workbench.http_client import HttpStoryboardWorkbenchClient

    calls: list[dict[str, Any]] = []
    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api",
        capability_loader=lambda **kwargs: calls.append(kwargs)
        or {
            "success": True,
            "can_regenerate_frame_image": False,
            "regenerate_unavailable_reason": "task submitter is not configured",
        },
    )

    assert client.get_capabilities() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "task submitter is not configured",
    }
    assert calls == [{"api_base_url": "http://localhost:8001/api"}]


def test_http_workbench_client_normalizes_candidate_display_urls():
    from web.workbench.http_client import HttpStoryboardWorkbenchClient

    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api/",
        capability_loader=lambda **_kwargs: {
            "can_regenerate_frame_image": True,
            "regenerate_unavailable_reason": None,
        },
        candidate_loader=lambda **_kwargs: {
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_1",
            "frame_id": "frame_1",
            "artifact_id": "artifact_1",
            "candidates": [
                {
                    "artifact_id": "artifact_1",
                    "version_id": "version_1",
                    "frame_id": "frame_1",
                    "prompt_plan_id": "prompt_plan_1",
                    "storage_key": "artifacts/workspace_1/file.png",
                    "status": "ready",
                    "url": "/api/files/artifacts/workspace_1/file.png",
                }
            ],
        },
    )

    response = client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    candidate = response["candidates"][0]
    assert candidate["image_display"] == {
        "kind": "url",
        "url": "http://localhost:8001/api/files/artifacts/workspace_1/file.png",
    }
    assert "url" not in candidate


def test_workbench_client_factory_does_not_cache_inprocess_client_without_core(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=None)

    assert client is None
    assert "storyboard_workbench_client" not in session_state


def test_workbench_client_factory_defaults_to_inprocess_without_reading_api_base_url(
    monkeypatch,
):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    monkeypatch.setenv("PIXELLE_API_BASE_URL", "http://localhost:8001/api")
    session_state = {}
    core = object()

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=core)

    assert client is not None
    assert session_state["storyboard_workbench_client_cache_key"] == (
        "inprocess",
        id(core),
    )


def test_workbench_client_factory_rebuilds_when_core_identity_changes(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    first = resolve_storyboard_workbench_client(session_state, pixelle_video=object())
    second = resolve_storyboard_workbench_client(session_state, pixelle_video=object())

    assert first is not None
    assert second is not None
    assert first is not second


def test_inprocess_client_lists_candidates_with_local_bytes_display(tmp_path):
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    image_path = tmp_path / "0123456789abcdef0123456789abcdef.png"
    image_path.write_bytes(b"png-bytes")

    class Candidate:
        def to_dict(self):
            return {
                "artifact_id": "artifact_1",
                "version_id": "version_1",
                "frame_id": "frame_1",
                "prompt_plan_id": "prompt_plan_1",
                "storage_key": "artifacts/workspace_1/0123456789abcdef0123456789abcdef.png",
                "status": "ready",
                "url": "/api/files/artifacts/workspace_1/file.png",
            }

    class Service:
        async def list_image_candidates(self, *, workspace_id, artifact_id):
            return (Candidate(),)

    class ObjectStore:
        async def get_local_file_uri(self, storage_key):
            return image_path.as_uri()

    class StateStore:
        async def load_frame_state(self, workspace_id, storyboard_id, frame_id):
            return {
                "frame_id": frame_id,
                "prompt_plan_id": "prompt_plan_1",
                "selected_image_artifact_id": "artifact_1",
                "selected_image_version_id": "version_1",
                "candidate_image_version_ids": ["version_1"],
                "lock_policy": "unlocked",
                "stale_flags": [],
            }

    core = type(
        "Core",
        (),
        {
            "storyboard_workbench_service": Service(),
            "artifact_object_store": ObjectStore(),
            "storyboard_workbench_state_store": StateStore(),
        },
    )()

    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)
    response = client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    candidate = response["candidates"][0]
    assert candidate["image_display"] == {
        "kind": "bytes",
        "data": b"png-bytes",
        "mime_type": "image/png",
    }
    assert "url" not in candidate


def test_inprocess_client_uses_task_submitter_for_regenerate():
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    class Service:
        def build_frame_image_regeneration_task_request(self, **_kwargs):
            return type(
                "TaskRequest",
                (),
                {
                    "generation_fingerprint": "fingerprint_1",
                    "request_params": {"workspace_id": "workspace_1"},
                },
            )()

    class StateStore:
        async def load_frame_state(self, *_args, **_kwargs):
            return {
                "frame_id": "frame_1",
                "selected_image_artifact_id": "artifact_1",
                "selected_image_version_id": "version_1",
                "candidate_image_version_ids": ["version_1"],
                "lock_policy": "unlocked",
                "stale_flags": [],
                "prompt_plan_id": "prompt_plan_1",
            }

    class Submitter:
        async def get_capabilities(self):
            return type(
                "Capabilities",
                (),
                {
                    "to_dict": lambda _self: {
                        "can_regenerate_frame_image": True,
                        "regenerate_unavailable_reason": None,
                    }
                },
            )()

        async def reserve_frame_image_regeneration(self, **kwargs):
            return type(
                "Submission",
                (),
                {
                    "to_dict": lambda _self: {
                        "task_id": "task_1",
                        "task_type": "frame_image_regeneration",
                        "created": True,
                        "reused_reason": None,
                    }
                },
            )()

    core = type(
        "Core",
        (),
        {
            "storyboard_workbench_service": Service(),
            "storyboard_workbench_state_store": StateStore(),
            "storyboard_workbench_task_submitter": Submitter(),
        },
    )()

    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)

    assert client.get_capabilities()["can_regenerate_frame_image"] is True
    assert client.regenerate_frame_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )["task_id"] == "task_1"


def test_storyboard_workbench_ui_does_not_import_transport_or_display_helpers():
    ui_files = [
        Path("web/components/storyboard_workbench_panel.py"),
        Path("web/components/storyboard_workbench_stale.py"),
        Path("web/components/storyboard_preview.py"),
        Path("web/pages/4_🧭_Storyboard_Workbench.py"),
    ]
    forbidden = (
        "web.utils.storyboard_workbench_api",
        "web.utils.stale_api",
        "web.utils.artifact_display_urls",
        "httpx",
        "localhost:8001",
    )

    for path in ui_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not depend on {token}"
