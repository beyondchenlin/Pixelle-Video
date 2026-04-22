from web.components import style_config
from web.utils import render_backend_ui
from web.utils import tts_ui


def test_get_task_render_backend_prefers_input_then_config():
    assert (
        render_backend_ui.get_task_render_backend(
            {
                "input": {"render_backend": "legacy"},
                "config": {"render_backend": "hyperframes_compiled"},
            }
        )
        == "legacy"
    )
    assert (
        render_backend_ui.get_task_render_backend(
            {
                "config": {"render_backend": "hyperframes_compiled"},
            }
        )
        == "hyperframes_compiled"
    )
    assert render_backend_ui.get_task_render_backend({}) is None


def test_render_render_backend_selector_uses_runtime_default(monkeypatch):
    captured = {}

    class FakeStreamlit:
        def radio(self, label, options, *, index, horizontal, format_func, key, help=None):
            captured["label"] = label
            captured["options"] = options
            captured["index"] = index
            captured["formatted"] = [format_func(option) for option in options]
            captured["key"] = key
            captured["help"] = help
            return options[index]

        def caption(self, body):
            captured["caption"] = body

    fake_config = type(
        "ConfigManager",
        (),
        {
            "config": type(
                "Config",
                (),
                {
                    "render": type("Render", (), {"backend": "hyperframes_compiled"})(),
                },
            )(),
        },
    )()

    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(style_config, "config_manager", fake_config)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    selected = style_config.render_render_backend_selector()

    assert selected == "hyperframes_compiled"
    assert captured["options"] == ["legacy", "hyperframes_compiled"]
    assert captured["index"] == 1
    assert captured["key"] == "render_backend_select"


def test_resolve_comfyui_tts_speed_prefers_comfyui_then_local_then_default():
    assert (
        tts_ui.resolve_comfyui_tts_speed(
            {
                "comfyui": {"speed": 1.1},
                "local": {"speed": 1.2},
            }
        )
        == 1.1
    )
    assert tts_ui.resolve_comfyui_tts_speed({"local": {"speed": 1.3}}) == 1.3
    assert tts_ui.resolve_comfyui_tts_speed({}) == 1.2
