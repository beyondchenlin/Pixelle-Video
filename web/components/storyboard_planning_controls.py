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
Shared storyboard-planning controls and payload helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from html import escape
from inspect import Parameter, signature
from textwrap import dedent

import streamlit as st

from pixelle_video.config import config_manager
from pixelle_video.config.storyboard_preset_library import (
    BUILTIN_SHOT_PRESETS,
    BUILTIN_WORLD_PRESETS,
)
from pixelle_video.models.video_generation_contract import (
    StoryboardControlsContract,
    is_plan_frame_override_payload,
)
from pixelle_video.prompt_language import CHINESE_PROMPT_LANGUAGE
from web.components.storyboard_preview import render_storyboard_preview
from web.components.storyboard_workbench_stale import build_stale_panel_context
from web.i18n import tr
from web.utils.streamlit_helpers import keyed_widget_default_kwargs

STORYBOARD_SHOT_PRESET_AUTO_VALUE = "__auto__"


def build_storyboard_control_payload(
    *,
    world_preset_id: str | None = None,
    shot_preset_id: str | None = None,
    storyboard_prompt_language: str | None = None,
    consistency_strength: str | None = None,
    content_mode: str | None = None,
    role_strategy: str | None = None,
    role_locking_strength: str | None = None,
    shot_strategy: str | None = None,
    frame_overrides: list[dict] | None = None,
) -> dict:
    """Build a normalized storyboard-control payload from UI selections."""
    if shot_preset_id == STORYBOARD_SHOT_PRESET_AUTO_VALUE:
        shot_preset_id = None

    filtered_frame_overrides = None
    if frame_overrides:
        filtered_frame_overrides = [
            dict(override)
            for override in frame_overrides
            if isinstance(override, dict) and is_plan_frame_override_payload(override)
        ]

    storyboard_contract = StoryboardControlsContract.from_mapping(
        {
            "world_preset_id": world_preset_id,
            "shot_preset_id": shot_preset_id,
            "storyboard_prompt_language": storyboard_prompt_language,
            "consistency_strength": consistency_strength,
            "content_mode": content_mode,
            "role_strategy": role_strategy,
            "role_locking_strength": role_locking_strength,
            "shot_strategy": shot_strategy,
            "frame_overrides": filtered_frame_overrides,
        },
        default_prompt_language=CHINESE_PROMPT_LANGUAGE,
    )
    return storyboard_contract.to_planning_dict(
        include_prompt_language=storyboard_prompt_language is not None,
    )


def resolve_storyboard_toggle_default(
    session_state,
    storyboard_default_enabled: bool,
    preview_snapshot,
    template_type: str | None = None,
):
    """Resolve the advanced-storyboard checkbox default from session state and preview."""
    if template_type == "static":
        return False
    if session_state is not None and "storyboard_planning_enabled" in session_state:
        return bool(session_state.get("storyboard_planning_enabled"))
    if preview_snapshot is not None:
        return bool(preview_snapshot)
    return bool(storyboard_default_enabled)


def resolve_storyboard_preset_label(
    item,
    *,
    translate: Callable[..., str] = tr,
) -> str:
    """Resolve a localized storyboard preset label with a display-name fallback."""
    if isinstance(item, dict):
        translation_key = item.get("display_name_key") or item.get("translation_key")
        display_name = item.get("display_name")
        preset_id = item.get("preset_id")
    else:
        translation_key = getattr(item, "display_name_key", None) or getattr(item, "translation_key", None)
        display_name = getattr(item, "display_name", None)
        preset_id = getattr(item, "preset_id", None)

    if translation_key:
        localized_label = translate(translation_key)
        if localized_label != translation_key:
            return localized_label
    if display_name:
        return display_name
    return str(preset_id or "")


STORYBOARD_GUIDE_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("storyboard.world_preset", "storyboard.guide.field.world_preset"),
    ("storyboard.shot_preset", "storyboard.guide.field.shot_preset"),
    ("storyboard.consistency_strength", "storyboard.guide.field.consistency_strength"),
    ("storyboard.content_mode", "storyboard.guide.field.content_mode"),
    ("storyboard.role_strategy", "storyboard.guide.field.role_strategy"),
    ("storyboard.role_locking_strength", "storyboard.guide.field.role_locking_strength"),
    ("storyboard.shot_strategy", "storyboard.guide.field.shot_strategy"),
)

