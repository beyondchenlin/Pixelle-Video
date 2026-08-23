import inspect

from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from web.components import content_series_visual_signature_controls


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSessionState(dict):
    def __init__(self):
        super().__init__()
        self.rendered_widget_keys = set()

    def __setitem__(self, key, value):
        if key in self.rendered_widget_keys:
            raise RuntimeError(f"cannot mutate rendered widget key: {key}")
        super().__setitem__(key, value)

    def mark_widget_rendered(self, key):
        if key:
            self.rendered_widget_keys.add(key)


class _FakeContentIPWorldUI:
    def __init__(self):
        self.session_state = _FakeSessionState()
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
        widget_value = self.session_state[key] if key in self.session_state else value
        self.session_state.mark_widget_rendered(key)
        return widget_value

    def button(self, label, **kwargs):
        key = kwargs.get("key")
        self.button_calls.append({"label": label, **kwargs})
        return bool(self.session_state.get("_button_returns", {}).get(key, False))

    def columns(self, spec):
        return [_FakeContext() for _ in spec]

    def container(self, **_kwargs):
        return _FakeContext()

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
                    "series_visual_signature_profile_id": "ip_main",
                    "name": "White Rabbit Guide",
                    "world_hint": "Friendly guide world.",
                }
            ],
        }
    ]



def _tr(key, **kwargs):
    return key.format(**kwargs) if kwargs else key



def test_render_content_series_visual_signature_controls_keeps_world_hint_without_ip():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["content_generation_world_hint"] = "Manual request world."
    loader_calls = []

    payload = content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=lambda: loader_calls.append("called"),
    )

    assert payload == {
        "series_visual_signature_enabled": False,
        "generation_world_hint": "Manual request world.",
    }
    assert loader_calls == []
    assert fake_ui.expanders == [{"label": "content.ip_world.section_title", "expanded": True}]


def test_render_content_series_visual_signature_controls_default_loader_is_lazy_when_ip_disabled(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    loader_calls = []

    monkeypatch.setattr(
        content_series_visual_signature_controls,
        "load_ip_prompt_chain_asset_bibles",
        lambda **_kwargs: loader_calls.append("called"),
    )

    payload = content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=object(),
        content_context={"title": "Demo", "text": "Script text"},
    )

    assert payload == {"series_visual_signature_enabled": False}
    assert loader_calls == []



def test_render_content_series_visual_signature_controls_returns_selected_ip_payload_without_helper_field():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
            "content_generation_world_hint": "Manual request world.",
        }
    )

    payload = content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_llm_prompt_assembly_enabled": False,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "off",
        "series_visual_signature_output_max_attempts": 1,
        "series_visual_signature_mode": "auto",
        "series_visual_signature_consistency_mode": "off",
        "series_visual_signature_presentation_mode": "auto",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
        "effective_series_visual_signature_mode": "auto",
        "generation_world_hint": "Manual request world.",
    }
    assert fake_ui.session_state["content_ip_profile_world_hint"] == "Friendly guide world."
    assert "ip_profile_world_hint" not in payload
    assert "generation_notes" not in payload
    assert "slot_preference_override" not in payload
    assert "presence_strength" not in payload



def test_render_content_series_visual_signature_controls_can_use_ip_default(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
            "_button_returns": {"content_world_hint_use_ip_default": True},
        }
    )
    reruns = []
    monkeypatch.setattr(content_series_visual_signature_controls, "safe_rerun", lambda: reruns.append("rerun"))

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert fake_ui.session_state["content_generation_world_hint"] == "Friendly guide world."
    assert fake_ui.session_state["content_generation_world_hint_source"] == "ip_default"
    assert reruns == ["rerun"]


def test_render_content_series_visual_signature_controls_warns_when_ip_default_missing(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
            "_button_returns": {"content_world_hint_use_ip_default": True},
        }
    )
    reruns = []
    monkeypatch.setattr(content_series_visual_signature_controls, "safe_rerun", lambda: reruns.append("rerun"))

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=lambda: [
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {
                        "series_visual_signature_profile_id": "ip_main",
                        "name": "White Rabbit Guide",
                    }
                ],
            }
        ],
    )

    assert fake_ui.warning_calls == ["content.ip_world.missing_ip_default"]
    assert "content_generation_world_hint" not in fake_ui.session_state
    assert reruns == []


def test_render_content_series_visual_signature_controls_clears_stale_ip_world_hint_when_ip_disabled():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["content_ip_profile_world_hint"] = "Stale helper world."

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert "content_ip_profile_world_hint" not in fake_ui.session_state


def test_render_content_series_visual_signature_controls_clears_stale_ip_world_hint_when_profile_has_no_hint():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
            "content_ip_profile_world_hint": "Stale helper world.",
        }
    )

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo", "text": "Script text"},
        asset_bible_loader=lambda: [
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {
                        "series_visual_signature_profile_id": "ip_main",
                        "name": "White Rabbit Guide",
                    }
                ],
            }
        ],
    )

    assert "content_ip_profile_world_hint" not in fake_ui.session_state



def test_render_content_series_visual_signature_controls_generates_world_hint_from_script(monkeypatch):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
            "_button_returns": {"content_world_hint_generate_from_content": True},
        }
    )
    captured = {}
    reruns = []
    monkeypatch.setattr(content_series_visual_signature_controls, "safe_rerun", lambda: reruns.append("rerun"))

    def _draft_generator(**payload):
        captured.update(payload)
        return {"world_hint_draft": "Generated request world."}

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
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



