from web.components import style_config
from web.utils import render_backend_ui, tts_audio_strategy_ui, tts_split_mode_ui, tts_ui


def test_get_task_render_backend_prefers_effective_backend_then_requested_backend():
    assert (
        render_backend_ui.get_task_render_backend(
            {
                "input": {
                    "render_backend": "hyperframes_compiled",
                    "render_backend_effective": "legacy",
                },
                "config": {
                    "render_backend": "hyperframes_compiled",
                    "render_backend_effective": "legacy",
                },
            }
        )
        == "legacy"
    )
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


def test_get_task_text_layer_summary_reads_result_payload():
    summary = render_backend_ui.get_task_text_layer_summary(
        {
            "result": {
                "text_layer_summary": {
                    "renderer": "ass",
                    "cue_count": 3,
                    "native_prompt_hint_count": 1,
                }
            }
        }
    )

    assert summary == {
        "renderer": "ass",
        "cue_count": 3,
        "native_prompt_hint_count": 1,
    }
    assert render_backend_ui.get_task_text_layer_summary({}) is None


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


def test_render_tts_audio_strategy_selector_uses_runtime_default(monkeypatch):
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
                    "render": type(
                        "Render",
                        (),
                        {
                            "timing": type("Timing", (), {"tts_audio_strategy": "master_track"})(),
                        },
                    )(),
                },
            )(),
        },
    )()

    monkeypatch.setattr(style_config, "st", FakeStreamlit())
    monkeypatch.setattr(style_config, "config_manager", fake_config)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    selected = style_config.render_tts_audio_strategy_selector()

    assert selected == "master_track"
    assert captured["options"] == ["auto", "per_frame", "master_track"]
    assert captured["index"] == 2
    assert captured["key"] == "tts_audio_strategy_select"


def test_copy_tts_audio_strategy_transfers_supported_value():
    target = {}

    tts_audio_strategy_ui.copy_tts_audio_strategy(
        {"tts_audio_strategy": "master_track"},
        target,
    )

    assert target["tts_audio_strategy"] == "master_track"


def test_copy_tts_split_settings_transfers_supported_values():
    target = {}

    tts_split_mode_ui.copy_tts_split_settings(
        {
            "tts_split_mode": "external_only",
            "max_chars_per_tts_segment": 120,
        },
        target,
    )

    assert target == {
        "tts_split_mode": "external_only",
        "max_chars_per_tts_segment": 120,
    }


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
