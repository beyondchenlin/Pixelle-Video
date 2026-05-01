import pytest


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ProjectionFakeUI:
    def __init__(self):
        self.session_state = {}
        self.text_inputs = []
        self.buttons = []
        self.selectboxes = []
        self.markdowns = []
        self.captions = []
        self.json_calls = []
        self.code_calls = []
        self.errors = []
        self.successes = []

    def container(self, *_args, **_kwargs):
        return _NoopContext()

    def expander(self, *_args, **_kwargs):
        return _NoopContext()

    def columns(self, count):
        return [_NoopContext() for _index in range(count)]

    def markdown(self, message, **kwargs):
        self.markdowns.append({"message": message, **kwargs})

    def caption(self, message):
        self.captions.append(message)

    def text_input(self, label, value="", **kwargs):
        self.text_inputs.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        return bool(self.session_state.get(kwargs.get("key"), False))

    def selectbox(self, label, options, index=0, **kwargs):
        option_list = list(options)
        self.selectboxes.append({"label": label, "options": option_list, "index": index, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state and self.session_state[key] in option_list:
            return self.session_state[key]
        if not option_list:
            return None
        return option_list[index]

    def json(self, value, **kwargs):
        self.json_calls.append({"value": value, **kwargs})

    def code(self, value, **kwargs):
        self.code_calls.append({"value": value, **kwargs})

    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)


def test_build_projection_request_payload_only_includes_endpoint_fields():
    from web.components.asset_prompt_plan_projection import build_projection_request_payload

    payload = build_projection_request_payload(
        workspace_id=" ws_1 ",
        storyboard_plan_id=" storyboard_1 ",
        frame_id=" frame_001 ",
    )

    assert payload == {
        "workspace_id": "ws_1",
        "storyboard_plan_id": "storyboard_1",
        "frame_id": "frame_001",
    }
    assert "title_style" not in payload
    assert "caption_style" not in payload
    assert "font" not in payload
    assert "local_path" not in payload


def test_preview_prompt_plan_projection_posts_to_non_persistent_endpoint(monkeypatch):
    from web.utils import asset_bible_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "projection": {
                    "prompt_plan": {"final_prompt": "cinematic castle"},
                    "source": {"asset_bible_id": "asset_1"},
                },
            }

    def fake_post(endpoint, json, timeout):
        captured["endpoint"] = endpoint
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(asset_bible_api.httpx, "post", fake_post)

    result = asset_bible_api.preview_prompt_plan_projection(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        asset_bible_id=" asset_1 ",
        scene_cast_id=" cast_1 ",
        workspace_id=" ws_1 ",
        storyboard_plan_id=" storyboard_1 ",
        frame_id=" frame_001 ",
    )

    assert captured["endpoint"] == (
        "http://localhost:8000/api/project_1/asset-bible/asset_1/"
        "scene-casts/cast_1/prompt-plan-projection"
    )
    assert captured["json"] == {
        "workspace_id": "ws_1",
        "storyboard_plan_id": "storyboard_1",
        "frame_id": "frame_001",
    }
    assert captured["timeout"] == 30.0
    assert result["projection"]["prompt_plan"]["final_prompt"] == "cinematic castle"


def test_preview_prompt_plan_projection_rejects_path_like_ids_before_http(monkeypatch):
    from web.utils import asset_bible_api

    def fail_post(*_args, **_kwargs):
        raise AssertionError("httpx.post must not be called for path-like IDs")

    monkeypatch.setattr(asset_bible_api.httpx, "post", fail_post)

    with pytest.raises(ValueError, match="project_id"):
        asset_bible_api.preview_prompt_plan_projection(
            api_base_url="http://localhost:8000/api",
            project_id="C:\\projects\\1",
            asset_bible_id="asset_1",
            scene_cast_id="cast_1",
            workspace_id="ws_1",
            storyboard_plan_id="storyboard_1",
            frame_id="frame_001",
        )


def test_preview_prompt_plan_projection_reuses_backend_domain_id_rule(monkeypatch):
    from web.utils import asset_bible_api

    def fail_post(*_args, **_kwargs):
        raise AssertionError("httpx.post must not be called for provider-like IDs")

    monkeypatch.setattr(asset_bible_api.httpx, "post", fail_post)

    with pytest.raises(ValueError, match="asset_bible_id"):
        asset_bible_api.preview_prompt_plan_projection(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            asset_bible_id="provider:bible",
            scene_cast_id="cast_1",
            workspace_id="ws_1",
            storyboard_plan_id="storyboard_1",
            frame_id="frame_001",
        )


