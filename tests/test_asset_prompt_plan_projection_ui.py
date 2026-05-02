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
        self.expanders = []
        self.markdowns = []
        self.captions = []
        self.json_calls = []
        self.code_calls = []
        self.errors = []
        self.successes = []

    def container(self, *_args, **_kwargs):
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


def _loaded_projection_context(
    *,
    api_base_url: str = "http://localhost:8000/api",
    project_id: str = "project_1",
    workspace_id: str = "ws_1",
) -> dict[str, str]:
    return {
        "api_base_url": api_base_url,
        "project_id": project_id,
        "workspace_id": workspace_id,
    }


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


def test_create_asset_bible_posts_minimal_draft_payload(monkeypatch):
    from web.utils import asset_bible_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "asset_bible": {
                    "asset_bible_id": "bible_1",
                    "workspace_id": "ws_1",
                    "project_id": "project_1",
                    "ip_profiles": [{"name": "Demo IP"}],
                },
            }

    def fake_post(endpoint, json, timeout):
        captured["endpoint"] = endpoint
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(asset_bible_api.httpx, "post", fake_post)

    result = asset_bible_api.create_asset_bible(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
        asset_bible_id=" bible_1 ",
        ip_name=" Demo IP ",
        world_hint=" sky city ",
        style_hint=" clean comic ",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/project_1/asset-bible",
        "json": {
            "workspace_id": "ws_1",
            "asset_bible_id": "bible_1",
            "ip_name": "Demo IP",
            "world_hint": "sky city",
            "style_hint": "clean comic",
        },
        "timeout": 30.0,
    }
    assert result["asset_bible"]["asset_bible_id"] == "bible_1"


def test_create_scene_cast_posts_minimal_draft_payload(monkeypatch):
    from web.utils import asset_bible_api

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "scene_cast": {
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
                },
            }

    def fake_post(endpoint, json, timeout):
        captured["endpoint"] = endpoint
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(asset_bible_api.httpx, "post", fake_post)

    result = asset_bible_api.create_scene_cast(
        api_base_url="http://localhost:8000/api/",
        project_id=" project_1 ",
        workspace_id=" ws_1 ",
        asset_bible_id=" bible_1 ",
        scene_cast_id=" cast_1 ",
        storyboard_plan_id=" storyboard_1 ",
        frame_id=" frame_001 ",
        character_ids=[" char_luna ", ""],
        scene_id=" scene_lab ",
        prop_ids=[" prop_compass "],
        style_id=" style_warm_comic ",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/project_1/asset-bible/bible_1/scene-casts",
        "json": {
            "workspace_id": "ws_1",
            "scene_cast_id": "cast_1",
            "storyboard_plan_id": "storyboard_1",
            "frame_id": "frame_001",
            "character_ids": ["char_luna"],
            "scene_id": "scene_lab",
            "prop_ids": ["prop_compass"],
            "style_id": "style_warm_comic",
        },
        "timeout": 30.0,
    }
    assert result["scene_cast"]["scene_cast_id"] == "cast_1"


