import json
from types import SimpleNamespace

from pixelle_video.models.layered_template import LayerSourceSpec
from web.components.layered_template_state import (
    LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY,
    LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY,
    LayeredTemplateEditorState,
)


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _TextRenderingFakeUI:
    def __init__(self):
        self.session_state = {
            "text_layer_enabled": False,
            "image_text_suppress_embedded_text": False,
            "image_text_positive_prompt": "",
        }
        self.button_calls = []
        self.markdown_calls = []
        self.tabs_calls = []

    def expander(self, *_args, **_kwargs):
        return _NoopContext()

    def container(self, *_args, **_kwargs):
        return _NoopContext()

    def tabs(self, labels):
        self.tabs_calls.append(list(labels))
        return [_NoopContext() for _label in labels]

    def markdown(self, body, **_kwargs):
        self.markdown_calls.append(body)

    def checkbox(self, _label, **kwargs):
        return self.session_state.get(kwargs.get("key"), kwargs.get("value", False))

    def text_area(self, _label, **kwargs):
        return self.session_state.get(kwargs.get("key"), kwargs.get("value", ""))

    def text_input(self, _label, **kwargs):
        return self.session_state.get(kwargs.get("key"), kwargs.get("value", ""))

    def number_input(self, _label, **kwargs):
        return self.session_state.get(kwargs.get("key"), kwargs.get("value", 0))

    def color_picker(self, _label, **kwargs):
        return self.session_state.get(kwargs.get("key"), kwargs.get("value", "#000000"))

    def selectbox(self, _label, options, **kwargs):
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return list(options)[kwargs.get("index", 0)]

    def radio(self, _label, options, **kwargs):
        return list(options)[kwargs.get("index", 0)]

    def button(self, label, **kwargs):
        self.button_calls.append({"label": label, **kwargs})
        return False


def test_render_text_rendering_controls_no_longer_renders_legacy_preview(monkeypatch):
    from web.components import text_rendering_config

    fake_ui = _TextRenderingFakeUI()
    monkeypatch.setattr(text_rendering_config, "discover_font_options", lambda *_args: [])
    monkeypatch.setattr(
        text_rendering_config,
        "build_text_rendering_preview_spec",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("legacy preview spec called")),
        raising=False,
    )
    monkeypatch.setattr(
        text_rendering_config,
        "render_text_rendering_preview",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy preview UI called")),
        raising=False,
    )
    monkeypatch.setattr(
        text_rendering_config,
        "request_real_preview_frame",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("legacy real preview called")),
        raising=False,
    )
    monkeypatch.setattr(
        text_rendering_config,
        "render_real_preview_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy preview status called")),
        raising=False,
    )

    payload = text_rendering_config.render_text_rendering_controls(
        "hyperframes",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        template_id="image_default",
    )

    assert payload["overlay"] == {"enabled": False}
    assert fake_ui.button_calls == []
    assert all("text_rendering_preview" not in str(body) for body in fake_ui.markdown_calls)


def test_render_style_config_returns_layered_template_spec_payload(monkeypatch):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=768,
                media_height=768,
            )
            .append_background_layer("Background")
            .append_image_layer("Generated image"),
            "text_rendering_real_preview_frame": {"url": "/legacy-preview.png"},
        }
    )
    image_layer_id = fake_st.session_state["layered_template_editor_state"].layers[1].id
    fake_st.session_state["layered_template_editor_state"] = fake_st.session_state[
        "layered_template_editor_state"
    ].update_layer_source(
        image_layer_id,
        LayerSourceSpec(kind="generated_media", ref="generated://primary"),
    )

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_supported_template_orientations",
        lambda _template_type: ["portrait"],
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation",
        lambda *_args: "1080x1920/image_default.html",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_compatible_template_for_orientation",
        lambda current_template, **_kwargs: current_template,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: _template_groups(),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    assert result["selected_template_preset_id"] == "image_default"
    spec = result["layered_template_spec"]
    assert spec["version"] == "layered_template.v1"
    assert spec["template_id"] == "image_default"
    assert spec["template_name"] == "Image Default"
    assert spec["template_type"] == "image"
    assert (spec["canvas_width"], spec["canvas_height"]) == (720, 1280)
    assert (spec["media_width"], spec["media_height"]) == (768, 768)
    assert [layer["type"] for layer in spec["layers"]] == ["background", "image"]
    assert "text_rendering_real_preview_frame" not in result
    assert "preview_media_url" not in result
    assert result["media_placement"] == {
        "basis": "canvas",
        "fit": "contain",
        "scale_percent": 100,
        "offset_x": 0,
        "offset_y": 0,
    }
    assert "anchor" not in result["media_placement"]


