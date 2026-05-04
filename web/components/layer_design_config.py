from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
import re

import streamlit as st

from pixelle_video.models.layered_template import LayerSourceSpec
from pixelle_video.utils.os_util import get_data_path, get_temp_path
from web.components.layered_template_state import (
    LAYERED_TEMPLATE_EDITOR_STATE_KEY,
    LayeredTemplateEditorState,
)
from web.i18n import get_language, tr


_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
_SAFE_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


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
    div[class*="st-key-layered_template_layer_card_"] {
        container-type: inline-size;
    }
    div[class*="st-key-layered_template_layer_card_"] div[data-testid="stHorizontalBlock"] {
        align-items: center;
    }
    div[class*="st-key-layered_template_layer_card_"] button {
        min-height: 2rem;
        white-space: nowrap;
    }
    </style>
    """


def _merge_layer_style(layer, **updates) -> dict:
    style = dict(layer.style)
    for key, value in updates.items():
        if value is None:
            style.pop(key, None)
        else:
            style[key] = value
    return style


def _safe_upload_suffix(uploaded_file) -> str:
    suffix = Path(str(getattr(uploaded_file, "name", "") or "")).suffix.lower()
    if suffix in _SAFE_UPLOAD_SUFFIXES:
        return suffix
    return ".png"


def _safe_original_filename(uploaded_file) -> str:
    filename = Path(str(getattr(uploaded_file, "name", "") or "uploaded_asset")).name
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "_", filename).strip("._")
    return sanitized or "uploaded_asset"


def _uploaded_file_bytes(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "getbuffer"):
        return bytes(uploaded_file.getbuffer())
    if hasattr(uploaded_file, "getvalue"):
        return bytes(uploaded_file.getvalue())
    if isinstance(uploaded_file, bytes):
        return uploaded_file
    raise TypeError("uploaded file must provide getbuffer(), getvalue(), or bytes")


def _persist_layer_asset(uploaded_file, *, layer_id: str) -> LayerSourceSpec:
    data = _uploaded_file_bytes(uploaded_file)
    digest = hashlib.sha256(data).hexdigest()[:16]
    suffix = _safe_upload_suffix(uploaded_file)
    original_filename = _safe_original_filename(uploaded_file)
    temp_dir = Path(get_temp_path("layer_assets"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{layer_id}_{digest}{suffix}"
    if not temp_path.exists():
        temp_path.write_bytes(data)

    asset_dir = Path(get_data_path("template_presets", "assets", "layer_draft"))
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / f"{layer_id}_{digest}{suffix}"
    if not asset_path.exists():
        asset_path.write_bytes(data)
    return LayerSourceSpec(
        kind="asset",
        ref=f"assets/layer_draft/{asset_path.name}",
        metadata={"original_filename": original_filename},
    )


def _render_layer_content_controls(
    state: LayeredTemplateEditorState,
    layer,
    key_prefix: str,
    *,
    ui=st,
    translate=tr,
) -> LayeredTemplateEditorState:
    if layer.type == "text":
        text_content = ui.text_area(
            _layered_template_editor_text(
                "layered_template.editor.layer_text_content",
                zh="文本内容",
                en="Text content",
                translate=translate,
            ),
            value=str(layer.style.get("text_content") or ""),
            key=f"{key_prefix}_text",
        )
        state = state.update_layer_style(
            layer.id,
            _merge_layer_style(layer, text_content=str(text_content).strip() or None),
        )
        return state

    if layer.type in {"image", "background"}:
        upload_label = _layered_template_editor_text(
            "layered_template.editor.layer_background_upload"
            if layer.type == "background"
            else "layered_template.editor.layer_image_upload",
            zh="上传背景图片" if layer.type == "background" else "上传图片",
            en="Upload background image" if layer.type == "background" else "Upload image",
            translate=translate,
        )
        uploaded_file = ui.file_uploader(
            upload_label,
            type=sorted(suffix.removeprefix(".") for suffix in _SAFE_UPLOAD_SUFFIXES),
            key=f"{key_prefix}_asset_upload",
        )
        has_uploaded_asset = uploaded_file is not None
        if uploaded_file is not None:
            state = state.update_layer_source(
                layer.id,
                _persist_layer_asset(uploaded_file, layer_id=layer.id),
            )
    else:
        has_uploaded_asset = False

    if layer.type == "background":
        existing_color = layer.style.get("background_color")
        if not _HEX_COLOR_PATTERN.fullmatch(str(existing_color or "")):
            existing_color = "#FFFFFF"
        background_color = ui.color_picker(
            _layered_template_editor_text(
                "layered_template.editor.layer_background_color",
                zh="背景颜色",
                en="Background color",
                translate=translate,
            ),
            value=str(existing_color),
            key=f"{key_prefix}_background_color",
        )
        if _HEX_COLOR_PATTERN.fullmatch(str(background_color)):
            state = state.update_layer_style(
                layer.id,
                _merge_layer_style(layer, background_color=str(background_color)),
            )
            layer_source = layer.source
            if not has_uploaded_asset and (layer_source is None or layer_source.kind == "color"):
                state = state.update_layer_source(
                    layer.id,
                    LayerSourceSpec(kind="color", ref=str(background_color)),
                )
    return state


def render_layer_design_config(
    state: LayeredTemplateEditorState,
    *,
    on_save_design=None,
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

        if on_save_design is not None and ui.button(
            _layered_template_editor_text(
                "layered_template.editor.save_design",
                zh="保存图层设计",
                en="Save layer design",
                translate=translate,
            ),
            key="layered_template_save_design",
            width="stretch",
        ):
            on_save_design(state)

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
    key_prefix = f"layered_template_layer_{layer.id}"
    expanded_key = f"{key_prefix}_expanded"
    expanded = bool(ui.session_state.get(expanded_key, layer.id == state.selected_layer_id))
    ui.session_state[expanded_key] = expanded
    with ui.container(border=True, key=f"layered_template_layer_card_{layer.id}"):
        header_columns = ui.columns([0.9, 3.1, 1, 1])
        with header_columns[0]:
            enabled = ui.checkbox(
                _layered_template_editor_text(
                    "layered_template.editor.layer_enabled",
                    zh="加入视频",
                    en="Include in video",
                    translate=translate,
                ),
                value=bool(layer.enabled),
                key=f"{key_prefix}_enabled",
            )
            state = state.update_layer_enabled(layer.id, bool(enabled))
            layer = next((item for item in state.layers if item.id == layer_id), layer)
        with header_columns[1]:
            ui.markdown(f"**{escape(label)}**")
        with header_columns[2]:
            toggle_label = _layered_template_editor_text(
                "layered_template.editor.layer_collapse"
                if expanded
                else "layered_template.editor.layer_expand",
                zh="收起" if expanded else "展开",
                en="Collapse" if expanded else "Expand",
                translate=translate,
            )
            if ui.button(
                toggle_label,
                key=f"{key_prefix}_toggle",
                width="stretch",
            ):
                expanded = not expanded
                ui.session_state[expanded_key] = expanded
                rerun = getattr(ui, "rerun", None)
                if callable(rerun):
                    rerun()
        with header_columns[3]:
            if ui.button(
                _layered_template_editor_text(
                    "layered_template.editor.layer_delete",
                    zh="删除",
                    en="Delete",
                    translate=translate,
                ),
                key=f"{key_prefix}_delete",
                width="stretch",
            ):
                ui.session_state.pop(expanded_key, None)
                ui.session_state.pop(f"{key_prefix}_enabled", None)
                return state.delete_layer(layer.id)

        if not expanded:
            return state

        name = ui.text_input(
            translate("layered_template.editor.layer_name"),
            value=layer.name,
            key=f"{key_prefix}_name",
        )
        state = _render_layer_content_controls(
            state,
            layer,
            key_prefix,
            ui=ui,
            translate=translate,
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
            role_options = ["custom", "title", "caption"]
            role_value = role or "custom"
            current_role = role_value if role_value in role_options else "custom"
            role = ui.selectbox(
                _layered_template_editor_text(
                    "layered_template.editor.layer_role",
                    zh="文本来源",
                    en="Text source",
                    translate=translate,
                ),
                role_options,
                index=role_options.index(current_role),
                key=f"{key_prefix}_role",
                format_func=lambda value: translate(
                    f"layered_template.editor.layer_role.{value}"
                ),
            )
            role = None if role == "custom" else role
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
