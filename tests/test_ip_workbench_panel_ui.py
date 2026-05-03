from __future__ import annotations

from typing import Any


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeUI:
    def __init__(self):
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.selectboxes: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []

    def container(self, **_kwargs):
        return _NoopContext()

    def markdown(self, message, **_kwargs):
        self.markdowns.append(message)

    def caption(self, message):
        self.captions.append(message)

    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)

    def selectbox(self, label, options, **kwargs):
        self.selectboxes.append({"label": label, "options": list(options), **kwargs})
        if not options:
            return None
        key = kwargs.get("key")
        if key and key in self.session_state:
            return self.session_state[key]
        index = int(kwargs.get("index", 0))
        return list(options)[index]

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        if kwargs.get("disabled"):
            return False
        return bool(self.session_state.get(kwargs.get("key"), False))


class _FakeIPClient:
    def __init__(
        self,
        *,
        asset_bibles: list[dict[str, Any]] | None = None,
        scene_casts: list[dict[str, Any]] | None = None,
    ) -> None:
        self.asset_bibles = asset_bibles if asset_bibles is not None else [_asset_bible()]
        self.scene_casts = scene_casts if scene_casts is not None else [_scene_cast()]
        self.calls: list[dict[str, Any]] = []

    def list_asset_bibles(self, **kwargs):
        self.calls.append({"method": "list_asset_bibles", **kwargs})
        return {"success": True, "asset_bibles": self.asset_bibles}

    def list_scene_casts(self, **kwargs):
        self.calls.append({"method": "list_scene_casts", **kwargs})
        return {"success": True, "scene_casts": self.scene_casts}

    def apply_scene_cast_to_prompt_plan(self, **kwargs):
        self.calls.append({"method": "apply", **kwargs})
        return {
            "success": True,
            "application": {
                "prompt_plan": {
                    "prompt_plan_id": "prompt_plan_1",
                    "character_ids": ["char_luna"],
                    "scene_id": "scene_lab",
                    "prop_ids": ["prop_compass"],
                    "style_id": "style_warm_comic",
                }
            },
        }


def _asset_bible(**overrides: Any) -> dict[str, Any]:
    payload = {
        "asset_bible_id": "bible_demo",
        "ip_profiles": [{"name": "Pixelle Demo"}],
        "character_profiles": [{"character_id": "char_luna", "display_name": "Luna"}],
        "scene_assets": [{"scene_id": "scene_lab", "display_name": "Sky Lab"}],
        "prop_assets": [{"prop_id": "prop_compass", "display_name": "Star Compass"}],
        "style_profiles": [{"style_id": "style_warm_comic", "display_name": "Warm Comic"}],
    }
    payload.update(overrides)
    return payload


def _scene_cast(**overrides: Any) -> dict[str, Any]:
    payload = {
        "scene_cast_id": "cast_frame_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "asset_bible_id": "bible_demo",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    payload.update(overrides)
    return payload


def test_ip_workbench_panel_lists_asset_bibles_and_scene_casts_from_client():
    from web.components.ip_workbench_panel import render_ip_workbench_panel

    fake_ui = _FakeUI()
    client = _FakeIPClient()

    render_ip_workbench_panel(
        ip_workbench_client=client,
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(fake_ui.markdowns + fake_ui.captions)
    assert "ip_workbench.panel.title" in rendered
    assert "bible_demo" in rendered
    assert "cast_frame_1" in rendered
    assert "char_luna" in rendered
    assert client.calls[:2] == [
        {
            "method": "list_asset_bibles",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
        },
        {
            "method": "list_scene_casts",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "asset_bible_id": "bible_demo",
        },
    ]


def test_ip_workbench_panel_disables_apply_when_scene_cast_frame_mismatch():
    from web.components.ip_workbench_panel import render_ip_workbench_panel

    fake_ui = _FakeUI()
    client = _FakeIPClient(scene_casts=[_scene_cast(frame_id="frame_9999")])

    render_ip_workbench_panel(
        ip_workbench_client=client,
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert fake_ui.buttons[-1]["disabled"] is True
    assert not any(call["method"] == "apply" for call in client.calls)


def test_ip_workbench_panel_applies_scene_cast_through_client():
    from web.components.ip_workbench_panel import render_ip_workbench_panel

    fake_ui = _FakeUI()
    fake_ui.session_state["ip_workbench_apply_frame_0001"] = True
    client = _FakeIPClient()

    render_ip_workbench_panel(
        ip_workbench_client=client,
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        actor_id="user_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert client.calls[-1] == {
        "method": "apply",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
        "scene_cast_id": "cast_frame_1",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "actor_id": "user_1",
    }
    assert fake_ui.successes == ["ip_workbench.panel.apply_success"]
    assert fake_ui.session_state["ip_workbench_last_application"]["prompt_plan"][
        "character_ids"
    ] == ["char_luna"]


def test_ip_workbench_panel_fails_closed_without_client():
    from web.components.ip_workbench_panel import render_ip_workbench_panel

    fake_ui = _FakeUI()

    render_ip_workbench_panel(
        ip_workbench_client=None,
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id="storyboard_plan_1",
        frame_id="frame_0001",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert fake_ui.captions == ["ip_workbench.panel.unavailable"]
    assert fake_ui.buttons == []
