import inspect
import json
import re
from pathlib import Path

import web.components.quick_create_flow as quick_create_flow
import web.components.style_config as style_config
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
        self.expanders: list[tuple[str, bool]] = []
        self.popovers: list[str] = []
        self.container_calls: list[dict] = []
        self.nested_expanders: list[tuple[str, bool]] = []
        self.checkbox_calls: list[dict] = []
        self.session_state = {
            "template_type_selector": "static",
            "storyboard_planning_enabled": True,
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
        self.checkbox_calls.append({"label": label, "value": value, **kwargs})
        return value

    def caption(self, *args, **_kwargs):
        if args:
            self.caption_calls.append(args[0])
        return None

    def info(self, *args, **_kwargs):
        if args:
            self.info_calls.append(args[0])
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def success(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def radio(self, _label, options, index=0, key=None, **_kwargs):
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
        if options:
            return options[index]
        return None

    def columns(self, sizes, **_kwargs):
        count = len(sizes) if isinstance(sizes, list) else int(sizes)
        return [_FakeContext() for _ in range(count)]

    def slider(self, _label, value=None, **_kwargs):
        return value

    def file_uploader(self, *_args, **_kwargs):
        return None

    def button(self, *_args, **_kwargs):
        return False

    def text_input(self, _label, value="", **_kwargs):
        return value

    def text_area(self, _label, value="", **_kwargs):
        return value

    def number_input(self, _label, value=0, **_kwargs):
        return value

    def color_picker(self, _label, value="#000000", **_kwargs):
        return value

    def audio(self, *_args, **_kwargs):
        return None

    def spinner(self, *_args, **_kwargs):
        return _FakeContext()

    def tabs(self, labels):
        return [_FakeContext() for _ in labels]

    def stop(self):
        raise RuntimeError("st.stop called")

    def write(self, *_args, **_kwargs):
        return None

    def image(self, *_args, **_kwargs):
        return None


def test_resolve_storyboard_toggle_default_prefers_session_state_then_preview_snapshot_then_default():
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
            storyboard_default_enabled=True,
            preview_snapshot={"frame_overrides": []},
        )
        is True
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


def test_build_storyboard_control_payload_drops_auto_shot_preset_selection():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="__auto__",
    )

    assert payload == {"world_preset_id": "neutral_knowledge_storyboard"}


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

    def fake_render_style_config(pixelle_video, storyboard_default_enabled=False):
        captured["pixelle_video"] = pixelle_video
        captured["storyboard_default_enabled"] = storyboard_default_enabled
        return {"style": "ok"}

    def fake_render_quick_create_flow_diagram():
        captured["rendered_quick_create_flow"] = True

    monkeypatch.setattr(standard_pipeline.st, "columns", fake_columns)
    monkeypatch.setattr(standard_pipeline, "render_content_input", lambda: {"content": "ok"})
    monkeypatch.setattr(standard_pipeline, "render_bgm_section", lambda: {"bgm": "ok"})
    monkeypatch.setattr(standard_pipeline, "render_version_info", lambda: None)
    monkeypatch.setattr(standard_pipeline, "render_style_config", fake_render_style_config)
    monkeypatch.setattr(standard_pipeline, "render_quick_create_flow_diagram", fake_render_quick_create_flow_diagram)
    monkeypatch.setattr(standard_pipeline, "render_output_preview", lambda pixelle_video, video_params: None)

    pipeline = standard_pipeline.StandardPipelineUI()
    pipeline.render(object())

    assert captured["storyboard_default_enabled"] is True
    assert captured["rendered_quick_create_flow"] is True


def test_build_quick_create_flow_diagram_html_includes_arrow_layout_and_final_generate_step(monkeypatch):
    monkeypatch.setattr(quick_create_flow, "tr", lambda key, **kwargs: key)

    html = quick_create_flow.build_quick_create_flow_diagram_html()

    assert "quick_create_flow.title" in html
    assert "quick-create-flow-card quick-create-flow-card-input" in html
    assert "quick-create-flow-arrow-horizontal" in html
    assert "quick-create-flow-arrow-vertical" in html
    assert "quick_create_flow.node.script_input.title" in html
    assert "quick_create_flow.node.voice.title" in html
    assert "quick_create_flow.node.image.title" in html
    assert "quick_create_flow.node.generate.title" in html
    assert "quick_create_flow.note" in html
    assert "min-height: clamp(" not in html
    assert "min-height: 440px;" in html
    assert "margin-top: auto;" not in html
    assert "padding-bottom: 12px;" in html
    assert "justify-content: space-between;" in html
    assert "justify-self: center;" in html


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
    assert 'tab_label = f"{orientation} {width}×{height}"' in source
    assert 'st.info(f"📋 {tr(\'template.selected_template\')}: **{selected_template_name}**")' in source
    assert 'st.markdown("📝 " + tr("template.custom_parameters"))' in source
    assert 'st.info(f"📐 {tr(\'template.size_info\')}: {template_width} × {template_height}")' in source
    assert 'st.info(f"📐 {size_info_text}")' in source
    assert 'st.info("ℹ️ " + tr("image.not_required"))' in source

    for broken_token in ("路 ", "脳", "馃", "鈩"):
        assert broken_token not in source


