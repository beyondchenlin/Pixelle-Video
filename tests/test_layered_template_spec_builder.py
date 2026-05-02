from pixelle_video.models.layered_template import LayerSourceSpec
from web.components.layered_template_state import (
    LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY,
    LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY,
    LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY,
    apply_pending_layered_template_widget_state,
    LayeredTemplateEditorState,
    LayeredTemplateSpecBuilder,
    ensure_layered_template_editor_state,
    load_layered_template_spec_into_editor_state,
    resolve_layered_template_spec_identity,
)


def test_spec_builder_builds_complete_spec_from_editor_state():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_text_layer("Title")

    spec = LayeredTemplateSpecBuilder.from_editor_state(state).build(
        template_id="demo",
        template_name="Demo",
        template_type="image",
        metadata={"source": "test"},
    )

    assert spec.template_id == "demo"
    assert spec.template_name == "Demo"
    assert spec.template_type == "image"
    assert (spec.canvas_width, spec.canvas_height) == (1080, 1920)
    assert (spec.media_width, spec.media_height) == (1080, 1920)
    assert spec.safe_area.to_dict() == {
        "x": 0.0,
        "y": 0.0,
        "width": 1080.0,
        "height": 1920.0,
        "unit": "px",
    }
    assert spec.layers[0].type == "text"
    assert spec.metadata["source"] == "test"


def test_editor_state_can_append_multiple_layers_with_unique_ids():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    )

    state = state.append_text_layer("Title")
    state = state.append_image_layer("Image")
    state = state.append_background_layer("Background")

    assert [layer.type for layer in state.layers] == ["text", "image", "background"]
    assert len({layer.id for layer in state.layers}) == 3
    assert state.selected_layer_id == state.layers[-1].id


def test_editor_state_update_layer_source_replaces_only_target_layer():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_image_layer("Image")
    target_id = state.layers[0].id

    updated = state.update_layer_source(
        target_id,
        LayerSourceSpec(kind="asset", ref="assets/demo/image.png"),
    )

    assert updated.layers[0].source is not None
    assert updated.layers[0].source.ref == "assets/demo/image.png"
    assert state.layers[0].source is None


def test_editor_state_update_layer_properties_replaces_only_target_fields():
    base = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    )
    base = base.append_background_layer("Background").append_text_layer("Title")
    target_id = base.layers[1].id

    updated = (
        base.update_layer_name(target_id, "Headline")
        .update_layer_rect(
            target_id,
            x=120,
            y=240,
            width=640,
            height=220,
        )
        .update_layer_z_index(target_id, 99)
        .update_layer_opacity(target_id, 0.55)
        .update_layer_rotation(target_id, 12.5)
        .update_layer_locked(target_id, True)
        .update_layer_role(target_id, "title")
        .update_layer_style(
            target_id,
            {
                "font_size": 88,
                "primary_color": "#112233",
            },
        )
    )

    assert updated.layers[0] == base.layers[0]
    assert updated.layers[1].name == "Headline"
    assert updated.layers[1].rect.to_dict() == {
        "x": 120.0,
        "y": 240.0,
        "width": 640.0,
        "height": 220.0,
        "unit": "px",
    }
    assert updated.layers[1].z_index == 99
    assert updated.layers[1].opacity == 0.55
    assert updated.layers[1].rotation == 12.5
    assert updated.layers[1].locked is True
    assert updated.layers[1].role == "title"
    assert updated.layers[1].style["font_size"] == 88
    assert updated.layers[1].style["primary_color"] == "#112233"
    assert updated.selected_layer_id == base.selected_layer_id
    assert base.layers[1].name == "Title"
    assert base.layers[1].rect != updated.layers[1].rect
    assert base.layers[1].style == {}


