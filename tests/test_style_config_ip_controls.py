from web import i18n
from web.components import series_visual_signature_controls


class _FakeStyleConfigUI:
    def __init__(self):
        self.session_state = {}
        self.toggle_calls = []
        self.selectbox_calls = []

    def toggle(self, label, value=False, **kwargs):
        key = kwargs.get("key")
        self.toggle_calls.append({"label": label, "value": value, **kwargs})
        return self.session_state.get(key, value)

    def selectbox(self, label, options, index=0, key=None, **kwargs):
        self.selectbox_calls.append(
            {"label": label, "options": list(options), "index": index, "key": key, **kwargs}
        )
        if key in self.session_state and self.session_state[key] in options:
            return self.session_state[key]
        return options[index] if options else None

    def caption(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def container(self, **kwargs):
        from contextlib import contextmanager

        @contextmanager
        def _null_context():
            yield None

        return _null_context()


def _default_presentation_payload():
    return {
        "series_visual_signature_llm_prompt_assembly_enabled": False,
        "mandatory_content_bound_anchor": True,
        "series_visual_signature_contract_version": "final_visual_prompt_contract.v4_6",
        "series_visual_signature_output_validation_mode": "off",
        "series_visual_signature_output_max_attempts": 1,
        "series_visual_signature_presentation_mode": "auto",
        "series_visual_signature_enforcement": "strict",
        "series_visual_signature_fallback_enabled": False,
        "series_visual_signature_fallback_mode": "disabled",
        "series_visual_signature_min_visibility": "clear",
    }


def test_style_config_renders_ip_enable_toggle_and_profile_selectors():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = True
    fake_ui.session_state["style_series_visual_signature_asset_bible_id"] = "bible_demo"
    fake_ui.session_state["style_series_visual_signature_profile_id"] = "ip_main"

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {"series_visual_signature_profile_id": "ip_main", "name": "正定向导兔"}
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_mode": "auto",
        "series_visual_signature_consistency_mode": "off",
        **_default_presentation_payload(),
    }
    assert [call["key"] for call in fake_ui.selectbox_calls] == [
        "style_series_visual_signature_asset_bible_id",
        "style_series_visual_signature_profile_id",
    ]
    assert all(
        call.get("key")
        != "style_ip_series_visual_signature_llm_prompt_assembly_enabled"
        for call in fake_ui.toggle_calls
    )


def test_series_visual_signature_presentation_i18n_keys_are_translated():
    i18n.set_language("en_US")
    assert (
        i18n.tr("series_visual_signature.presentation.content_bound_mandatory_ip")
        == "Content-bound IP actor (recommended)"
    )

    i18n.set_language("zh_CN")
    assert (
        i18n.tr("series_visual_signature.presentation.content_bound_mandatory_ip")
        == "内容角色型 IP 出镜（推荐）"
    )


def test_render_series_visual_signature_controls_returns_selected_profile_world_hint():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = True

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {
                        "series_visual_signature_profile_id": "ip_main",
                        "name": "白兔向导",
                        "world_hint": "适合亲切文旅讲解世界。",
                    }
                ],
            }
        ],
        translate=lambda key, **kwargs: key,
    )

    assert payload["ip_profile_world_hint"] == "适合亲切文旅讲解世界。"


def test_resolve_selected_ip_prompt_chain_profile_summary_returns_world_hint():
    summary = series_visual_signature_controls.resolve_selected_ip_prompt_chain_profile_summary(
        session_state={
            "style_series_visual_signature_enabled": True,
            "style_series_visual_signature_asset_bible_id": "bible_demo",
            "style_series_visual_signature_profile_id": "ip_main",
        },
        asset_bibles=[
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
        ],
    )

    assert summary["ip_profile_world_hint"] == "Friendly guide world."
    assert summary["ip_profile_name"] == "White Rabbit Guide"


