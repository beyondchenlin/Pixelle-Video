from pixelle_video.models.layered_template import LayerSourceSpec
from web.components.layered_template_state import (
    LayeredTemplateEditorState,
    LayeredTemplateSpecBuilder,
    ensure_layered_template_editor_state,
    load_layered_template_spec_into_editor_state,
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