def test_render_asset_bible_draft_setup_creates_asset_bible(monkeypatch):
    from web.components import asset_bible_draft_setup

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_scene_casts": [{"scene_cast_id": "cast_old"}],
            "projection_scene_cast_id": "cast_old",
            "projection_scene_cast_select": "cast_old",
            "projection_storyboard_plan_id": "storyboard_old",
            "projection_frame_id": "frame_old",
            "projection_preview_result": {"projection": {"source": {"scene_cast_id": "cast_old"}}},
            "stage2_asset_bible_id": "bible_1",
            "stage2_ip_name": "Demo IP",
            "stage2_world_hint": "sky city",
            "stage2_style_hint": "clean comic",
            "stage2_create_asset_bible_submit": True,
        }
    )
    captured = {}

    def fake_create_asset_bible(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "asset_bible": {
                "asset_bible_id": "bible_1",
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "ip_profiles": [{"name": "Demo IP"}],
            },
        }

    monkeypatch.setattr(
        asset_bible_draft_setup,
        "create_asset_bible",
        fake_create_asset_bible,
    )

    asset_bible_draft_setup.render_asset_bible_draft_setup(
        ui=fake_ui,
        api_base_url="http://localhost:8000/api",
        project_id="project_1",
        workspace_id="ws_1",
        translate=lambda key, **_kwargs: key,
    )

    assert captured == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "workspace_id": "ws_1",
        "asset_bible_id": "bible_1",
        "ip_name": "Demo IP",
        "world_hint": "sky city",
        "style_hint": "clean comic",
    }
    assert fake_ui.session_state["projection_asset_bible_id"] == "bible_1"
    assert fake_ui.session_state["projection_context_source"] == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "workspace_id": "ws_1",
    }
    assert fake_ui.session_state["projection_asset_bibles"] == [
        {
            "asset_bible_id": "bible_1",
            "workspace_id": "ws_1",
            "project_id": "project_1",
            "ip_profiles": [{"name": "Demo IP"}],
        }
    ]
    assert fake_ui.session_state["projection_scene_casts"] == []
    assert "projection_scene_cast_id" not in fake_ui.session_state
    assert "projection_scene_cast_select" not in fake_ui.session_state
    assert "projection_storyboard_plan_id" not in fake_ui.session_state
    assert "projection_frame_id" not in fake_ui.session_state
    assert "projection_preview_result" not in fake_ui.session_state
    assert fake_ui.successes == ["stage2.asset_bible.created"]


def test_render_asset_bible_draft_setup_creates_scene_cast(monkeypatch):
    from web.components import asset_bible_draft_setup

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "projection_asset_bible_id": "bible_old",
            "projection_asset_bible_select": "bible_1",
            "stage2_scene_cast_id": "cast_1",
            "stage2_storyboard_plan_id": "storyboard_1",
            "stage2_frame_id": "frame_001",
            "stage2_character_ids": "char_luna, char_milo",
            "stage2_scene_id": "scene_lab",
            "stage2_prop_ids": "prop_compass",
            "stage2_style_id": "style_warm_comic",
            "stage2_create_scene_cast_submit": True,
            "projection_preview_result": {"projection": {"source": {"scene_cast_id": "cast_old"}}},
        }
    )
    captured = {}

    def fake_create_scene_cast(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "scene_cast": {
                "scene_cast_id": "cast_1",
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "asset_bible_id": "bible_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
                "character_ids": ["char_luna", "char_milo"],
                "scene_id": "scene_lab",
                "prop_ids": ["prop_compass"],
                "style_id": "style_warm_comic",
            },
        }

    monkeypatch.setattr(
        asset_bible_draft_setup,
        "create_scene_cast",
        fake_create_scene_cast,
    )

    asset_bible_draft_setup.render_asset_bible_draft_setup(
        ui=fake_ui,
        api_base_url="http://localhost:8000/api",
        project_id="project_1",
        workspace_id="ws_1",
        translate=lambda key, **_kwargs: key,
    )

    assert captured == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "workspace_id": "ws_1",
        "asset_bible_id": "bible_1",
        "scene_cast_id": "cast_1",
        "storyboard_plan_id": "storyboard_1",
        "frame_id": "frame_001",
        "character_ids": ["char_luna", "char_milo"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
    }
    assert fake_ui.session_state["projection_scene_cast_id"] == "cast_1"
    assert fake_ui.session_state["projection_asset_bible_id"] == "bible_1"
    assert fake_ui.session_state["projection_asset_bible_select"] == "bible_1"
    assert fake_ui.session_state["projection_context_source"] == {
        "api_base_url": "http://localhost:8000/api",
        "project_id": "project_1",
        "workspace_id": "ws_1",
    }
    assert fake_ui.session_state["projection_storyboard_plan_id"] == "storyboard_1"
    assert fake_ui.session_state["projection_frame_id"] == "frame_001"
    assert fake_ui.session_state["projection_scene_casts"] == [
        {
            "scene_cast_id": "cast_1",
            "workspace_id": "ws_1",
            "project_id": "project_1",
            "asset_bible_id": "bible_1",
            "storyboard_plan_id": "storyboard_1",
            "frame_id": "frame_001",
            "character_ids": ["char_luna", "char_milo"],
            "scene_id": "scene_lab",
            "prop_ids": ["prop_compass"],
            "style_id": "style_warm_comic",
        }
    ]
    assert "projection_preview_result" not in fake_ui.session_state
    assert fake_ui.successes == ["stage2.scene_cast.created"]