def test_render_series_visual_signature_controls_supports_content_state_prefix():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["content_series_visual_signature_enabled"] = True
    fake_ui.session_state["content_series_visual_signature_asset_bible_id"] = "bible_demo"
    fake_ui.session_state["content_series_visual_signature_profile_id"] = "ip_main"

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[
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
        ],
        translate=lambda key, **_kwargs: key,
        state_key_prefix="content_ip",
        label_key_prefix="content.ip_world",
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_mode": "auto",
        "series_visual_signature_consistency_mode": "off",
        **_default_presentation_payload(),
        "ip_profile_world_hint": "Friendly guide world.",
    }
    assert fake_ui.toggle_calls[0]["key"] == "content_series_visual_signature_enabled"
    assert [call["key"] for call in fake_ui.selectbox_calls] == [
        "content_series_visual_signature_asset_bible_id",
        "content_series_visual_signature_profile_id",
    ]


def test_resolve_selected_ip_prompt_chain_profile_summary_supports_content_state_prefix():
    summary = series_visual_signature_controls.resolve_selected_ip_prompt_chain_profile_summary(
        session_state={
            "content_series_visual_signature_enabled": True,
            "content_series_visual_signature_asset_bible_id": "bible_demo",
            "content_series_visual_signature_profile_id": "ip_main",
        },
        asset_bibles=[
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
        ],
        state_key_prefix="content_ip",
    )

    assert summary == {
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "ip_profile_name": "White Rabbit Guide",
        "ip_profile_world_hint": "Friendly guide world.",
    }


def test_resolve_selected_ip_prompt_chain_profile_summary_treats_string_false_as_disabled():
    summary = series_visual_signature_controls.resolve_selected_ip_prompt_chain_profile_summary(
        session_state={
            "style_series_visual_signature_enabled": "false",
            "style_series_visual_signature_asset_bible_id": "bible_demo",
            "style_series_visual_signature_profile_id": "ip_main",
        },
        asset_bibles=[
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

    assert summary == {}


def test_style_config_hides_ip_selectors_when_disabled():
    fake_ui = _FakeStyleConfigUI()

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"series_visual_signature_enabled": False}
    assert fake_ui.selectbox_calls == []


def test_style_config_treats_string_false_enable_state_as_disabled():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = "false"

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"series_visual_signature_enabled": False}
    assert fake_ui.toggle_calls[0]["value"] is False
    assert fake_ui.selectbox_calls == []


def test_style_config_does_not_load_ip_assets_when_disabled():
    fake_ui = _FakeStyleConfigUI()
    loader_calls = []

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bible_loader=lambda: loader_calls.append("called"),
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"series_visual_signature_enabled": False}
    assert loader_calls == []


def test_style_config_loads_ip_assets_after_enable_toggle():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = True

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bible_loader=lambda: [
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {"series_visual_signature_profile_id": "ip_main", "name": "正定向导兔"}
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "bible_demo",
        "series_visual_signature_profile_id": "ip_main",
        "series_visual_signature_expression_mode": "auto",
        "series_visual_signature_structure_mode": "auto",
        "series_visual_signature_participation_mode": "auto",
        "series_visual_signature_mode": "auto",
        "series_visual_signature_consistency_mode": "off",
        **_default_presentation_payload(),
    }


def test_style_config_treats_string_false_fallback_state_as_disabled():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = True
    fake_ui.session_state["style_ip_series_visual_signature_fallback_enabled"] = "false"

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {"series_visual_signature_profile_id": "ip_main", "name": "正定向导兔"}
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload["series_visual_signature_fallback_enabled"] is False
    assert payload["series_visual_signature_fallback_mode"] == "disabled"


def test_style_config_keeps_prompt_assembly_deterministic():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_series_visual_signature_enabled"] = True
    fake_ui.session_state[
        "style_ip_series_visual_signature_llm_prompt_assembly_enabled"
    ] = False

    payload = series_visual_signature_controls.render_series_visual_signature_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {
                        "series_visual_signature_profile_id": "ip_main",
                        "name": "正定向导兔",
                    }
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload["series_visual_signature_llm_prompt_assembly_enabled"] is False
    assert all(
        call.get("key")
        != "style_ip_series_visual_signature_llm_prompt_assembly_enabled"
        for call in fake_ui.toggle_calls
    )