def test_list_asset_bibles_gets_project_workspace_endpoint(monkeypatch):
    from web.utils import asset_bible_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "asset_bibles": [
                    {
                        "asset_bible_id": "bible_1",
                        "workspace_id": "ws_1",
                        "project_id": "project_1",
                    }
                ],
            }

    def fake_get(endpoint, params, timeout):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(asset_bible_api.httpx, "get", fake_get)

    result = asset_bible_api.list_asset_bibles(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/project_1/asset-bible",
        "params": {"workspace_id": "ws_1"},
        "timeout": 30.0,
    }
    assert result == [
        {
            "asset_bible_id": "bible_1",
            "workspace_id": "ws_1",
            "project_id": "project_1",
        }
    ]


def test_list_scene_casts_gets_selected_asset_bible_endpoint(monkeypatch):
    from web.utils import asset_bible_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "scene_casts": [
                    {
                        "scene_cast_id": "cast_1",
                        "workspace_id": "ws_1",
                        "project_id": "project_1",
                        "asset_bible_id": "bible_1",
                        "storyboard_plan_id": "storyboard_1",
                        "frame_id": "frame_001",
                    }
                ],
            }

    def fake_get(endpoint, params, timeout):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(asset_bible_api.httpx, "get", fake_get)

    result = asset_bible_api.list_scene_casts(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
        asset_bible_id=" bible_1 ",
    )

    assert captured == {
        "endpoint": ("http://localhost:8000/api/project_1/asset-bible/bible_1/scene-casts"),
        "params": {"workspace_id": "ws_1"},
        "timeout": 30.0,
    }
    assert result[0]["scene_cast_id"] == "cast_1"
    assert result[0]["storyboard_plan_id"] == "storyboard_1"
    assert result[0]["frame_id"] == "frame_001"


def test_list_helpers_reject_path_like_ids_before_http(monkeypatch):
    from web.utils import asset_bible_api

    def fail_get(*_args, **_kwargs):
        raise AssertionError("httpx.get must not be called for path-like IDs")

    monkeypatch.setattr(asset_bible_api.httpx, "get", fail_get)

    with pytest.raises(ValueError, match="workspace_id"):
        asset_bible_api.list_asset_bibles(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="C:\\workspaces\\1",
        )

    with pytest.raises(ValueError, match="asset_bible_id"):
        asset_bible_api.list_scene_casts(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="ws_1",
            asset_bible_id="C:\\bibles\\1",
        )


def test_list_helpers_reject_malformed_response_items(monkeypatch):
    from web.utils import asset_bible_api

    class _AssetBibleResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "asset_bibles": ["not-a-dict"]}

    monkeypatch.setattr(
        asset_bible_api.httpx,
        "get",
        lambda *_args, **_kwargs: _AssetBibleResponse(),
    )

    with pytest.raises(ValueError, match="asset_bibles\\[0\\]"):
        asset_bible_api.list_asset_bibles(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="ws_1",
        )

    class _SceneCastResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "scene_casts": ["not-a-dict"]}

    monkeypatch.setattr(
        asset_bible_api.httpx,
        "get",
        lambda *_args, **_kwargs: _SceneCastResponse(),
    )

    with pytest.raises(ValueError, match="scene_casts\\[0\\]"):
        asset_bible_api.list_scene_casts(
            api_base_url="http://localhost:8000/api",
            project_id="project_1",
            workspace_id="ws_1",
            asset_bible_id="bible_1",
        )


