import pytest


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeUI:
    def __init__(self):
        self.session_state = {}
        self.markdowns = []
        self.captions = []
        self.successes = []
        self.warnings = []
        self.infos = []
        self.errors = []
        self.buttons = []
        self.json_calls = []
        self.code_calls = []
        self.containers = []

    def container(self, **kwargs):
        self.containers.append(kwargs)
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

    def json(self, value, **kwargs):
        self.json_calls.append({"value": value, **kwargs})

    def code(self, value, **kwargs):
        self.code_calls.append({"value": value, **kwargs})


def _clean_summary(**overrides):
    summary = {
        "workspace_id": "ws_1",
        "project_id": "project_1",
        "target_type": "prompt_plan",
        "target_id": "prompt_1",
        "is_stale": False,
        "stale_marks": [],
        "upstream_refs": [
            {
                "upstream_type": "scene_cast",
                "upstream_id": "cast_1",
                "upstream_version": 7,
            }
        ],
        "primary_reasons": [],
    }
    summary.update(overrides)
    return summary


def test_get_stale_target_rejects_path_like_ids_before_http(monkeypatch):
    from web.utils import stale_api

    def fail_get(*_args, **_kwargs):
        raise AssertionError("httpx.get must not be called for path-like IDs")

    monkeypatch.setattr(stale_api.httpx, "get", fail_get)

    with pytest.raises(ValueError, match="target_id"):
        stale_api.get_stale_target_summary(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="ws_1",
            target_type="prompt_plan",
            target_id=r"C:\tmp\prompt_1",
        )


def test_get_stale_target_uses_contract_endpoint_and_validates_shape(monkeypatch):
    from web.utils import stale_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "ok",
                "stale_summary": _clean_summary(),
            }

    def fake_get(endpoint, params, timeout):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(stale_api.httpx, "get", fake_get)

    result = stale_api.get_stale_target_summary(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
        target_type=" prompt_plan ",
        target_id=" prompt_1 ",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/projects/project_1/stale/targets/prompt_plan/prompt_1",
        "params": {"workspace_id": "ws_1"},
        "timeout": 30.0,
    }
    assert result["stale_summary"]["target_id"] == "prompt_1"


def test_get_stale_target_rejects_malformed_json_shape(monkeypatch):
    from web.utils import stale_api

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "stale_summary": {
                    "workspace_id": "ws_1",
                    "project_id": "project_1",
                    "target_type": "prompt_plan",
                    "is_stale": True,
                    "stale_marks": [],
                    "upstream_refs": [],
                    "primary_reasons": [],
                },
            }

    monkeypatch.setattr(stale_api.httpx, "get", lambda *_args, **_kwargs: _Response())

    with pytest.raises(ValueError, match="stale_summary.target_id"):
        stale_api.get_stale_target_summary(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="ws_1",
            target_type="prompt_plan",
            target_id="prompt_1",
        )


def test_get_stale_downstream_uses_contract_endpoint(monkeypatch):
    from web.utils import stale_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "ok",
                "downstream": {
                    "workspace_id": "ws_1",
                    "project_id": "project_1",
                    "upstream_type": "scene_cast",
                    "upstream_id": "cast_1",
                    "dependency_edges": [],
                    "downstream_refs": [],
                },
            }

    def fake_get(endpoint, params, timeout):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(stale_api.httpx, "get", fake_get)

    result = stale_api.get_stale_downstream(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
        upstream_type=" scene_cast ",
        upstream_id=" cast_1 ",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/projects/project_1/stale/upstream/scene_cast/cast_1/downstream",
        "params": {"workspace_id": "ws_1"},
        "timeout": 30.0,
    }
    assert result["downstream"]["upstream_id"] == "cast_1"


def test_render_stale_panel_shows_clean_state_without_regenerate_action():
    from web.components.stale_panel import render_stale_target_panel

    fake_ui = _FakeUI()

    render_stale_target_panel(
        stale_summary=_clean_summary(is_stale=False),
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
        + fake_ui.successes
        + fake_ui.infos
    )
    button_labels = " ".join(item["label"] for item in fake_ui.buttons).lower()
    assert "stale.clean" in rendered
    assert "cast_1" in rendered
    assert "regenerate" not in button_labels
    assert "generate" not in button_labels


def test_render_stale_panel_shows_marks_without_leaking_paths_or_provider_urls():
    from web.components.stale_panel import render_stale_target_panel

    fake_ui = _FakeUI()
    stale_summary = _clean_summary(
        is_stale=True,
        primary_reasons=["scene_cast_changed"],
        stale_marks=[
            {
                "reason": "scene_cast_changed",
                "upstream_type": "scene_cast",
                "upstream_id": "cast_1",
                "source_relation": "prompt_plan.depends_on_scene_cast",
                "workflow_path": "workflows/selfhost/image.json",
                "provider_url": "https://provider.example/model",
                "local_path": r"D:\models\secret.safetensors",
            }
        ],
        upstream_refs=[
            {
                "upstream_type": "scene_cast",
                "upstream_id": "cast_1",
                "upstream_version": 12,
                "workflow_path": "workflows/selfhost/image.json",
            }
        ],
    )

    render_stale_target_panel(
        stale_summary=stale_summary,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
        + fake_ui.warnings
        + fake_ui.infos
    )
    assert "stale.needs_refresh" in rendered
    assert "scene_cast_changed" in rendered
    assert "cast_1" in rendered
    assert "prompt_plan.depends_on_scene_cast" in rendered
    assert "12" in rendered
    assert "workflows/selfhost/image.json" not in rendered
    assert "provider.example" not in rendered
    assert r"D:\models\secret.safetensors" not in rendered
    assert fake_ui.json_calls == []
    assert fake_ui.code_calls == []
    assert fake_ui.buttons == []