def test_render_style_config_updates_layer_properties_from_editor_controls(monkeypatch):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    initial_state = LayeredTemplateEditorState.empty(
        canvas_width=720,
        canvas_height=1280,
        media_width=768,
        media_height=768,
    ).append_text_layer("Headline")
    layer_id = initial_state.layers[0].id
    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "layered_template_editor_state": initial_state,
            f"layered_template_layer_{layer_id}_name": "Hero title",
            f"layered_template_layer_{layer_id}_x": 123,
            f"layered_template_layer_{layer_id}_y": 234,
            f"layered_template_layer_{layer_id}_width": 345,
            f"layered_template_layer_{layer_id}_height": 156,
            f"layered_template_layer_{layer_id}_z_index": 42,
            f"layered_template_layer_{layer_id}_opacity": 0.65,
            f"layered_template_layer_{layer_id}_rotation": -12.5,
            f"layered_template_layer_{layer_id}_locked": True,
            f"layered_template_layer_{layer_id}_role": "title",
        }
    )

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_supported_template_orientations", lambda _template_type: ["portrait"])
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation", lambda *_args: "1080x1920/image_default.html")
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_compatible_template_for_orientation", lambda current_template, **_kwargs: current_template)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda _template_name: "image")
    monkeypatch.setattr("pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type", lambda _template_type: _template_groups())
    monkeypatch.setattr("pixelle_video.utils.template_util.parse_template_size", lambda _path: (1080, 1920))
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    layer = result["layered_template_spec"]["layers"][0]
    assert layer["name"] == "Hero title"
    assert layer["rect"] == {
        "x": 123.0,
        "y": 234.0,
        "width": 345.0,
        "height": 156.0,
        "unit": "px",
    }
    assert layer["z_index"] == 42
    assert layer["opacity"] == 0.65
    assert layer["rotation"] == -12.5
    assert layer["locked"] is True
    assert layer["role"] == "title"
    assert '"anchor"' not in json.dumps(result["layered_template_spec"])


def test_render_style_config_uses_selected_layered_template_identity(monkeypatch):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=768,
                media_height=768,
            ).append_background_layer("Background"),
            LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY: {
                "template_id": "user:branded_news",
                "template_name": "Branded News",
                "template_type": "image",
                "metadata": {"source_kind": "user", "brand": "demo"},
            },
            LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY: {
                "canvas_width": 720,
                "canvas_height": 1280,
                "media_width": 768,
                "media_height": 768,
                "video_orientation": "portrait",
                "video_resolution_preset": "portrait_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            },
        }
    )

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_supported_template_orientations", lambda _template_type: ["portrait"])
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation", lambda *_args: "1080x1920/image_default.html")
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_compatible_template_for_orientation", lambda current_template, **_kwargs: current_template)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda _template_name: "image")
    monkeypatch.setattr("pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type", lambda _template_type: _template_groups())
    monkeypatch.setattr("pixelle_video.utils.template_util.parse_template_size", lambda _path: (1080, 1920))
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    assert result["selected_template_preset_id"] == "user:branded_news"
    spec = result["layered_template_spec"]
    assert spec["template_id"] == "user:branded_news"
    assert spec["template_name"] == "Branded News"
    assert spec["metadata"] == {"source_kind": "user", "brand": "demo"}


def test_render_style_config_preserves_selected_template_non_standard_dimensions(
    monkeypatch,
):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "video_orientation": "portrait",
            "video_resolution_preset": "portrait_hd",
            "media_orientation": "portrait",
            "media_resolution_preset": "1k",
            "sync_media_size_to_canvas": False,
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=1000,
                canvas_height=1500,
                media_width=900,
                media_height=1200,
            ).append_background_layer("Background"),
            LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY: {
                "template_id": "user:non_standard",
                "template_name": "Non Standard",
                "template_type": "image",
                "metadata": {"source_kind": "user"},
            },
            LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY: {
                "canvas_width": 1000,
                "canvas_height": 1500,
                "media_width": 900,
                "media_height": 1200,
                "video_orientation": "portrait",
                "video_resolution_preset": "portrait_hd",
                "media_orientation": "portrait",
                "media_resolution_preset": "1k",
                "sync_media_size_to_canvas": False,
            },
        }
    )

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_supported_template_orientations", lambda _template_type: ["portrait"])
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation", lambda *_args: "1080x1920/image_default.html")
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_compatible_template_for_orientation", lambda current_template, **_kwargs: current_template)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda _template_name: "image")
    monkeypatch.setattr("pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type", lambda _template_type: _template_groups())
    monkeypatch.setattr("pixelle_video.utils.template_util.parse_template_size", lambda _path: (1080, 1920))
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    spec = result["layered_template_spec"]
    assert (spec["canvas_width"], spec["canvas_height"]) == (1000, 1500)
    assert (spec["media_width"], spec["media_height"]) == (900, 1200)
    assert result["selected_template_preset_id"] == "user:non_standard"