def test_render_projection_preview_calls_api_and_displays_projection_fields(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_asset_bible_id": "asset_1",
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
            "projection_preview_submit": True,
        }
    )
    captured = {}

    def fake_preview_prompt_plan_projection(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "projection": {
                "prompt_plan": {
                    "final_prompt": "wide shot of a clockwork library",
                    "prompt_sections": {"scene": "library", "character": "archivist"},
                    "character_ids": ["char_archivist"],
                    "scene_id": "scene_library",
                    "prop_ids": ["prop_key"],
                    "style_id": "style_etching",
                },
                "source": {
                    "asset_bible_id": "asset_1",
                    "scene_cast_id": "cast_1",
                    "prompt_plan_id": "prompt_1",
                },
            },
        }

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fake_preview_prompt_plan_projection,
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert captured == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "asset_bible_id": "asset_1",
        "scene_cast_id": "cast_1",
        "workspace_id": "ws_1",
        "storyboard_plan_id": "storyboard_1",
        "frame_id": "frame_001",
    }
    assert result["projection"]["prompt_plan"]["final_prompt"] == (
        "wide shot of a clockwork library"
    )
    rendered_text = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
        + [item["value"] for item in fake_ui.code_calls]
    )
    assert "非持久化预览" in rendered_text
    assert "不保存" in rendered_text
    assert "不触发生成" in rendered_text
    assert "wide shot of a clockwork library" in rendered_text
    assert "char_archivist" in rendered_text
    assert "scene_library" in rendered_text
    assert "prop_key" in rendered_text
    assert "style_etching" in rendered_text
    assert fake_ui.json_calls[-1]["value"] == {
        "asset_bible_id": "asset_1",
        "scene_cast_id": "cast_1",
        "prompt_plan_id": "prompt_1",
    }


def test_render_projection_preview_loads_asset_and_scene_cast_choices(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_load": True,
            "projection_preview_submit": True,
        }
    )
    captured = {"asset_lists": [], "scene_lists": [], "preview": {}}

    def fake_list_asset_bibles(**kwargs):
        captured["asset_lists"].append(kwargs)
        return [
            {
                "asset_bible_id": "bible_1",
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "ip_profiles": [{"name": "Demo IP"}],
            }
        ]

    def fake_list_scene_casts(**kwargs):
        captured["scene_lists"].append(kwargs)
        return [
            {
                "scene_cast_id": "cast_1",
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "asset_bible_id": "bible_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
                "character_ids": ["char_luna"],
                "scene_id": "scene_lab",
                "prop_ids": ["prop_compass"],
                "style_id": "style_warm_comic",
            }
        ]

    def fake_preview_prompt_plan_projection(**kwargs):
        captured["preview"] = kwargs
        return {
            "success": True,
            "projection": {
                "prompt_plan": {
                    "final_prompt": "Luna enters the sky lab",
                    "prompt_sections": {"scene": "sky lab"},
                    "character_ids": ["char_luna"],
                    "scene_id": "scene_lab",
                    "prop_ids": ["prop_compass"],
                    "style_id": "style_warm_comic",
                },
                "source": {
                    "asset_bible_id": "bible_1",
                    "scene_cast_id": "cast_1",
                    "prompt_plan_id": "prompt_1",
                },
            },
        }

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "list_asset_bibles",
        fake_list_asset_bibles,
    )
    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "list_scene_casts",
        fake_list_scene_casts,
    )
    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fake_preview_prompt_plan_projection,
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert captured["asset_lists"] == [
        {
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "ws_1",
        }
    ]
    assert captured["scene_lists"] == [
        {
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "ws_1",
            "asset_bible_id": "bible_1",
        }
    ]
    assert captured["preview"] == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "asset_bible_id": "bible_1",
        "scene_cast_id": "cast_1",
        "workspace_id": "ws_1",
        "storyboard_plan_id": "storyboard_1",
        "frame_id": "frame_001",
    }
    assert fake_ui.session_state["projection_asset_bible_id"] == "bible_1"
    assert fake_ui.session_state["projection_scene_cast_id"] == "cast_1"
    assert fake_ui.session_state["projection_storyboard_plan_id"] == "storyboard_1"
    assert fake_ui.session_state["projection_frame_id"] == "frame_001"
    assert [item["options"] for item in fake_ui.selectboxes] == [
        ["bible_1"],
        ["cast_1"],
    ]
    assert result["projection"]["prompt_plan"]["final_prompt"] == ("Luna enters the sky lab")