STORYBOARD_GUIDE_PRESET_PICKER_SPECS: tuple[dict[str, object], ...] = (
    {
        "title_key": "storyboard.guide.preset_picker.world.title",
        "body_key": "storyboard.guide.preset_picker.world.body",
        "item_key_prefix": "storyboard.guide.preset_picker.world.item",
        "presets": BUILTIN_WORLD_PRESETS,
        "accent_color": "#6d28d9",
        "background_color": "rgba(250, 245, 255, 0.96)",
        "border_color": "rgba(167, 139, 250, 0.22)",
    },
    {
        "title_key": "storyboard.guide.preset_picker.shot.title",
        "body_key": "storyboard.guide.preset_picker.shot.body",
        "item_key_prefix": "storyboard.guide.preset_picker.shot.item",
        "presets": BUILTIN_SHOT_PRESETS,
        "accent_color": "#0369a1",
        "background_color": "rgba(240, 249, 255, 0.96)",
        "border_color": "rgba(56, 189, 248, 0.22)",
    },
)

STORYBOARD_GUIDE_COMBO_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (
        "storyboard.guide.combo.explainer.title",
        "storyboard.guide.combo.explainer.body",
        "#b45309",
        "rgba(255, 247, 237, 0.96)",
    ),
    (
        "storyboard.guide.combo.theme_mapping.title",
        "storyboard.guide.combo.theme_mapping.body",
        "#0f766e",
        "rgba(240, 253, 250, 0.96)",
    ),
    (
        "storyboard.guide.combo.iteration.title",
        "storyboard.guide.combo.iteration.body",
        "#1d4ed8",
        "rgba(239, 246, 255, 0.96)",
    ),
)

STORYBOARD_GUIDE_NOTE_SPECS: tuple[dict[str, str], ...] = (
    {
        "title_key": "storyboard.guide.default_on_title",
        "body_key": "storyboard.guide.default_on_body",
        "accent_color": "#c2410c",
        "background_color": "linear-gradient(135deg, rgba(255, 247, 237, 0.98), rgba(255, 251, 235, 0.94))",
        "border_color": "rgba(245, 158, 11, 0.24)",
        "title_size": "12px",
        "body_color": "#44403c",
    },
    {
        "title_key": "storyboard.guide.when_to_turn_off.title",
        "body_key": "storyboard.guide.when_to_turn_off.body",
        "accent_color": "#7c2d12",
        "background_color": "rgba(248, 250, 252, 0.92)",
        "border_color": "rgba(148, 163, 184, 0.18)",
        "title_size": "12px",
        "body_color": "#44403c",
    },
)


