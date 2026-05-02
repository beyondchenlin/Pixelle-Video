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
        self.markdowns: list[dict[str, Any]] = []
        self.captions: list[str] = []
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.buttons: list[dict[str, Any]] = []
        self.checkboxes: list[dict[str, Any]] = []
        self.text_inputs: list[dict[str, Any]] = []
        self.text_areas: list[dict[str, Any]] = []
        self.containers: list[dict[str, Any]] = []
        self.expanders: list[dict[str, Any]] = []

    def container(self, **kwargs):
        self.containers.append(kwargs)
        return _NoopContext()

    def expander(self, label, **kwargs):
        self.expanders.append({"label": label, **kwargs})
        return _NoopContext()

    def columns(self, count):
        return [_NoopContext() for _index in range(count)]

    def markdown(self, message, **kwargs):
        self.markdowns.append({"message": message, **kwargs})

    def caption(self, message):
        self.captions.append(message)

    def success(self, message):
        self.successes.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        return False

    def checkbox(self, label, **kwargs):
        self.checkboxes.append({"label": label, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return bool(self.session_state[key])
        return bool(kwargs.get("value", False))

    def text_input(self, label, **kwargs):
        self.text_inputs.append({"label": label, **kwargs})
        return str(kwargs.get("value", ""))

    def text_area(self, label, **kwargs):
        self.text_areas.append({"label": label, **kwargs})
        return str(kwargs.get("value", ""))

    def selectbox(self, label, options, **kwargs):
        index = int(kwargs.get("index", 0))
        return list(options)[index]

    def radio(self, label, options, **kwargs):
        index = int(kwargs.get("index", 0))
        return list(options)[index]


def _planning_snapshot() -> dict[str, Any]:
    return {
        "storyboard_generation": {
            "plan_id": "prompt_plan_1",
            "revision": 2,
            "source_digest": "a" * 64,
            "frames": [
                {
                    "frame_id": "frame_0001",
                    "index": 1,
                    "image_artifact_id": "artifact_frame_0001_image",
                    "selected_image_version_id": "artifact_version_001",
                    "shot_type": "medium_shot",
                    "shot_purpose": "context",
                    "primary_subject": "coach",
                    "world_elements": ["board"],
                    "continuity_anchors": ["desk"],
                    "focus_detail": "marker notes",
                    "prompt_intent": "teach concept A",
                    "locked_fields": ["shot_type"],
                },
                {
                    "frame_id": "frame_0002",
                    "index": 2,
                    "shot_type": "close_up",
                    "shot_purpose": "detail",
                    "primary_subject": "chart",
                    "world_elements": ["chart"],
                    "continuity_anchors": ["desk"],
                    "focus_detail": "axis label",
                    "prompt_intent": "teach concept B",
                },
            ],
        },
        "frames": [
            {
                "scene_id": "scene-1",
                "shot_type": "medium_shot",
                "shot_purpose": "context",
                "primary_subject": "coach",
                "world_elements": ["board"],
                "continuity_anchors": ["desk"],
                "focus_detail": "marker notes",
                "prompt_intent": "teach concept A",
            },
            {
                "scene_id": "scene-2",
                "shot_type": "close_up",
                "shot_purpose": "detail",
                "primary_subject": "chart",
                "world_elements": ["chart"],
                "continuity_anchors": ["desk"],
                "focus_detail": "axis label",
                "prompt_intent": "teach concept B",
            },
        ],
    }


def _stale_summary() -> dict[str, Any]:
    return {
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "target_type": "prompt_plan",
        "target_id": "prompt_plan_1",
        "is_stale": True,
        "primary_reasons": ["scene_cast_changed"],
        "upstream_refs": [
            {
                "upstream_type": "scene_cast",
                "upstream_id": "scene_cast_1",
                "upstream_version": 4,
            }
        ],
        "stale_marks": [
            {
                "reason": "scene_cast_changed",
                "upstream_type": "scene_cast",
                "upstream_id": "scene_cast_1",
                "workflow_path": "workflows/private.json",
                "provider_url": "https://provider.example/private",
                "local_path": r"D:\models\secret.safetensors",
            }
        ],
    }


def test_render_prompt_plan_stale_panel_loads_summary_and_renders_panel():
    from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel

    calls: list[dict[str, Any]] = []
    rendered: list[dict[str, Any]] = []
    fake_ui = _FakeUI()

    def loader(**kwargs):
        calls.append(kwargs)
        return {"success": True, "message": "ok", "stale_summary": _stale_summary()}

    def panel_renderer(**kwargs):
        rendered.append(kwargs)

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        stale_summary_loader=loader,
        panel_renderer=panel_renderer,
        api_base_url="http://localhost:8000/api",
        workspace_id="workspace_1",
        project_id="project_1",
    )

    assert calls == [
        {
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
            "target_type": "prompt_plan",
            "target_id": "prompt_plan_1",
        }
    ]
    assert rendered[0]["stale_summary"]["target_id"] == "prompt_plan_1"
    assert rendered[0]["ui"] is fake_ui


def test_render_prompt_plan_stale_panel_fails_closed_without_required_context():
    from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel

    fake_ui = _FakeUI()

    def loader(**_kwargs):
        raise AssertionError("stale API must not be called without full context")

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        stale_summary_loader=loader,
        project_id="project_1",
        workspace_id="",
    )

    assert fake_ui.captions == ["stale.workbench.missing_context"]
    assert fake_ui.errors == []