def test_build_storyboard_control_payload_includes_storyboard_fields():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        shot_preset_id="balanced_explainer",
        consistency_strength="strong",
        content_mode="concept_explainer",
        role_strategy="auto",
        role_locking_strength="strong",
        shot_strategy="strict",
        frame_overrides=[
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "shot_preset_id": "balanced_explainer",
        "consistency_strength": "strong",
        "content_mode": "concept_explainer",
        "role_strategy": "auto",
        "role_locking_strength": "strong",
        "shot_strategy": "strict",
        "frame_overrides": [
            {
                "scene_id": "scene-1",
                "locked_fields": ["shot_type"],
                "shot_type": "medium_shot",
            }
        ],
    }


def test_build_storyboard_control_payload_includes_no_text_toggle():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        forbid_embedded_text_in_image=False,
    )

    assert payload == {
        "world_preset_id": "neutral_knowledge_storyboard",
        "forbid_embedded_text_in_image": False,
    }


def test_render_style_config_disables_storyboard_for_static_templates(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["storyboard_forbid_embedded_text_in_image"] = False
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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
            return "static"
        return original_radio(label, options, index=index, key=key, **kwargs)

    fake_st.radio = _radio

    class _FakeMedia:
        @staticmethod
        def list_workflows():
            return [
                {
                    "display_name": "Image Default",
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert fake_st.checkbox_calls
    storyboard_checkbox = next(call for call in fake_st.checkbox_calls if call["label"] == "storyboard.enabled")
    assert storyboard_checkbox["disabled"] is True
    assert storyboard_checkbox["value"] is False
    assert fake_st.session_state["storyboard_planning_enabled"] is True
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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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


def test_render_style_config_defaults_no_text_toggle_to_true(monkeypatch):
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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["forbid_embedded_text_in_image"] is True
    no_text_checkbox = next(
        call for call in fake_st.checkbox_calls if call["label"] == "storyboard.forbid_embedded_text"
    )
    assert no_text_checkbox["value"] is True


def test_render_style_config_does_not_apply_no_text_override_when_storyboard_disabled(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["storyboard_planning_enabled"] = False
    fake_st.session_state["storyboard_forbid_embedded_text_in_image"] = False
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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert "forbid_embedded_text_in_image" not in result
    assert all(call["label"] != "storyboard.forbid_embedded_text" for call in fake_st.checkbox_calls)


def test_render_style_config_restores_session_no_text_choice_when_storyboard_reenabled(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["storyboard_planning_enabled"] = True
    fake_st.session_state["storyboard_forbid_embedded_text_in_image"] = False
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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["forbid_embedded_text_in_image"] is False
    no_text_checkbox = next(
        call for call in fake_st.checkbox_calls if call["label"] == "storyboard.forbid_embedded_text"
    )
    assert no_text_checkbox["value"] is False


def test_render_style_config_template_and_image_workflow_help_use_popovers_without_nested_expander(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state["template_type_selector"] = "image"
    fake_st.session_state["template_media_type"] = "image"
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
            "video": {},
        },
    )
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "render_backend")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_storyboard_planning_guide", lambda: None)
    monkeypatch.setattr(style_config, "render_storyboard_preview", lambda _snapshot: [])
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    result = style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    assert result["media_workflow"] == "selfhost/image_z_image_turbo.json"
    assert ("section.image", False) in fake_st.expanders
    assert fake_st.nested_expanders == []
    assert fake_st.popovers == ["help.feature_description", "help.feature_description"]
    expander_html = "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
    assert "**style.image_model_selection_title**" in expander_html
    assert "template.what" not in expander_html
    assert "template.how" not in expander_html
    popover_html = "\n".join(body for body, _kwargs in fake_st.popover_markdowns)
    assert "style.image_model_selection_title" not in popover_html
    assert "template.what" in popover_html
    assert "template.how" in popover_html
    assert "style.workflow_what" in popover_html
    assert "style.workflow_how" in popover_html


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
    monkeypatch.setattr(style_config, "check_and_warn_selfhost_workflow", lambda *_args, **_kwargs: None)
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
                    "key": "selfhost/image_z_image_turbo.json",
                }
            ]

    class _FakeVideo:
        config = {"template": {}}
        media = _FakeMedia()

    style_config.render_style_config(_FakeVideo(), storyboard_default_enabled=True)

    expected_collapsed_sections = {
        ("section.tts", False),
        ("section.render_backend", False),
        ("section.storyboard_planning", False),
        ("section.template", False),
    }

    assert expected_collapsed_sections.issubset(set(fake_st.expanders))
    assert ("section.image", False) in fake_st.expanders
    assert fake_st.nested_expanders == []
    assert fake_st.popovers == ["help.feature_description", "help.feature_description"]

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
        workflow_key="selfhost/image_z_image_turbo.json",
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
    assert "storyboard.guide.field.forbid_embedded_text" in expander_html
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
        "storyboard.guide.field.world_preset",
        "storyboard.guide.field.shot_preset",
        "storyboard.guide.field.consistency_strength",
        "storyboard.guide.field.content_mode",
        "storyboard.guide.field.role_strategy",
        "storyboard.guide.field.role_locking_strength",
        "storyboard.guide.field.shot_strategy",
        "storyboard.forbid_embedded_text",
        "storyboard.forbid_embedded_text_help",
        "storyboard.guide.field.forbid_embedded_text",
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