def _preview_renderer_accepts_stale_context(preview_renderer: Callable[..., list[dict]]) -> bool:
    try:
        parameters = signature(preview_renderer).parameters
    except (TypeError, ValueError):
        return False
    stale_context_parameter = parameters.get("stale_context")
    return stale_context_parameter is not None or any(
        parameter.kind is Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _render_preview_snapshot(
    preview_snapshot,
    *,
    preview_renderer: Callable[[dict | None], list[dict]],
    stale_context: dict[str, str],
) -> list[dict]:
    if _preview_renderer_accepts_stale_context(preview_renderer):
        return preview_renderer(
            preview_snapshot,
            stale_context=stale_context,
        )
    return preview_renderer(preview_snapshot)


def _normalize_storyboard_guide_html(html: str) -> str:
    return "\n".join(
        line.lstrip() if line.strip() else ""
        for line in dedent(html).strip().splitlines()
    )


def _build_storyboard_guide_note_html(
    note_spec: dict[str, str],
    *,
    translate: Callable[..., str],
) -> str:
    return _normalize_storyboard_guide_html(
        f"""
    <div style="
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid {note_spec["border_color"]};
        background: {note_spec["background_color"]};
        margin-bottom: 10px;
    ">
        <div style="
            font-size: {note_spec["title_size"]};
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: {note_spec["accent_color"]};
            margin-bottom: 6px;
        ">{escape(translate(note_spec["title_key"]))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: {note_spec["body_color"]};
        ">{escape(translate(note_spec["body_key"]))}</div>
    </div>
    """
    )


def _build_storyboard_guide_combo_html(
    title_key: str,
    body_key: str,
    accent_color: str,
    background_color: str,
    *,
    translate: Callable[..., str],
) -> str:
    return _normalize_storyboard_guide_html(
        f"""
    <div style="
        padding: 12px 14px;
        border-radius: 14px;
        border: 1px solid rgba(148, 163, 184, 0.18);
        background: {background_color};
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
        margin-bottom: 10px;
    ">
        <div style="
            font-size: 13px;
            font-weight: 700;
            color: {accent_color};
            margin-bottom: 6px;
        ">{escape(translate(title_key))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: #334155;
        ">{escape(translate(body_key))}</div>
    </div>
    """
    )


def _build_storyboard_guide_preset_picker_html(
    section_spec: dict[str, object],
    *,
    translate: Callable[..., str],
) -> str:
    preset_items_html = "\n".join(
        _normalize_storyboard_guide_html(
            f"""
        <li style="margin-bottom: 10px;">
            <span style="font-weight: 700; color: #1f2937;">{escape(resolve_storyboard_preset_label(preset, translate=translate))}</span><br/>
            <span style="color: #475569;">{escape(translate(f"{section_spec['item_key_prefix']}.{preset.preset_id}"))}</span>
        </li>
        """
        )
        for preset in section_spec["presets"]
    )
    return _normalize_storyboard_guide_html(
        f"""
    <div style="
        margin-top: 12px;
        padding: 14px 16px;
        border-radius: 16px;
        border: 1px solid {section_spec["border_color"]};
        background: {section_spec["background_color"]};
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
    ">
        <div style="
            font-size: 13px;
            font-weight: 700;
            color: {section_spec["accent_color"]};
            margin-bottom: 6px;
        ">{escape(translate(section_spec["title_key"]))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: #334155;
            margin-bottom: 10px;
        ">{escape(translate(section_spec["body_key"]))}</div>
        <ul style="
            margin: 0;
            padding-left: 18px;
            font-size: 13px;
            line-height: 1.65;
        ">
            {preset_items_html}
        </ul>
    </div>
    """
    )


def render_storyboard_planning_guide(
    *,
    ui=st,
    translate: Callable[..., str] = tr,
) -> None:
    """Render a quick-start and deep-dive guide for advanced storyboard planning."""
    guide_notes_html = "".join(
        _build_storyboard_guide_note_html(note_spec, translate=translate)
        for note_spec in STORYBOARD_GUIDE_NOTE_SPECS
    )
    ui.markdown(guide_notes_html, unsafe_allow_html=True)

    combo_cards_html = "".join(
        _build_storyboard_guide_combo_html(
            title_key,
            body_key,
            accent_color,
            background_color,
            translate=translate,
        )
        for title_key, body_key, accent_color, background_color in STORYBOARD_GUIDE_COMBO_SPECS
    )
    field_items_html = "\n".join(
        _normalize_storyboard_guide_html(
            f"""
        <li style="margin-bottom: 10px;">
            <span style="font-weight: 700; color: #1f2937;">{escape(translate(label_key))}</span><br/>
            <span style="color: #475569;">{escape(translate(description_key))}</span>
        </li>
        """
        )
        for label_key, description_key in STORYBOARD_GUIDE_FIELD_SPECS
    )
    preset_picker_html = "".join(
        _build_storyboard_guide_preset_picker_html(section_spec, translate=translate)
        for section_spec in STORYBOARD_GUIDE_PRESET_PICKER_SPECS
    )

    with ui.expander(translate("storyboard.guide.title"), expanded=False):
        ui.markdown(
            _normalize_storyboard_guide_html(
                f"""
            <div style="margin-top: 12px;">
                <div style="
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: #92400e;
                    margin-bottom: 8px;
                ">{escape(translate("storyboard.guide.recommended_title"))}</div>
                {combo_cards_html}
            </div>
            <div style="
                margin-top: 14px;
                padding: 14px 16px;
                border-radius: 16px;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background: rgba(255, 255, 255, 0.96);
            ">
                <div style="
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: #475569;
                    margin-bottom: 10px;
                ">{escape(translate("storyboard.guide.fields_title"))}</div>
                <ul style="
                    margin: 0;
                    padding-left: 18px;
                    font-size: 13px;
                    line-height: 1.65;
                ">
                    {field_items_html}
                </ul>
            </div>
            <div style="margin-top: 12px;">
                <div style="
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: #475569;
                    margin-bottom: 8px;
                ">{escape(translate("storyboard.guide.preset_picker_title"))}</div>
                {preset_picker_html}
            </div>
            <div style="
                margin-top: 12px;
                padding: 12px 14px;
                border-radius: 14px;
                border: 1px solid rgba(59, 130, 246, 0.18);
                background: rgba(239, 246, 255, 0.92);
            ">
                <div style="
                    font-size: 13px;
                    font-weight: 700;
                    color: #1d4ed8;
                    margin-bottom: 6px;
                ">{escape(translate("storyboard.guide.override_title"))}</div>
                <div style="
                    font-size: 13px;
                    line-height: 1.65;
                    color: #334155;
                ">{escape(translate("storyboard.guide.override_body"))}</div>
            </div>
            """,
            ),
            unsafe_allow_html=True,
        )


def render_storyboard_advanced_controls(
    *,
    ui=st,
    translate: Callable[..., str] = tr,
    session_state=None,
    storyboard_default_enabled: bool = False,
    selected_template_type: str | None = None,
    preview_snapshot=None,
    world_library_loader: Callable[[], dict] | None = None,
    shot_library_loader: Callable[[], dict] | None = None,
    preview_renderer: Callable[[dict | None], list[dict]] = render_storyboard_preview,
) -> dict:
    """Render the advanced storyboard controls gated behind a single checkbox."""
    world_library_loader = world_library_loader or config_manager.get_storyboard_world_preset_library
    shot_library_loader = shot_library_loader or config_manager.get_storyboard_shot_preset_library

    storyboard_controls_disabled = selected_template_type == "static"
    storyboard_checkbox_key = (
        "storyboard_planning_enabled_static"
        if storyboard_controls_disabled
        else "storyboard_planning_enabled"
    )
    storyboard_enabled = ui.checkbox(
        translate("storyboard.advanced_enabled"),
        key=storyboard_checkbox_key,
        help=translate("storyboard.advanced_enabled_help"),
        disabled=storyboard_controls_disabled,
        **keyed_widget_default_kwargs(
            session_state,
            storyboard_checkbox_key,
            value=resolve_storyboard_toggle_default(
                session_state,
                storyboard_default_enabled=storyboard_default_enabled,
                preview_snapshot=preview_snapshot,
                template_type=selected_template_type,
            ),
        ),
    )

    if storyboard_controls_disabled:
        ui.caption(translate("template.type.static_hint"))
        return {}

    stale_context = build_stale_panel_context(session_state)
    if not storyboard_enabled:
        if preview_snapshot is not None:
            preview_context = nullcontext()
            if hasattr(ui, "container"):
                preview_context = ui.container()
            with preview_context:
                _render_preview_snapshot(
                    preview_snapshot,
                    preview_renderer=preview_renderer,
                    stale_context=stale_context,
                )
        else:
            ui.caption(translate("storyboard.preview.empty"))
        return {}

    render_storyboard_planning_guide(ui=ui, translate=translate)
    world_library = world_library_loader()
    shot_library = shot_library_loader()
    world_items = world_library.get("items", [])
    shot_items = shot_library.get("items", [])
    world_ids = [item["preset_id"] for item in world_items]
    shot_ids = [item["preset_id"] for item in shot_items]
    world_label_map = {
        item["preset_id"]: resolve_storyboard_preset_label(item, translate=translate)
        for item in world_items
    }
    shot_label_map = {
        item["preset_id"]: resolve_storyboard_preset_label(item, translate=translate)
        for item in shot_items
    }

    default_world_id = world_library.get("default_world_preset_id")
    if default_world_id not in world_ids and world_ids:
        default_world_id = world_ids[0]

    storyboard_world_preset_id = None
    storyboard_shot_preset_id = None
    storyboard_consistency_strength = None
    storyboard_content_mode = None
    storyboard_role_strategy = None
    storyboard_role_locking_strength = None
    storyboard_shot_strategy = None
    storyboard_frame_overrides: list[dict] = []

    storyboard_col1, storyboard_col2 = ui.columns(2)
    with storyboard_col1:
        if world_ids:
            storyboard_world_preset_id = ui.selectbox(
                translate("storyboard.world_preset"),
                options=world_ids,
                index=world_ids.index(default_world_id),
                format_func=lambda value: world_label_map.get(value, value),
                key="storyboard_world_preset_id",
            )
        storyboard_consistency_strength = ui.radio(
            translate("storyboard.consistency_strength"),
            options=["standard", "strong"],
            index=0,
            horizontal=True,
            format_func=lambda value: translate(f"storyboard.option.consistency.{value}"),
            key="storyboard_consistency_strength",
        )
        content_mode_selection = ui.selectbox(
            translate("storyboard.content_mode"),
            options=["auto", "concept_explainer", "theme_mapping"],
            index=0,
            format_func=lambda value: translate(f"storyboard.option.content_mode.{value}"),
            key="storyboard_content_mode",
        )
        storyboard_content_mode = None if content_mode_selection == "auto" else content_mode_selection

    with storyboard_col2:
        if shot_ids:
            storyboard_shot_preset_id = ui.selectbox(
                translate("storyboard.shot_preset"),
                options=[STORYBOARD_SHOT_PRESET_AUTO_VALUE, *shot_ids],
                index=0,
                format_func=lambda value: (
                    translate("storyboard.option.content_mode.auto")
                    if value == STORYBOARD_SHOT_PRESET_AUTO_VALUE
                    else shot_label_map.get(value, value)
                ),
                key="storyboard_shot_preset_id",
            )
            if storyboard_shot_preset_id == STORYBOARD_SHOT_PRESET_AUTO_VALUE:
                storyboard_shot_preset_id = None
        storyboard_role_strategy = ui.selectbox(
            translate("storyboard.role_strategy"),
            options=["auto", "stable_explainer_cast", "theme_mapping"],
            index=0,
            format_func=lambda value: translate(f"storyboard.option.role_strategy.{value}"),
            key="storyboard_role_strategy",
        )
        storyboard_role_locking_strength = ui.radio(
            translate("storyboard.role_locking_strength"),
            options=["standard", "strong"],
            index=0,
            horizontal=True,
            format_func=lambda value: translate(f"storyboard.option.consistency.{value}"),
            key="storyboard_role_locking_strength",
        )
        storyboard_shot_strategy = ui.radio(
            translate("storyboard.shot_strategy"),
            options=["adaptive", "strict"],
            index=0,
            horizontal=True,
            format_func=lambda value: translate(f"storyboard.option.shot_strategy.{value}"),
            key="storyboard_shot_strategy",
        )

    preview_context = nullcontext()
    if hasattr(ui, "container"):
        preview_context = ui.container()
    with preview_context:
        storyboard_frame_overrides = _render_preview_snapshot(
            preview_snapshot,
            preview_renderer=preview_renderer,
            stale_context=stale_context,
        )

    return build_storyboard_control_payload(
        world_preset_id=storyboard_world_preset_id,
        shot_preset_id=storyboard_shot_preset_id,
        consistency_strength=storyboard_consistency_strength,
        content_mode=storyboard_content_mode,
        role_strategy=storyboard_role_strategy,
        role_locking_strength=storyboard_role_locking_strength,
        shot_strategy=storyboard_shot_strategy,
        frame_overrides=storyboard_frame_overrides,
    )


__all__ = [
    "STORYBOARD_SHOT_PRESET_AUTO_VALUE",
    "build_storyboard_control_payload",
    "render_storyboard_advanced_controls",
    "render_storyboard_planning_guide",
    "resolve_storyboard_preset_label",
    "resolve_storyboard_toggle_default",
]