def test_render_projection_preview_calls_api_and_displays_projection_fields(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
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
                    "prompt_sections": {
                        "scene": "library",
                        "character": "archivist",
                        "style": "etched editorial frame",
                    },
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
    assert "PromptPlan 投影预览" in rendered_text
    assert "不保存" in rendered_text
    assert "不触发生成" in rendered_text
    assert "非持久化预览 / 不保存 / 不触发生成" not in rendered_text
    assert "投影后的 PromptPlan" in rendered_text
    assert "wide shot of a clockwork library" in rendered_text
    assert "Projection Lab" in rendered_text
    assert "IP Context" in rendered_text
    assert "Prompt Output" in rendered_text
    assert "Asset Locks" in rendered_text
    assert "Source Trace" in rendered_text
    assert "char_archivist" in rendered_text
    assert "scene_library" in rendered_text
    assert "prop_key" in rendered_text
    assert "style_etching" in rendered_text
    assert "asset_1" in rendered_text
    assert "cast_1" in rendered_text
    assert "prompt_1" in rendered_text
    assert fake_ui.code_calls == []
    assert fake_ui.json_calls == []


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

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "4. Storyboard Frame" in rendered
    assert "5. Preview" in rendered
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
            "projection_context_source": _loaded_projection_context(),
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


def test_render_projection_preview_clears_choices_when_reload_returns_no_asset_bibles(
    monkeypatch,
):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_context_load": True,
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

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "list_asset_bibles",
        lambda **_kwargs: [],
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert fake_ui.session_state["projection_asset_bibles"] == []
    assert fake_ui.session_state["projection_scene_casts"] == []
    assert "projection_asset_bible_id" not in fake_ui.session_state
    assert "projection_scene_cast_id" not in fake_ui.session_state
    assert "projection_preview_result" not in fake_ui.session_state


def test_render_projection_preview_retries_scene_cast_load_after_failure(monkeypatch):
    import httpx

    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
        }
    )
    calls = []

    def fake_list_scene_casts(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise httpx.ConnectError("temporary outage")
        return [
            {
                "scene_cast_id": "cast_1",
                "asset_bible_id": "bible_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
            }
        ]

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "list_scene_casts",
        fake_list_scene_casts,
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )
    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert len(calls) == 2
    assert fake_ui.session_state["projection_scene_cast_asset_bible_id"] == "bible_1"
    assert fake_ui.session_state["projection_scene_cast_id"] == "cast_1"


def test_render_projection_preview_drops_cached_result_when_request_source_changes():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_002",
            "projection_preview_result_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
                "asset_bible_id": "bible_1",
                "scene_cast_id": "cast_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
            },
            "projection_preview_result": {"projection": {"source": {"scene_cast_id": "cast_1"}}},
        }
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert result is None
    assert "projection_preview_result" not in fake_ui.session_state
    assert "projection_preview_result_source" not in fake_ui.session_state


def test_render_projection_preview_clears_orphan_cached_result():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bible_id": "asset_1",
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
            "projection_preview_result": {"projection": {"source": {"scene_cast_id": "cast_1"}}},
        }
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert result is None
    assert "projection_preview_result" not in fake_ui.session_state


