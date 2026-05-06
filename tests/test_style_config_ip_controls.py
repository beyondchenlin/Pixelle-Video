from web.components import ip_prompt_chain_controls


class _FakeStyleConfigUI:
    def __init__(self):
        self.session_state = {}
        self.toggle_calls = []
        self.selectbox_calls = []

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


def test_style_config_renders_ip_enable_toggle_and_profile_selectors():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_ip_enabled"] = True
    fake_ui.session_state["style_ip_asset_bible_id"] = "bible_demo"
    fake_ui.session_state["style_ip_profile_id"] = "ip_main"

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {"ip_profile_id": "ip_main", "name": "正定向导兔"}
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
    }
    assert [call["key"] for call in fake_ui.selectbox_calls] == [
        "style_ip_asset_bible_id",
        "style_ip_profile_id",
    ]


def test_render_ip_prompt_chain_controls_returns_selected_profile_world_hint():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_ip_enabled"] = True

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {
                        "ip_profile_id": "ip_main",
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
    summary = ip_prompt_chain_controls.resolve_selected_ip_prompt_chain_profile_summary(
        session_state={
            "style_ip_enabled": True,
            "style_ip_asset_bible_id": "bible_demo",
            "style_ip_profile_id": "ip_main",
        },
        asset_bibles=[
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
        ],
    )

    assert summary["ip_profile_world_hint"] == "Friendly guide world."
    assert summary["ip_profile_name"] == "White Rabbit Guide"


def test_render_ip_prompt_chain_controls_supports_content_state_prefix():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["content_ip_enabled"] = True
    fake_ui.session_state["content_ip_asset_bible_id"] = "bible_demo"
    fake_ui.session_state["content_ip_profile_id"] = "ip_main"

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[
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
        ],
        translate=lambda key, **_kwargs: key,
        state_key_prefix="content_ip",
        label_key_prefix="content.ip_world",
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "ip_profile_world_hint": "Friendly guide world.",
    }
    assert fake_ui.toggle_calls[0]["key"] == "content_ip_enabled"
    assert [call["key"] for call in fake_ui.selectbox_calls] == [
        "content_ip_asset_bible_id",
        "content_ip_profile_id",
    ]


def test_resolve_selected_ip_prompt_chain_profile_summary_supports_content_state_prefix():
    summary = ip_prompt_chain_controls.resolve_selected_ip_prompt_chain_profile_summary(
        session_state={
            "content_ip_enabled": True,
            "content_ip_asset_bible_id": "bible_demo",
            "content_ip_profile_id": "ip_main",
        },
        asset_bibles=[
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
        ],
        state_key_prefix="content_ip",
    )

    assert summary == {
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "ip_profile_name": "White Rabbit Guide",
        "ip_profile_world_hint": "Friendly guide world.",
    }


def test_style_config_hides_ip_selectors_when_disabled():
    fake_ui = _FakeStyleConfigUI()

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bibles=[],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"ip_enabled": False}
    assert fake_ui.selectbox_calls == []


def test_style_config_does_not_load_ip_assets_when_disabled():
    fake_ui = _FakeStyleConfigUI()
    loader_calls = []

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bible_loader=lambda: loader_calls.append("called"),
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {"ip_enabled": False}
    assert loader_calls == []


def test_style_config_loads_ip_assets_after_enable_toggle():
    fake_ui = _FakeStyleConfigUI()
    fake_ui.session_state["style_ip_enabled"] = True

    payload = ip_prompt_chain_controls.render_ip_prompt_chain_controls(
        ui=fake_ui,
        asset_bible_loader=lambda: [
            {
                "asset_bible_id": "bible_demo",
                "ip_profiles": [
                    {"ip_profile_id": "ip_main", "name": "正定向导兔"}
                ],
            }
        ],
        translate=lambda key, **_kwargs: key,
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
    }