def test_render_style_config_keeps_selected_recent_preset_when_gallery_template_incompatible(
    monkeypatch,
):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "selected_template": "1920x1080/image_landscape.html",
            "last_template_type": "image",
            "video_orientation": "portrait",
            "video_resolution_preset": "portrait_hd",
            "media_orientation": "square",
            "media_resolution_preset": "768",
            "sync_media_size_to_canvas": False,
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=768,
                media_height=768,
            ).append_background_layer("Background"),
            LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY: {
                "template_id": "user:portrait_recent",
                "template_name": "Portrait Recent",
                "template_type": "image",
                "metadata": {"source_kind": "user"},
            },
            LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY: {
                "canvas_width": 720,
                "canvas_height": 1280,
                "media_width": 768,
                "media_height": 768,
                "video_orientation": "portrait",
                "video_resolution_preset": "portrait_hd",
                "media_orientation": "square",
                "media_resolution_preset": "768",
                "sync_media_size_to_canvas": False,
            },
        }
    )

    def _resolve_compatible_template(current_template, **kwargs):
        assert current_template == "1920x1080/image_landscape.html"
        assert kwargs["orientation"] == "portrait"
        return "1080x1920/image_default.html"

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_supported_template_orientations", lambda _template_type: ["portrait"])
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation", lambda *_args: "1080x1920/image_default.html")
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_compatible_template_for_orientation", _resolve_compatible_template)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda _template_name: "image")
    monkeypatch.setattr("pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type", lambda _template_type: _template_groups())
    monkeypatch.setattr("pixelle_video.utils.template_util.parse_template_size", lambda _path: (1080, 1920))
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)
    monkeypatch.setattr(
        style_config,
        "safe_rerun",
        lambda: (_ for _ in ()).throw(AssertionError("should not rerun")),
    )

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    assert result["selected_template_preset_id"] == "user:portrait_recent"
    assert result["layered_template_spec"]["template_id"] == "user:portrait_recent"


def test_render_style_config_keeps_recent_user_template_without_legacy_frame_path(
    monkeypatch,
):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "video",
            "last_template_type": "video",
            "video_orientation": "portrait",
            "video_resolution_preset": "portrait_hd",
            "media_orientation": "portrait",
            "media_resolution_preset": "1k",
            "sync_media_size_to_canvas": False,
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=720,
                media_height=1280,
            ).append_background_layer("Background"),
            LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY: {
                "template_id": "user:video_recent",
                "template_name": "Video Recent",
                "template_type": "video",
                "metadata": {"source_kind": "user"},
            },
            LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY: {
                "canvas_width": 720,
                "canvas_height": 1280,
                "media_width": 720,
                "media_height": 1280,
                "video_orientation": "portrait",
                "video_resolution_preset": "portrait_hd",
                "media_orientation": "portrait",
                "media_resolution_preset": "1k",
                "sync_media_size_to_canvas": False,
            },
        }
    )

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_generate_single_style_preview_result", lambda **_kwargs: {})
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_supported_template_orientations", lambda _template_type: ["portrait"])
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation", lambda *_args: "1080x1920/video_default.html")
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_compatible_template_for_orientation", lambda current_template, **_kwargs: current_template)
    monkeypatch.setattr("pixelle_video.utils.template_util.get_template_type", lambda _template_name: "video")
    monkeypatch.setattr("pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type", lambda _template_type: _video_template_groups())
    monkeypatch.setattr("pixelle_video.utils.template_util.parse_template_size", lambda _path: (1080, 1920))
    monkeypatch.setattr("pixelle_video.utils.template_util.resolve_template_path", lambda path: path)
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    assert result["selected_template_preset_id"] == "user:video_recent"
    assert result["layered_template_spec"]["template_type"] == "video"
    assert result["frame_template"] == "1080x1920/video_default.html"


