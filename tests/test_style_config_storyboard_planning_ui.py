import inspect
import json
import re
from pathlib import Path

import web.components.quick_create_flow as quick_create_flow
import web.components.selfhost_workflow_notice as selfhost_workflow_notice
import web.components.storyboard_planning_controls as storyboard_planning_controls
import web.components.style_config as style_config
import web.components.text_rendering_config as text_rendering_config
import web.pipelines.standard as standard_pipeline
from pixelle_video.config.storyboard_preset_library import (
    BUILTIN_SHOT_PRESETS,
    BUILTIN_WORLD_PRESETS,
)
from web.components.style_config import build_storyboard_control_payload


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.top_level_markdowns: list[tuple[str, dict]] = []
        self.expander_markdowns: list[tuple[str, dict]] = []
        self.popover_markdowns: list[tuple[str, dict]] = []
        self.caption_calls: list[str] = []
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.expanders: list[tuple[str, bool]] = []
        self.popovers: list[str] = []
        self.container_calls: list[dict] = []
        self.nested_expanders: list[tuple[str, bool]] = []
        self.checkbox_calls: list[dict] = []
        self.tab_label_sets: list[list[str]] = []
        self.session_state = {
            "template_type_selector": "static",
            "storyboard_planning_enabled": True,
            "video_orientation": "portrait",
        }
        self._in_expander = False
        self._in_popover = False

    def markdown(self, body, **kwargs):
        if self._in_popover:
            target = self.popover_markdowns
        elif self._in_expander:
            target = self.expander_markdowns
        else:
            target = self.top_level_markdowns
        target.append((body, kwargs))
        return None

    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return _FakeContext()

    def expander(self, label, expanded=False):
        if self._in_expander:
            self.nested_expanders.append((label, expanded))
        self.expanders.append((label, expanded))
        fake_st = self

        class _FakeExpander(_FakeContext):
            def __enter__(self):
                fake_st._in_expander = True
                return self

            def __exit__(self, exc_type, exc, tb):
                fake_st._in_expander = False
                return False

        return _FakeExpander()

    def popover(self, label, **_kwargs):
        self.popovers.append(label)
        fake_st = self

        class _FakePopover(_FakeContext):
            def __enter__(self):
                fake_st._in_popover = True
                return self

            def __exit__(self, exc_type, exc, tb):
                fake_st._in_popover = False
                return False

        return _FakePopover()

    def checkbox(self, label, value=False, **kwargs):
        key = kwargs.get("key")
        if key in self.session_state:
            value = self.session_state[key]
        self.checkbox_calls.append({"label": label, "value": value, **kwargs})
        return value

    def toggle(self, label, value=False, **kwargs):
        return self.checkbox(label, value=value, **kwargs)

    def caption(self, *args, **_kwargs):
        if args:
            self.caption_calls.append(args[0])
        return None

    def info(self, *args, **_kwargs):
        if args:
            self.info_calls.append(args[0])
        return None

    def warning(self, *_args, **_kwargs):
        if _args:
            self.warning_calls.append(_args[0])
        return None

    def success(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def radio(self, _label, options, index=0, key=None, **_kwargs):
        if key in self.session_state:
            return self.session_state[key]
        if key == "tts_inference_mode":
            return "local"
        if key == "template_type_selector":
            return "static"
        if key in {"storyboard_consistency_strength", "storyboard_role_locking_strength"}:
            return options[index]
        if key == "storyboard_shot_strategy":
            return options[index]
        return options[index]

    def selectbox(self, _label, options, index=0, key=None, **_kwargs):
        if key in self.session_state:
            return self.session_state[key]
        if options:
            return options[index]
        return None

    def columns(self, sizes, **_kwargs):
        count = len(sizes) if isinstance(sizes, list) else int(sizes)
        return [_FakeContext() for _ in range(count)]

    def slider(self, _label, value=None, **_kwargs):
        key = _kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def file_uploader(self, *_args, **_kwargs):
        return None

    def button(self, *_args, **_kwargs):
        key = _kwargs.get("key")
        return bool(self.session_state.get("_button_returns", {}).get(key, False))

    def text_input(self, _label, value="", **_kwargs):
        key = _kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def text_area(self, _label, value="", **_kwargs):
        key = _kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def number_input(self, _label, value=0, **_kwargs):
        key = _kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def color_picker(self, _label, value="#000000", **_kwargs):
        key = _kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def audio(self, *_args, **_kwargs):
        return None

    def spinner(self, *_args, **_kwargs):
        return _FakeContext()

    def tabs(self, labels):
        self.tab_label_sets.append(list(labels))
        return [_FakeContext() for _ in labels]

    def stop(self):
        raise RuntimeError("st.stop called")

    def write(self, *_args, **_kwargs):
        return None

    def image(self, *_args, **_kwargs):
        return None


def test_resolve_storyboard_toggle_default_prefers_session_state_then_default():
    assert (
        style_config.resolve_storyboard_toggle_default(
            {"storyboard_planning_enabled": False},
            storyboard_default_enabled=True,
            preview_snapshot={"frame_overrides": []},
        )
        is False
    )

    assert (
        style_config.resolve_storyboard_toggle_default(
            {},
            storyboard_default_enabled=False,
            preview_snapshot={"frame_overrides": []},
        )
        is False
    )

    assert (
        style_config.resolve_storyboard_toggle_default(
            {},
            storyboard_default_enabled=False,
            preview_snapshot=None,
        )
        is False
    )


def test_resolve_storyboard_toggle_default_disables_static_template_even_when_enabled_elsewhere():
    assert (
        style_config.resolve_storyboard_toggle_default(
            {"storyboard_planning_enabled": True},
            storyboard_default_enabled=True,
            preview_snapshot={"frame_overrides": []},
            template_type="static",
        )
        is False
    )


def test_resolve_media_generation_section_expanded_collapses_image_and_keeps_video_open():
    assert style_config.resolve_media_generation_section_expanded("image") is False
    assert style_config.resolve_media_generation_section_expanded("video") is True
    assert style_config.resolve_media_generation_section_expanded("static") is False


def test_render_style_config_comfyui_tts_shows_inline_selfhost_notice(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(selfhost_workflow_notice, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    monkeypatch.setattr(
        selfhost_workflow_notice,
        "tr",
        lambda key, **kwargs: key.format(**kwargs) if kwargs else key,
    )
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "comfyui_url": "http://127.0.0.1:8000",
            "tts": {
                "inference_mode": "comfyui",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {"default_workflow": "selfhost/tts_index2.json"},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, **_kwargs: ("voice.wav", None),
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "tts_inference_mode":
            return "comfyui"
        if key == "template_type_selector":
            return "static"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeTTS:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "tts_index2.json - Selfhost",
                    "key": "selfhost/tts_index2.json",
                }
            ]

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return []

    class _FakeVideo:
        config = {"template": {}}
        tts = _FakeTTS()
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["tts_workflow"] == "selfhost/tts_index2.json"
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
    assert "selfhost.warning.inline_title" in expander_html
    assert "workflows/selfhost/tts_index2.json" in expander_html
    assert fake_st.warning_calls == ["selfhost.warning.hint"]


def test_render_style_config_comfyui_tts_default_workflow_prefers_omnivoice_when_config_empty(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    fake_st.session_state["tts_inference_mode"] = "comfyui"
    captured = {}

    def _selectbox(label, options, index=0, key=None, **kwargs):
        if key == "tts_workflow_select":
            captured["workflow_options"] = list(options)
            captured["workflow_index"] = index
            captured["workflow_key"] = key
        return options[index]

    fake_st.selectbox = _selectbox
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "comfyui_url": "http://127.0.0.1:8000",
            "tts": {
                "inference_mode": "comfyui",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config, "render_selfhost_workflow_notice", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        style_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeTTS:
        @staticmethod
        def list_workflows():
            return [
                {"display_name": "Edge TTS", "key": "selfhost/tts_edge.json"},
                {"display_name": "IndexTTS2", "key": "selfhost/tts_index2.json"},
                {
                    "display_name": "OmniVoice Duration",
                    "key": "selfhost/tts_omnivoice_clone_duration_bf16.json",
                },
                {
                    "display_name": "OmniVoice Longform",
                    "key": "selfhost/tts_omnivoice_longform_bf16.json",
                },
            ]

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return []

    class _FakeVideo:
        config = {"template": {}}
        tts = _FakeTTS()
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert captured["workflow_key"] == "tts_workflow_select"
    assert captured["workflow_index"] == 3
    assert result["tts_workflow"] == "selfhost/tts_omnivoice_longform_bf16.json"


def test_render_style_config_warns_when_selected_tts_requires_reference_audio(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    fake_st.session_state["tts_inference_mode"] = "comfyui"
    preview_buttons = []

    def _button(label, **kwargs):
        if kwargs.get("key") == "preview_tts":
            preview_buttons.append({"label": label, **kwargs})
        return False

    fake_st.button = _button
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "comfyui_url": "http://127.0.0.1:8000",
            "tts": {
                "inference_mode": "comfyui",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {
                    "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                },
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config, "render_selfhost_workflow_notice", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        style_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, **_kwargs: (None, None),
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeTTS:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "OmniVoice Longform",
                    "key": "selfhost/tts_omnivoice_longform_bf16.json",
                },
            ]

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return []

    class _FakeVideo:
        config = {"template": {}}
        tts = _FakeTTS()
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["ref_audio"] is None
    assert "tts.reference_audio_required" in fake_st.warning_calls
    assert preview_buttons[-1]["disabled"] is True


def test_render_style_config_returns_tts_duration_for_duration_workflow(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    fake_st.session_state["tts_inference_mode"] = "comfyui"
    fake_st.session_state["tts_workflow_select"] = "OmniVoice Duration"
    fake_st.session_state["tts_duration_seconds"] = 8.0
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "comfyui_url": "http://127.0.0.1:8000",
            "tts": {
                "inference_mode": "comfyui",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {
                    "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                },
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config, "render_selfhost_workflow_notice", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        style_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, **_kwargs: ("voice.wav", "参考音频文本"),
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeTTS:
        @staticmethod
        def list_workflows():
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

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return []

    class _FakeVideo:
        config = {"template": {}}
        tts = _FakeTTS()
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["tts_workflow"] == "selfhost/tts_omnivoice_clone_duration_bf16.json"
    assert result["tts_duration"] == 8.0


def test_render_style_config_local_mode_preview_button_does_not_require_ref_audio(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    fake_st.session_state["tts_inference_mode"] = "local"
    preview_buttons = []

    def _button(label, **kwargs):
        if kwargs.get("key") == "preview_tts":
            preview_buttons.append({"label": label, **kwargs})
        return False

    fake_st.button = _button
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "comfyui_url": "http://127.0.0.1:8000",
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {
                    "default_workflow": "selfhost/tts_omnivoice_longform_bf16.json"
                },
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config,
        "render_tts_voice_profile_controls",
        lambda _workflow_key, **_kwargs: ("voice.wav", None),
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return []

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["tts_inference_mode"] == "local"
    assert preview_buttons[-1]["disabled"] is False


def test_build_storyboard_control_payload_drops_auto_shot_preset_selection():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="__auto__",
    )

    assert payload == {"world_preset_id": "neutral_knowledge_storyboard"}


def test_render_storyboard_advanced_controls_no_longer_renders_generation_world_hint(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["storyboard_planning_enabled"] = True
    fake_st.session_state["storyboard_generation_world_hint"] = "古城清晨漫游"
    text_area_calls = []
    button_calls = []

    def _text_area(label, value="", **kwargs):
        text_area_calls.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key in fake_st.session_state:
            return fake_st.session_state[key]
        return value

    def _button(*args, **kwargs):
        button_calls.append({"args": args, **kwargs})
        key = kwargs.get("key")
        return bool(fake_st.session_state.get("_button_returns", {}).get(key, False))

    fake_st.text_area = _text_area
    fake_st.button = _button
    monkeypatch.setattr(
        storyboard_planning_controls,
        "render_storyboard_planning_guide",
        lambda **_kwargs: None,
    )

    payload = storyboard_planning_controls.render_storyboard_advanced_controls(
        ui=fake_st,
        translate=lambda key, **kwargs: key,
        session_state=fake_st.session_state,
        storyboard_default_enabled=True,
        world_library_loader=lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [
                {"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}
            ],
        },
        shot_library_loader=lambda: {"items": []},
    )

    assert "generation_world_hint" not in payload
    assert not any(
        call["label"] == "storyboard.generation_world_hint" for call in text_area_calls
    )
    assert not any(
        call.get("key") in {
            "storyboard_world_hint_generate_from_content",
            "storyboard_world_hint_use_ip_default",
        }
        for call in button_calls
    )


def test_resolve_storyboard_preset_label_uses_translation_key_or_display_name_fallback(monkeypatch):
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: f"localized:{key}")

    assert (
        style_config.resolve_storyboard_preset_label(
            {"preset_id": "balanced_explainer", "display_name_key": "storyboard.preset.shot.balanced_explainer.name"}
        )
        == "localized:storyboard.preset.shot.balanced_explainer.name"
    )

    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    assert (
        style_config.resolve_storyboard_preset_label(
            {
                "preset_id": "fallback_only",
                "display_name_key": "storyboard.preset.shot.fallback_only.name",
                "display_name": "Fallback Name",
            }
        )
        == "Fallback Name"
    )

    assert (
        style_config.resolve_storyboard_preset_label(
            {"preset_id": "fallback_only", "display_name": "Fallback Name"}
        )
        == "Fallback Name"
    )


def test_standard_pipeline_ui_passes_storyboard_default_enabled_to_render_style_config(monkeypatch):
    captured = {}

    class _FakeColumn(_FakeContext):
        pass

    def fake_columns(_sizes):
        return [_FakeColumn(), _FakeColumn(), _FakeColumn()]

    def fake_render_style_config(
        pixelle_video,
        storyboard_default_enabled=False,
        storyboard_prompt_language="zh_CN",
        content_context=None,
    ):
        captured["pixelle_video"] = pixelle_video
        captured["storyboard_default_enabled"] = storyboard_default_enabled
        captured["storyboard_prompt_language"] = storyboard_prompt_language
        captured["content_context"] = content_context
        return {"style": "ok"}

    def fake_render_quick_create_flow_diagram():
        captured["rendered_quick_create_flow"] = True

    monkeypatch.setattr(standard_pipeline.st, "columns", fake_columns)
    monkeypatch.setattr(
        standard_pipeline,
        "render_content_input",
        lambda *, pixelle_video=None: {
            "content": "ok",
            "title": "Preview title",
            "text": "Preview caption",
            "storyboard_prompt_language": "en_US",
        },
    )
    monkeypatch.setattr(standard_pipeline, "render_bgm_section", lambda **_kwargs: {"bgm": "ok"})
    monkeypatch.setattr(standard_pipeline, "render_version_info", lambda: None)
    monkeypatch.setattr(standard_pipeline, "render_style_config", fake_render_style_config)
    monkeypatch.setattr(standard_pipeline, "render_quick_create_flow_diagram", fake_render_quick_create_flow_diagram)
    monkeypatch.setattr(standard_pipeline, "render_output_preview", lambda pixelle_video, video_params: None)

    pipeline = standard_pipeline.StandardPipelineUI()
    pipeline.render(object())

    assert captured["storyboard_default_enabled"] is False
    assert captured["storyboard_prompt_language"] == "en_US"
    assert captured["content_context"]["title"] == "Preview title"
    assert captured["content_context"]["text"] == "Preview caption"
    assert captured["rendered_quick_create_flow"] is True


def test_build_quick_create_flow_diagram_html_uses_responsive_layout_contract(monkeypatch):
    monkeypatch.setattr(quick_create_flow, "tr", lambda key, **kwargs: key)

    html = quick_create_flow.build_quick_create_flow_diagram_html()

    assert "quick_create_flow.title" in html
    assert 'data-node="script_input"' in html
    assert 'data-node="generate"' in html
    assert "quick-create-flow-desktop" in html
    assert "quick-create-flow-tablet" in html
    assert "quick-create-flow-stepper" in html
    assert "quick-create-flow-arrow-horizontal" in html
    assert "quick-create-flow-arrow-vertical" in html
    assert "quick_create_flow.node.script_input.title" in html
    assert "quick_create_flow.node.voice.title" in html
    assert "quick_create_flow.node.image.title" in html
    assert "quick_create_flow.node.generate.title" in html
    assert "quick_create_flow.note" in html
    assert "container-type: inline-size;" in html
    assert "container-name: quick-create-flow;" in html
    assert "@container quick-create-flow (max-width: 860px)" in html
    assert "@container quick-create-flow (max-width: 620px)" in html
    assert "@container quick-create-flow (max-width: 430px)" in html
    assert "overflow-wrap: anywhere;" in html
    assert "--flow-tablet-card-width: 11.75rem;" in html
    assert "grid-template-columns: var(--flow-tablet-card-width) var(--flow-arrow-span) var(--flow-tablet-card-width);" in html
    assert "@media (max-width: 980px)" not in html
    assert "padding-bottom: 12px;" in html
    assert (
        "grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr);"
        not in html
    )
    assert "grid-column: 7;" not in html


def test_render_quick_create_flow_diagram_uses_bordered_container_and_html_markdown(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(quick_create_flow, "st", fake_st)
    monkeypatch.setattr(quick_create_flow, "tr", lambda key, **kwargs: key)

    quick_create_flow.render_quick_create_flow_diagram()

    assert {"border": True} in fake_st.container_calls
    assert any(kwargs.get("unsafe_allow_html") for _body, kwargs in fake_st.top_level_markdowns)
    rendered_html = "\n".join(body for body, _kwargs in fake_st.top_level_markdowns)
    assert "quick_create_flow.title" in rendered_html
    assert "quick_create_flow.node.generate.title" in rendered_html


def test_style_config_source_keeps_expected_ui_glyphs_and_separators():
    source = inspect.getsource(style_config)

    assert 'f"· {get_prompt_prefix_category_label(active_item[\'style_category_id\'], \'style\', language)} "' in source
    assert 'f"· {get_prompt_prefix_category_label(active_item[\'scene_category_id\'], \'scene\', language)}"' in source
    assert 'st.caption(f"📁 {audio_path}")' in source
    assert "_build_template_gallery_tab_label(" in source
    assert 'tab_label = f"{orientation} {width}' not in source
    assert 'st.info(f"📋 {tr(\'template.selected_template\')}: **{selected_template_name}**")' in source
    assert 'st.markdown("📝 " + tr("template.custom_parameters"))' in source
    assert '"size.final_video_info"' in source
    assert '"size.template_base_info"' in source
    assert 'st.info(f"📐 {size_info_text}")' in source
    assert 'st.info("ℹ️ " + tr("image.not_required"))' in source

    for broken_token in ("路 ", "脳", "馃", "鈩"):
        assert broken_token not in source


def test_build_storyboard_control_payload_includes_storyboard_fields():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        storyboard_prompt_language="zh_CN",
        consistency_strength="strong",
        content_mode="concept_explainer",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
        frame_overrides=[
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": ["visual_goal"],
                "visual_goal": "Locked visual goal.",
            }
        ],
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "shot_preset_id": "balanced_explainer",
        "storyboard_prompt_language": "zh_CN",
        "consistency_strength": "strong",
        "content_mode": "concept_explainer",
        "role_locking_strength": "strong",
        "shot_strategy": "strict",
        "frame_overrides": [
            {
                "plan_id": "plan_abc",
                "plan_revision": 1,
                "frame_id": "frame_0001",
                "source_digest": "a" * 64,
                "locked_fields": ["visual_goal"],
                "visual_goal": "Locked visual goal.",
            }
        ],
    }


def test_build_storyboard_control_payload_defaults_to_chinese_prompt_language_when_blank():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        storyboard_prompt_language="  ",
    )

    assert payload["storyboard_prompt_language"] == "zh_CN"


def test_build_storyboard_control_payload_trims_string_fields_with_shared_contract():
    payload = build_storyboard_control_payload(
        world_preset_id="  neutral_knowledge_storyboard  ",
        shot_preset_id="  balanced_explainer  ",
        storyboard_prompt_language=" en_US ",
        consistency_strength=" strong ",
        content_mode=" concept_explainer ",
        role_strategy=" auto ",
        role_locking_strength=" strong ",
        shot_strategy=" strict ",
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "shot_preset_id": "balanced_explainer",
        "storyboard_prompt_language": "en_US",
        "consistency_strength": "strong",
        "content_mode": "concept_explainer",
        "role_locking_strength": "strong",
        "shot_strategy": "strict",
    }


def test_build_storyboard_control_payload_drops_legacy_scene_identity_overrides():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        frame_overrides=[
            {
                "scene_id": "scene-1",
                "snapshot_identity": "snapshot:scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    )

    assert payload == {"world_preset_id": "neutral_knowledge_storyboard"}


def test_build_text_rendering_payload_defaults_image_text_suppression_off():
    payload = style_config.build_text_rendering_payload(
        overlay_policy=None,
        suppress_embedded_text=False,
        positive_prompt="avoid generated lettering",
    )

    assert payload == {
        "overlay": {"enabled": False},
        "image_text": {
            "suppress_embedded_text": False,
            "positive_prompt": "avoid generated lettering",
        },
    }


def test_build_text_rendering_payload_preserves_cleared_positive_prompt():
    payload = style_config.build_text_rendering_payload(
        overlay_policy=None,
        suppress_embedded_text=True,
        positive_prompt="   ",
    )

    assert payload["image_text"] == {
        "suppress_embedded_text": True,
        "positive_prompt": "",
    }


def test_render_text_rendering_controls_returns_nested_policy_when_enabled(monkeypatch):
    fake_st = _FakeStreamlit()
    text_area_calls = []

    def _checkbox(label, value=False, key=None, **kwargs):
        fake_st.checkbox_calls.append({"label": label, "value": value, "key": key, **kwargs})
        return key in {"text_layer_enabled", "image_text_suppress_embedded_text"}

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "text_layer_mode":
            return "hybrid"
        if key == "text_layer_target_preset":
            return "both"
        return options[index]

    def _selectbox(label, options, index=0, key=None, **kwargs):
        if key == "text_layer_density":
            return "low"
        return options[index]

    monkeypatch.setattr(text_rendering_config, "st", fake_st)
    monkeypatch.setattr(text_rendering_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])
    fake_st.checkbox = _checkbox
    fake_st.radio = _radio
    fake_st.selectbox = _selectbox
    fake_st.number_input = lambda *args, **kwargs: 1
    fake_st.text_area = lambda label, value="", **kwargs: (
        text_area_calls.append({"label": label, "value": value, **kwargs}) or value
    )

    policy = style_config.render_text_rendering_controls("hyperframes_compiled")

    assert policy["overlay"] == {
        "enabled": True,
        "mode": "hybrid",
        "renderer_targets": ["hyperframes", "ass"],
        "density": "low",
        "max_items_per_frame": 1,
    }
    assert policy["caption_style"] == {
        "font_family": "Noto Sans CJK SC",
        "font_size": 1,
        "primary_color": "#2C3E50",
        "stroke_color": "#000000",
        "stroke_width": 1,
        "background_color": "#000000",
        "background_opacity": 1.0,
        "position": "bottom",
        "alignment": "center",
        "margin_x": 1,
        "margin_y": 1,
        "max_width_ratio": 1.0,
        "max_chars_per_line": 1,
    }
    assert policy["overlay_style"] == {
        "font_family": "Noto Sans CJK SC",
        "font_size": 1,
        "primary_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 1,
        "background_color": "#000000",
        "background_opacity": 1.0,
        "position": "center",
        "alignment": "center",
        "margin_x": 1,
        "margin_y": 1,
        "max_width_ratio": 1.0,
        "max_chars_per_line": 1,
    }
    assert policy["image_text"] == {
        "suppress_embedded_text": True,
        "positive_prompt": style_config.DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT,
    }
    assert text_area_calls[0]["disabled"] is False


def test_render_text_rendering_controls_keeps_prompt_editable_when_suppression_is_off(monkeypatch):
    fake_st = _FakeStreamlit()
    text_area_calls = []

    def _checkbox(label, value=False, key=None, **kwargs):
        fake_st.checkbox_calls.append({"label": label, "value": value, "key": key, **kwargs})
        return False

    monkeypatch.setattr(text_rendering_config, "st", fake_st)
    monkeypatch.setattr(text_rendering_config, "tr", lambda key, **kwargs: key)
    fake_st.checkbox = _checkbox
    fake_st.text_area = lambda label, value="", **kwargs: (
        text_area_calls.append({"label": label, "value": value, **kwargs}) or "custom disabled-state prompt"
    )

    policy = style_config.render_text_rendering_controls("hyperframes_compiled")

    assert policy["image_text"] == {
        "suppress_embedded_text": False,
        "positive_prompt": "custom disabled-state prompt",
    }
    assert text_area_calls[0]["disabled"] is False


def test_render_style_config_disables_storyboard_for_static_templates(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: (_ for _ in ()).throw(AssertionError("guide should not render for static templates")))
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "static"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert ("section.storyboard_planning", False) not in fake_st.expanders
    assert all(
        call["label"] not in {"storyboard.enabled", "storyboard.advanced_enabled"}
        for call in fake_st.checkbox_calls
    )
    assert "forbid_embedded_text_in_image" not in result


def test_render_style_config_shows_expanded_image_notice_when_template_does_not_require_media(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "static"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "static",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/static_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "static_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "static"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            raise AssertionError("media workflows should not be loaded for static templates")

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert ("section.image", True) in fake_st.expanders
    assert result["media_workflow"] is None
    assert result["prompt_prefix"] == ""
    assert any("image.not_required" in message for message in fake_st.info_calls)
    assert "image.not_required_hint" in fake_st.caption_calls


def test_render_style_config_defaults_image_text_suppression_to_false(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
                return [
                    {
                        "display_name": "Image Default",
                        "key": "selfhost/image_z_image_turbo_gguf.json",
                    }
                ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["text_rendering"]["image_text"]["suppress_embedded_text"] is False
    no_text_checkbox = next(
        call for call in fake_st.checkbox_calls if call["label"] == "image_text.suppress_embedded_text"
    )
    assert no_text_checkbox["value"] is False


def test_render_style_config_allows_switching_storyboard_prompt_language(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(
        _FakeVideo(),
        storyboard_default_enabled=True,
        storyboard_prompt_language="en_US",
    )

    assert result["storyboard_prompt_language"] == "en_US"


def test_render_style_config_does_not_apply_no_text_override_when_storyboard_disabled(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["storyboard_planning_enabled"] = False
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["text_rendering"]["image_text"]["suppress_embedded_text"] is False
    assert all(call["label"] != "storyboard.forbid_embedded_text" for call in fake_st.checkbox_calls)


def test_render_style_config_restores_session_image_text_choice(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["storyboard_planning_enabled"] = True
    fake_st.session_state["image_text_suppress_embedded_text"] = True
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["text_rendering"]["image_text"]["suppress_embedded_text"] is True
    no_text_checkbox = next(
        call for call in fake_st.checkbox_calls if call["label"] == "image_text.suppress_embedded_text"
    )
    assert no_text_checkbox["value"] is True


def test_render_style_config_template_and_image_workflow_help_use_popovers_without_nested_expander(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["template_media_type"] = "image"
    fake_st.session_state["template_requires_media"] = True
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(selfhost_workflow_notice, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(selfhost_workflow_notice, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["media_workflow"] == "selfhost/image_z_image_turbo_gguf.json"
    assert ("section.image", False) in fake_st.expanders
    assert fake_st.nested_expanders == []
    assert ["orientation.portrait"] in fake_st.tab_label_sets
    assert ["caption_style.tab", "title_style.tab"] in fake_st.tab_label_sets
    assert fake_st.popovers == ["help.feature_description", "help.feature_description"]
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
    assert "**style.image_model_selection_title**" in expander_html
    assert "selfhost.warning.inline_title" in expander_html
    assert "workflows/selfhost/image_z_image_turbo_gguf.json" in expander_html
    assert "template.what" not in expander_html
    assert "template.how" not in expander_html
    popover_html = "\n".join(body for body, _kwargs in fake_st.popover_markdowns)
    assert "style.image_model_selection_title" not in popover_html
    assert "template.what" in popover_html
    assert "template.how" in popover_html
    assert "style.workflow_what" in popover_html
    assert "style.workflow_how" in popover_html


def test_render_style_config_keeps_video_generation_section_expanded_by_default(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "video"
    fake_st.session_state["template_media_type"] = "video"
    fake_st.session_state["template_requires_media"] = True
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {"prompt_prefix": "cinematic mood"},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_world_preset_library",
        lambda: {
            "default_world_preset_id": "neutral_knowledge_storyboard",
            "items": [{"preset_id": "neutral_knowledge_storyboard", "display_name": "Neutral"}],
        },
    )
    monkeypatch.setattr(
        style_config.config_manager,
        "get_storyboard_shot_preset_library",
        lambda: {
            "default_shot_preset_id": "balanced_explainer",
            "items": [{"preset_id": "balanced_explainer", "display_name": "Balanced"}],
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "video",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/video_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "video_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "video"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Video Default",
                    "key": "selfhost/video_default.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["media_workflow"] == "selfhost/video_default.json"
    assert result["prompt_prefix"] == "cinematic mood"
    assert ("section.video", True) in fake_st.expanders
    assert fake_st.popovers == ["help.feature_description"]
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
    assert "style.video_workflow_what" in expander_html
    assert "style.video_workflow_how" in expander_html
    popover_html = "\n".join(body for body, _kwargs in fake_st.popover_markdowns)
    assert "style.video_workflow_what" not in popover_html
    assert "style.video_workflow_how" not in popover_html


def test_render_style_config_defaults_other_middle_sections_to_collapsed_while_image_starts_collapsed(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    expected_collapsed_sections = {
        ("section.tts", False),
        ("section.render_backend", False),
        ("section.template", False),
        ("section.layer_design", False),
    }

    assert expected_collapsed_sections.issubset(set(fake_st.expanders))
    assert ("section.image", False) in fake_st.expanders
    assert fake_st.nested_expanders == []
    assert fake_st.popovers == ["help.feature_description", "help.feature_description"]


def test_style_config_no_longer_renders_standard_ip_selector_in_middle_column():
    source = (
        Path(__file__).resolve().parents[1] / "web" / "components" / "style_config.py"
    ).read_text(encoding="utf-8")

    assert "render_ip_prompt_chain_controls(" not in source
    assert "style_ip_asset_bibles" not in source
    assert "style_ip_profile_world_hint" not in source
    assert "**ip_prompt_chain_controls" not in source


def test_render_style_config_does_not_emit_ip_prompt_chain_payload(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["style_ip_enabled"] = True
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {
                "inference_mode": "local",
                "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
                "comfyui": {},
            },
            "image": {},
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: {
            "1080x1920": [
                type(
                    "TemplateInfo",
                    (),
                    {
                        "template_path": "1080x1920/image_default.html",
                        "display_info": type(
                            "DisplayInfo",
                            (),
                            {
                                "name": "image_default",
                                "orientation": "portrait",
                                "width": 1080,
                                "height": 1920,
                            },
                        )(),
                    },
                )()
            ]
        },
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )

    class _FakeFrameGenerator:
        def __init__(self, _template_path):
            self._template_path = _template_path

        def parse_template_parameters(self):
            return {}

        def get_media_size(self):
            return (1080, 1920)

    monkeypatch.setattr(
        "pixelle_video.services.frame_html.HTMLFrameGenerator",
        _FakeFrameGenerator,
    )

    original_radio = fake_st.radio

    def _radio(label, options, index=0, key=None, **kwargs):
        if key == "template_type_selector":
            return "image"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo_gguf.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert "ip_enabled" not in result
    assert "ip_asset_bible_id" not in result
    assert "ip_profile_id" not in result
    assert "style_ip_asset_bibles" not in fake_st.session_state
    assert "style_ip_profile_world_hint" not in fake_st.session_state


def test_render_image_prompt_prefix_library_renders_filter_panel_without_nested_expander(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(
        style_config,
        "config_manager",
        type(
            "FakeConfigManager",
            (),
            {
                "config": type(
                    "Config",
                    (),
                    {
                        "comfyui": type("ComfyUI", (), {"image": {}})(),
                    },
                )(),
                "get_image_prompt_prefix_library": lambda self: {
                    "active_prefix_id": None,
                    "items": [],
                },
            },
        )(),
    )
    monkeypatch.setattr(
        style_config,
        "get_localized_prompt_prefix_category_options",
        lambda language="en_US": (
            [{"id": "storybook", "label": "Storybook"}],
            [{"id": "childrens_story", "label": "Children"}],
        ),
    )
    monkeypatch.setattr(
        style_config,
        "sanitize_prompt_prefix_preview_selection",
        lambda selected_ids, valid_ids: [],
    )
    monkeypatch.setattr(style_config, "_build_prompt_prefix_live_preview_map", lambda: {})
    monkeypatch.setattr(
        style_config,
        "filter_prompt_prefix_items",
        lambda library_items, style_category_id=None, scene_category_id=None, keyword=None: [],
    )

    style_config._render_image_prompt_prefix_library(
        pixelle_video=object(),
        workflow_key="selfhost/image_z_image_turbo_gguf.json",
        media_width=1024,
        media_height=1024,
        workflow_display_map={},
    )

    assert ("style.prefix_library.filter_panel", False) in fake_st.expanders
    assert fake_st.nested_expanders == []


def test_collapsible_section_helper_does_not_require_key_parameter():
    assert "key" not in inspect.signature(style_config.render_middle_column_collapsible_section).parameters


def test_render_storyboard_planning_guide_renders_default_on_copy_and_detail_section(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    style_config.render_storyboard_planning_guide()

    assert ("storyboard.guide.title", False) in fake_st.expanders

    top_level_html = "\n".join(body for body, _kwargs in fake_st.top_level_markdowns)
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)

    assert "**storyboard.guide.title**" not in expander_html
    assert "storyboard.guide.default_on_title" in top_level_html
    assert "storyboard.guide.default_on_body" in top_level_html
    assert "storyboard.guide.when_to_turn_off.title" in top_level_html
    assert "storyboard.guide.when_to_turn_off.body" in top_level_html
    assert "storyboard.guide.quick_title" not in expander_html
    assert "storyboard.guide.quick_body" not in expander_html

    assert "storyboard.guide.combo.explainer.title" in expander_html
    assert "storyboard.guide.combo.theme_mapping.title" in expander_html
    assert "storyboard.guide.field.world_preset" in expander_html
    assert "storyboard.guide.preset_picker_title" in expander_html
    assert "storyboard.guide.preset_picker.world.title" in expander_html
    assert "storyboard.guide.preset_picker.shot.title" in expander_html
    assert "storyboard.guide.preset_picker.world.item.angry_birds_three_kingdoms" in expander_html
    assert "storyboard.guide.preset_picker.shot.item.character_relationship" in expander_html
    assert "storyboard.guide.override_title" in expander_html
    assert any(kwargs.get("unsafe_allow_html") for _body, kwargs in fake_st.expander_markdowns)


def test_render_storyboard_planning_guide_avoids_indented_html_block_lines(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **kwargs: key)

    style_config.render_storyboard_planning_guide()

    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
    indented_html_lines = [
        line
        for line in expander_html.splitlines()
        if re.match(r"^\s{2,}</?(div|ul|li|span)\b", line)
    ]

    assert indented_html_lines == []


def test_storyboard_planning_guide_translation_keys_exist_in_supported_locales():
    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    built_in_preset_keys = [
        *(key for preset in BUILTIN_WORLD_PRESETS for key in (preset.display_name_key, preset.description_key)),
        *(key for preset in BUILTIN_SHOT_PRESETS for key in (preset.display_name_key, preset.description_key)),
    ]
    required_keys = [
        "storyboard.guide.title",
        "storyboard.guide.default_on_title",
        "storyboard.guide.default_on_body",
        "storyboard.guide.when_to_turn_off.title",
        "storyboard.guide.when_to_turn_off.body",
        "storyboard.guide.recommended_title",
        "storyboard.guide.combo.explainer.title",
        "storyboard.guide.combo.explainer.body",
        "storyboard.guide.combo.theme_mapping.title",
        "storyboard.guide.combo.theme_mapping.body",
        "storyboard.guide.combo.iteration.title",
        "storyboard.guide.combo.iteration.body",
        "storyboard.guide.fields_title",
        "storyboard.generation_world_hint_generate",
        "storyboard.generation_world_hint_use_ip_default",
        "storyboard.generation_world_hint_missing_content",
        "storyboard.generation_world_hint_missing_ip_default",
        "storyboard.guide.field.world_preset",
        "storyboard.guide.field.shot_preset",
        "storyboard.guide.field.consistency_strength",
        "storyboard.guide.field.content_mode",
        "storyboard.guide.field.role_strategy",
        "storyboard.guide.field.role_locking_strength",
        "storyboard.guide.field.shot_strategy",
        "storyboard.guide.preset_picker_title",
        "storyboard.guide.preset_picker.world.title",
        "storyboard.guide.preset_picker.world.body",
        "storyboard.guide.preset_picker.world.item.neutral_knowledge_storyboard",
        "storyboard.guide.preset_picker.world.item.dual_mode_storyboard",
        "storyboard.guide.preset_picker.world.item.angry_birds_three_kingdoms",
        "storyboard.guide.preset_picker.world.item.angry_birds_knowledge_classroom",
        "storyboard.guide.preset_picker.world.item.angry_birds_history_classroom",
        "storyboard.guide.preset_picker.shot.title",
        "storyboard.guide.preset_picker.shot.body",
        "storyboard.guide.preset_picker.shot.item.balanced_explainer",
        "storyboard.guide.preset_picker.shot.item.detail_focus",
        "storyboard.guide.preset_picker.shot.item.opening_world_building",
        "storyboard.guide.preset_picker.shot.item.character_relationship",
        "storyboard.guide.preset_picker.shot.item.classroom_demo",
        "storyboard.guide.override_title",
        "storyboard.guide.override_body",
    ]
    required_keys.extend(built_in_preset_keys)

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []


def test_image_generation_translation_keys_exist_in_supported_locales():
    locale_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"
    required_keys = [
        "style.image_model_selection_title",
        "quick_create_flow.title",
        "quick_create_flow.caption",
        "quick_create_flow.badge",
        "quick_create_flow.note",
        "quick_create_flow.node.script_input.title",
        "quick_create_flow.node.script_input.description",
        "quick_create_flow.node.mode.title",
        "quick_create_flow.node.mode.description",
        "quick_create_flow.node.scene_count.title",
        "quick_create_flow.node.scene_count.description",
        "quick_create_flow.node.bgm.title",
        "quick_create_flow.node.bgm.description",
        "quick_create_flow.node.voice.title",
        "quick_create_flow.node.voice.description",
        "quick_create_flow.node.render.title",
        "quick_create_flow.node.render.description",
        "quick_create_flow.node.storyboard.title",
        "quick_create_flow.node.storyboard.description",
        "quick_create_flow.node.template.title",
        "quick_create_flow.node.template.description",
        "quick_create_flow.node.image.title",
        "quick_create_flow.node.image.description",
        "quick_create_flow.node.generate.title",
        "quick_create_flow.node.generate.description",
    ]

    for locale_name in ("zh_CN.json", "en_US.json"):
        translations = json.loads((locale_dir / locale_name).read_text(encoding="utf-8"))["t"]
        missing_keys = [key for key in required_keys if key not in translations]
        assert missing_keys == []