def test_render_projection_preview_reloads_scene_casts_when_asset_bible_changes(
    monkeypatch,
):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_asset_bibles": [
                {"asset_bible_id": "bible_1", "ip_profiles": [{"name": "Old IP"}]},
                {"asset_bible_id": "bible_2", "ip_profiles": [{"name": "New IP"}]},
            ],
            "projection_asset_bible_id": "bible_1",
            "projection_asset_bible_select": "bible_2",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_old",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_old",
                    "frame_id": "frame_old",
                }
            ],
            "projection_preview_submit": True,
        }
    )
    captured = {"scene_lists": [], "preview": {}}

    def fake_list_scene_casts(**kwargs):
        captured["scene_lists"].append(kwargs)
        return [
            {
                "scene_cast_id": "cast_2",
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "asset_bible_id": "bible_2",
                "storyboard_plan_id": "storyboard_2",
                "frame_id": "frame_002",
            }
        ]

    def fake_preview_prompt_plan_projection(**kwargs):
        captured["preview"] = kwargs
        return {
            "success": True,
            "projection": {
                "prompt_plan": {
                    "final_prompt": "new cast preview",
                    "prompt_sections": {},
                },
                "source": {
                    "asset_bible_id": "bible_2",
                    "scene_cast_id": "cast_2",
                    "prompt_plan_id": "prompt_2",
                },
            },
        }

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "list_scene_casts",
        fake_list_scene_casts,
    )
    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fake_preview_prompt_plan_projection,
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert captured["scene_lists"] == [
        {
            "api_base_url": "http://localhost:8000/api",
            "project_id": "project_1",
            "workspace_id": "ws_1",
            "asset_bible_id": "bible_2",
        }
    ]
    assert captured["preview"]["asset_bible_id"] == "bible_2"
    assert captured["preview"]["scene_cast_id"] == "cast_2"
    assert captured["preview"]["storyboard_plan_id"] == "storyboard_2"
    assert captured["preview"]["frame_id"] == "frame_002"


def test_render_projection_preview_clears_loaded_choices_when_context_changes():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_2",
            "projection_workspace_id": "ws_1",
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_asset_bibles": [{"asset_bible_id": "bible_old"}],
            "projection_asset_bible_id": "bible_old",
            "projection_asset_bible_select": "bible_old",
            "projection_scene_casts": [{"scene_cast_id": "cast_old"}],
            "projection_scene_cast_id": "cast_old",
            "projection_scene_cast_select": "cast_old",
            "projection_storyboard_plan_id": "storyboard_old",
            "projection_frame_id": "frame_old",
            "projection_preview_result": {"projection": {"source": {"scene_cast_id": "cast_old"}}},
        }
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert "projection_context_source" not in fake_ui.session_state
    assert fake_ui.session_state["projection_asset_bibles"] == []
    assert fake_ui.session_state["projection_scene_casts"] == []
    assert "projection_asset_bible_id" not in fake_ui.session_state
    assert "projection_scene_cast_id" not in fake_ui.session_state
    assert "projection_preview_result" not in fake_ui.session_state
    assert fake_ui.selectboxes == []


def test_render_projection_result_uses_workbench_sections(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_asset_bible_id": "asset_1",
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
            "projection_preview_submit": True,
        }
    )

    def fake_preview_prompt_plan_projection(**_kwargs):
        return {
            "success": True,
            "projection": {
                "prompt_plan": {
                    "final_prompt": "wide shot of a clockwork library",
                    "prompt_sections": {"scene": "library"},
                    "character_ids": ["char_archivist"],
                    "scene_id": "scene_library",
                    "prop_ids": ["prop_key"],
                    "style_id": "style_etching",
                },
                "source": {
                    "asset_bible_id": "asset_1",
                    "scene_cast_id": "cast_1",
                    "prompt_plan_id": "prompt_1",
                },
            },
        }

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fake_preview_prompt_plan_projection,
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered_markdown = "\n".join(item["message"] for item in fake_ui.markdowns)
    assert "Projection Workbench" in rendered_markdown
    assert "PromptPlan Output" in rendered_markdown
    assert "Reserved Asset References" in rendered_markdown
    assert "Source Metadata" in rendered_markdown
    assert "Provider" not in rendered_markdown


def test_render_projection_preview_does_not_render_style_or_path_inputs():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    labels = " ".join(item["label"] for item in fake_ui.text_inputs).lower()
    assert "project" in labels
    assert "workspace" in labels
    assert "asset bible" in labels
    assert "scene cast" in labels
    assert "storyboard" in labels
    assert "frame" in labels
    assert "title_style" not in labels
    assert "caption_style" not in labels
    assert "font" not in labels
    assert "path" not in labels