def test_render_content_series_visual_signature_controls_warns_when_generating_without_script():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state["_button_returns"] = {"content_world_hint_generate_from_content": True}
    generator_calls = []

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "   "},
        world_hint_draft_generator=lambda **payload: generator_calls.append(payload),
    )

    assert generator_calls == []
    assert fake_ui.warning_calls == ["content.ip_world.missing_content"]


def test_render_content_series_visual_signature_controls_warns_and_preserves_state_when_generator_raises(
    monkeypatch,
):
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_generation_world_hint": "Existing world hint.",
            "content_generation_world_hint_source": "generated_from_script",
            "_button_returns": {"content_world_hint_generate_from_content": True},
        }
    )
    reruns = []
    monkeypatch.setattr(content_series_visual_signature_controls, "safe_rerun", lambda: reruns.append("rerun"))

    def _draft_generator(**_payload):
        raise RuntimeError("boom")

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "Script text"},
        world_hint_draft_generator=_draft_generator,
    )

    assert fake_ui.warning_calls == ["content.ip_world.generate_failed"]
    assert fake_ui.session_state["content_generation_world_hint"] == "Existing world hint."
    assert fake_ui.session_state["content_generation_world_hint_source"] == "generated_from_script"
    assert reruns == []


def test_render_content_series_visual_signature_controls_warns_without_rerun_for_invalid_generated_world_hint(
    monkeypatch,
):
    scenarios = [
        "not-a-mapping",
        {"world_hint_draft": "   "},
    ]

    for response in scenarios:
        fake_ui = _FakeContentIPWorldUI()
        fake_ui.session_state.update(
            {
                "content_generation_world_hint": "Existing world hint.",
                "content_generation_world_hint_source": "ip_default",
                "_button_returns": {"content_world_hint_generate_from_content": True},
            }
        )
        reruns = []
        monkeypatch.setattr(
            content_series_visual_signature_controls, "safe_rerun", lambda: reruns.append("rerun")
        )

        content_series_visual_signature_controls.render_content_series_visual_signature_controls(
            ui=fake_ui,
            translate=_tr,
            pixelle_video=None,
            content_context={"title": "Demo title", "text": "Script text"},
            world_hint_draft_generator=lambda **_payload: response,
        )

        assert fake_ui.warning_calls == ["content.ip_world.generate_failed"]
        assert fake_ui.session_state["content_generation_world_hint"] == "Existing world hint."
        assert fake_ui.session_state["content_generation_world_hint_source"] == "ip_default"
        assert reruns == []


def test_render_content_series_visual_signature_controls_marks_auto_world_hint_as_manual_after_user_edit():
    fake_ui = _FakeContentIPWorldUI()
    fake_ui.session_state.update(
        {
            "content_generation_world_hint": "Edited world hint.",
            "content_generation_world_hint_source": "generated_from_script",
            "content_generation_world_hint_last_value": "Original generated world hint.",
        }
    )

    payload = content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert payload == {
        "series_visual_signature_enabled": False,
        "generation_world_hint": "Edited world hint.",
    }
    assert fake_ui.session_state["content_generation_world_hint_source"] == "manual"
    assert fake_ui.session_state["content_generation_world_hint_last_value"] == "Edited world hint."


def test_content_series_visual_signature_controls_render_request_world_hint_keys():
    fake_ui = _FakeContentIPWorldUI()

    content_series_visual_signature_controls.render_content_series_visual_signature_controls(
        ui=fake_ui,
        translate=_tr,
        pixelle_video=None,
        content_context={"title": "Demo title", "text": "Script text"},
        asset_bible_loader=_asset_bibles,
    )

    assert fake_ui.text_area_calls == [
        {
            "label": "content.ip_world.generation_world_hint",
            "key": "content_generation_world_hint",
            "value": "",
            "height": 92,
            "help": "content.ip_world.generation_world_hint_help",
        }
    ]
    assert [call["key"] for call in fake_ui.button_calls] == [
        "content_world_hint_generate_from_content",
        "content_world_hint_use_ip_default",
    ]


def test_build_content_ip_world_payload_uses_formal_contract_only():
    payload = content_series_visual_signature_controls.build_content_ip_world_payload(
        ip_payload={
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "bible_demo",
            "series_visual_signature_profile_id": "ip_main",
            "ip_profile_world_hint": "helper only",
            "generation_notes": "legacy",
            "slot_preference_override": "legacy",
            "presence_strength": "legacy",
        },
        generation_world_hint="script world",
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_llm_prompt_assembly_enabled": False,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "off",
        "series_visual_signature_output_max_attempts": 1,
        "series_visual_signature_mode": "auto",
        "series_visual_signature_consistency_mode": "off",
        "series_visual_signature_presentation_mode": "auto",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
        "effective_series_visual_signature_mode": "auto",
        "generation_world_hint": "script world",
    }


def test_content_series_visual_signature_controls_uses_shared_default_prompt_language_constant():
    source = inspect.getsource(content_series_visual_signature_controls.render_content_series_visual_signature_controls)

    assert "storyboard_prompt_language: str = CHINESE_PROMPT_LANGUAGE" in source
    assert 'storyboard_prompt_language: str = "zh_CN"' not in source
    assert (
        content_series_visual_signature_controls.render_content_series_visual_signature_controls.__kwdefaults__[
            "storyboard_prompt_language"
        ]
        == CHINESE_PROMPT_LANGUAGE
    )
