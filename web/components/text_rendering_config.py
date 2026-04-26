# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Focused Streamlit controls for the shared text rendering contract.
"""

from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import streamlit as st

from pixelle_video.models.text_overlay import DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT
from pixelle_video.models.text_style import (
    DEFAULT_CAPTION_FONT_SIZE,
    DEFAULT_CAPTION_PRIMARY_COLOR,
    DEFAULT_CAPTION_STROKE_WIDTH,
    DEFAULT_OVERLAY_FONT_SIZE,
    DEFAULT_OVERLAY_PRIMARY_COLOR,
    DEFAULT_OVERLAY_STROKE_WIDTH,
)
from pixelle_video.render_backend import LEGACY_RENDER_BACKEND
from pixelle_video.services.font_discovery import (
    FontOption,
    discover_font_options,
    font_path_for_payload,
)
from pixelle_video.services.font_discovery import (
    discover_font_families as _discover_font_families,
)
from web.i18n import tr

CAPTION_STYLE_DEFAULTS: dict[str, Any] = {
    "font_family": "Noto Sans CJK SC",
    "font_size": DEFAULT_CAPTION_FONT_SIZE,
    "primary_color": DEFAULT_CAPTION_PRIMARY_COLOR,
    "stroke_color": "#000000",
    "stroke_width": DEFAULT_CAPTION_STROKE_WIDTH,
    "background_color": "#000000",
    "background_opacity": 0.0,
    "position": "bottom",
    "margin_y": 140,
    "max_chars_per_line": None,
}

OVERLAY_STYLE_DEFAULTS: dict[str, Any] = {
    **CAPTION_STYLE_DEFAULTS,
    "font_size": DEFAULT_OVERLAY_FONT_SIZE,
    "primary_color": DEFAULT_OVERLAY_PRIMARY_COLOR,
    "stroke_width": DEFAULT_OVERLAY_STROKE_WIDTH,
    "position": "center",
    "margin_y": 80,
}

TEXT_POSITION_OPTIONS = [
    "top",
    "center",
    "bottom",
    "lower_third",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
]

FONT_SEARCH_DIRS = (
    Path("fonts"),
    Path("font"),
    Path("resource/fonts"),
)
LEGACY_CAPTION_STYLE_DEFAULTS = {
    "font_size": 64,
    "primary_color": "#FFFFFF",
    "stroke_width": 2,
}
CAPTION_DEFAULTS_MIGRATION_KEY = "caption_style_template_defaults_migrated_v2"


def _resolve_ui(ui: Any | None) -> Any:
    return ui or st


def _resolve_translate(translate: Any | None):
    return translate or tr


def _session_value(ui: Any, key: str, default: Any) -> Any:
    session_state = getattr(ui, "session_state", {})
    if hasattr(session_state, "get"):
        return session_state.get(key, default)
    return default


def _set_session_value(ui: Any, key: str, value: Any) -> None:
    session_state = getattr(ui, "session_state", None)
    if session_state is None or not hasattr(session_state, "__setitem__"):
        return
    session_state[key] = value


def _migrate_legacy_caption_style_defaults(ui: Any) -> None:
    session_state = getattr(ui, "session_state", None)
    if session_state is None or not hasattr(session_state, "get"):
        return
    if session_state.get(CAPTION_DEFAULTS_MIGRATION_KEY):
        return

    has_legacy_caption_defaults = all(
        session_state.get(f"caption_style_{key}") == value
        for key, value in LEGACY_CAPTION_STYLE_DEFAULTS.items()
    )
    if has_legacy_caption_defaults:
        _set_session_value(ui, "caption_style_font_size", DEFAULT_CAPTION_FONT_SIZE)
        _set_session_value(ui, "caption_style_primary_color", DEFAULT_CAPTION_PRIMARY_COLOR)
        _set_session_value(ui, "caption_style_stroke_width", DEFAULT_CAPTION_STROKE_WIDTH)
    _set_session_value(ui, CAPTION_DEFAULTS_MIGRATION_KEY, True)


def discover_font_families(
    candidate_dirs: Iterable[str | Path] | None = None,
) -> list[str]:
    return _discover_font_families(candidate_dirs or FONT_SEARCH_DIRS)


def _font_select_labels(font_options: list[FontOption]) -> dict[str, FontOption]:
    labels: dict[str, FontOption] = {}
    for option in font_options:
        label = f"{option.family} ({option.path.name})"
        if label in labels:
            label = f"{option.family} ({font_path_for_payload(option.path)})"
        labels[label] = option
    return labels


def _font_option_for_current_value(
    current_value: str,
    labels_by_option: dict[str, FontOption],
) -> FontOption | None:
    if current_value in labels_by_option:
        return labels_by_option[current_value]
    for option in labels_by_option.values():
        if font_path_for_payload(option.path).casefold() == current_value.casefold():
            return option
        if option.family.casefold() == current_value.casefold():
            return option
    return None


@contextmanager
def _render_middle_column_collapsible_section(
    ui: Any,
    label: str,
    *,
    expanded: bool = False,
):
    with ui.expander(label, expanded=expanded):
        yield


@contextmanager
def _render_middle_column_detail_section(ui: Any, label: str):
    with ui.container(border=True):
        ui.markdown(f"**{label}**")
        yield


def _call_control(ui: Any, name: str, fallback: Any, *args, **kwargs) -> Any:
    control = getattr(ui, name, None)
    if control is None:
        return fallback
    return control(*args, **kwargs)


def _clean_text_style_payload(style: Mapping[str, Any] | None) -> dict | None:
    if not style:
        return None

    payload: dict[str, Any] = {}
    for key, value in style.items():
        if value is None:
            continue
        if key in {"font_family", "font_file"}:
            value = str(value).strip()
            if not value:
                continue
        if key in {"font_size", "stroke_width", "margin_y"}:
            value = int(value)
        if key == "max_chars_per_line":
            value = int(value)
            if value <= 0:
                continue
        if key == "background_opacity":
            value = float(value)
        payload[key] = value
    return payload or None


def build_text_rendering_payload(
    *,
    overlay_policy: dict | None,
    suppress_embedded_text: bool,
    positive_prompt: str,
    caption_style: dict | None = None,
    overlay_style: dict | None = None,
) -> dict:
    """Build the nested text_rendering payload used by API and pipelines."""
    cleaned_prompt = str(positive_prompt or "").strip()
    payload = {
        "overlay": overlay_policy or {"enabled": False},
        "image_text": {
            "suppress_embedded_text": bool(suppress_embedded_text),
            "positive_prompt": cleaned_prompt,
        },
    }

    caption_style_payload = _clean_text_style_payload(caption_style)
    if caption_style_payload is not None:
        payload["caption_style"] = caption_style_payload

    overlay_style_payload = _clean_text_style_payload(overlay_style)
    if overlay_style_payload is not None:
        payload["overlay_style"] = overlay_style_payload

    return payload


def _render_text_style_controls(
    prefix: str,
    defaults: Mapping[str, Any],
    *,
    ui: Any,
    translate,
) -> dict:
    if prefix == "caption_style":
        _migrate_legacy_caption_style_defaults(ui)

    configured_font_family = str(
        _session_value(ui, f"{prefix}_font_family", defaults["font_family"])
    ).strip() or str(defaults["font_family"])
    discovered_font_options = discover_font_options(FONT_SEARCH_DIRS)
    font_option = None
    if discovered_font_options:
        labels_by_option = _font_select_labels(discovered_font_options)
        font_option_labels = list(labels_by_option)
        configured_font_option = str(
            _session_value(ui, f"{prefix}_font_option", configured_font_family)
        ).strip()
        configured_font_file = str(
            _session_value(ui, f"{prefix}_font_file", "")
        ).strip()
        selected_font_option = (
            _font_option_for_current_value(configured_font_file, labels_by_option)
            or _font_option_for_current_value(configured_font_option, labels_by_option)
            or _font_option_for_current_value(configured_font_family, labels_by_option)
            or labels_by_option[font_option_labels[0]]
        )
        selected_font_label = next(
            label
            for label, option in labels_by_option.items()
            if option == selected_font_option
        )
        _set_session_value(ui, f"{prefix}_font_family", selected_font_option.family)
        _set_session_value(
            ui,
            f"{prefix}_font_file",
            font_path_for_payload(selected_font_option.path),
        )

        selected_label = _call_control(
            ui,
            "selectbox",
            selected_font_label,
            translate(f"{prefix}.font_family"),
            font_option_labels,
            index=font_option_labels.index(selected_font_label),
            key=f"{prefix}_font_option",
            help=translate(f"{prefix}.font_family_help"),
        )
        font_option = labels_by_option[str(selected_label)]
        font_family = font_option.family
        _set_session_value(ui, f"{prefix}_font_family", font_family)
        _set_session_value(
            ui,
            f"{prefix}_font_file",
            font_path_for_payload(font_option.path),
        )
    else:
        font_family = _call_control(
            ui,
            "text_input",
            configured_font_family,
            translate(f"{prefix}.font_family"),
            value=configured_font_family,
            key=f"{prefix}_font_family",
            help=translate(f"{prefix}.font_family_help"),
        )
    font_file = font_path_for_payload(font_option.path) if font_option else None
    font_size = _call_control(
        ui,
        "number_input",
        _session_value(ui, f"{prefix}_font_size", defaults["font_size"]),
        translate(f"{prefix}.font_size"),
        min_value=8,
        max_value=240,
        value=int(_session_value(ui, f"{prefix}_font_size", defaults["font_size"])),
        step=1,
        key=f"{prefix}_font_size",
    )
    primary_color = _call_control(
        ui,
        "color_picker",
        _session_value(ui, f"{prefix}_primary_color", defaults["primary_color"]),
        translate(f"{prefix}.primary_color"),
        value=_session_value(ui, f"{prefix}_primary_color", defaults["primary_color"]),
        key=f"{prefix}_primary_color",
    )
    stroke_color = _call_control(
        ui,
        "color_picker",
        _session_value(ui, f"{prefix}_stroke_color", defaults["stroke_color"]),
        translate(f"{prefix}.stroke_color"),
        value=_session_value(ui, f"{prefix}_stroke_color", defaults["stroke_color"]),
        key=f"{prefix}_stroke_color",
    )
    stroke_width = _call_control(
        ui,
        "number_input",
        _session_value(ui, f"{prefix}_stroke_width", defaults["stroke_width"]),
        translate(f"{prefix}.stroke_width"),
        min_value=0,
        max_value=16,
        value=int(_session_value(ui, f"{prefix}_stroke_width", defaults["stroke_width"])),
        step=1,
        key=f"{prefix}_stroke_width",
    )
    background_color = _call_control(
        ui,
        "color_picker",
        _session_value(ui, f"{prefix}_background_color", defaults["background_color"]),
        translate(f"{prefix}.background_color"),
        value=_session_value(ui, f"{prefix}_background_color", defaults["background_color"]),
        key=f"{prefix}_background_color",
    )
    background_opacity = _call_control(
        ui,
        "number_input",
        _session_value(ui, f"{prefix}_background_opacity", defaults["background_opacity"]),
        translate(f"{prefix}.background_opacity"),
        min_value=0.0,
        max_value=1.0,
        value=float(_session_value(ui, f"{prefix}_background_opacity", defaults["background_opacity"])),
        step=0.05,
        format="%.2f",
        key=f"{prefix}_background_opacity",
    )

    configured_position = _session_value(ui, f"{prefix}_position", defaults["position"])
    if configured_position not in TEXT_POSITION_OPTIONS:
        configured_position = defaults["position"]
    position = _call_control(
        ui,
        "selectbox",
        configured_position,
        translate(f"{prefix}.position"),
        TEXT_POSITION_OPTIONS,
        index=TEXT_POSITION_OPTIONS.index(configured_position),
        format_func=lambda value: translate(f"text_style.position.{value}"),
        key=f"{prefix}_position",
    )
    margin_y = _call_control(
        ui,
        "number_input",
        _session_value(ui, f"{prefix}_margin_y", defaults["margin_y"]),
        translate(f"{prefix}.margin_y"),
        min_value=0,
        max_value=1000,
        value=int(_session_value(ui, f"{prefix}_margin_y", defaults["margin_y"])),
        step=1,
        key=f"{prefix}_margin_y",
    )
    default_max_chars = defaults.get("max_chars_per_line") or 0
    max_chars_per_line = _call_control(
        ui,
        "number_input",
        _session_value(ui, f"{prefix}_max_chars_per_line", default_max_chars),
        translate(f"{prefix}.max_chars_per_line"),
        min_value=0,
        max_value=200,
        value=int(_session_value(ui, f"{prefix}_max_chars_per_line", default_max_chars)),
        step=1,
        key=f"{prefix}_max_chars_per_line",
    )

    return {
        "font_family": font_family,
        "font_file": font_file,
        "font_size": font_size,
        "primary_color": primary_color,
        "stroke_color": stroke_color,
        "stroke_width": stroke_width,
        "background_color": background_color,
        "background_opacity": background_opacity,
        "position": position,
        "margin_y": margin_y,
        "max_chars_per_line": max_chars_per_line,
    }


def render_text_rendering_controls(
    render_backend: str,
    *,
    ui: Any | None = None,
    translate=None,
) -> dict:
    """Render text rendering controls as independent caption, overlay, and image policy sections."""
    ui = _resolve_ui(ui)
    translate = _resolve_translate(translate)
    with _render_middle_column_collapsible_section(
        ui,
        translate("section.text_rendering"),
        expanded=False,
    ):
        with _render_middle_column_detail_section(ui, translate("caption_style.title")):
            caption_style = _render_text_style_controls(
                "caption_style",
                CAPTION_STYLE_DEFAULTS,
                ui=ui,
                translate=translate,
            )

        with _render_middle_column_detail_section(ui, translate("text_layer.title")):
            overlay_policy = render_text_layer_controls(
                render_backend,
                ui=ui,
                translate=translate,
            )
            overlay_style = None
            if overlay_policy and overlay_policy.get("enabled"):
                overlay_style = _render_text_style_controls(
                    "overlay_style",
                    OVERLAY_STYLE_DEFAULTS,
                    ui=ui,
                    translate=translate,
                )

        with _render_middle_column_detail_section(ui, translate("image_text.policy_title")):
            suppress_embedded_text = ui.checkbox(
                translate("image_text.suppress_embedded_text"),
                value=_session_value(ui, "image_text_suppress_embedded_text", False),
                help=translate("image_text.suppress_embedded_text_help"),
                key="image_text_suppress_embedded_text",
            )
            positive_prompt = ui.text_area(
                translate("image_text.positive_prompt"),
                value=_session_value(
                    ui,
                    "image_text_positive_prompt",
                    DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT,
                ),
                help=translate("image_text.positive_prompt_help"),
                key="image_text_positive_prompt",
                disabled=False,
            )

    return build_text_rendering_payload(
        caption_style=caption_style,
        overlay_policy=overlay_policy,
        overlay_style=overlay_style,
        suppress_embedded_text=suppress_embedded_text,
        positive_prompt=positive_prompt,
    )


def render_text_layer_controls(
    render_backend: str,
    *,
    ui: Any | None = None,
    translate=None,
) -> dict | None:
    """Render optional overlay/keyword/native-hint text layer controls."""
    ui = _resolve_ui(ui)
    translate = _resolve_translate(translate)
    enabled = ui.checkbox(
        translate("text_layer.enabled"),
        value=_session_value(ui, "text_layer_enabled", False),
        key="text_layer_enabled",
        help=translate("text_layer.enabled_help"),
    )
    if not enabled:
        return None

    mode_options = ["programmatic_only", "native_hint", "hybrid"]
    mode = ui.radio(
        translate("text_layer.mode"),
        mode_options,
        index=0,
        horizontal=True,
        format_func=lambda value: translate(f"text_layer.mode.{value}"),
        key="text_layer_mode",
    )

    default_target = "ass" if render_backend == LEGACY_RENDER_BACKEND else "hyperframes"
    target_options = ["hyperframes", "ass", "both"]
    target_preset = ui.radio(
        translate("text_layer.targets"),
        target_options,
        index=target_options.index(default_target),
        horizontal=True,
        format_func=lambda value: translate(f"text_layer.target.{value}"),
        key="text_layer_target_preset",
    )

    density_options = ["low", "medium", "high"]
    density = ui.selectbox(
        translate("text_layer.density"),
        density_options,
        index=1,
        format_func=lambda value: translate(f"text_layer.density.{value}"),
        key="text_layer_density",
    )

    max_items_per_frame = ui.number_input(
        translate("text_layer.max_items_per_frame"),
        min_value=1,
        max_value=5,
        value=2,
        step=1,
        key="text_layer_max_items_per_frame",
    )

    target_map = {
        "hyperframes": ["hyperframes"],
        "ass": ["ass"],
        "both": ["hyperframes", "ass"],
    }
    return {
        "enabled": True,
        "mode": mode,
        "renderer_targets": target_map[target_preset],
        "density": density,
        "max_items_per_frame": int(max_items_per_frame),
    }
