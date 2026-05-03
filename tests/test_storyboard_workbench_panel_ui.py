from __future__ import annotations

from typing import Any


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _WorkbenchFakeUI:
    def __init__(self):
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[dict[str, Any]] = []
        self.captions: list[str] = []
        self.images: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.containers: list[dict[str, Any]] = []

    def container(self, **kwargs):
        self.containers.append(kwargs)
        return _NoopContext()

    def columns(self, count):
        return [_NoopContext() for _index in range(count)]

    def markdown(self, message, **kwargs):
        self.markdowns.append({"message": message, **kwargs})

    def caption(self, message):
        self.captions.append(message)

    def image(self, image, **kwargs):
        self.images.append({"image": image, **kwargs})

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        if kwargs.get("disabled"):
            return False
        return bool(self.session_state.get(kwargs.get("key"), False))

    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)


def _candidate_response() -> dict[str, Any]:
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
                "provider": "comfyui",
                "image_display": {
                    "kind": "url",
                    "url": "https://cdn.pixelle.test/artifacts/frame_0001.png",
                },
                "width": 1024,
                "height": 1024,
                "trace_event_id": "generation_event_001",
            },
            {
                "artifact_id": "artifact_frame_0001_image",
                "version_id": "artifact_version_002",
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "storage_key": "artifacts/workspace_1/frame_0001/artifact_version_002.png",
                "status": "candidate",
                "provider": "comfyui",
                "image_display": {
                    "kind": "url",
                    "url": "https://cdn.pixelle.test/artifacts/frame_0002.png",
                },
                "width": 1024,
                "height": 1024,
                "trace_event_id": "generation_event_002",
            },
        ],
    }


class _FakeWorkbenchClient:
    def __init__(
        self,
        *,
        candidates: list[dict[str, Any]] | None = None,
        can_regenerate: bool = True,
        fail_list: bool = False,
    ) -> None:
        self.candidates = candidates if candidates is not None else _candidate_response()["candidates"]
        self.can_regenerate = can_regenerate
        self.fail_list = fail_list
        self.calls: list[dict[str, Any]] = []

    def get_capabilities(self):
        return {
            "can_regenerate_frame_image": self.can_regenerate,
            "regenerate_unavailable_reason": (
                None if self.can_regenerate else "task submitter is not configured"
            ),
        }

    def list_image_candidates(self, **kwargs):
        self.calls.append({"method": "list", **kwargs})
        if self.fail_list:
            raise RuntimeError(r"provider_url=https://provider.example D:\secret")
        return {**_candidate_response(), "candidates": self.candidates}

    def select_image_candidate(self, **kwargs):
        self.calls.append({"method": "select", **kwargs})
        return {
            "success": True,
            "state": {
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "selected_image_artifact_id": "artifact_frame_0001_image",
                "selected_image_version_id": kwargs["version_id"],
                "candidate_image_version_ids": ["artifact_version_001", kwargs["version_id"]],
                "lock_policy": "unlocked",
                "stale_flags": ["video_segment"],
            },
        }

    def regenerate_frame_image(self, **kwargs):
        self.calls.append({"method": "regenerate", **kwargs})
        return {
            "success": True,
            "task_id": "regen-task-1",
            "task_type": "frame_image_regeneration",
            "created": True,
            "generation_fingerprint": "fingerprint-frame-0001",
        }


def test_render_storyboard_workbench_panel_requires_context_before_client_calls():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        selected_version_id="artifact_version_001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert client.calls == []
    assert fake_ui.captions == ["workbench.panel.missing_context"]
    assert fake_ui.errors == []


def test_render_storyboard_workbench_panel_fails_closed_without_client():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=None,
    )

    assert fake_ui.captions == ["workbench.panel.unavailable"]


def test_render_storyboard_workbench_panel_uses_default_workspace_context():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient(candidates=[])

    render_storyboard_workbench_panel(
        workspace_id=None,
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert client.calls == [
        {
            "method": "list",
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "artifact_id": "artifact_frame_0001_image",
        }
    ]
    assert fake_ui.captions == ["workbench.panel.help", "workbench.panel.empty"]


def test_render_storyboard_workbench_panel_lists_candidates_and_actions():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        selected_version_id="artifact_version_001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    rendered = "\n".join(item["message"] for item in fake_ui.markdowns)
    button_labels = [button["label"] for button in fake_ui.buttons]

    assert client.calls[0] == {
        "method": "list",
        "workspace_id": "workspace_1",
        "storyboard_id": "storyboard_001",
        "frame_id": "frame_0001",
        "artifact_id": "artifact_frame_0001_image",
    }
    assert "workbench.panel.title" in rendered
    assert "artifact_version_001" in rendered
    assert "artifact_version_002" in rendered
    assert "**artifact_version_001** - workbench.panel.selected_badge" in rendered
    assert fake_ui.images == [
        {
            "image": "https://cdn.pixelle.test/artifacts/frame_0001.png",
            "caption": "artifact_version_001",
            "width": "stretch",
        },
        {
            "image": "https://cdn.pixelle.test/artifacts/frame_0002.png",
            "caption": "artifact_version_002",
            "width": "stretch",
        },
    ]
    assert button_labels.count("workbench.panel.select") == 1
    assert "workbench.panel.regenerate" in button_labels


def test_storyboard_workbench_panel_renders_bytes_display_without_api_base_url():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient(
        candidates=[
            {
                "artifact_id": "artifact_frame_0001_image",
                "version_id": "artifact_version_001",
                "frame_id": "frame_0001",
                "status": "ready",
                "image_display": {
                    "kind": "bytes",
                    "data": b"fake-image",
                    "mime_type": "image/png",
                },
            }
        ],
        can_regenerate=False,
    )

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert fake_ui.images[0]["image"] == b"fake-image"
    assert fake_ui.buttons[-1]["disabled"] is True


def test_render_storyboard_workbench_panel_selects_candidate_and_refreshes_state():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    fake_ui.session_state["workbench_select_frame_0001_artifact_version_002"] = True
    client = _FakeWorkbenchClient()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        selected_version_id="artifact_version_001",
        actor_id="user_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert client.calls[1] == {
        "method": "select",
        "workspace_id": "workspace_1",
        "storyboard_id": "storyboard_001",
        "frame_id": "frame_0001",
        "artifact_id": "artifact_frame_0001_image",
        "version_id": "artifact_version_002",
        "actor_id": "user_1",
    }
    assert fake_ui.session_state["workbench_selected_versions"]["frame_0001"] == "artifact_version_002"
    assert fake_ui.successes == ["workbench.panel.select_success"]


def test_render_storyboard_workbench_panel_requests_regeneration_task():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    fake_ui.session_state["workbench_regenerate_frame_0001"] = True
    client = _FakeWorkbenchClient()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        selected_version_id="artifact_version_001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert client.calls[-1] == {
        "method": "regenerate",
        "workspace_id": "workspace_1",
        "storyboard_id": "storyboard_001",
        "frame_id": "frame_0001",
        "artifact_id": "artifact_frame_0001_image",
    }
    assert fake_ui.infos == ["workbench.panel.regenerate_started"]
    assert fake_ui.session_state["workbench_last_regeneration_tasks"]["frame_0001"] == "regen-task-1"


def test_render_storyboard_workbench_panel_hides_client_exception_details():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient(fail_list=True)

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        selected_version_id="artifact_version_001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    rendered = "\n".join(fake_ui.captions + fake_ui.errors)
    assert "workbench.panel.unavailable" in rendered
    assert "provider.example" not in rendered
    assert r"D:\secret" not in rendered
