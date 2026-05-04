from web.components import content_ip_world_controls


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeContentIPWorldUI:
    def __init__(self):
        self.session_state = {}
        self.expanders = []
        self.toggle_calls = []
        self.selectbox_calls = []
        self.text_area_calls = []
        self.button_calls = []
        self.warning_calls = []

    def expander(self, label, expanded=False):
        self.expanders.append({"label": label, "expanded": expanded})
        return _FakeContext()

    def toggle(self, label, value=False, **kwargs):
        key = kwargs.get("key")
        self.toggle_calls.append({"label": label, "value": value, **kwargs})
        return bool(self.session_state.get(key, value))

    def selectbox(self, label, options, index=0, key=None, **kwargs):
        self.selectbox_calls.append(
            {"label": label, "options": list(options), "index": index, "key": key, **kwargs}
        )
        if key in self.session_state and self.session_state[key] in options:
            return self.session_state[key]
        return list(options)[index] if options else None

    def text_area(self, label, value="", **kwargs):
        key = kwargs.get("key")
        self.text_area_calls.append({"label": label, "value": value, **kwargs})
        if key in self.session_state:
            return self.session_state[key]
        return value

    def button(self, label, **kwargs):
        key = kwargs.get("key")
        self.button_calls.append({"label": label, **kwargs})
        return bool(self.session_state.get("_button_returns", {}).get(key, False))

    def columns(self, spec):
        return [_FakeContext() for _ in spec]

    def caption(self, *_args, **_kwargs):
        return None

    def warning(self, message, **_kwargs):
        self.warning_calls.append(message)



def _asset_bibles():
    return [
        {
            "asset_bible_id": "bible_demo",
            "ip_profiles": [
                {
                    "ip_profile_id": "ip_main",
                    "name": "White Rabbit Guide",
                    "world_hint": "Friendly guide world.",
                }
            ],
        }
    ]



def _tr(key, **kwargs):
    return key.format(**kwargs) if kwargs else key



def test_render_content_ip_world_controls_keeps_world_hint_without_ip():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["content_generation_world_hint"] = "Manual request world."
    loader_calls = []

    payload = content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=lambda: loader_calls.append("called"),
    )

    assert payload == {
        "ip_enabled": False,
        "generation_world_hint": "Manual request world.",
    }
    assert loader_calls == []
    assert fake_ui.expanders == [{"label": "content.ip_world.section_title", "expanded": True}]



def test_render_content_ip_world_controls_returns_selected_ip_payload_without_helper_field():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_ip_enabled": True,
            "content_ip_asset_bible_id": "bible_demo",
            "content_ip_profile_id": "ip_main",
            "content_generation_world_hint": "Manual request world.",
        }
    )

    payload = content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "generation_world_hint": "Manual request world.",
    }
    assert fake_ui.session_state["content_ip_profile_world_hint"] == "Friendly guide world."
    assert "ip_profile_world_hint" not in payload



def test_render_content_ip_world_controls_can_use_ip_default(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_ip_enabled": True,
            "content_ip_asset_bible_id": "bible_demo",
            "content_ip_profile_id": "ip_main",
            "_button_returns": {"content_world_hint_use_ip_default": True},
        }
    )
    reruns = []
    monkeypatch.setattr(content_ip_world_controls, "safe_rerun", lambda: reruns.append("rerun"))

    content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert fake_ui.session_state["content_generation_world_hint"] == "Friendly guide world."
    assert fake_ui.session_state["content_generation_world_hint_source"] == "ip_default"
    assert reruns == ["rerun"]



def test_render_content_ip_world_controls_generates_world_hint_from_script(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_ip_enabled": True,
            "content_ip_asset_bible_id": "bible_demo",
            "content_ip_profile_id": "ip_main",
            "_button_returns": {"content_world_hint_generate_from_content": True},
        }
    )
    captured = {}
    reruns = []
    monkeypatch.setattr(content_ip_world_controls, "safe_rerun", lambda: reruns.append("rerun"))

    def _draft_generator(**payload):
        captured.update(payload)
        return {"world_hint_draft": "Generated request world."}

    content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "Script text"},
        storyboard_prompt_language="zh_CN",
        world_preset_id="neutral_knowledge_storyboard",
        asset_bible_loader=_asset_bibles,
        world_hint_draft_generator=_draft_generator,
    )

    assert captured == {
        "source_text": "Script text",
        "title": "Demo title",
        "world_preset_id": "neutral_knowledge_storyboard",
        "storyboard_prompt_language": "zh_CN",
        "ip_default_world_hint": "Friendly guide world.",
    }
    assert fake_ui.session_state["content_generation_world_hint"] == "Generated request world."
    assert fake_ui.session_state["content_generation_world_hint_source"] == "generated_from_script"
    assert reruns == ["rerun"]



def test_render_content_ip_world_controls_warns_when_generating_without_script():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["_button_returns"] = {"content_world_hint_generate_from_content": True}
    generator_calls = []

    content_ip_world_controls.render_content_ip_world_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "   "},
        world_hint_draft_generator=lambda **payload: generator_calls.append(payload),
    )

    assert generator_calls == []
    assert fake_ui.warning_calls == ["content.ip_world.missing_content"]
