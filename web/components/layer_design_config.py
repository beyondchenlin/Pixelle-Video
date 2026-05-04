from __future__ import annotations

from html import escape

import streamlit as st

from web.components.layered_template_state import (
    LAYERED_TEMPLATE_EDITOR_STATE_KEY,
    LayeredTemplateEditorState,
)
from web.i18n import get_language, tr


def _layered_template_editor_text(
    key: str,
    *,
    zh: str,
    en: str,
    translate=tr,
) -> str:
    fallback = zh if get_language() == "zh_CN" else en
    return translate(key, fallback=fallback)


def _build_layered_template_editor_css() -> str:
    return """
    <style>
    .st-key-layered_template_add_row {
        container-type: inline-size;
    }
    .st-key-layered_template_add_row > div[data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }
    .st-key-layered_template_add_row div[data-testid="stHorizontalBlock"] {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(128px, 100%), 1fr));
        gap: 0.5rem !important;
        align-items: stretch;
    }
    .st-key-layered_template_add_row div[data-testid="stColumn"] {
        width: 100% !important;
        min-width: 0 !important;
        flex: 1 1 auto !important;
    }
    .st-key-layered_template_add_row button {
        min-height: 2.25rem;
        width: 100% !important;
        padding-inline: 0.5rem;
        white-space: nowrap;
    }
    .st-key-layered_template_add_row button p {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    </style>
    """


def render_layer_design_config(
    state: LayeredTemplateEditorState,
    *,
    ui=st,
    translate=tr,
) -> LayeredTemplateEditorState:
    with ui.expander(translate("section.layer_design"), expanded=False):
        ui.caption(
            _layered_template_editor_text(
                "layered_template.editor.caption",
                zh="添加背景、图片或文本层；位置、尺寸、层级等属性在下方图层中调整。",
                en=(
                    "Add background, image, or text layers; adjust position, "
                    "size, stack, and other properties below."
                ),
                translate=translate,
            )
        )
        next_counts = {
            "background": sum(1 for layer in state.layers if layer.type == "background") + 1,
            "image": sum(1 for layer in state.layers if layer.type == "image") + 1,
            "text": sum(1 for layer in state.layers if layer.type == "text") + 1,
        }

        with ui.container(key="layered_template_add_row"):
            ui.markdown(_build_layered_template_editor_css(), unsafe_allow_html=True)
            add_background_col, add_image_col, add_text_col = ui.columns(3)
            with add_background_col:
                if ui.button(
                    _layered_template_editor_text(
                        "layered_template.editor.add_background",
                        zh="添加背景",
                        en="Add background",
                        translate=translate,
                    ),
                    key="layered_template_add_background_layer",
                    width="stretch",
                ):
                    state = state.append_background_layer(
                        f"Background layer {next_counts['background']}"
                    )
            with add_image_col:
                if ui.button(
                    _layered_template_editor_text(
                        "layered_template.editor.add_image",
                        zh="添加图片",
                        en="Add image",
                        translate=translate,
                    ),
                    key="layered_template_add_image_layer",
                    width="stretch",
                ):
                    state = state.append_image_layer(f"Image layer {next_counts['image']}")
            with add_text_col:
                if ui.button(
                    _layered_template_editor_text(
                        "layered_template.editor.add_text",
                        zh="添加文本",
                        en="Add text",
                        translate=translate,
                    ),
                    key="layered_template_add_text_layer",
                    width="stretch",
                ):
                    state = state.append_text_layer(f"Text layer {next_counts['text']}")

        if state.layers:
            for layer in sorted(state.layers, key=lambda item: item.z_index):
                state = _render_layered_template_layer_controls(
                    state,
                    layer.id,
                    ui=ui,
                    translate=translate,
                )
        else:
            ui.info(translate("layered_template.editor.empty"))

    ui.session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY] = state
    return state


def _render_layered_template_layer_controls(
    state: LayeredTemplateEditorState,
    layer_id: str,
    *,
    ui=st,
    translate=tr,
) -> LayeredTemplateEditorState:
    layer = next((item for item in state.layers if item.id == layer_id), None)
    if layer is None:
        return state

    label = (
        f"{layer.name} - {layer.type} - "
        f"{int(layer.rect.width)}x{int(layer.rect.height)} - z{layer.z_index}"
    )
    with ui.container(border=True):
        ui.markdown(f"**{escape(label)}**")
        key_prefix = f"layered_template_layer_{layer.id}"
        name = ui.text_input(
            translate("layered_template.editor.layer_name"),
            value=layer.name,
            key=f"{key_prefix}_name",
        )

        geometry_columns = ui.columns(4)
        with geometry_columns[0]:
            x = ui.number_input(
                translate("layered_template.editor.layer_x"),
                value=float(layer.rect.x),
                key=f"{key_prefix}_x",
            )
        with geometry_columns[1]:
            y = ui.number_input(
                translate("layered_template.editor.layer_y"),
                value=float(layer.rect.y),
                key=f"{key_prefix}_y",
            )
        with geometry_columns[2]:
            width = ui.number_input(
                translate("layered_template.editor.layer_width"),
                min_value=1.0,
                value=float(layer.rect.width),
                key=f"{key_prefix}_width",
            )
        with geometry_columns[3]:
            height = ui.number_input(
                translate("layered_template.editor.layer_height"),
                min_value=1.0,
                value=float(layer.rect.height),
                key=f"{key_prefix}_height",
            )

        display_columns = ui.columns(4)
        with display_columns[0]:
            z_index = ui.number_input(
                translate("layered_template.editor.layer_z_index"),
                value=int(layer.z_index),
                step=1,
                key=f"{key_prefix}_z_index",
            )
        with display_columns[1]:
            opacity = ui.number_input(
                translate("layered_template.editor.layer_opacity"),
                min_value=0.0,
                max_value=1.0,
                value=float(layer.opacity),
                step=0.05,
                key=f"{key_prefix}_opacity",
            )
        with display_columns[2]:
            rotation = ui.number_input(
                translate("layered_template.editor.layer_rotation"),
                value=float(layer.rotation),
                step=1.0,
                key=f"{key_prefix}_rotation",
            )
        with display_columns[3]:
            locked = ui.checkbox(
                translate("layered_template.editor.layer_locked"),
                value=bool(layer.locked),
                key=f"{key_prefix}_locked",
            )

        role = layer.role
        if layer.type == "text":
            role_options = ["", "title", "caption"]
            current_role = role if role in role_options else ""
            role = ui.selectbox(
                translate("layered_template.editor.layer_role"),
                role_options,
                index=role_options.index(current_role),
                key=f"{key_prefix}_role",
                format_func=lambda value: translate(
                    f"layered_template.editor.layer_role.{value or 'none'}"
                ),
            )
            role = role or None
        elif role:
            ui.caption(
                translate("layered_template.editor.layer_role_summary").format(
                    role=escape(str(role))
                )
            )

        state = state.update_layer_name(layer.id, name)
        state = state.update_layer_rect(
            layer.id,
            x=float(x),
            y=float(y),
            width=max(1.0, float(width)),
            height=max(1.0, float(height)),
        )
        state = state.update_layer_z_index(layer.id, int(z_index))
        state = state.update_layer_opacity(layer.id, float(opacity))
        state = state.update_layer_rotation(layer.id, float(rotation))
        state = state.update_layer_locked(layer.id, bool(locked))
        state = state.update_layer_role(layer.id, role)
    return state
