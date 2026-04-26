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

        def button(self, label, *, key, width):
            return False

    class FakeConfigManager:
        def get_comfyui_config(self):
            return {
                "tts": {
                    "inference_mode": "comfyui",
                    "local": {"speed": 1.2},
                    "comfyui": {
                        "default_workflow": "selfhost/tts_longcat_clone.json",
                        "speed": 1.0,
                    },
                }
            }

    class FakeTTS:
        def list_workflows(self):
            return [
                {"display_name": "IndexTTS2", "key": "runninghub/tts_index2.json"},
                {"display_name": "LongCat Clone", "key": "selfhost/tts_longcat_clone.json"},
            ]

    fake_pixelle_video = type("FakePixelleVideo", (), {"tts": FakeTTS()})()

    monkeypatch.setattr(digital_tts_config, "st", FakeStreamlit())
    monkeypatch.setattr(digital_tts_config, "config_manager", FakeConfigManager())
    monkeypatch.setattr(digital_tts_config, "tr", lambda key, **kwargs: key)

    result = digital_tts_config.render_style_config(fake_pixelle_video)

    assert captured["workflow_options"] == ["IndexTTS2", "LongCat Clone"]
    assert captured["workflow_index"] == 1
    assert captured["workflow_key"] == "digital_tts_workflow_select"
    assert result["tts_workflow"] == "selfhost/tts_longcat_clone.json"


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

        def button(self, label, *, key, width):
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
