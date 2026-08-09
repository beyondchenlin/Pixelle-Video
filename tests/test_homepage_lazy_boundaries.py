from types import SimpleNamespace

from web.components import settings, style_config


def test_configured_settings_form_is_not_built_by_default(monkeypatch):
    fake_streamlit = SimpleNamespace(
        toggle=lambda *_args, **_kwargs: False,
        caption=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(settings, "st", fake_streamlit)
    monkeypatch.setattr(settings, "tr", lambda key: key)
    monkeypatch.setattr(settings.config_manager, "validate", lambda: True)
    monkeypatch.setattr(
        settings,
        "_render_advanced_settings_form",
        lambda: (_ for _ in ()).throw(AssertionError("hidden settings form was built")),
    )

    settings.render_advanced_settings()


def test_prompt_prefix_library_is_not_built_by_default(monkeypatch):
    session_state = {}
    fake_streamlit = SimpleNamespace(
        session_state=session_state,
        markdown=lambda *_args, **_kwargs: None,
        caption=lambda *_args, **_kwargs: None,
        toggle=lambda *_args, **_kwargs: False,
    )
    image_config = SimpleNamespace(
        prompt_prefix_library=SimpleNamespace(
            active_prefix_id="active",
            items=[{"id": "active", "name": "Active", "content": "cinematic"}],
        )
    )
    fake_manager = SimpleNamespace(
        config=SimpleNamespace(comfyui=SimpleNamespace(image=image_config)),
        get_image_prompt_prefix_library=lambda: {
            "active_prefix_id": "active",
            "items": [{"id": "active", "name": "Active"}],
        },
    )
    monkeypatch.setattr(style_config, "st", fake_streamlit)
    monkeypatch.setattr(style_config, "config_manager", fake_manager)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: kwargs.get("name", key))
    monkeypatch.setattr(
        style_config,
        "_render_image_prompt_prefix_library",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("hidden style gallery was built")),
    )

    value = style_config._render_image_prompt_prefix_library_on_demand(
        object(),
        workflow_key="image.json",
        media_width=768,
        media_height=768,
    )

    assert value == "cinematic"
    assert session_state["prompt_prefix_effective_value"] == "cinematic"


def test_prompt_prefix_pagination_is_bounded_and_clamped():
    items = [{"id": str(index)} for index in range(19)]

    assert [item["id"] for item in style_config.paginate_prompt_prefix_items(items, 2)] == [
        str(index) for index in range(8, 16)
    ]
    assert [item["id"] for item in style_config.paginate_prompt_prefix_items(items, 99)] == [
        "16",
        "17",
        "18",
    ]
