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