def test_render_style_config_no_longer_renders_middle_column_legacy_template_preview(
    monkeypatch,
):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=768,
                media_height=768,
            ),
        }
    )

    button_calls = []

    def fake_button(_label, **kwargs):
        button_calls.append(kwargs)
        return False

    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_supported_template_orientations",
        lambda _template_type: ["portrait"],
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation",
        lambda *_args: "1080x1920/image_default.html",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_compatible_template_for_orientation",
        lambda current_template, **_kwargs: current_template,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: _template_groups(),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )
    fake_st.button = fake_button
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    assert result["layered_template_spec"]["template_id"] == "image_default"
    assert "btn_preview_template" not in {call.get("key") for call in button_calls}


def test_render_style_config_adds_layers_from_layered_template_editor_buttons(monkeypatch):
    from tests.test_style_config_storyboard_planning_ui import _FakeStreamlit
    from web.components import style_config

    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "template_type_selector": "image",
            "layered_template_editor_state": LayeredTemplateEditorState.empty(
                canvas_width=720,
                canvas_height=1280,
                media_width=768,
                media_height=768,
            ),
        }
    )
    clicked_keys = {
        "layered_template_add_background_layer",
        "layered_template_add_image_layer",
        "layered_template_add_text_layer",
    }

    def fake_button(_label, **kwargs):
        return kwargs.get("key") in clicked_keys

    fake_st.button = fake_button
    monkeypatch.setattr(style_config, "st", fake_st)
    monkeypatch.setattr(style_config, "tr", lambda key, **_kwargs: key)
    monkeypatch.setattr(style_config, "get_language", lambda: "en_US")
    monkeypatch.setattr(style_config, "render_render_backend_selector", lambda: "hyperframes")
    monkeypatch.setattr(style_config, "render_tts_audio_strategy_selector", lambda: "auto")
    monkeypatch.setattr(style_config, "render_tts_split_settings", lambda: {})
    monkeypatch.setattr(style_config, "render_element_animation_controls", lambda: {})
    monkeypatch.setattr(style_config, "render_text_rendering_controls", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(style_config, "_render_image_prompt_prefix_library", lambda **_kwargs: "")
    monkeypatch.setattr(style_config.config_manager, "get_comfyui_config", _fake_comfyui_config)
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_supported_template_orientations",
        lambda _template_type: ["portrait"],
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_default_template_for_type_and_orientation",
        lambda *_args: "1080x1920/image_default.html",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_compatible_template_for_orientation",
        lambda current_template, **_kwargs: current_template,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_template_type",
        lambda _template_name: "image",
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.get_templates_grouped_by_size_and_type",
        lambda _template_type: _template_groups(),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.parse_template_size",
        lambda _path: (1080, 1920),
    )
    monkeypatch.setattr(
        "pixelle_video.utils.template_util.resolve_template_path",
        lambda path: path,
    )
    monkeypatch.setattr("pixelle_video.services.frame_html.HTMLFrameGenerator", _FakeFrameGenerator)

    result = style_config.render_style_config(
        _FakeVideo(),
        content_context={"title": "Runtime Title", "text": "Runtime Caption"},
    )

    spec = result["layered_template_spec"]
    assert [layer["type"] for layer in spec["layers"]] == ["background", "image", "text"]
    assert [layer["name"] for layer in spec["layers"]] == [
        "Background layer 1",
        "Image layer 1",
        "Text layer 1",
    ]
    assert [
        layer.type
        for layer in fake_st.session_state["layered_template_editor_state"].layers
    ] == ["background", "image", "text"]


def _fake_comfyui_config():
    return {
        "tts": {
            "inference_mode": "local",
            "local": {"voice": "zh-CN-YunjianNeural", "speed": 1.2},
            "comfyui": {},
        },
        "image": {},
        "video": {},
    }


def _template_groups():
    return {
        "1080x1920": [
            SimpleNamespace(
                template_path="1080x1920/image_default.html",
                display_info=SimpleNamespace(
                    name="Image Default",
                    orientation="portrait",
                    width=1080,
                    height=1920,
                ),
            )
        ]
    }


def _video_template_groups():
    return {
        "1080x1920": [
            SimpleNamespace(
                template_path="1080x1920/video_default.html",
                display_info=SimpleNamespace(
                    name="Video Default",
                    orientation="portrait",
                    width=1080,
                    height=1920,
                ),
            )
        ]
    }


class _FakeFrameGenerator:
    def __init__(self, _template_path):
        pass

    def parse_template_parameters(self):
        return {}

    def get_media_size(self):
        return (768, 1024)


class _FakeMedia:
    @staticmethod
    def list_workflows():
        return [{"display_name": "Image Default", "key": "selfhost/image.json"}]


class _FakeVideo:
    config = {"template": {}}
    media = _FakeMedia()