def test_render_projection_preview_renders_cached_result_when_source_is_current():
    from web.components import asset_prompt_plan_projection

    cached_result = {
        "success": True,
        "projection": {
            "prompt_plan": {
                "prompt_plan_id": "prompt_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
                "final_prompt": "cached projection preview",
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
    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bible_id": "asset_1",
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
            "projection_preview_result_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
                "asset_bible_id": "asset_1",
                "scene_cast_id": "cast_1",
                "storyboard_plan_id": "storyboard_1",
                "frame_id": "frame_001",
            },
            "projection_preview_result": cached_result,
        }
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered_markdown = "\n".join(item["message"] for item in fake_ui.markdowns)
    assert result == cached_result
    assert "Projection Lab" in rendered_markdown
    assert "cached projection preview" in rendered_markdown


def test_render_projection_result_uses_projection_lab_sections(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
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
    assert "Projection Lab" in rendered_markdown
    assert "IP Context" in rendered_markdown
    assert "Prompt Output" in rendered_markdown
    assert "Asset Locks" in rendered_markdown
    assert "Source Trace" in rendered_markdown
    assert "Provider" not in rendered_markdown
    assert "Generate" not in rendered_markdown
    assert "Save" not in rendered_markdown
    assert "Stale" not in rendered_markdown
    assert fake_ui.code_calls == []
    assert fake_ui.json_calls == []


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
    assert "storyboard" not in labels
    assert "frame" not in labels
    assert "title_style" not in labels
    assert "caption_style" not in labels
    assert "font" not in labels
    assert "path" not in labels


def test_render_projection_preview_hides_manual_asset_ids_in_default_flow():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    projection_labels = {
        item["key"]: item["label"]
        for item in fake_ui.text_inputs
        if item.get("key", "").startswith("projection_")
    }
    assert "projection_asset_bible_id" not in projection_labels
    assert "projection_scene_cast_id" not in projection_labels
    assert fake_ui.expanders == []


def test_render_projection_preview_guides_user_through_selection_steps():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "1. Context" in rendered
    assert "2. AssetBible" in rendered
    assert "3. SceneCast" in rendered
    assert "4. Storyboard Frame" in rendered
    assert "5. Preview" in rendered
    assert "Load context before selecting AssetBible" in rendered
    assert "Load context before selecting SceneCast" in rendered
    assert (
        "Preview is locked until context, AssetBible, SceneCast, storyboard, and frame are ready"
        in rendered
    )


def test_render_projection_preview_does_not_show_frame_inputs_before_context_is_loaded():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    projection_labels = {
        item["key"]: item["label"]
        for item in fake_ui.text_inputs
        if item.get("key", "").startswith("projection_")
    }
    assert "projection_project_id" in projection_labels
    assert "projection_workspace_id" in projection_labels
    assert "projection_storyboard_plan_id" not in projection_labels
    assert "projection_frame_id" not in projection_labels


def test_render_projection_preview_shows_manual_asset_ids_in_advanced_debug():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_advanced_debug": True,
        }
    )

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    projection_labels = {
        item["key"]: item["label"]
        for item in fake_ui.text_inputs
        if item.get("key", "").startswith("projection_")
    }
    assert fake_ui.expanders == [{"label": "Advanced Debug", "expanded": False}]
    assert projection_labels["projection_asset_bible_id"] == "Asset Bible ID"
    assert projection_labels["projection_scene_cast_id"] == "Scene Cast ID"


def test_render_projection_preview_shows_derived_frame_status_from_scene_cast():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_1",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_1",
                    "frame_id": "frame_001",
                }
            ],
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
        }
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "Storyboard/frame derived from selected SceneCast" in rendered
    assert "storyboard_1 / frame_001" in rendered


def test_render_projection_preview_blocks_mismatched_scene_cast_frame_before_http(
    monkeypatch,
):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": _loaded_projection_context(),
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_1",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_1",
                    "frame_id": "frame_001",
                }
            ],
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_other",
            "projection_frame_id": "frame_999",
            "projection_preview_submit": True,
        }
    )

    def fail_preview(**_kwargs):
        raise AssertionError("preview API must not be called for mismatched derived frame")

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fail_preview,
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert result is None
    assert any(
        "Storyboard/frame no longer matches selected SceneCast" in item
        for item in fake_ui.errors
    )
