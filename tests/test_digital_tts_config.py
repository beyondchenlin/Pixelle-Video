from web.components import digital_tts_config


def test_digital_tts_config_returns_selected_comfyui_workflow(monkeypatch):
    captured = {}

    class FakeStreamlit:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            return "comfyui"

        def caption(self, body):
            return None

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            captured["workflow_options"] = options
            captured["workflow_index"] = index
            captured["workflow_key"] = key
            return options[index]

        def file_uploader(self, label, *, type, help, key):
            return None

        def text_area(self, label, *, value, placeholder, help, key, height):
            return ""

        def text_input(self, label, *, value, placeholder, key):
            return value

        def warning(self, message):
            return None

        def button(self, label, *, key, width, disabled=False):
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "comfyui",
                    "local": {"speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_edge.json",
                        "speed": 1.0,
                    },
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [
                {"display_name": "IndexTTS2", "key": "runninghub/tts_index2.json"},
                {"display_name": "Edge TTS", "key": "selfhost/tts_edge.json"},
            ]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: (None, None),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert captured["workflow_options"] == ["IndexTTS2", "Edge TTS"]
    assert captured["workflow_index"] == 1
    assert captured["workflow_key"] == "digital_tts_workflow_select"
    assert result["tts_workflow"] == "selfhost/tts_edge.json"


def test_digital_tts_config_defaults_to_comfyui_when_mode_is_missing(monkeypatch):
    captured = {}

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit(FakeContext):
        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            captured["mode_index"] = index
            return options[index]

        def caption(self, body):
            return None

        def columns(self, spec):
            return [FakeContext(), FakeContext()]

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            if key == "digital_tts_workflow_select":
                captured["workflow_key"] = key
            return options[index]

        def slider(self, label, *, min_value, max_value, value, step, format, key):
            return value

        def text_input(self, label, *, value, placeholder, key):
            return value

        def warning(self, message):
            return None

        def button(self, label, *, key, width, disabled=False):
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "local": {"speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_index2.json",
                        "speed": 1.0,
                    },
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [{"display_name": "IndexTTS2", "key": "selfhost/tts_index2.json"}]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: (None, None),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert captured["mode_index"] == 1
    assert captured["workflow_key"] == "digital_tts_workflow_select"
    assert result["tts_inference_mode"] == "comfyui"


def test_digital_tts_config_default_workflow_prefers_omnivoice_when_config_is_empty(monkeypatch):
    captured = {}

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit(FakeContext):
        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            return "comfyui"

        def caption(self, body):
            return None

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            if key == "digital_tts_workflow_select":
                captured["workflow_index"] = index
                captured["workflow_key"] = key
            return options[index]

        def text_input(self, label, *, value, placeholder, key):
            return value

        def warning(self, message):
            return None

        def button(self, label, *, key, width, disabled=False):
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "comfyui",
                    "local": {"speed": 1.2},
                    "comfyui": {},
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [
                {"display_name": "Edge TTS", "key": "selfhost/tts_edge.json"},
                {"display_name": "OmniVoice Longform", "key": "selfhost/tts_omnivoice_longform_bf16.json"},
            ]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: (None, None),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert captured["workflow_key"] == "digital_tts_workflow_select"
    assert captured["workflow_index"] == 1
    assert result["tts_workflow"] == "selfhost/tts_omnivoice_longform_bf16.json"


def test_digital_tts_config_warns_when_selected_tts_requires_reference_audio(monkeypatch):
    captured = {"buttons": []}

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit(FakeContext):
        def __init__(self):
            self.warning_calls = []

        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            return "comfyui"

        def caption(self, body):
            return None

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            return options[index]

        def text_input(self, label, *, value, placeholder, key):
            return value

        def warning(self, message):
            self.warning_calls.append(message)

        def button(self, label, *, key, width, disabled=False):
            captured["buttons"].append({"key": key, "disabled": disabled})
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "comfyui",
                    "local": {"speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                    },
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [
                {"display_name": "OmniVoice Longform", "key": "selfhost/tts_omnivoice_longform_bf16.json"},
            ]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()
    fake_st = FakeStreamlit()

    monkeypatch.setattr(digital_tts_config, "st", fake_st)
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: (None, None),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert result["ref_audio"] is None
    assert "tts.reference_audio_required" in fake_st.warning_calls
    assert captured["buttons"][-1] == {
        "key": "gidital_preview_tts",
        "disabled": True,
    }


def test_digital_tts_config_returns_tts_duration_for_duration_workflow(monkeypatch):
    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit(FakeContext):
        session_state = {
            "digital_tts_workflow_select": "OmniVoice Duration",
            "digital_tts_duration_seconds": 8.0,
        }

        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            return "comfyui"

        def caption(self, body):
            return None

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            return self.session_state.get(key, options[index])

        def number_input(self, label, value=0.0, **kwargs):
            return self.session_state.get(kwargs.get("key"), value)

        def text_input(self, label, *, value, placeholder, key):
            return value

        def button(self, label, *, key, width, disabled=False):
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "comfyui",
                    "local": {"speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                    },
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [
                {
                    "display_name": "OmniVoice Duration",
                    "key": "selfhost/tts_omnivoice_clone_duration_bf16.json",
                },
                {
                    "display_name": "OmniVoice Longform",
                    "key": "selfhost/tts_omnivoice_longform_bf16.json",
                },
            ]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: ("voice.wav", "参考音频文本"),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert result["tts_workflow"] == "selfhost/tts_omnivoice_clone_duration_bf16.json"
    assert result["tts_duration"] == 8.0


def test_digital_tts_config_local_mode_preview_button_does_not_require_ref_audio(monkeypatch):
    captured = {"buttons": []}

    class FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit(FakeContext):
        def container(self, border=False):
            return self

        def expander(self, label, expanded=False):
            return self

        def markdown(self, body):
            return None

        def radio(self, label, options, *, horizontal, format_func, index, key):
            return "local"

        def caption(self, body):
            return None

        def columns(self, spec):
            return [FakeContext(), FakeContext()]

        def selectbox(self, label, options, *, index=0, key=None, label_visibility=None):
            return options[index]

        def slider(self, label, *, min_value, max_value, value, step, format, key):
            return value

        def text_input(self, label, *, value, placeholder, key):
            return value

        def button(self, label, *, key, width, disabled=False):
            captured["buttons"].append({"key": key, "disabled": disabled})
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "local",
                    "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                    },
                }
            }

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": object()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        digital_tts_config,
        "render_selfhost_workflow_notice",
        lambda _workflow_key: None,
    )
    monkeypatch.setattr(
        digital_tts_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, *, key_prefix: (None, None),
    )

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert result["tts_inference_mode"] == "local"
    assert captured["buttons"][-1] == {
        "key": "gidital_preview_tts",
        "disabled": False,
    }