def test_workbench_stale_translations_have_user_facing_fallbacks():
    import web.i18n as i18n

    for language in ("en_US", "zh_CN"):
        translations = i18n._locales[language]["t"]
        assert translations["stale.workbench.missing_context"] != "stale.workbench.missing_context"
        assert translations["stale.workbench.unavailable"] != "stale.workbench.unavailable"


def test_render_prompt_plan_stale_panel_hides_loader_exception_details():
    from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel

    fake_ui = _FakeUI()

    def loader(**_kwargs):
        raise RuntimeError(r"provider_url=https://provider.example D:\secret")

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        stale_summary_loader=loader,
        api_base_url="http://localhost:8000/api",
        project_id="project_1",
        workspace_id="workspace_1",
    )

    rendered = "\n".join(fake_ui.captions + fake_ui.errors)
    assert "stale.workbench.unavailable" in rendered
    assert "provider.example" not in rendered
    assert r"D:\secret" not in rendered


def test_render_prompt_plan_stale_panel_uses_session_context_defaults():
    from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel

    calls: list[dict[str, Any]] = []
    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://api.example/api/",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        }
    )

    def loader(**kwargs):
        calls.append(kwargs)
        return {"success": True, "message": "ok", "stale_summary": _stale_summary()}

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        stale_summary_loader=loader,
    )

    assert calls[0]["api_base_url"] == "http://api.example/api"
    assert calls[0]["project_id"] == "project_1"
    assert calls[0]["workspace_id"] == "workspace_1"


def test_build_stale_panel_context_uses_repo_defaults_without_session_state():
    from web.components.storyboard_workbench_stale import build_stale_panel_context

    context = build_stale_panel_context({})

    assert context == {
        "api_base_url": "http://localhost:8000/api",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
    }