def test_editor_state_update_layer_helpers_ignore_unknown_layer_id():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_text_layer("Title")

    unchanged = (
        state.update_layer_name("missing", "Ignored")
        .update_layer_rect("missing", x=1, y=2, width=3, height=4)
        .update_layer_z_index("missing", 7)
        .update_layer_opacity("missing", 0.2)
        .update_layer_rotation("missing", 8)
        .update_layer_locked("missing", True)
        .update_layer_role("missing", "caption")
        .update_layer_style("missing", {"font_size": 42})
        .update_layer_source("missing", LayerSourceSpec(kind="asset", ref="assets/demo.png"))
    )

    assert unchanged == state


def test_ensure_editor_state_resets_when_dimensions_change():
    session_state = {}
    state = ensure_layered_template_editor_state(
        session_state=session_state,
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_text_layer("Title")
    session_state["layered_template_editor_state"] = state

    updated = ensure_layered_template_editor_state(
        session_state=session_state,
        canvas_width=1920,
        canvas_height=1080,
        media_width=1920,
        media_height=1080,
    )

    assert updated.layers == ()
    assert (updated.canvas_width, updated.canvas_height) == (1920, 1080)
    assert session_state["layered_template_editor_state"] == updated


def test_load_layered_template_spec_into_editor_state_round_trips_layers():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_background_layer("Background")
    spec = state.build_spec(
        template_id="demo",
        template_name="Demo",
        template_type="image",
    )
    session_state = {}

    loaded = load_layered_template_spec_into_editor_state(session_state, spec.to_dict())

    assert loaded.layers == spec.layers
    assert loaded.selected_layer_id == spec.layers[0].id
    assert session_state["layered_template_editor_state"] == loaded


def test_load_layered_template_spec_preserves_identity_for_generation_fact_source():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_background_layer("Background")
    spec = state.build_spec(
        template_id="user:branded_news",
        template_name="Branded News",
        template_type="image",
        metadata={"source_kind": "user", "brand": "demo"},
    )
    session_state = {}

    loaded = load_layered_template_spec_into_editor_state(session_state, spec.to_dict())
    identity = resolve_layered_template_spec_identity(
        session_state,
        fallback_template_id="image_default",
        fallback_template_name="Image Default",
        fallback_template_type="image",
    )

    assert session_state[LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY] == {
        "template_id": "user:branded_news",
        "template_name": "Branded News",
        "template_type": "image",
        "metadata": {"source_kind": "user", "brand": "demo"},
    }
    assert session_state[LAYERED_TEMPLATE_SELECTED_SIZE_PARAMS_KEY] == {
        "canvas_width": 1080,
        "canvas_height": 1920,
        "media_width": 1080,
        "media_height": 1920,
        "video_orientation": "portrait",
        "video_resolution_preset": "portrait_full_hd",
        "media_orientation": "portrait",
        "media_resolution_preset": "2k",
        "sync_media_size_to_canvas": False,
    }
    assert session_state[LAYERED_TEMPLATE_PENDING_WIDGET_STATE_KEY] == {
        "video_orientation": "portrait",
        "video_resolution_preset": "portrait_full_hd",
        "media_orientation": "portrait",
        "media_resolution_preset": "2k",
        "sync_media_size_to_canvas": False,
        "template_type_selector": "image",
        "last_template_type": "image",
        "selected_template": None,
    }
    apply_pending_layered_template_widget_state(session_state)
    assert session_state["video_orientation"] == "portrait"
    assert session_state["video_resolution_preset"] == "portrait_full_hd"
    assert session_state["media_orientation"] == "portrait"
    assert session_state["media_resolution_preset"] == "2k"
    assert identity == session_state[LAYERED_TEMPLATE_SELECTED_SPEC_IDENTITY_KEY]
    generated_spec = loaded.build_spec(**identity)
    assert generated_spec.template_id == "user:branded_news"
    assert generated_spec.template_name == "Branded News"
    assert generated_spec.metadata["brand"] == "demo"


def test_load_layered_template_spec_preserves_non_default_safe_area():
    state = LayeredTemplateEditorState.empty(
        canvas_width=1080,
        canvas_height=1920,
        media_width=1080,
        media_height=1920,
    ).append_background_layer("Background")
    spec = state.build_spec(
        template_id="user:safe-area-demo",
        template_name="Safe Area Demo",
        template_type="image",
    )
    spec = LayeredTemplateSpecBuilder.from_editor_state(
        state
    ).build(
        template_id="user:safe-area-demo",
        template_name="Safe Area Demo",
        template_type="image",
        metadata={},
    )
    spec_payload = spec.to_dict()
    spec_payload["safe_area"] = {
        "x": 80,
        "y": 120,
        "width": 920,
        "height": 1680,
        "unit": "px",
    }
    session_state = {}

    loaded = load_layered_template_spec_into_editor_state(session_state, spec_payload)
    regenerated = loaded.build_spec(
        template_id="user:safe-area-demo",
        template_name="Safe Area Demo",
        template_type="image",
    )

    assert regenerated.safe_area.to_dict() == spec_payload["safe_area"]


def test_load_layered_template_spec_defers_widget_key_mutation_until_next_rerun():
    class _WidgetLockedSessionState(dict):
        locked_keys = {
            "template_type_selector",
            "last_template_type",
            "selected_template",
            "video_orientation",
            "video_resolution_preset",
            "media_orientation",
            "media_resolution_preset",
            "sync_media_size_to_canvas",
        }
        lock_widget_keys = True

        def __setitem__(self, key, value):
            if self.lock_widget_keys and key in self.locked_keys:
                raise AssertionError(f"widget key mutated too late: {key}")
            return super().__setitem__(key, value)

    state = LayeredTemplateEditorState.empty(
        canvas_width=720,
        canvas_height=1280,
        media_width=720,
        media_height=1280,
    )
    spec = state.build_spec(
        template_id="user:video-template",
        template_name="Video Template",
        template_type="video",
        metadata={"source_kind": "user"},
    )
    session_state = _WidgetLockedSessionState()

    load_layered_template_spec_into_editor_state(session_state, spec.to_dict())

    assert "template_type_selector" not in session_state
    session_state.lock_widget_keys = False
    apply_pending_layered_template_widget_state(session_state)
    assert session_state["template_type_selector"] == "video"


def test_load_layered_template_spec_syncs_template_selector_state():
    state = LayeredTemplateEditorState.empty(
        canvas_width=720,
        canvas_height=1280,
        media_width=720,
        media_height=1280,
    )
    spec = state.build_spec(
        template_id="user:video-template",
        template_name="Video Template",
        template_type="video",
        metadata={"source_kind": "user"},
    )
    session_state = {
        "template_type_selector": "image",
        "last_template_type": "image",
        "selected_template": "1920x1080/image_landscape.html",
    }

    load_layered_template_spec_into_editor_state(session_state, spec.to_dict())

    assert session_state["template_type_selector"] == "image"
    apply_pending_layered_template_widget_state(session_state)
    assert session_state["template_type_selector"] == "video"
    assert session_state["last_template_type"] == "video"
    assert "selected_template" not in session_state


def test_load_layered_template_spec_uses_legacy_template_path_when_available():
    state = LayeredTemplateEditorState.empty(
        canvas_width=720,
        canvas_height=1280,
        media_width=720,
        media_height=1280,
    )
    spec = state.build_spec(
        template_id="system:1080x1920/video_default.html",
        template_name="video_default.html",
        template_type="video",
        metadata={
            "source_kind": "legacy_html",
            "legacy_template_path": "1080x1920/video_default.html",
        },
    )
    session_state = {"selected_template": "1080x1920/image_default.html"}

    load_layered_template_spec_into_editor_state(session_state, spec.to_dict())

    assert session_state["selected_template"] == "1080x1920/image_default.html"
    apply_pending_layered_template_widget_state(session_state)
    assert session_state["template_type_selector"] == "video"
    assert session_state["last_template_type"] == "video"
    assert session_state["selected_template"] == "1080x1920/video_default.html"