def test_storyboard_preview_invokes_stale_renderer_once_per_prompt_plan_without_changing_overrides(monkeypatch):
    from web.components import storyboard_preview

    fake_ui = _FakeUI()
    calls: list[dict[str, Any]] = []

    def stale_renderer(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(storyboard_preview, "st", fake_ui)

    overrides = storyboard_preview.render_storyboard_preview(
        _planning_snapshot(),
        stale_context={
            "api_base_url": "http://localhost:8000/api",
            "storyboard_id": "storyboard_001",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        },
        stale_renderer=stale_renderer,
        workbench_renderer=None,
    )

    assert [call["prompt_plan_id"] for call in calls] == ["prompt_plan_1"]
    assert all(call["project_id"] == "project_1" for call in calls)
    assert all(call["workspace_id"] == "workspace_1" for call in calls)
    assert all(call["api_base_url"] == "http://localhost:8000/api" for call in calls)
    assert overrides == [
        {
            "plan_id": "prompt_plan_1",
            "plan_revision": 2,
            "frame_id": "frame_0001",
            "source_digest": "a" * 64,
            "locked_fields": ["shot_type"],
            "shot_type": "medium_shot",
            "override_source": "user_preview",
        }
    ]


def test_storyboard_preview_invokes_workbench_renderer_for_frames_with_artifact_context(monkeypatch):
    from web.components import storyboard_preview

    fake_ui = _FakeUI()
    calls: list[dict[str, Any]] = []

    def workbench_renderer(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(storyboard_preview, "st", fake_ui)

    storyboard_preview.render_storyboard_preview(
        _planning_snapshot(),
        stale_context={
            "api_base_url": "http://localhost:8000/api",
            "storyboard_id": "storyboard_001",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        },
        stale_renderer=None,
        workbench_renderer=workbench_renderer,
    )

    assert calls == [
        {
            "api_base_url": "http://localhost:8000/api",
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "artifact_id": "artifact_frame_0001_image",
            "selected_version_id": "artifact_version_001",
            "ui": fake_ui,
            "translate": storyboard_preview.tr,
        }
    ]


def test_storyboard_preview_uses_plan_id_as_workbench_storyboard_id_when_missing(monkeypatch):
    from web.components import storyboard_preview

    fake_ui = _FakeUI()
    calls: list[dict[str, Any]] = []
    snapshot = _planning_snapshot()
    snapshot["storyboard_generation"]["plan_id"] = "storyboard_plan_001"

    def workbench_renderer(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(storyboard_preview, "st", fake_ui)

    storyboard_preview.render_storyboard_preview(
        snapshot,
        stale_context={
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        },
        stale_renderer=None,
        workbench_renderer=workbench_renderer,
    )

    assert calls[0]["storyboard_id"] == "storyboard_plan_001"


def test_storyboard_advanced_controls_passes_stale_context_to_preview_renderer(monkeypatch):
    from web.components import storyboard_planning_controls

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "storyboard_planning_enabled": True,
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        }
    )
    captured: list[dict[str, Any]] = []

    def preview_renderer(snapshot, *, stale_context=None):
        captured.append({"snapshot": snapshot, "stale_context": stale_context})
        return []

    monkeypatch.setattr(storyboard_planning_controls, "render_storyboard_planning_guide", lambda **_kwargs: None)

    payload = storyboard_planning_controls.render_storyboard_advanced_controls(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        session_state=fake_ui.session_state,
        preview_snapshot=_planning_snapshot(),
        world_library_loader=lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [
                {
                    "preset_id": "neutral_knowledge_storyboard",
                    "display_name": "Neutral",
                }
            ],
        },
        shot_library_loader=lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [
                {
                    "preset_id": "balanced_explainer",
                    "display_name": "Balanced",
                }
            ],
        },
        preview_renderer=preview_renderer,
    )

    assert captured[0]["snapshot"] == _planning_snapshot()
    assert captured[0]["stale_context"] == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "workspace_id": "workspace_1",
    }
    assert payload["world_preset_id"] == "neutral_knowledge_storyboard"


def test_storyboard_advanced_controls_does_not_retry_renderer_internal_type_error(monkeypatch):
    from web.components import storyboard_planning_controls

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "storyboard_planning_enabled": True,
            "project_id": "project_1",
            "workspace_id": "workspace_1",
        }
    )
    calls: list[dict[str, Any]] = []

    def preview_renderer(snapshot, *, stale_context=None):
        calls.append({"snapshot": snapshot, "stale_context": stale_context})
        raise TypeError("renderer internal bug")

    monkeypatch.setattr(storyboard_planning_controls, "render_storyboard_planning_guide", lambda **_kwargs: None)

    try:
        storyboard_planning_controls.render_storyboard_advanced_controls(
            ui=fake_ui,
            translate=lambda key, **_kwargs: key,
            session_state=fake_ui.session_state,
            preview_snapshot=_planning_snapshot(),
            world_library_loader=lambda: {
                "default_world_preset_id": "neutral_knowledge_storyboard",
                "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
            },
            shot_library_loader=lambda: {
                "default_shot_preset_id": "balanced_explainer",
                "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
            },
            preview_renderer=preview_renderer,
        )
    except TypeError as exc:
        assert str(exc) == "renderer internal bug"
    else:
        raise AssertionError("renderer TypeError must propagate")

    assert len(calls) == 1
    assert calls[0]["stale_context"]["project_id"] == "project_1"
