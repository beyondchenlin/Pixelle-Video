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
Style configuration components for web UI (middle column)
"""

import base64
import os
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

import streamlit as st
from loguru import logger
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

from pixelle_video.config import config_manager
from pixelle_video.config.prompt_prefix_library import (
    build_prompt_prefix_workflow_preview_record,
    filter_prompt_prefix_items,
    get_effective_image_prompt_prefix,
    get_prompt_prefix_category_label,
    get_prompt_prefix_workflow_preview_asset_path,
    resolve_prompt_prefix_gallery_cover,
)
from pixelle_video.config.storyboard_preset_library import (
    BUILTIN_SHOT_PRESETS,
    BUILTIN_WORLD_PRESETS,
)
from pixelle_video.models.video_generation_contract import is_plan_frame_override_payload
from pixelle_video.prompts.prompt_prefix_generation import (
    build_prompt_prefix_generation_prompt,
)
from pixelle_video.render_backend import SUPPORTED_RENDER_BACKENDS
from pixelle_video.tts_audio_strategy import SUPPORTED_TTS_AUDIO_STRATEGIES
from pixelle_video.tts_split_strategy import SUPPORTED_TTS_SPLIT_MODES
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_prefix_generation import (
    PromptPrefixGenerationResult,
    build_prompt_prefix_preview_batch,
    sanitize_prompt_prefix_candidates,
)
from pixelle_video.utils.text_splitting import (
    SUPPORTED_CAPTION_PUNCTUATION_MODES,
    SUPPORTED_TTS_SENTENCE_JOINER_MODES,
)
from web.components.selfhost_workflow_notice import (
    is_selfhost_workflow,
    render_selfhost_workflow_notice,
)
from web.components.storyboard_preview import render_storyboard_preview
from web.components.text_rendering_config import (
    DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT,  # noqa: F401
    build_text_rendering_payload,  # noqa: F401
    render_text_layer_controls,  # noqa: F401
    render_text_rendering_controls,
)
from web.components.tts_voice_profile_controls import render_tts_voice_profile_controls
from web.i18n import get_language, tr
from web.utils.async_helpers import run_async
from web.utils.preview_media import load_preview_media
from web.utils.prompt_prefix_ui import (
    clear_prompt_prefix_form_item_id,
    clone_prompt_prefix_preview_asset,
    create_prompt_prefix_item,
    delete_prompt_prefix_preview_asset,
    get_localized_prompt_prefix_category_options,
    get_prompt_prefix_form_item_id,
    persist_generated_prompt_prefix_workflow_preview,
    persist_uploaded_prompt_prefix_preview,
    sanitize_prompt_prefix_preview_selection,
    toggle_prompt_prefix_preview_selection,
)
from web.utils.render_backend_ui import get_render_backend_default
from web.utils.streamlit_helpers import safe_rerun
from web.utils.tts_audio_strategy_ui import get_tts_audio_strategy_default
from web.utils.tts_split_mode_ui import get_tts_split_mode_default
from web.utils.tts_ui import resolve_comfyui_tts_speed, resolve_configured_tts_mode
from web.utils.workflow_defaults import resolve_selectbox_default_index

STORYBOARD_SHOT_PRESET_AUTO_VALUE = "__auto__"


def _call_with_streamlit_fragment(func, *args, **kwargs):
    """Use fragment reruns when a real Streamlit script context is active."""
    fragment = getattr(st, "fragment", None)
    if fragment is None or get_script_run_ctx() is None:
        return func(*args, **kwargs)
    return fragment(func)(*args, **kwargs)


def render_generated_style_preview(preview_media_path: str, template_media_type: str):
    """Render generated preview media using a shared normalization path."""
    preview_media = load_preview_media(preview_media_path, template_media_type)

    if template_media_type == "video":
        st.video(preview_media.data, format=preview_media.format)
        return

    st.image(
        preview_media.data,
        caption=tr("style.preview_caption"),
        width="stretch",
    )


@contextmanager
def render_middle_column_collapsible_section(
    label: str,
    *,
    expanded: bool = False,
):
    """Render one collapsible config section using Streamlit's default appearance."""
    with st.expander(label, expanded=expanded):
        yield


@contextmanager
def render_middle_column_detail_section(label: str):
    """Render a bordered subsection inside a middle-column config section."""
    with st.container(border=True):
        st.markdown(f"**{label}**")
        yield


def resolve_media_generation_section_expanded(template_media_type: str) -> bool:
    """Collapse illustration generation by default while keeping video generation open."""
    return template_media_type == "video"


def _render_template_gallery_preview_placeholder(template_name: str):
    """Render a compact placeholder card when a template preview is unavailable."""
    escaped_name = escape(template_name)
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 150px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            border-radius: 8px;
            color: white;
            margin-bottom: 15px;
            padding: 10px;
        ">
            <div style="
                font-size: 14px;
                opacity: 0.95;
                overflow: hidden;
                text-overflow: ellipsis;
                display: -webkit-box;
                -webkit-line-clamp: 5;
                -webkit-box-orient: vertical;
                word-break: break-all;
            ">{escaped_name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_template_gallery_preview(preview_path: str, template_name: str):
    """Render one template preview image, falling back to a placeholder on preview failures."""
    try:
        st.image(preview_path, width="stretch")
    except Exception as exc:
        logger.warning(f"Template preview render failed for {preview_path}: {exc}")
        _render_template_gallery_preview_placeholder(template_name)


def build_storyboard_control_payload(
    *,
    world_preset_id: str | None = None,
    shot_preset_id: str | None = None,
    consistency_strength: str | None = None,
    content_mode: str | None = None,
    role_strategy: str | None = None,
    role_locking_strength: str | None = None,
    shot_strategy: str | None = None,
    frame_overrides: list[dict] | None = None,
) -> dict:
    """Build a normalized storyboard control payload from UI selections."""
    if shot_preset_id == STORYBOARD_SHOT_PRESET_AUTO_VALUE:
        shot_preset_id = None

    payload = {
        "world_preset_id": world_preset_id,
        "shot_preset_id": shot_preset_id,
        "consistency_strength": consistency_strength,
        "content_mode": content_mode,
        "role_strategy": role_strategy,
        "role_locking_strength": role_locking_strength,
        "shot_strategy": shot_strategy,
    }

    normalized_payload: dict = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        normalized_payload[key] = value

    if frame_overrides:
        plan_identity_overrides = [
            dict(override)
            for override in frame_overrides
            if isinstance(override, dict) and is_plan_frame_override_payload(override)
        ]
        if plan_identity_overrides:
            normalized_payload["frame_overrides"] = plan_identity_overrides
    return normalized_payload


def resolve_storyboard_toggle_default(
    session_state,
    storyboard_default_enabled: bool,
    preview_snapshot,
    template_type: str | None = None,
):
    """Resolve the storyboard checkbox default from session state, preview state, then caller default."""
    if template_type == "static":
        return False
    if session_state is not None and "storyboard_planning_enabled" in session_state:
        return bool(session_state.get("storyboard_planning_enabled"))
    if preview_snapshot is not None:
        return bool(preview_snapshot)
    return bool(storyboard_default_enabled)


def resolve_storyboard_preset_label(item) -> str:
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
        localized_label = tr(translation_key)
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


def _normalize_storyboard_guide_html(html: str) -> str:
    return "\n".join(
        line.lstrip() if line.strip() else ""
        for line in dedent(html).strip().splitlines()
    )


def _build_storyboard_guide_note_html(note_spec: dict[str, str]) -> str:
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
        ">{escape(tr(note_spec["title_key"]))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: {note_spec["body_color"]};
        ">{escape(tr(note_spec["body_key"]))}</div>
    </div>
    """
    )


def _build_storyboard_guide_combo_html(
    title_key: str,
    body_key: str,
    accent_color: str,
    background_color: str,
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
        ">{escape(tr(title_key))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: #334155;
        ">{escape(tr(body_key))}</div>
    </div>
    """
    )


def _build_storyboard_guide_preset_picker_html(section_spec: dict[str, object]) -> str:
    preset_items_html = "\n".join(
        _normalize_storyboard_guide_html(
            f"""
        <li style="margin-bottom: 10px;">
            <span style="font-weight: 700; color: #1f2937;">{escape(resolve_storyboard_preset_label(preset))}</span><br/>
            <span style="color: #475569;">{escape(tr(f"{section_spec['item_key_prefix']}.{preset.preset_id}"))}</span>
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
        ">{escape(tr(section_spec["title_key"]))}</div>
        <div style="
            font-size: 13px;
            line-height: 1.65;
            color: #334155;
            margin-bottom: 10px;
        ">{escape(tr(section_spec["body_key"]))}</div>
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


def render_storyboard_planning_guide():
    """Render a mixed quick-start + deep-dive guide for storyboard planning."""
    guide_notes_html = "".join(
        _build_storyboard_guide_note_html(note_spec) for note_spec in STORYBOARD_GUIDE_NOTE_SPECS
    )
    st.markdown(guide_notes_html, unsafe_allow_html=True)

    combo_cards_html = "".join(
        _build_storyboard_guide_combo_html(title_key, body_key, accent_color, background_color)
        for title_key, body_key, accent_color, background_color in STORYBOARD_GUIDE_COMBO_SPECS
    )
    field_items_html = "\n".join(
        _normalize_storyboard_guide_html(
            f"""
        <li style="margin-bottom: 10px;">
            <span style="font-weight: 700; color: #1f2937;">{escape(tr(label_key))}</span><br/>
            <span style="color: #475569;">{escape(tr(description_key))}</span>
        </li>
        """
        )
        for label_key, description_key in STORYBOARD_GUIDE_FIELD_SPECS
    )
    preset_picker_html = "".join(
        _build_storyboard_guide_preset_picker_html(section_spec)
        for section_spec in STORYBOARD_GUIDE_PRESET_PICKER_SPECS
    )

    with render_middle_column_collapsible_section(
        tr("storyboard.guide.title"),
        expanded=False,
    ):
        st.markdown(
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
                ">{escape(tr("storyboard.guide.recommended_title"))}</div>
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
                ">{escape(tr("storyboard.guide.fields_title"))}</div>
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
                ">{escape(tr("storyboard.guide.preset_picker_title"))}</div>
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
                ">{escape(tr("storyboard.guide.override_title"))}</div>
                <div style="
                    font-size: 13px;
                    line-height: 1.65;
                    color: #334155;
                ">{escape(tr("storyboard.guide.override_body"))}</div>
            </div>
            """,
            ),
            unsafe_allow_html=True,
        )


def _save_image_prompt_prefix_library(library: dict):
    """Persist image prompt prefix library changes immediately."""
    config_manager.set_image_prompt_prefix_library(library)
    config_manager.save()


def _upsert_image_prompt_prefix_item(item: dict, set_active: bool = False):
    """Insert or replace one image prompt prefix item."""
    library = config_manager.get_image_prompt_prefix_library()
    items = [existing for existing in library.get("items", []) if existing.get("id") != item["id"]]
    items.append(item)
    library["items"] = items
    if set_active:
        library["active_prefix_id"] = item["id"]
    _save_image_prompt_prefix_library(library)


def _delete_image_prompt_prefix_item(item_id: str):
    """Delete one non-builtin image prompt prefix item."""
    library = config_manager.get_image_prompt_prefix_library()
    deleted_item = next(
        (item for item in library.get("items", []) if item.get("id") == item_id),
        None,
    )
    library["items"] = [
        item for item in library.get("items", [])
        if item.get("id") != item_id
    ]
    if library.get("active_prefix_id") == item_id:
        library["active_prefix_id"] = None
    if deleted_item:
        delete_prompt_prefix_preview_asset(deleted_item.get("preview_asset_path"))
        for workflow_preview_asset in (deleted_item.get("workflow_preview_assets") or {}).values():
            delete_prompt_prefix_preview_asset(
                get_prompt_prefix_workflow_preview_asset_path(workflow_preview_asset)
            )
    _save_image_prompt_prefix_library(library)


def _set_active_image_prompt_prefix(item_id: str):
    """Set active image prompt prefix id and persist it."""
    config_manager.set_active_image_prompt_prefix(item_id)
    config_manager.save()


def _remove_generated_candidate_from_session(item_id: str):
    """Remove one generated candidate and its transient preview state after it is saved."""
    st.session_state["prompt_prefix_generated_candidates"] = [
        candidate
        for candidate in st.session_state.get("prompt_prefix_generated_candidates", [])
        if candidate.get("id") != item_id
    ]
    st.session_state["prompt_prefix_generated_preview_results"] = [
        result
        for result in st.session_state.get("prompt_prefix_generated_preview_results", [])
        if result.get("id") != item_id
    ]


def _prepare_prompt_prefix_item_for_library_save(
    item: dict,
    workflow_key: str,
    preview_media_path: str | None = None,
    reference_prompt: str | None = None,
) -> dict:
    """Attach a persisted workflow-scoped preview asset before saving an item to the library."""
    prepared_item = dict(item)
    workflow_preview_assets = dict(prepared_item.get("workflow_preview_assets") or {})
    existing_preview_record = workflow_preview_assets.get(workflow_key)
    persisted_preview_asset_path = persist_generated_prompt_prefix_workflow_preview(
        preview_media_path,
        item["id"],
        workflow_key,
        previous_preview_asset_path=get_prompt_prefix_workflow_preview_asset_path(existing_preview_record),
    )
    if persisted_preview_asset_path:
        workflow_preview_assets[workflow_key] = build_prompt_prefix_workflow_preview_record(
            asset_path=persisted_preview_asset_path,
            reference_prompt=reference_prompt,
            generated_at=datetime.now(timezone.utc).isoformat(),
            status="ready",
        )
        prepared_item["workflow_preview_assets"] = workflow_preview_assets
    return prepared_item


def _render_image_prompt_prefix_library_legacy(pixelle_video, workflow_key: str, media_width: int, media_height: int) -> str:
    """Render the image-only prompt prefix library UI and return effective prefix content."""
    language = get_language()
    image_config = config_manager.config.comfyui.image
    library = config_manager.get_image_prompt_prefix_library()
    library_items = library.get("items", [])
    library_items_by_id = {item["id"]: item for item in library_items}
    active_prefix_id = library.get("active_prefix_id")
    active_item = library_items_by_id.get(active_prefix_id)
    effective_prefix = get_effective_image_prompt_prefix(image_config)

    st.markdown(f"**{tr('style.prompt_prefix')}**")
    st.caption(tr("style.prefix_library.title"))
    st.markdown(
        """
        <style>
        div.stButton > button p {
            white-space: nowrap;
            word-break: keep-all;
            overflow-wrap: normal;
            writing-mode: horizontal-tb;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if active_item:
        st.caption(
            f"{tr('style.prefix_library.active')}: {active_item['name']} "
            f"· {get_prompt_prefix_category_label(active_item['style_category_id'], 'style', language)} "
            f"· {get_prompt_prefix_category_label(active_item['scene_category_id'], 'scene', language)}"
        )
        st.code(active_item["content"], language=None)
    elif effective_prefix:
        st.caption(tr("style.prefix_library.active_legacy"))
        st.code(effective_prefix, language=None)
    else:
        st.caption(tr("style.prefix_library.active_empty"))

    style_options, scene_options = get_localized_prompt_prefix_category_options(language=language)
    style_label_map = {option["id"]: option["label"] for option in style_options}
    scene_label_map = {option["id"]: option["label"] for option in scene_options}

    filter_style_col, filter_scene_col, filter_keyword_col = st.columns([1, 1, 1.3])
    with filter_style_col:
        selected_style = st.selectbox(
            tr("style.prefix_library.style_filter"),
            options=[""] + [option["id"] for option in style_options],
            format_func=lambda value: tr("style.prefix_library.all") if not value else style_label_map[value],
            key="prompt_prefix_style_filter",
        )
    with filter_scene_col:
        selected_scene = st.selectbox(
            tr("style.prefix_library.scene_filter"),
            options=[""] + [option["id"] for option in scene_options],
            format_func=lambda value: tr("style.prefix_library.all") if not value else scene_label_map[value],
            key="prompt_prefix_scene_filter",
        )
    with filter_keyword_col:
        keyword = st.text_input(
            tr("style.prefix_library.keyword"),
            placeholder=tr("style.prefix_library.keyword_placeholder"),
            key="prompt_prefix_keyword_filter",
        )

    filtered_items = filter_prompt_prefix_items(
        library_items,
        style_category_id=selected_style or None,
        scene_category_id=selected_scene or None,
        keyword=keyword,
    )

    generated_candidates = st.session_state.get("prompt_prefix_generated_candidates", [])
    selected_preview_ids = sanitize_prompt_prefix_preview_selection(
        st.session_state.get("prompt_prefix_preview_ids", []),
        {item["id"] for item in library_items} | {item["id"] for item in generated_candidates},
    )
    if selected_preview_ids != st.session_state.get("prompt_prefix_preview_ids", []):
        st.session_state["prompt_prefix_preview_ids"] = selected_preview_ids
        st.session_state.pop("prompt_prefix_preview_results", None)

    if not filtered_items:
        st.caption(tr("style.prefix_library.no_items"))

    for item in filtered_items:
        style_label = get_prompt_prefix_category_label(item["style_category_id"], "style", language)
        scene_label = get_prompt_prefix_category_label(item["scene_category_id"], "scene", language)
        with st.container(border=True):
            st.markdown(f"**{item['name']}**")
            st.caption(
                f"{style_label} / {scene_label} / {_get_prompt_prefix_source_label(item.get('source', 'manual'))}"
            )
            if item.get("note"):
                st.caption(item["note"])
            st.code(item["content"], language=None)

            set_active_col, preview_col, duplicate_col, delete_col = st.columns([1, 1, 1, 1])
            with set_active_col:
                if st.button(
                    tr("style.prefix_library.set_active"),
                    key=f"set_active_prefix_{item['id']}",
                    width="stretch",
                ):
                    _set_active_image_prompt_prefix(item["id"])
                    safe_rerun()
            with preview_col:
                in_preview = item["id"] in selected_preview_ids
                preview_label = (
                    tr("style.prefix_library.remove_from_preview")
                    if in_preview
                    else tr("style.prefix_library.add_to_preview")
                )
                if st.button(
                    preview_label,
                    key=f"toggle_preview_prefix_{item['id']}",
                    width="stretch",
                ):
                    if not in_preview and len(selected_preview_ids) >= 4:
                        st.warning(tr("style.prefix_library.preview_limit"))
                    else:
                        st.session_state["prompt_prefix_preview_ids"] = toggle_prompt_prefix_preview_selection(
                            selected_preview_ids,
                            item["id"],
                        )
                        st.session_state.pop("prompt_prefix_preview_results", None)
                        safe_rerun()
            with duplicate_col:
                if st.button(
                    tr("style.prefix_library.duplicate"),
                    key=f"duplicate_prefix_{item['id']}",
                    width="stretch",
                ):
                    duplicated_item = create_prompt_prefix_item(
                        name=f"{item['name']} Copy",
                        content=item["content"],
                        style_category_id=item["style_category_id"],
                        scene_category_id=item["scene_category_id"],
                        note=item.get("note", ""),
                        source="manual",
                    )
                    _upsert_image_prompt_prefix_item(duplicated_item)
                    safe_rerun()
            with delete_col:
                if item.get("is_builtin"):
                    st.button(
                        tr("style.prefix_library.delete_disabled"),
                        key=f"delete_prefix_disabled_{item['id']}",
                        disabled=True,
                        width="stretch",
                    )
                elif st.button(
                    tr("style.prefix_library.delete"),
                    key=f"delete_prefix_{item['id']}",
                    width="stretch",
                ):
                    _delete_image_prompt_prefix_item(item["id"])
                    st.session_state["prompt_prefix_preview_ids"] = [
                        selected_id
                        for selected_id in selected_preview_ids
                        if selected_id != item["id"]
                    ]
                    st.session_state.pop("prompt_prefix_preview_results", None)
                    safe_rerun()

    with st.expander(tr("style.prefix_library.manual_create"), expanded=False):
        manual_name = st.text_input(
            tr("style.prefix_library.manual_name"),
            key="manual_prompt_prefix_name",
        )
        manual_style_col, manual_scene_col = st.columns(2)
        with manual_style_col:
            manual_style_category = st.selectbox(
                tr("style.prefix_library.style_filter"),
                options=[option["id"] for option in style_options],
                format_func=lambda value: style_label_map[value],
                key="manual_prompt_prefix_style",
            )
        with manual_scene_col:
            manual_scene_category = st.selectbox(
                tr("style.prefix_library.scene_filter"),
                options=[option["id"] for option in scene_options],
                format_func=lambda value: scene_label_map[value],
                key="manual_prompt_prefix_scene",
            )
        manual_content = st.text_area(
            tr("style.prefix_library.manual_content"),
            key="manual_prompt_prefix_content",
            height=120,
        )
        manual_note = st.text_input(
            tr("style.prefix_library.manual_note"),
            key="manual_prompt_prefix_note",
        )
        if st.button(tr("style.prefix_library.save"), key="manual_prompt_prefix_save", width="stretch"):
            if not manual_name.strip() or not manual_content.strip():
                st.warning(tr("style.prefix_library.validation_required"))
            else:
                manual_item = create_prompt_prefix_item(
                    name=manual_name,
                    content=manual_content,
                    style_category_id=manual_style_category,
                    scene_category_id=manual_scene_category,
                    note=manual_note,
                    source="manual",
                )
                _upsert_image_prompt_prefix_item(manual_item)
                safe_rerun()

    with st.expander(tr("style.prefix_library.ai_generate"), expanded=False):
        ai_idea = st.text_area(
            tr("style.prefix_library.ai_idea"),
            key="prompt_prefix_ai_idea",
            height=100,
        )
        if st.button(tr("style.prefix_library.ai_generate_button"), key="prompt_prefix_ai_generate", width="stretch"):
            if not config_manager.config.is_llm_configured():
                st.warning(tr("style.prefix_library.ai_unavailable"))
            elif not ai_idea.strip():
                st.warning(tr("style.prefix_library.validation_required"))
            else:
                with st.spinner(tr("style.prefix_library.ai_generating")):
                    try:
                        generation_prompt = build_prompt_prefix_generation_prompt(
                            user_idea=ai_idea,
                            language=language,
                        )
                        result = run_async(
                            pixelle_video.llm(
                                generation_prompt,
                                response_type=PromptPrefixGenerationResult,
                                temperature=0.4,
                                max_tokens=1200,
                            )
                        )
                        generated_candidates = [
                            create_prompt_prefix_item(
                                name=candidate["name"],
                                content=candidate["content"],
                                style_category_id=candidate["style_category_id"],
                                scene_category_id=candidate["scene_category_id"],
                                note=candidate.get("note", ""),
                                source="llm",
                            )
                            for candidate in sanitize_prompt_prefix_candidates(result)
                        ]
                        st.session_state["prompt_prefix_generated_candidates"] = generated_candidates
                        st.session_state["prompt_prefix_preview_ids"] = sanitize_prompt_prefix_preview_selection(
                            st.session_state.get("prompt_prefix_preview_ids", []),
                            {item["id"] for item in library_items} | {item["id"] for item in generated_candidates},
                        )
                        selected_preview_ids = st.session_state["prompt_prefix_preview_ids"]
                        st.session_state.pop("prompt_prefix_preview_results", None)
                    except Exception as e:
                        st.error(tr("style.preview_failed", error=str(e)))
                        logger.exception(e)

        generated_candidates = st.session_state.get("prompt_prefix_generated_candidates", [])
        if generated_candidates:
            st.caption(tr("style.prefix_library.ai_results"))
            for candidate in generated_candidates:
                with st.container(border=True):
                    st.markdown(f"**{candidate['name']}**")
                    st.caption(
                        f"{get_prompt_prefix_category_label(candidate['style_category_id'], 'style', language)} "
                        f"· {get_prompt_prefix_category_label(candidate['scene_category_id'], 'scene', language)}"
                    )
                    if candidate.get("note"):
                        st.caption(candidate["note"])
                    st.code(candidate["content"], language=None)
                    add_col, preview_col, active_col = st.columns([1, 1, 1])
                    with add_col:
                        if st.button(
                            tr("style.prefix_library.add_to_library"),
                            key=f"add_generated_prefix_{candidate['id']}",
                            width="stretch",
                        ):
                            _upsert_image_prompt_prefix_item(candidate)
                            safe_rerun()
                    with preview_col:
                        generated_in_preview = candidate["id"] in selected_preview_ids
                        preview_label = (
                            tr("style.prefix_library.remove_from_preview")
                            if generated_in_preview
                            else tr("style.prefix_library.add_to_preview")
                        )
                        if st.button(
                            preview_label,
                            key=f"preview_generated_prefix_{candidate['id']}",
                            width="stretch",
                        ):
                            if not generated_in_preview and len(selected_preview_ids) >= 4:
                                st.warning(tr("style.prefix_library.preview_limit"))
                            else:
                                st.session_state["prompt_prefix_preview_ids"] = toggle_prompt_prefix_preview_selection(
                                    selected_preview_ids,
                                    candidate["id"],
                                )
                                st.session_state.pop("prompt_prefix_preview_results", None)
                                safe_rerun()
                    with active_col:
                        if st.button(
                            tr("style.prefix_library.set_active"),
                            key=f"set_generated_active_prefix_{candidate['id']}",
                            width="stretch",
                        ):
                            _upsert_image_prompt_prefix_item(candidate, set_active=True)
                            safe_rerun()

    preview_title = tr("style.preview_title")
    with st.expander(preview_title, expanded=False):
        test_prompt = st.text_input(
            tr("style.test_prompt"),
            value="a dog",
            help=tr("style.test_prompt_help"),
            key="style_test_prompt",
        )

        preview_items_by_id = {item["id"]: item for item in library_items}
        preview_items_by_id.update({item["id"]: item for item in generated_candidates})
        preview_items = build_prompt_prefix_preview_batch(
            items_by_id=preview_items_by_id,
            selected_ids=selected_preview_ids,
        ) if selected_preview_ids else []

        st.caption(tr("style.prefix_library.preview_selected_count", count=len(preview_items)))
        if preview_items:
            st.caption(", ".join(item["name"] for item in preview_items))
        else:
            st.caption(tr("style.prefix_library.no_preview_items"))

        if st.button(tr("style.preview"), key="preview_style", width="stretch"):
            if not preview_items:
                st.warning(tr("style.prefix_library.preview_selection_required"))
            else:
                with st.spinner(tr("style.previewing")):
                    try:
                        st.session_state["prompt_prefix_preview_results"] = _generate_prompt_prefix_preview_results(
                            pixelle_video=pixelle_video,
                            workflow_key=workflow_key,
                            media_width=int(media_width),
                            media_height=int(media_height),
                            test_prompt=test_prompt,
                            items=preview_items,
                        )
                    except Exception as e:
                        st.error(tr("style.preview_failed", error=str(e)))
                        logger.exception(e)

        preview_results = st.session_state.get("prompt_prefix_preview_results", [])
        if preview_results:
            preview_columns = st.columns(len(preview_results))
            for idx, preview_result in enumerate(preview_results):
                with preview_columns[idx]:
                    st.markdown(f"**{preview_result['name']}**")
                    render_generated_style_preview(preview_result["preview_media_path"], "image")
                    st.caption(preview_result["content"])
                    if st.button(
                        tr("style.prefix_library.set_active"),
                        key=f"set_preview_active_prefix_{preview_result['id']}",
                        width="stretch",
                    ):
                        if preview_result["id"] in preview_items_by_id:
                            candidate_item = preview_items_by_id[preview_result["id"]]
                            if preview_result["id"] not in library_items_by_id:
                                _upsert_image_prompt_prefix_item(candidate_item, set_active=True)
                            else:
                                _set_active_image_prompt_prefix(preview_result["id"])
                            safe_rerun()
                    st.info(f"**{tr('style.final_prompt_label')}**\n{preview_result['final_prompt']}")

    return effective_prefix


def _open_prompt_prefix_panel(mode: str, item_id: str | None = None):
    """Open one prompt-prefix side panel mode."""
    if mode != "manual":
        clear_prompt_prefix_form_item_id(st.session_state)
    st.session_state["prompt_prefix_panel_mode"] = mode
    st.session_state["prompt_prefix_panel_item_id"] = item_id


def _close_prompt_prefix_panel():
    """Close the prompt-prefix side panel."""
    clear_prompt_prefix_form_item_id(st.session_state)
    st.session_state.pop("prompt_prefix_panel_mode", None)
    st.session_state.pop("prompt_prefix_panel_item_id", None)
    st.session_state.pop("prompt_prefix_delete_confirm_id", None)


def _resolve_prompt_prefix_modal_image_src(asset_path: str) -> str:
    """Return a stable image src for modal rendering without relying on Streamlit's image DOM."""
    if not asset_path:
        return asset_path
    if asset_path.startswith(("http://", "https://", "data:")):
        return asset_path

    asset_file = Path(asset_path)
    if not asset_file.is_absolute():
        asset_file = Path(__file__).resolve().parents[2] / asset_path

    try:
        payload = asset_file.read_bytes()
    except OSError:
        return asset_path

    mime_type = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(asset_file.suffix.lower(), "application/octet-stream")
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _render_prompt_prefix_details_modal(
    panel_item: dict,
    workflow_key: str,
    workflow_display_map: dict[str, str],
    language: str,
    selected_preview_ids: list[str],
) -> None:
    """Render the prompt-prefix details experience in a modal dialog."""
    panel_cover_state = resolve_prompt_prefix_gallery_cover(panel_item, workflow_key)
    modal_image_src = _resolve_prompt_prefix_modal_image_src(panel_cover_state["asset_path"])
    style_label = get_prompt_prefix_category_label(panel_item["style_category_id"], "style", language)
    scene_label = get_prompt_prefix_category_label(panel_item["scene_category_id"], "scene", language)
    source_label = _get_prompt_prefix_source_label(panel_item.get("source", "manual"))
    detail_chip_labels = [style_label, scene_label, source_label]
    detail_summary_line = (panel_item.get("note") or "").strip() or None
    detail_meta_lines = [_get_prompt_prefix_cover_status_label(panel_cover_state)]
    workflow_display_label = _resolve_prompt_prefix_workflow_display_label(
        panel_cover_state.get("workflow_key"),
        workflow_display_map,
    )
    if workflow_display_label:
        detail_meta_lines.append(
            f"{tr('style.prefix_library.thumbnail_workflow_label')}: {workflow_display_label}"
        )
    if panel_cover_state.get("generated_at"):
        detail_meta_lines.append(
            f"{tr('style.prefix_library.thumbnail_generated_at_label')}: "
            f"{_format_prompt_prefix_generated_at(panel_cover_state['generated_at'])}"
        )
    if panel_cover_state.get("reference_prompt"):
        detail_meta_lines.append(
            f"{tr('style.prefix_library.thumbnail_reference_prompt_label')}: "
            f"{panel_cover_state['reference_prompt']}"
        )

    @st.dialog(tr("style.prefix_library.view_details"), width="medium", on_dismiss=_close_prompt_prefix_panel)
    def _show_prompt_prefix_details_dialog() -> None:
        st.markdown(
            dedent(
                """
            <style>
            .st-key-prompt_prefix_details_modal_body {
                --prompt-prefix-scale: 1;
                --prompt-prefix-space-scale: 1;
                --prompt-prefix-content-min-height: 10.2rem;
            }
            @media (max-height: 900px) {
                .st-key-prompt_prefix_details_modal_body {
                    --prompt-prefix-scale: 0.92;
                    --prompt-prefix-space-scale: 0.9;
                    --prompt-prefix-content-min-height: 9.4rem;
                }
            }
            @media (max-height: 760px) {
                .st-key-prompt_prefix_details_modal_body {
                    --prompt-prefix-scale: 0.84;
                    --prompt-prefix-space-scale: 0.82;
                    --prompt-prefix-content-min-height: 8.6rem;
                }
            }
            .st-key-prompt_prefix_details_modal_body .stButton > button {
                min-height: calc(2.35rem * var(--prompt-prefix-space-scale));
            }
            .st-key-prompt_prefix_details_modal_media {
                padding: calc(0.42rem * var(--prompt-prefix-space-scale));
                border-radius: 1.25rem;
                background: linear-gradient(180deg, rgba(247, 249, 252, 0.96), rgba(255, 255, 255, 0.92));
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
            }
            .prompt_prefix_details_modal_media_frame {
                aspect-ratio: 1 / 1;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .prompt_prefix_details_modal_image {
                width: 100%;
                height: 100%;
                border-radius: 1.05rem;
                object-fit: contain;
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
            }
            .st-key-prompt_prefix_details_modal_info {
                padding-top: 0.1rem;
            }
            .prompt_prefix_details_modal_title {
                margin: 0;
                font-size: calc(1.55rem * var(--prompt-prefix-scale));
                line-height: 1.16;
                font-weight: 700;
                color: rgba(17, 24, 39, 0.96);
            }
            .prompt_prefix_details_modal_chip_row {
                display: flex;
                flex-wrap: wrap;
                gap: calc(0.45rem * var(--prompt-prefix-space-scale));
                margin: calc(0.45rem * var(--prompt-prefix-space-scale)) 0 calc(0.8rem * var(--prompt-prefix-space-scale));
            }
            .prompt_prefix_details_modal_chip {
                padding: calc(0.28rem * var(--prompt-prefix-space-scale)) calc(0.62rem * var(--prompt-prefix-space-scale));
                border-radius: 999px;
                border: 1px solid rgba(37, 99, 235, 0.14);
                background: rgba(239, 246, 255, 0.76);
                color: rgba(30, 64, 175, 0.92);
                font-size: calc(0.76rem * var(--prompt-prefix-scale));
                line-height: 1.1;
                font-weight: 600;
            }
            .prompt_prefix_details_modal_detail_list {
                display: grid;
                gap: calc(0.42rem * var(--prompt-prefix-space-scale));
                margin-bottom: calc(0.85rem * var(--prompt-prefix-space-scale));
            }
            .prompt_prefix_details_modal_detail_item {
                font-size: calc(0.82rem * var(--prompt-prefix-scale));
                line-height: 1.4;
                color: rgba(49, 51, 63, 0.78);
            }
            .prompt_prefix_details_modal_summary {
                margin-bottom: calc(0.72rem * var(--prompt-prefix-space-scale));
                padding: calc(0.7rem * var(--prompt-prefix-space-scale)) calc(0.82rem * var(--prompt-prefix-space-scale));
                border-radius: 0.9rem;
                background: rgba(248, 250, 252, 0.9);
                color: rgba(31, 41, 55, 0.88);
                font-size: calc(0.84rem * var(--prompt-prefix-scale));
                line-height: 1.48;
            }
            .prompt_prefix_details_modal_content {
                min-height: var(--prompt-prefix-content-min-height);
                border: 1px solid rgba(49, 51, 63, 0.12);
                border-radius: 1rem;
                padding: calc(0.95rem * var(--prompt-prefix-space-scale)) calc(1rem * var(--prompt-prefix-space-scale));
                background: rgba(248, 250, 252, 0.82);
                white-space: pre-wrap;
                word-break: break-word;
                overflow-wrap: anywhere;
                font-size: calc(0.9rem * var(--prompt-prefix-scale));
                line-height: 1.52;
                color: rgba(17, 24, 39, 0.92);
            }
            </style>
            """
            ),
            unsafe_allow_html=True,
        )
        with st.container(key="prompt_prefix_details_modal_body"):
            detail_media_col, detail_content_col = st.columns([1.38, 0.82], gap="large")
            with detail_media_col:
                with st.container(key="prompt_prefix_details_modal_media", border=True):
                    st.markdown(
                        (
                            '<div class="prompt_prefix_details_modal_media_frame">'
                            f'<img class="prompt_prefix_details_modal_image" src="{escape(modal_image_src, quote=True)}" '
                            f'alt="{escape(panel_item["name"], quote=True)}" />'
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
            with detail_content_col:
                with st.container(key="prompt_prefix_details_modal_info"):
                    st.markdown(
                        f'<div class="prompt_prefix_details_modal_title">{escape(panel_item["name"])}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        (
                            '<div class="prompt_prefix_details_modal_chip_row">'
                            + "".join(
                                f'<span class="prompt_prefix_details_modal_chip">{escape(label)}</span>'
                                for label in detail_chip_labels
                            )
                            + "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
                    if detail_summary_line:
                        st.markdown(
                            f'<div class="prompt_prefix_details_modal_summary">{escape(detail_summary_line)}</div>',
                            unsafe_allow_html=True,
                        )
                    if detail_meta_lines:
                        st.markdown(
                            (
                                '<div class="prompt_prefix_details_modal_detail_list">'
                                + "".join(
                                    f'<div class="prompt_prefix_details_modal_detail_item">{escape(line)}</div>'
                                    for line in detail_meta_lines
                                )
                                + "</div>"
                            ),
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        (
                            '<div class="prompt_prefix_details_modal_content">'
                            f"{escape(panel_item['content'])}"
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )

            detail_action_col, detail_compare_col = st.columns(2, gap="small")
            with detail_action_col:
                if st.button(
                    tr("style.prefix_library.set_active"),
                    key=f"detail_set_active_{panel_item['id']}",
                    width="stretch",
                ):
                    _set_active_image_prompt_prefix(panel_item["id"])
                    safe_rerun()
            with detail_compare_col:
                detail_in_preview = panel_item["id"] in selected_preview_ids
                preview_label = (
                    tr("style.prefix_library.remove_from_preview")
                    if detail_in_preview
                    else tr("style.prefix_library.add_to_preview")
                )
                if st.button(
                    preview_label,
                    key=f"detail_toggle_preview_{panel_item['id']}",
                    width="stretch",
                ):
                    if not detail_in_preview and len(selected_preview_ids) >= 4:
                        st.warning(tr("style.prefix_library.preview_limit"))
                    else:
                        st.session_state["prompt_prefix_preview_ids"] = toggle_prompt_prefix_preview_selection(
                            selected_preview_ids,
                            panel_item["id"],
                        )
                        st.session_state.pop("prompt_prefix_preview_results", None)
                        safe_rerun()

            duplicate_col, custom_action_col = st.columns(2, gap="small")
            with duplicate_col:
                if st.button(
                    tr("style.prefix_library.duplicate"),
                    key=f"detail_duplicate_{panel_item['id']}",
                    width="stretch",
                ):
                    duplicated_item_id = f"manual-{uuid4().hex[:12]}"
                    duplicated_item = create_prompt_prefix_item(
                        item_id=duplicated_item_id,
                        name=f"{panel_item['name']} Copy",
                        content=panel_item["content"],
                        style_category_id=panel_item["style_category_id"],
                        scene_category_id=panel_item["scene_category_id"],
                        note=panel_item.get("note", ""),
                        source="manual",
                        preview_asset_path=clone_prompt_prefix_preview_asset(
                            panel_item.get("preview_asset_path"),
                            duplicated_item_id,
                        ),
                    )
                    _upsert_image_prompt_prefix_item(duplicated_item)
                    safe_rerun()
            with custom_action_col:
                if panel_item.get("is_builtin"):
                    st.button(
                        tr("style.prefix_library.delete_disabled"),
                        key=f"detail_builtin_badge_{panel_item['id']}",
                        disabled=True,
                        width="stretch",
                    )
                elif st.button(
                    tr("style.prefix_library.edit"),
                    key=f"detail_edit_{panel_item['id']}",
                    width="stretch",
                ):
                    _open_prompt_prefix_panel("edit", panel_item["id"])
                    safe_rerun()

            if not panel_item.get("is_builtin"):
                if st.session_state.get("prompt_prefix_delete_confirm_id") == panel_item["id"]:
                    st.warning(tr("style.prefix_library.delete_confirm"))
                    confirm_col, cancel_col = st.columns(2, gap="small")
                    with confirm_col:
                        if st.button(
                            tr("style.prefix_library.delete"),
                            key=f"detail_delete_confirm_{panel_item['id']}",
                            width="stretch",
                        ):
                            _delete_image_prompt_prefix_item(panel_item["id"])
                            st.session_state["prompt_prefix_preview_ids"] = [
                                selected_id for selected_id in selected_preview_ids if selected_id != panel_item["id"]
                            ]
                            st.session_state.pop("prompt_prefix_preview_results", None)
                            st.session_state.pop("prompt_prefix_generated_preview_results", None)
                            _close_prompt_prefix_panel()
                            safe_rerun()
                    with cancel_col:
                        if st.button(
                            tr("style.prefix_library.cancel"),
                            key=f"detail_delete_cancel_{panel_item['id']}",
                            width="stretch",
                        ):
                            st.session_state.pop("prompt_prefix_delete_confirm_id", None)
                            safe_rerun()
                elif st.button(
                    tr("style.prefix_library.delete"),
                    key=f"detail_delete_{panel_item['id']}",
                    width="stretch",
                ):
                    st.session_state["prompt_prefix_delete_confirm_id"] = panel_item["id"]
                    safe_rerun()

    _show_prompt_prefix_details_dialog()


def _render_prompt_prefix_editor_panel(
    panel_mode: str,
    panel_item: dict | None,
    workflow_key: str,
    language: str,
    live_preview_map: dict[str, str],
    style_options: list[dict],
    scene_options: list[dict],
    style_label_map: dict[str, str],
    scene_label_map: dict[str, str],
) -> None:
    """Render the manual-create and edit flows below the gallery."""
    editing_item = panel_item if panel_mode == "edit" else None
    form_item_id = get_prompt_prefix_form_item_id(
        st.session_state,
        editing_item["id"] if editing_item else None,
    )
    form_suffix = f"{panel_mode}_{form_item_id}"
    current_cover = live_preview_map.get(form_item_id)
    if editing_item:
        current_cover = current_cover or resolve_prompt_prefix_gallery_cover(editing_item, workflow_key)["asset_path"]
    if current_cover:
        st.image(current_cover, width="stretch")
        st.caption(tr("style.prefix_library.preview_asset_current"))

    form_name = st.text_input(
        tr("style.prefix_library.manual_name"),
        value=editing_item["name"] if editing_item else "",
        key=f"prompt_prefix_form_name_{form_suffix}",
    )
    form_style_col, form_scene_col = st.columns(2, gap="small")
    with form_style_col:
        form_style_category = st.selectbox(
            tr("style.prefix_library.style_filter"),
            options=[option["id"] for option in style_options],
            index=[option["id"] for option in style_options].index(
                editing_item["style_category_id"] if editing_item else style_options[0]["id"]
            ),
            format_func=lambda value: style_label_map[value],
            key=f"prompt_prefix_form_style_{form_suffix}",
        )
    with form_scene_col:
        form_scene_category = st.selectbox(
            tr("style.prefix_library.scene_filter"),
            options=[option["id"] for option in scene_options],
            index=[option["id"] for option in scene_options].index(
                editing_item["scene_category_id"] if editing_item else scene_options[0]["id"]
            ),
            format_func=lambda value: scene_label_map[value],
            key=f"prompt_prefix_form_scene_{form_suffix}",
        )
    form_content = st.text_area(
        tr("style.prefix_library.manual_content"),
        value=editing_item["content"] if editing_item else "",
        key=f"prompt_prefix_form_content_{form_suffix}",
        height=160,
    )
    form_note = st.text_input(
        tr("style.prefix_library.manual_note"),
        value=editing_item.get("note", "") if editing_item else "",
        key=f"prompt_prefix_form_note_{form_suffix}",
    )
    uploaded_preview = st.file_uploader(
        tr("style.prefix_library.preview_asset_upload"),
        type=["png", "jpg", "jpeg", "webp", "svg"],
        key=f"prompt_prefix_form_upload_{form_suffix}",
    )
    set_active_on_save = st.checkbox(
        tr("style.prefix_library.save_and_set_active"),
        value=False,
        key=f"prompt_prefix_form_set_active_{form_suffix}",
    )
    if st.button(
        tr("style.prefix_library.save"),
        key=f"prompt_prefix_form_save_{form_suffix}",
        width="stretch",
    ):
        if not form_name.strip() or not form_content.strip():
            st.warning(tr("style.prefix_library.validation_required"))
        else:
            preview_asset_path = editing_item.get("preview_asset_path") if editing_item else None
            uploaded_preview_path = persist_uploaded_prompt_prefix_preview(
                uploaded_preview,
                form_item_id,
                previous_preview_asset_path=preview_asset_path,
            )
            if uploaded_preview_path:
                preview_asset_path = uploaded_preview_path

            saved_item = create_prompt_prefix_item(
                item_id=form_item_id,
                name=form_name,
                content=form_content,
                style_category_id=form_style_category,
                scene_category_id=form_scene_category,
                note=form_note,
                source=editing_item.get("source", "manual") if editing_item else "manual",
                preview_asset_path=preview_asset_path,
                workflow_preview_assets=editing_item.get("workflow_preview_assets", {}) if editing_item else {},
            )
            _upsert_image_prompt_prefix_item(saved_item, set_active=set_active_on_save)
            _open_prompt_prefix_panel("details", saved_item["id"])
            safe_rerun()


def _render_prompt_prefix_ai_panel(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    language: str,
    library_items: list[dict],
    selected_preview_ids: list[str],
) -> None:
    """Render the AI-generated prompt-prefix workflow below the gallery."""
    generated_candidates = st.session_state.get("prompt_prefix_generated_candidates", [])
    ai_idea = st.text_area(
        tr("style.prefix_library.ai_idea"),
        value=st.session_state.get("prompt_prefix_ai_idea", ""),
        key="prompt_prefix_ai_idea",
        height=100,
    )
    candidate_preview_prompt = st.text_input(
        tr("style.prefix_library.ai_preview_prompt"),
        value=st.session_state.get("style_test_prompt", "a dog"),
        key="prompt_prefix_ai_preview_prompt",
    )
    if st.button(
        tr("style.prefix_library.ai_generate_button"),
        key="prompt_prefix_ai_generate",
        width="stretch",
    ):
        if not config_manager.config.is_llm_configured():
            st.warning(tr("style.prefix_library.ai_unavailable"))
        elif not ai_idea.strip():
            st.warning(tr("style.prefix_library.validation_required"))
        else:
            with st.spinner(tr("style.prefix_library.ai_generating")):
                try:
                    generation_prompt = build_prompt_prefix_generation_prompt(
                        user_idea=ai_idea,
                        language=language,
                    )
                    result = run_async(
                        pixelle_video.llm(
                            generation_prompt,
                            response_type=PromptPrefixGenerationResult,
                            temperature=0.4,
                            max_tokens=1200,
                        )
                    )
                    generated_candidates = [
                        create_prompt_prefix_item(
                            name=candidate["name"],
                            content=candidate["content"],
                            style_category_id=candidate["style_category_id"],
                            scene_category_id=candidate["scene_category_id"],
                            note=candidate.get("note", ""),
                            source="llm",
                        )
                        for candidate in sanitize_prompt_prefix_candidates(result)
                    ]
                    st.session_state["prompt_prefix_generated_candidates"] = generated_candidates
                    st.session_state["prompt_prefix_generated_preview_results"] = []
                    st.session_state["prompt_prefix_preview_ids"] = sanitize_prompt_prefix_preview_selection(
                        st.session_state.get("prompt_prefix_preview_ids", []),
                        {item["id"] for item in library_items} | {item["id"] for item in generated_candidates},
                    )
                    safe_rerun()
                except Exception as e:
                    st.error(tr("style.preview_failed", error=str(e)))
                    logger.exception(e)
    if st.button(
        tr("style.prefix_library.generate_candidate_previews"),
        key="prompt_prefix_ai_generate_previews",
        width="stretch",
    ):
        if not generated_candidates:
            st.warning(tr("style.prefix_library.ai_preview_none"))
        else:
            with st.spinner(tr("style.previewing")):
                try:
                    st.session_state["prompt_prefix_generated_preview_results"] = _generate_prompt_prefix_preview_results(
                        pixelle_video=pixelle_video,
                        workflow_key=workflow_key,
                        media_width=media_width,
                        media_height=media_height,
                        test_prompt=candidate_preview_prompt,
                        items=generated_candidates,
                    )
                    safe_rerun()
                except Exception as e:
                    st.error(tr("style.preview_failed", error=str(e)))
                    logger.exception(e)

    generated_candidates = st.session_state.get("prompt_prefix_generated_candidates", [])
    candidate_preview_map = {
        result["id"]: result["preview_media_path"]
        for result in st.session_state.get("prompt_prefix_generated_preview_results", [])
        if result.get("preview_media_path")
    }
    if generated_candidates:
        st.caption(tr("style.prefix_library.ai_results"))
        for candidate in generated_candidates:
            candidate_cover = candidate_preview_map.get(candidate["id"]) or resolve_prompt_prefix_gallery_cover(
                candidate,
                workflow_key,
            )["asset_path"]
            with st.container(border=True):
                st.image(candidate_cover, width="stretch")
                st.markdown(f"**{candidate['name']}**")
                st.caption(
                    f"{get_prompt_prefix_category_label(candidate['style_category_id'], 'style', language)} / "
                    f"{get_prompt_prefix_category_label(candidate['scene_category_id'], 'scene', language)}"
                )
                if candidate.get("note"):
                    st.caption(candidate["note"])
                if candidate["id"] not in candidate_preview_map:
                    st.caption(tr("style.prefix_library.candidate_preview_pending"))
                st.code(candidate["content"], language=None)

                add_col, active_col = st.columns(2, gap="small")
                with add_col:
                    if st.button(
                        tr("style.prefix_library.add_to_library"),
                        key=f"add_generated_prefix_{candidate['id']}",
                        width="stretch",
                    ):
                        _save_prompt_prefix_item_with_workflow_preview(
                            candidate,
                            workflow_key=workflow_key,
                            preview_media_path=candidate_preview_map.get(candidate["id"]),
                        )
                        _remove_generated_candidate_from_session(candidate["id"])
                        safe_rerun()
                with active_col:
                    if st.button(
                        tr("style.prefix_library.set_active"),
                        key=f"set_generated_active_prefix_{candidate['id']}",
                        width="stretch",
                    ):
                        _save_prompt_prefix_item_with_workflow_preview(
                            candidate,
                            workflow_key=workflow_key,
                            preview_media_path=candidate_preview_map.get(candidate["id"]),
                            set_active=True,
                        )
                        _remove_generated_candidate_from_session(candidate["id"])
                        safe_rerun()

                generated_in_preview = candidate["id"] in selected_preview_ids
                preview_label = (
                    tr("style.prefix_library.remove_from_preview")
                    if generated_in_preview
                    else tr("style.prefix_library.add_to_preview")
                )
                if st.button(
                    preview_label,
                    key=f"preview_generated_prefix_{candidate['id']}",
                    width="stretch",
                ):
                    if not generated_in_preview and len(selected_preview_ids) >= 4:
                        st.warning(tr("style.prefix_library.preview_limit"))
                    else:
                        st.session_state["prompt_prefix_preview_ids"] = toggle_prompt_prefix_preview_selection(
                            selected_preview_ids,
                            candidate["id"],
                        )
                        st.session_state.pop("prompt_prefix_preview_results", None)
                        safe_rerun()
    else:
        st.caption(tr("style.prefix_library.ai_preview_none"))


def _build_prompt_prefix_live_preview_map() -> dict[str, str]:
    """Collect session-scoped preview overrides for gallery cards."""
    preview_map: dict[str, str] = {}

    for result in st.session_state.get("prompt_prefix_generated_preview_results", []):
        preview_path = result.get("preview_media_path")
        if preview_path:
            preview_map[result["id"]] = preview_path

    return preview_map


def _generate_prompt_prefix_preview_results(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    test_prompt: str,
    items: list[dict],
) -> list[dict]:
    """Generate prompt-prefix previews sequentially for the current workflow."""
    preview_results: list[dict] = []
    for item in items:
        preview_result = _generate_single_style_preview_result(
            pixelle_video=pixelle_video,
            workflow_key=workflow_key,
            media_width=media_width,
            media_height=media_height,
            test_prompt=test_prompt,
            prompt_prefix=item["content"],
            media_type="image",
        )
        if preview_result["preview_media_path"]:
            preview_results.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "content": item["content"],
                    "final_prompt": preview_result["final_prompt"],
                    "preview_media_path": preview_result["preview_media_path"],
                }
            )

    return preview_results


def _generate_single_style_preview_result(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    test_prompt: str,
    prompt_prefix: str,
    media_type: str,
) -> dict[str, str | None]:
    media_config = pixelle_video.config.get("comfyui", {}).get(media_type, {})
    styled_batch = run_async(
        generate_styled_image_prompt_batch(
            llm_service=pixelle_video.llm,
            narrations=[test_prompt],
            image_config=media_config,
            prompt_prefix=prompt_prefix,
            workflow=workflow_key,
            media_service=pixelle_video.media,
            media_type=media_type,
        )
    )
    final_prompt = styled_batch.prompts[0]
    media_result = run_async(
        pixelle_video.media(
            prompt=final_prompt,
            negative_prompt=styled_batch.negative_prompt,
            workflow=workflow_key,
            media_type=media_type,
            width=int(media_width),
            height=int(media_height),
        )
    )
    return {
        "final_prompt": final_prompt,
        "preview_media_path": media_result.url,
    }


def _save_prompt_prefix_item_with_workflow_preview(
    item: dict,
    workflow_key: str,
    preview_media_path: str | None = None,
    reference_prompt: str | None = None,
    set_active: bool = False,
):
    """Persist one prompt-prefix item, attaching a workflow-scoped preview when available."""
    _upsert_image_prompt_prefix_item(
        _prepare_prompt_prefix_item_for_library_save(
            item,
            workflow_key=workflow_key,
            preview_media_path=preview_media_path,
            reference_prompt=reference_prompt,
        ),
        set_active=set_active,
    )


def _get_prompt_prefix_cover_status_label(cover_state: dict) -> str:
    """Return a short localized caption for the current gallery cover state."""
    if cover_state.get("source") == "workflow":
        return tr(
            "style.prefix_library.thumbnail_status_stale"
            if cover_state.get("is_stale")
            else "style.prefix_library.thumbnail_status_current"
        )
    return tr("style.prefix_library.thumbnail_status_reference")


def _format_prompt_prefix_generated_at(iso_string: str | None) -> str | None:
    """Format workflow thumbnail timestamps for compact UI display."""
    normalized = (iso_string or "").strip()
    if not normalized:
        return None

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return normalized
    return parsed.strftime("%m-%d %H:%M")


def _resolve_prompt_prefix_workflow_display_label(
    workflow_key: str | None,
    workflow_display_map: dict[str, str],
) -> str | None:
    """Resolve a human-readable workflow label for prompt-prefix details."""
    normalized = (workflow_key or "").strip()
    if not normalized:
        return None
    return workflow_display_map.get(normalized) or normalized


def _get_prompt_prefix_source_label(source: str | None) -> str:
    """Return a localized source label for prompt-prefix cards and details."""
    normalized = (source or "").strip().lower()
    key = {
        "builtin": "style.prefix_library.source_builtin",
        "manual": "style.prefix_library.source_manual",
        "llm": "style.prefix_library.source_llm",
    }.get(normalized)
    if key:
        return tr(key)
    return normalized or "manual"


def _render_prompt_prefix_library_action_toolbar(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    filtered_items: list[dict],
    thumbnail_reference_prompt: str,
    on_open_panel=None,
) -> None:
    with st.container():
        if st.button(
            tr("style.prefix_library.generate_thumbnails"),
            key="prompt_prefix_generate_thumbnails",
            width="stretch",
        ):
            if not filtered_items:
                st.warning(tr("style.prefix_library.thumbnail_empty"))
            elif not workflow_key.strip():
                st.warning(tr("style.prefix_library.thumbnail_workflow_required"))
            elif not thumbnail_reference_prompt.strip():
                st.warning(tr("style.prefix_library.thumbnail_prompt_required"))
            else:
                progress_placeholder = st.empty()
                generated_count = 0
                failed_count = 0
                with st.spinner(tr("style.prefix_library.thumbnail_generating")):
                    for idx, item in enumerate(filtered_items, start=1):
                        progress_placeholder.caption(
                            tr(
                                "style.prefix_library.thumbnail_progress",
                                completed=idx - 1,
                                total=len(filtered_items),
                                name=item["name"],
                            )
                        )
                        preview_results = _generate_prompt_prefix_preview_results(
                            pixelle_video=pixelle_video,
                            workflow_key=workflow_key,
                            media_width=media_width,
                            media_height=media_height,
                            test_prompt=thumbnail_reference_prompt,
                            items=[item],
                        )
                        if not preview_results:
                            failed_count += 1
                            continue
                        _save_prompt_prefix_item_with_workflow_preview(
                            item,
                            workflow_key=workflow_key,
                            preview_media_path=preview_results[0].get("preview_media_path"),
                            reference_prompt=thumbnail_reference_prompt,
                        )
                        generated_count += 1
                    summary = tr(
                        "style.prefix_library.thumbnail_summary",
                        generated=generated_count,
                        failed=failed_count,
                        total=len(filtered_items),
                    )
                    progress_placeholder.caption(summary)
                    st.session_state["prompt_prefix_thumbnail_status"] = summary
                safe_rerun()
    with st.container():
        if st.button(tr("style.prefix_library.toolbar_add"), key="prompt_prefix_toolbar_add", width="stretch"):
            if on_open_panel is None:
                _open_prompt_prefix_panel("manual")
                safe_rerun()
            else:
                on_open_panel("manual")
    with st.container():
        if st.button(tr("style.prefix_library.toolbar_ai"), key="prompt_prefix_toolbar_ai", width="stretch"):
            if on_open_panel is None:
                _open_prompt_prefix_panel("ai")
                safe_rerun()
            else:
                on_open_panel("ai")


def _render_image_prompt_prefix_library(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    workflow_display_map: dict[str, str] | None = None,
) -> str:
    """Render the gallery-style image prompt prefix library UI and return effective prefix content."""
    language = get_language()
    workflow_display_map = workflow_display_map or {}
    image_config = config_manager.config.comfyui.image
    library = config_manager.get_image_prompt_prefix_library()
    library_items = library.get("items", [])
    library_items_by_id = {item["id"]: item for item in library_items}
    active_prefix_id = library.get("active_prefix_id")
    active_item = library_items_by_id.get(active_prefix_id)
    effective_prefix = get_effective_image_prompt_prefix(image_config)
    st.session_state["prompt_prefix_effective_value"] = effective_prefix

    style_options, scene_options = get_localized_prompt_prefix_category_options(language=language)
    style_label_map = {option["id"]: option["label"] for option in style_options}
    scene_label_map = {option["id"]: option["label"] for option in scene_options}

    generated_candidates = st.session_state.get("prompt_prefix_generated_candidates", [])
    valid_ids = {item["id"] for item in library_items} | {item["id"] for item in generated_candidates}
    selected_preview_ids = sanitize_prompt_prefix_preview_selection(
        st.session_state.get("prompt_prefix_preview_ids", []),
        valid_ids,
    )
    if selected_preview_ids != st.session_state.get("prompt_prefix_preview_ids", []):
        st.session_state["prompt_prefix_preview_ids"] = selected_preview_ids
        st.session_state.pop("prompt_prefix_preview_results", None)

    live_preview_map = _build_prompt_prefix_live_preview_map()
    panel_mode = st.session_state.get("prompt_prefix_panel_mode")
    panel_item_id = st.session_state.get("prompt_prefix_panel_item_id")
    panel_item = library_items_by_id.get(panel_item_id)
    thumbnail_reference_prompt = st.session_state.get(
        "prompt_prefix_thumbnail_reference_prompt",
        st.session_state.get("style_test_prompt", "a dog"),
    )

    st.markdown(f"**{tr('style.prompt_prefix')}**")
    st.caption(tr("style.prefix_library.title"))
    st.markdown(
        """
        <style>
        .st-key-prompt_prefix_library_root div.stButton > button {
            padding-inline: 0.45rem;
        }
        .st-key-prompt_prefix_library_root div.stButton > button p {
            white-space: nowrap !important;
            word-break: keep-all !important;
            overflow-wrap: normal !important;
            writing-mode: horizontal-tb !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def _set_prompt_prefix_panel_state(mode: str, item: dict | None = None) -> None:
        """Keep local panel state in sync so open actions don't need a second rerun."""
        nonlocal panel_mode, panel_item_id, panel_item
        item_id = item["id"] if item else None
        _open_prompt_prefix_panel(mode, item_id)
        panel_mode = mode
        panel_item_id = item_id
        panel_item = item

    with st.container(border=True):
        active_info_col, active_action_col = st.columns(2, gap="small")
        with active_info_col:
            if active_item:
                st.markdown(f"### {active_item['name']}")
                st.caption(
                    f"{tr('style.prefix_library.active')} / "
                    f"{get_prompt_prefix_category_label(active_item['style_category_id'], 'style', language)} / "
                    f"{get_prompt_prefix_category_label(active_item['scene_category_id'], 'scene', language)}"
                )
                if active_item.get("note"):
                    st.caption(active_item["note"])
            elif effective_prefix:
                st.caption(tr("style.prefix_library.active_legacy"))
                st.code(effective_prefix, language=None)
            else:
                st.caption(tr("style.prefix_library.active_empty"))
        with active_action_col:
            if active_item and st.button(
                tr("style.prefix_library.view_details"),
                key="prompt_prefix_active_details",
                width="stretch",
            ):
                _set_prompt_prefix_panel_state("details", active_item)
            st.caption(tr("style.prefix_library.reference_cover"))

    with render_middle_column_collapsible_section(
        tr("style.prefix_library.filter_panel"),
        expanded=False,
    ):
        filter_style_col, filter_scene_col = st.columns(2, gap="small")
        with filter_style_col:
            selected_style = st.selectbox(
                tr("style.prefix_library.style_filter"),
                options=[""] + [option["id"] for option in style_options],
                format_func=lambda value: tr("style.prefix_library.all") if not value else style_label_map[value],
                key="prompt_prefix_style_filter",
            )
        with filter_scene_col:
            selected_scene = st.selectbox(
                tr("style.prefix_library.scene_filter"),
                options=[""] + [option["id"] for option in scene_options],
                format_func=lambda value: tr("style.prefix_library.all") if not value else scene_label_map[value],
                key="prompt_prefix_scene_filter",
            )
        keyword = st.text_input(
            tr("style.prefix_library.keyword"),
            placeholder=tr("style.prefix_library.keyword_placeholder"),
            key="prompt_prefix_keyword_filter",
        )
        thumbnail_reference_prompt = st.text_input(
            tr("style.prefix_library.thumbnail_prompt"),
            value=thumbnail_reference_prompt,
            key="prompt_prefix_thumbnail_reference_prompt",
            placeholder=tr("style.prefix_library.thumbnail_prompt_placeholder"),
        )
    filtered_items = filter_prompt_prefix_items(
        library_items,
        style_category_id=selected_style or None,
        scene_category_id=selected_scene or None,
        keyword=keyword,
    )
    st.caption(tr("style.prefix_library.thumbnail_scope", count=len(filtered_items)))
    if st.session_state.get("prompt_prefix_thumbnail_status"):
        st.caption(st.session_state["prompt_prefix_thumbnail_status"])
    st.caption(tr("style.prefix_library.compare_count", count=len(selected_preview_ids)))

    gallery_col = st.container(key="prompt_prefix_library_root")
    lower_panel_col = st.container()
    action_toolbar_col = st.container()
    with gallery_col:
        if not filtered_items:
            st.caption(tr("style.prefix_library.no_items"))
        else:
            num_cols = 4
            gallery_columns = st.columns(num_cols)
            for idx, item in enumerate(filtered_items):
                style_label = get_prompt_prefix_category_label(item["style_category_id"], "style", language)
                scene_label = get_prompt_prefix_category_label(item["scene_category_id"], "scene", language)
                cover_state = resolve_prompt_prefix_gallery_cover(item, workflow_key)
                is_active = item["id"] == active_prefix_id
                in_preview = item["id"] in selected_preview_ids
                title_html = escape(item["name"])
                meta_label = escape(" / ".join([style_label, scene_label]))
                source_label = escape(_get_prompt_prefix_source_label(item.get("source", "manual")))
                status_label = escape(_get_prompt_prefix_cover_status_label(cover_state))

                with gallery_columns[idx % num_cols]:
                    with st.container(border=True):
                        st.image(cover_state["asset_path"], width="stretch")
                        st.markdown(
                            f"""
                            <div style="
                                min-height: 2.9rem;
                                font-weight: 600;
                                font-size: 0.98rem;
                                line-height: 1.45;
                                overflow: hidden;
                                display: -webkit-box;
                                -webkit-line-clamp: 2;
                                -webkit-box-orient: vertical;
                                margin-bottom: 0.2rem;
                            ">{title_html}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"""
                            <div style="
                                min-height: 1.35rem;
                                color: rgba(49, 51, 63, 0.72);
                                font-size: 0.82rem;
                                line-height: 1.35;
                                overflow: hidden;
                                text-overflow: ellipsis;
                                white-space: nowrap;
                                margin-bottom: 0.15rem;
                            ">{meta_label}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"""
                            <div style="
                                min-height: 1.25rem;
                                color: rgba(49, 51, 63, 0.58);
                                font-size: 0.76rem;
                                line-height: 1.3;
                                overflow: hidden;
                                text-overflow: ellipsis;
                                white-space: nowrap;
                                margin-bottom: 0.45rem;
                            ">{source_label} / {status_label}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            tr("style.prefix_library.view_details"),
                            key=f"open_prefix_details_compact_{item['id']}",
                            width="stretch",
                        ):
                            _set_prompt_prefix_panel_state("details", item)

                        compare_col, select_col = st.columns(2, gap="small")
                        with compare_col:
                            compare_label = (
                                tr("style.prefix_library.compare_chip_active")
                                if in_preview
                                else tr("style.prefix_library.compare_chip_short")
                            )
                            if st.button(
                                compare_label,
                                key=f"compare_prefix_card_compact_{item['id']}",
                                width="stretch",
                            ):
                                if not in_preview and len(selected_preview_ids) >= 4:
                                    st.warning(tr("style.prefix_library.preview_limit"))
                                else:
                                    st.session_state["prompt_prefix_preview_ids"] = toggle_prompt_prefix_preview_selection(
                                        selected_preview_ids,
                                        item["id"],
                                    )
                                    st.session_state.pop("prompt_prefix_preview_results", None)
                                    safe_rerun()
                        with select_col:
                            if st.button(
                                tr("template.selected") if is_active else tr("template.select_button"),
                                key=f"select_prefix_card_compact_{item['id']}",
                                width="stretch",
                                type="primary" if is_active else "secondary",
                            ):
                                _set_active_image_prompt_prefix(item["id"])
                                safe_rerun()

    if panel_mode == "details" and panel_item:
        _render_prompt_prefix_details_modal(
            panel_item=panel_item,
            workflow_key=workflow_key,
            workflow_display_map=workflow_display_map,
            language=language,
            selected_preview_ids=selected_preview_ids,
        )
    elif panel_mode == "details":
        _close_prompt_prefix_panel()

    with lower_panel_col:
        if panel_mode in {"manual", "edit", "ai"}:
            with st.container(border=True):
                panel_header_col, panel_close_col = st.columns([2.2, 1], gap="small")
                with panel_header_col:
                    if panel_mode == "edit" and panel_item:
                        st.markdown(f"### {tr('style.prefix_library.edit')}")
                    elif panel_mode == "manual":
                        st.markdown(f"### {tr('style.prefix_library.manual_create')}")
                    else:
                        st.markdown(f"### {tr('style.prefix_library.ai_generate')}")
                with panel_close_col:
                    if st.button(
                        tr("style.prefix_library.close_panel"),
                        key="prompt_prefix_close_panel",
                        width="stretch",
                    ):
                        _close_prompt_prefix_panel()
                        safe_rerun()

                if panel_mode in {"manual", "edit"}:
                    _render_prompt_prefix_editor_panel(
                        panel_mode=panel_mode,
                        panel_item=panel_item,
                        workflow_key=workflow_key,
                        language=language,
                        live_preview_map=live_preview_map,
                        style_options=style_options,
                        scene_options=scene_options,
                        style_label_map=style_label_map,
                        scene_label_map=scene_label_map,
                    )
                if panel_mode == "ai":
                    _render_prompt_prefix_ai_panel(
                        pixelle_video=pixelle_video,
                        workflow_key=workflow_key,
                        media_width=media_width,
                        media_height=media_height,
                        language=language,
                        library_items=library_items,
                        selected_preview_ids=selected_preview_ids,
                    )

    with action_toolbar_col:
        _render_prompt_prefix_library_action_toolbar(
            pixelle_video=pixelle_video,
            workflow_key=workflow_key,
            media_width=media_width,
            media_height=media_height,
            filtered_items=filtered_items,
            thumbnail_reference_prompt=thumbnail_reference_prompt,
            on_open_panel=lambda mode: _set_prompt_prefix_panel_state(mode),
        )

    preview_title = tr("style.preview_title")
    with render_middle_column_detail_section(preview_title):
        test_prompt = st.text_input(
            tr("style.test_prompt"),
            value=st.session_state.get("style_test_prompt", "a dog"),
            help=tr("style.test_prompt_help"),
            key="style_test_prompt",
        )
        st.caption(tr("style.prefix_library.workflow_preview_hint"))

        preview_items_by_id = {item["id"]: item for item in library_items}
        preview_items_by_id.update({item["id"]: item for item in generated_candidates})
        preview_items = build_prompt_prefix_preview_batch(
            items_by_id=preview_items_by_id,
            selected_ids=selected_preview_ids,
        ) if selected_preview_ids else []

        st.caption(tr("style.prefix_library.preview_selected_count", count=len(preview_items)))
        if preview_items:
            st.caption(", ".join(item["name"] for item in preview_items))
        else:
            st.caption(tr("style.prefix_library.no_preview_items"))

        if st.button(tr("style.preview"), key="preview_style", width="stretch"):
            if not preview_items:
                st.warning(tr("style.prefix_library.preview_selection_required"))
            else:
                with st.spinner(tr("style.previewing")):
                    try:
                        st.session_state["prompt_prefix_preview_results"] = _generate_prompt_prefix_preview_results(
                            pixelle_video=pixelle_video,
                            workflow_key=workflow_key,
                            media_width=media_width,
                            media_height=media_height,
                            test_prompt=test_prompt,
                            items=preview_items,
                        )
                    except Exception as e:
                        st.error(tr("style.preview_failed", error=str(e)))
                        logger.exception(e)

        preview_results = st.session_state.get("prompt_prefix_preview_results", [])
        if preview_results:
            preview_columns = st.columns(len(preview_results))
            for idx, preview_result in enumerate(preview_results):
                with preview_columns[idx]:
                    st.markdown(f"**{preview_result['name']}**")
                    render_generated_style_preview(preview_result["preview_media_path"], "image")
                    if st.button(
                        tr("style.prefix_library.set_active"),
                        key=f"set_preview_active_prefix_{preview_result['id']}",
                        width="stretch",
                    ):
                        if preview_result["id"] in preview_items_by_id:
                            candidate_item = preview_items_by_id[preview_result["id"]]
                            if preview_result["id"] not in library_items_by_id:
                                _save_prompt_prefix_item_with_workflow_preview(
                                    candidate_item,
                                    workflow_key=workflow_key,
                                    preview_media_path=preview_result.get("preview_media_path"),
                                    set_active=True,
                                )
                                _remove_generated_candidate_from_session(preview_result["id"])
                            else:
                                _save_prompt_prefix_item_with_workflow_preview(
                                    candidate_item,
                                    workflow_key=workflow_key,
                                    preview_media_path=preview_result.get("preview_media_path"),
                                    set_active=True,
                                )
                            safe_rerun()
                    st.info(f"**{tr('style.final_prompt_label')}**\n{preview_result['final_prompt']}")

    return effective_prefix


def render_style_config(pixelle_video, storyboard_default_enabled: bool = False):
    """Render style configuration section (middle column)"""
    # TTS Section (moved from left column)
    # ====================================================================
    with render_middle_column_collapsible_section(
        tr("section.tts"),
        expanded=False,
    ):
        with render_middle_column_detail_section(tr("help.feature_description")):
            st.markdown(f"**{tr('help.what')}**")
            st.markdown(tr("tts.what"))
            st.markdown(f"**{tr('help.how')}**")
            st.markdown(tr("tts.how"))
        
        # Get TTS config
        comfyui_config = config_manager.get_comfyui_config()
        tts_config = comfyui_config["tts"]
        
        # Inference mode selection
        tts_mode = st.radio(
            tr("tts.inference_mode"),
            ["local", "comfyui"],
            horizontal=True,
            format_func=lambda x: tr(f"tts.mode.{x}"),
            index=0 if resolve_configured_tts_mode(tts_config) == "local" else 1,
            key="tts_inference_mode"
        )
        
        # Show hint based on mode
        if tts_mode == "local":
            st.caption(tr("tts.mode.local_hint"))
        else:
            st.caption(tr("tts.mode.comfyui_hint"))
        
        # ================================================================
        # Local Mode UI
        # ================================================================
        if tts_mode == "local":
            # Import voice configuration
            from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
            
            # Get saved voice from config
            local_config = tts_config.get("local", {})
            saved_voice = local_config.get("voice", "zh-CN-YunjianNeural")
            saved_speed = local_config.get("speed", 1.2)
            
            # Build voice options with i18n
            voice_options = []
            voice_ids = []
            default_voice_index = 0
            
            for idx, voice_config in enumerate(EDGE_TTS_VOICES):
                voice_id = voice_config["id"]
                display_name = get_voice_display_name(voice_id, tr, get_language())
                voice_options.append(display_name)
                voice_ids.append(voice_id)
                
                # Set default index if matches saved voice
                if voice_id == saved_voice:
                    default_voice_index = idx
            
            # Two-column layout: Voice | Speed
            voice_col, speed_col = st.columns([1, 1])
            
            with voice_col:
                # Voice selector
                selected_voice_display = st.selectbox(
                    tr("tts.voice_selector"),
                    voice_options,
                    index=default_voice_index,
                    key="tts_local_voice"
                )
                
                # Get actual voice ID
                selected_voice_index = voice_options.index(selected_voice_display)
                selected_voice = voice_ids[selected_voice_index]
            
            with speed_col:
                # Speed slider
                tts_speed = st.slider(
                    tr("tts.speed"),
                    min_value=0.5,
                    max_value=2.0,
                    value=saved_speed,
                    step=0.1,
                    format="%.1fx",
                    key="tts_local_speed"
                )
                st.caption(tr("tts.speed_label", speed=f"{tts_speed:.1f}"))
            
            # Variables for video generation
            tts_workflow_key = None
            ref_audio_path = None
            ref_audio_text = None
        
        # ================================================================
        # ComfyUI Mode UI
        # ================================================================
        else:  # comfyui mode
            # Get available TTS workflows
            tts_workflows = pixelle_video.tts.list_workflows()
            
            # Build options for selectbox
            tts_workflow_options = [wf["display_name"] for wf in tts_workflows]
            tts_workflow_keys = [wf["key"] for wf in tts_workflows]
            
            # Default to saved workflow if exists
            default_tts_index = 0
            saved_tts_workflow = tts_config.get("comfyui", {}).get("default_workflow")
            if saved_tts_workflow and saved_tts_workflow in tts_workflow_keys:
                default_tts_index = tts_workflow_keys.index(saved_tts_workflow)
            
            tts_workflow_display = st.selectbox(
                "TTS Workflow",
                tts_workflow_options if tts_workflow_options else ["No TTS workflows found"],
                index=default_tts_index,
                label_visibility="collapsed",
                key="tts_workflow_select"
            )
            
            # Get the actual workflow key
            if tts_workflow_options:
                tts_selected_index = tts_workflow_options.index(tts_workflow_display)
                tts_workflow_key = tts_workflow_keys[tts_selected_index]
            else:
                tts_workflow_key = "selfhost/tts_index2.json"
            
            render_selfhost_workflow_notice(
                tts_workflow_key,
                expanded=True,
            )
            ref_audio_path, ref_audio_text = render_tts_voice_profile_controls(tts_workflow_key)
            
            # Variables for video generation
            selected_voice = None
            tts_speed = resolve_comfyui_tts_speed(tts_config)
        
        # ================================================================
        # TTS Preview (works for both modes)
        # ================================================================
        with render_middle_column_detail_section(tr("tts.preview_title")):
            # Preview text input
            preview_text = st.text_input(
                tr("tts.preview_text"),
                value="大家好，这是一段测试语音。",
                placeholder=tr("tts.preview_text_placeholder"),
                key="tts_preview_text"
            )
            
            # Preview button
            if st.button(tr("tts.preview_button"), key="preview_tts", width="stretch"):
                with st.spinner(tr("tts.previewing")):
                    try:
                        # Build TTS params based on mode
                        tts_params = {
                            "text": preview_text,
                            "inference_mode": tts_mode
                        }
                        
                        if tts_mode == "local":
                            tts_params["voice"] = selected_voice
                            tts_params["speed"] = tts_speed
                        else:  # comfyui
                            tts_params["workflow"] = tts_workflow_key
                            tts_params["speed"] = tts_speed
                            if ref_audio_path:
                                tts_params["ref_audio"] = str(ref_audio_path)
                            if ref_audio_text:
                                tts_params["ref_audio_text"] = ref_audio_text
                        
                        audio_path = run_async(pixelle_video.tts(**tts_params))
                        
                        # Play the audio
                        if audio_path:
                            st.success(tr("tts.preview_success"))
                            if os.path.exists(audio_path):
                                st.audio(audio_path, format="audio/mp3")
                            elif audio_path.startswith('http'):
                                st.audio(audio_path)
                            else:
                                st.error("Failed to generate preview audio")
                            
                            # Show file path
                            st.caption(f"📁 {audio_path}")
                        else:
                            st.error("Failed to generate preview audio")
                    except Exception as e:
                        st.error(tr("tts.preview_failed", error=str(e)))
                        logger.exception(e)

    with render_middle_column_collapsible_section(
        tr("section.render_backend"),
        expanded=False,
    ):
        render_backend = render_render_backend_selector()
        tts_audio_strategy = render_tts_audio_strategy_selector()
        tts_split_settings = render_tts_split_settings()

    element_animation_settings = render_element_animation_controls()
    text_rendering = render_text_rendering_controls(
        render_backend,
        ui=st,
        translate=tr,
    )

    storyboard_world_preset_id = None
    storyboard_shot_preset_id = None
    storyboard_consistency_strength = None
    storyboard_content_mode = None
    storyboard_role_strategy = None
    storyboard_role_locking_strength = None
    storyboard_shot_strategy = None
    storyboard_frame_overrides: list[dict] = []
    selected_template_type_for_storyboard = st.session_state.get("template_type_selector")
    storyboard_controls_disabled = selected_template_type_for_storyboard == "static"
    storyboard_checkbox_key = (
        "storyboard_planning_enabled_static"
        if storyboard_controls_disabled
        else "storyboard_planning_enabled"
    )

    with render_middle_column_collapsible_section(
        tr("section.storyboard_planning"),
        expanded=False,
    ):
        storyboard_enabled = st.checkbox(
            tr("storyboard.enabled"),
            value=resolve_storyboard_toggle_default(
                st.session_state,
                storyboard_default_enabled=storyboard_default_enabled,
                preview_snapshot=st.session_state.get("storyboard_preview_snapshot"),
                template_type=selected_template_type_for_storyboard,
            ),
            key=storyboard_checkbox_key,
            help=tr("storyboard.enabled_help"),
            disabled=storyboard_controls_disabled,
        )

        if storyboard_controls_disabled:
            st.caption(tr("template.type.static_hint"))
        elif storyboard_enabled:
            render_storyboard_planning_guide()
            world_library = config_manager.get_storyboard_world_preset_library()
            shot_library = config_manager.get_storyboard_shot_preset_library()
            world_items = world_library.get("items", [])
            shot_items = shot_library.get("items", [])
            world_ids = [item["preset_id"] for item in world_items]
            shot_ids = [item["preset_id"] for item in shot_items]
            world_label_map = {item["preset_id"]: resolve_storyboard_preset_label(item) for item in world_items}
            shot_label_map = {item["preset_id"]: resolve_storyboard_preset_label(item) for item in shot_items}

            default_world_id = world_library.get("default_world_preset_id")
            if default_world_id not in world_ids and world_ids:
                default_world_id = world_ids[0]
            storyboard_col1, storyboard_col2 = st.columns(2)
            with storyboard_col1:
                if world_ids:
                    storyboard_world_preset_id = st.selectbox(
                        tr("storyboard.world_preset"),
                        options=world_ids,
                        index=world_ids.index(default_world_id),
                        format_func=lambda value: world_label_map.get(value, value),
                        key="storyboard_world_preset_id",
                    )
                storyboard_consistency_strength = st.radio(
                    tr("storyboard.consistency_strength"),
                    options=["standard", "strong"],
                    index=0,
                    horizontal=True,
                    format_func=lambda value: tr(f"storyboard.option.consistency.{value}"),
                    key="storyboard_consistency_strength",
                )
                content_mode_selection = st.selectbox(
                    tr("storyboard.content_mode"),
                    options=["auto", "concept_explainer", "theme_mapping"],
                    index=0,
                    format_func=lambda value: tr(f"storyboard.option.content_mode.{value}"),
                    key="storyboard_content_mode",
                )
                storyboard_content_mode = (
                    None if content_mode_selection == "auto" else content_mode_selection
                )

            with storyboard_col2:
                if shot_ids:
                    storyboard_shot_preset_id = st.selectbox(
                        tr("storyboard.shot_preset"),
                        options=[STORYBOARD_SHOT_PRESET_AUTO_VALUE, *shot_ids],
                        index=0,
                        format_func=lambda value: (
                            tr("storyboard.option.content_mode.auto")
                            if value == STORYBOARD_SHOT_PRESET_AUTO_VALUE
                            else shot_label_map.get(value, value)
                        ),
                        key="storyboard_shot_preset_id",
                    )
                    if storyboard_shot_preset_id == STORYBOARD_SHOT_PRESET_AUTO_VALUE:
                        storyboard_shot_preset_id = None
                storyboard_role_strategy = st.selectbox(
                    tr("storyboard.role_strategy"),
                    options=["auto", "stable_explainer_cast", "theme_mapping"],
                    index=0,
                    format_func=lambda value: tr(f"storyboard.option.role_strategy.{value}"),
                    key="storyboard_role_strategy",
                )
                storyboard_role_locking_strength = st.radio(
                    tr("storyboard.role_locking_strength"),
                    options=["standard", "strong"],
                    index=0,
                    horizontal=True,
                    format_func=lambda value: tr(f"storyboard.option.consistency.{value}"),
                    key="storyboard_role_locking_strength",
                )
                storyboard_shot_strategy = st.radio(
                    tr("storyboard.shot_strategy"),
                    options=["adaptive", "strict"],
                    index=0,
                    horizontal=True,
                    format_func=lambda value: tr(f"storyboard.option.shot_strategy.{value}"),
                    key="storyboard_shot_strategy",
                )
            storyboard_frame_overrides = render_storyboard_preview(
                st.session_state.get("storyboard_preview_snapshot")
            )
        else:
            st.caption(tr("storyboard.preview.empty"))
    
    # ====================================================================
    # Storyboard Template Section
    # ====================================================================
    
    def get_template_preview_path(template_path: str, language: str = "zh_CN") -> str:
        """
        Get the preview image path for a template based on language.
        
        Args:
            template_path: Template path like "1080x1920/image_default.html"
            language: Language code, either "zh_CN" or "en"
            
        Returns:
            Path to preview image in docs/images/
        """
        # Extract size and template name from path
        # e.g., "1080x1920/image_default.html" -> size="1080x1920", name="image_default"
        path_parts = template_path.split('/')
        if len(path_parts) >= 2:
            size = path_parts[0]  # e.g., "1080x1920"
            template_file = path_parts[1]  # e.g., "image_default.html"
            template_name = template_file.replace('.html', '')  # e.g., "image_default"
            
            # Build preview image path
            # Format: docs/images/{size}/{template_name}.jpg or {template_name}_en.jpg
            # Chinese uses Chinese preview, all other languages use English preview for better i18n
            suffix = "" if language == "zh_CN" else "_en"
            
            # Try different image extensions
            for ext in ['.jpg', '.png']:
                preview_path = f"docs/images/{size}/{template_name}{suffix}{ext}"
                if os.path.exists(preview_path):
                    return preview_path
            
            # Fallback: try without language suffix (for templates with only one version)
            for ext in ['.jpg', '.png']:
                preview_path = f"docs/images/{size}/{template_name}{ext}"
                if os.path.exists(preview_path):
                    return preview_path
        
        # If no preview found, return empty string
        return ""
    
    with render_middle_column_collapsible_section(
        tr("section.template"),
        expanded=False,
    ):
        with st.popover(tr("help.feature_description")):
            st.markdown(f"**{tr('help.what')}**")
            st.markdown(tr("template.what"))
            st.markdown(f"**{tr('help.how')}**")
            st.markdown(tr("template.how"))
        
        # Template preview link (based on language)
        current_lang = get_language()
        
        # Import template utilities
        from pixelle_video.utils.template_util import (
            get_template_type,
            get_templates_grouped_by_size_and_type,
        )
        
        # Template type selector
        st.markdown(f"**{tr('template.type_selector')}**")
        
        template_type_options = {
            'static': tr('template.type.static'),
            'image': tr('template.type.image'),
            'video': tr('template.type.video')
        }
        
        # Radio buttons in horizontal layout
        selected_template_type = st.radio(
            tr('template.type_selector'),
            options=list(template_type_options.keys()),
            format_func=lambda x: template_type_options[x],
            index=1,  # Default to 'image'
            key="template_type_selector",
            label_visibility="collapsed",
            horizontal=True
        )
        
        # Display hint based on selected type (below radio buttons)
        if selected_template_type == 'static':
            st.info(tr('template.type.static_hint'))
        elif selected_template_type == 'image':
            st.info(tr('template.type.image_hint'))
        elif selected_template_type == 'video':
            st.info(tr('template.type.video_hint'))
        
        # Get templates grouped by size, filtered by selected type
        grouped_templates = get_templates_grouped_by_size_and_type(selected_template_type)
        
        if not grouped_templates:
            st.warning(f"No {template_type_options[selected_template_type]} templates found. Please select a different type or add templates.")
            st.stop()
        
        # Build orientation i18n mapping
        ORIENTATION_I18N = {
            'portrait': tr('orientation.portrait'),
            'landscape': tr('orientation.landscape'),
            'square': tr('orientation.square')
        }
        
        # Get default template from config
        template_config = pixelle_video.config.get("template", {})
        config_default_template = template_config.get("default_template", "1080x1920/image_default.html")

        # Backward compatibility
        if config_default_template == "1080x1920/default.html":
            config_default_template = "1080x1920/image_default.html"
        
        # Determine type-specific default template
        type_default_templates = {
            'static': '1080x1920/static_default.html',
            'image': '1080x1920/image_default.html',
            'video': '1080x1920/video_default.html'
        }
        type_specific_default = type_default_templates.get(selected_template_type, config_default_template)
        
        # Initialize selected template in session state if not exists
        if 'selected_template' not in st.session_state:
            st.session_state['selected_template'] = type_specific_default
        
        # Track last selected template type to detect type changes
        last_template_type = st.session_state.get('last_template_type', None)
        if last_template_type != selected_template_type:
            # Template type changed, reset to type-specific default
            st.session_state['selected_template'] = type_specific_default
            st.session_state['last_template_type'] = selected_template_type
        
        # Collect size groups and prepare tabs
        size_groups = []
        size_labels = []
        
        for size, templates in grouped_templates.items():
            if not templates:
                continue
            
            # Filter templates to only include those with proper naming convention
            # Only show templates starting with static_, image_, or video_
            valid_templates = []
            for template in templates:
                template_name = template.display_info.name
                if template_name.startswith(('static_', 'image_', 'video_')):
                    valid_templates.append(template)
            
            # Skip if no valid templates after filtering
            if not valid_templates:
                continue
            
            # Separate templates into two groups: with preview and without preview
            templates_with_preview = []
            templates_without_preview = []
            
            for template in valid_templates:
                preview_path = get_template_preview_path(template.template_path, current_lang)
                if preview_path and os.path.exists(preview_path):
                    templates_with_preview.append(template)
                else:
                    templates_without_preview.append(template)
            
            # Skip this group if no templates at all
            if not templates_with_preview and not templates_without_preview:
                continue
            
            # Combine: templates with preview first, then without preview
            all_templates = templates_with_preview + templates_without_preview
            
            # Get orientation from first template in group
            orientation = ORIENTATION_I18N.get(
                all_templates[0].display_info.orientation, 
                all_templates[0].display_info.orientation
            )
            width = all_templates[0].display_info.width
            height = all_templates[0].display_info.height
            
            # Create tab label
            tab_label = f"{orientation} {width}×{height}"
            size_labels.append(tab_label)
            size_groups.append(all_templates)
        
        # Create tabs for each size group (wrapped in expander)
        with render_middle_column_detail_section(tr("template.gallery_view")):
            if size_groups:
                tabs = st.tabs(size_labels)
                
                for tab, all_templates in zip(tabs, size_groups):
                    with tab:
                        # Create grid layout (5 columns)
                        num_cols = 5
                        cols = st.columns(num_cols)
                        
                        for idx, template in enumerate(all_templates):
                            col_idx = idx % num_cols
                            with cols[col_idx]:
                                # Get preview image path
                                preview_path = get_template_preview_path(template.template_path, current_lang)
                                
                                # Display preview image or placeholder
                                if preview_path and os.path.exists(preview_path):
                                    _render_template_gallery_preview(preview_path, template.display_info.name)
                                else:
                                    _render_template_gallery_preview_placeholder(template.display_info.name)
                                
                                # Select button (unified label)
                                is_selected = (st.session_state['selected_template'] == template.template_path)
                                button_label = f"{tr('template.selected')}" if is_selected else tr('template.select_button')
                                button_type = "primary" if is_selected else "secondary"
                                
                                if st.button(
                                    button_label,
                                    key=f"template_{template.template_path}",
                                    width="stretch",
                                    type=button_type,
                                ):
                                    st.session_state['selected_template'] = template.template_path
                                    st.rerun()
            else:
                st.warning(tr("template.no_templates_with_preview"))
            
            # Display selected template name (inside expander, below tabs)
            frame_template = st.session_state['selected_template']
            
            # Find the selected template's display name
            selected_template_name = None
            for size, templates in grouped_templates.items():
                for template in templates:
                    if template.template_path == frame_template:
                        selected_template_name = template.display_info.name
                        break
                if selected_template_name:
                    break
            
        if selected_template_name:
            st.info(f"📋 {tr('template.selected_template')}: **{selected_template_name}**")
        

        # Display video size from template
        from pixelle_video.utils.template_util import parse_template_size
        video_width, video_height = parse_template_size(frame_template)
        st.caption(tr("template.video_size_info", width=video_width, height=video_height))
        
        # Custom template parameters (for video generation)
        from pixelle_video.services.frame_html import HTMLFrameGenerator

        # Resolve template path to support both data/templates/ and templates/
        from pixelle_video.utils.template_util import resolve_template_path
        template_path_for_params = resolve_template_path(frame_template)
        generator_for_params = HTMLFrameGenerator(template_path_for_params)
        custom_params_for_video = generator_for_params.parse_template_parameters()
        
        # Get media size from template (for image/video generation)
        media_width, media_height = generator_for_params.get_media_size()
        st.session_state['template_media_width'] = media_width
        st.session_state['template_media_height'] = media_height
        
        # Detect template media type
        
        template_name = Path(frame_template).name
        template_media_type = get_template_type(template_name)
        template_requires_media = (template_media_type in ["image", "video"])
        
        # Store in session state for workflow filtering
        st.session_state['template_media_type'] = template_media_type
        st.session_state['template_requires_media'] = template_requires_media
        
        # Backward compatibility
        st.session_state['template_requires_image'] = (template_media_type == "image")
        
        custom_values_for_video = {}
        if custom_params_for_video:
            st.markdown("📝 " + tr("template.custom_parameters"))
            
            # Render custom parameter inputs in 2 columns
            video_custom_col1, video_custom_col2 = st.columns(2)
            
            param_items = list(custom_params_for_video.items())
            mid_point = (len(param_items) + 1) // 2
            
            # Left column parameters
            with video_custom_col1:
                for param_name, config in param_items[:mid_point]:
                    param_type = config['type']
                    default = config['default']
                    label = config['label']
                    
                    if param_type == 'text':
                        custom_values_for_video[param_name] = st.text_input(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'number':
                        custom_values_for_video[param_name] = st.number_input(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'color':
                        custom_values_for_video[param_name] = st.color_picker(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'bool':
                        custom_values_for_video[param_name] = st.checkbox(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
            
            # Right column parameters
            with video_custom_col2:
                for param_name, config in param_items[mid_point:]:
                    param_type = config['type']
                    default = config['default']
                    label = config['label']
                    
                    if param_type == 'text':
                        custom_values_for_video[param_name] = st.text_input(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'number':
                        custom_values_for_video[param_name] = st.number_input(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'color':
                        custom_values_for_video[param_name] = st.color_picker(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
                    elif param_type == 'bool':
                        custom_values_for_video[param_name] = st.checkbox(
                            label,
                            value=default,
                            key=f"video_custom_{param_name}"
                        )
        
        # Template preview expander
        with render_middle_column_detail_section(tr("template.preview_title")):
            col1, col2 = st.columns(2)
            
            with col1:
                preview_title = st.text_input(
                    tr("template.preview_param_title"), 
                    value=tr("template.preview_default_title"),
                    key="preview_title"
                )
                preview_image = st.text_input(
                    tr("template.preview_param_image"), 
                    value="resources/example.png",
                    help=tr("template.preview_image_help"),
                    key="preview_image"
                )
            
            with col2:
                preview_text = st.text_area(
                    tr("template.preview_param_text"), 
                    value=tr("template.preview_default_text"),
                    height=100,
                    key="preview_text"
                )
            
            # Info: Size is auto-determined from template
            from pixelle_video.utils.template_util import parse_template_size, resolve_template_path
            template_width, template_height = parse_template_size(resolve_template_path(frame_template))
            st.info(f"📐 {tr('template.size_info')}: {template_width} × {template_height}")
            
            # Preview button
            if st.button(tr("template.preview_button"), key="btn_preview_template", width="stretch"):
                with st.spinner(tr("template.preview_generating")):
                    try:
                        from pixelle_video.services.frame_html import HTMLFrameGenerator

                        # Use the currently selected template (size is auto-parsed)
                        from pixelle_video.utils.template_util import resolve_template_path
                        template_path = resolve_template_path(frame_template)
                        generator = HTMLFrameGenerator(template_path)
                        
                        # Build ext dict with auto-injected parameters (same as FrameProcessor)
                        ext = {
                            "index": 1,  # Preview uses index 1
                        }
                        
                        # Add custom parameters from user input
                        if custom_values_for_video:
                            ext.update(custom_values_for_video)
                        
                        # Generate preview
                        preview_path = run_async(generator.generate_frame(
                            title=preview_title,
                            text=preview_text,
                            image=preview_image,
                            ext=ext
                        ))
                        
                        # Display preview
                        if preview_path:
                            st.success(tr("template.preview_success"))
                            st.image(
                                preview_path, 
                                caption=tr("template.preview_caption", template=frame_template),
                            )
                            
                            # Show file path
                            st.caption(f"📁 {preview_path}")
                        else:
                            st.error("Failed to generate preview")
                            
                    except Exception as e:
                        st.error(tr("template.preview_failed", error=str(e)))
                        logger.exception(e)
    
    # ====================================================================
    # Media Generation Section (conditional based on template)
    # ====================================================================
    # Check if current template requires media generation
    template_media_type = st.session_state.get('template_media_type', 'image')
    template_requires_media = st.session_state.get('template_requires_media', True)
    
    if template_requires_media:
        # Template requires media - show Media Generation Section
        if template_media_type == "video":
            section_title = tr('section.video')
        else:
            section_title = tr('section.image')

        with render_middle_column_collapsible_section(
            section_title,
            expanded=resolve_media_generation_section_expanded(template_media_type),
        ):
            # 1. ComfyUI Workflow selection
            if template_media_type == "image":
                st.markdown(f"**{tr('style.image_model_selection_title')}**")
                with st.popover(tr("help.feature_description")):
                    st.markdown(f"**{tr('help.what')}**")
                    st.markdown(tr("style.workflow_what"))
                    st.markdown(f"**{tr('help.how')}**")
                    st.markdown(tr("style.workflow_how"))
            else:
                with render_middle_column_detail_section(tr("help.feature_description")):
                    st.markdown(f"**{tr('help.what')}**")
                    st.markdown(tr('style.video_workflow_what'))
                    st.markdown(f"**{tr('help.how')}**")
                    st.markdown(tr('style.video_workflow_how'))
        
            # Get available workflows and filter by template type
            all_workflows = pixelle_video.media.list_workflows()
            
            # Filter workflows based on template media type
            if template_media_type == "video":
                # Only show video_ workflows
                workflows = [wf for wf in all_workflows if "video_" in wf["key"].lower()]
            else:
                # Only show image_ workflows (exclude video_)
                workflows = [wf for wf in all_workflows if "video_" not in wf["key"].lower()]
        
            # Build options for selectbox
            # Display: "image_flux.json - Runninghub"
            # Value: "runninghub/image_flux.json"
            workflow_options = [wf["display_name"] for wf in workflows]
            workflow_keys = [wf["key"] for wf in workflows]
            workflow_display_map = {
                str(wf["key"]): str(wf["display_name"])
                for wf in all_workflows
            }
        
            # If user has a saved preference in config, try to match it
            comfyui_config = config_manager.get_comfyui_config()
            # Select config based on template type (image or video)
            media_config_key = "video" if template_media_type == "video" else "image"
            saved_workflow = comfyui_config.get(media_config_key, {}).get("default_workflow")
            default_workflow_index = resolve_selectbox_default_index(
                domain=media_config_key,
                workflow_keys=workflow_keys,
                configured_workflow=saved_workflow,
            )
        
            workflow_display = st.selectbox(
                "Workflow",
                workflow_options if workflow_options else ["No workflows found"],
                index=default_workflow_index,
                label_visibility="collapsed",
                key="media_workflow_select"
            )
        
            # Get the actual workflow key (e.g., "runninghub/image_flux.json")
            if workflow_options:
                workflow_selected_index = workflow_options.index(workflow_display)
                workflow_key = workflow_keys[workflow_selected_index]
            else:
                workflow_key = None
            
            render_selfhost_workflow_notice(
                workflow_key,
                expanded=is_selfhost_workflow(workflow_key),
            )
        
            # Get media size from template
            media_width = st.session_state.get('template_media_width')
            media_height = st.session_state.get('template_media_height')
            
            # Display media size info (read-only)
            if template_media_type == "video":
                size_info_text = tr('style.video_size_info', width=media_width, height=media_height)
            else:
                size_info_text = tr('style.image_size_info', width=media_width, height=media_height)
            st.info(f"📐 {size_info_text}")
        
            if template_media_type == "video":
                current_prefix = comfyui_config.get(media_config_key, {}).get("prompt_prefix", "")

                prompt_prefix = st.text_area(
                    tr('style.prompt_prefix'),
                    value=current_prefix,
                    placeholder=tr("style.prompt_prefix_placeholder"),
                    height=80,
                    label_visibility="visible",
                    help=tr("style.prompt_prefix_help")
                )

                with render_middle_column_detail_section(tr("style.video_preview_title")):
                    test_prompt = st.text_input(
                        tr("style.test_video_prompt"),
                        value="a dog running in the park",
                        help=tr("style.test_prompt_help"),
                        key="style_test_prompt"
                    )

                    if st.button(tr("style.video_preview"), key="preview_style", width="stretch"):
                        with st.spinner(tr("style.video_previewing")):
                            try:
                                preview_result = _generate_single_style_preview_result(
                                    pixelle_video=pixelle_video,
                                    workflow_key=workflow_key,
                                    media_width=int(media_width),
                                    media_height=int(media_height),
                                    test_prompt=test_prompt,
                                    prompt_prefix=prompt_prefix,
                                    media_type=template_media_type,
                                )
                                final_prompt = preview_result["final_prompt"]
                                preview_media_path = preview_result["preview_media_path"]

                                if preview_media_path:
                                    st.success(tr("style.video_preview_success"))
                                    render_generated_style_preview(preview_media_path, template_media_type)
                                    st.info(f"**{tr('style.final_prompt_label')}**\n{final_prompt}")
                                    st.caption(f"Preview path: {preview_media_path}")
                                else:
                                    st.error(tr("style.preview_failed_general"))
                            except Exception as e:
                                st.error(tr("style.preview_failed", error=str(e)))
                                logger.exception(e)
            else:
                _call_with_streamlit_fragment(
                    _render_image_prompt_prefix_library,
                    pixelle_video=pixelle_video,
                    workflow_key=workflow_key,
                    media_width=int(media_width),
                    media_height=int(media_height),
                    workflow_display_map=workflow_display_map,
                )
                prompt_prefix = st.session_state.get("prompt_prefix_effective_value", "")
        
    
    else:
        # Template doesn't need images - show simplified message
        with render_middle_column_collapsible_section(
            tr("section.image"),
            expanded=True,
        ):
            st.info("ℹ️ " + tr("image.not_required"))
            st.caption(tr("image.not_required_hint"))
            
            # Get media size from template (even though not used, for consistency)
            media_width = st.session_state.get('template_media_width')
            media_height = st.session_state.get('template_media_height')
            
            # Set default values for later use
            workflow_key = None
            prompt_prefix = ""
    
    storyboard_payload = build_storyboard_control_payload(
        world_preset_id=storyboard_world_preset_id,
        shot_preset_id=storyboard_shot_preset_id,
        consistency_strength=storyboard_consistency_strength,
        content_mode=storyboard_content_mode,
        role_strategy=storyboard_role_strategy,
        role_locking_strength=storyboard_role_locking_strength,
        shot_strategy=storyboard_shot_strategy,
        frame_overrides=storyboard_frame_overrides,
    )

    # Return all style configuration parameters
    result = {
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice if tts_mode == "local" else None,
        "tts_speed": tts_speed,
        "tts_workflow": tts_workflow_key if tts_mode == "comfyui" else None,
        "ref_audio": str(ref_audio_path) if ref_audio_path else None,
        "ref_audio_text": ref_audio_text if tts_mode == "comfyui" and ref_audio_text else None,
        "render_backend": render_backend,
        "tts_audio_strategy": tts_audio_strategy,
        **tts_split_settings,
        "frame_template": frame_template,
        "template_params": custom_values_for_video if custom_values_for_video else None,
        "media_workflow": workflow_key,
        "prompt_prefix": prompt_prefix if prompt_prefix else "",
        "media_width": media_width,
        "media_height": media_height,
        "text_rendering": text_rendering,
        **element_animation_settings,
        **storyboard_payload,
    }
    return result


def render_element_animation_controls() -> dict:
    """Render optional SAM3.1 element micro-motion controls."""
    configured = config_manager.config.render.element_animation
    backend_options = ["hyperframes_canvas", "python_ffmpeg"]
    intensity_options = ["low", "medium", "high"]
    configured_backend = (
        configured.backend
        if configured.backend in backend_options
        else "hyperframes_canvas"
    )
    configured_intensity = (
        configured.intensity
        if configured.intensity in intensity_options
        else "medium"
    )

    with render_middle_column_collapsible_section(
        tr("section.element_animation"),
        expanded=False,
    ):
        enabled = st.toggle(
            tr("element_animation.enabled"),
            value=bool(configured.enabled),
            help=tr("element_animation.enabled_help"),
            key="element_animation_enabled",
        )
        subject_count = st.slider(
            tr("element_animation.subject_count"),
            min_value=1,
            max_value=8,
            value=max(1, int(configured.subject_count)),
            disabled=not enabled,
            key="element_animation_subject_count",
        )

        with render_middle_column_detail_section(tr("element_animation.advanced")):
            candidate_limit = st.slider(
                tr("element_animation.candidate_limit"),
                min_value=subject_count,
                max_value=12,
                value=max(subject_count, int(configured.candidate_limit)),
                disabled=not enabled,
                key="element_animation_candidate_limit",
            )
            backend = st.selectbox(
                tr("element_animation.backend"),
                options=backend_options,
                index=backend_options.index(configured_backend),
                format_func=lambda value: tr(f"element_animation.backend.{value}"),
                disabled=not enabled,
                key="element_animation_backend",
            )
            intensity = st.selectbox(
                tr("element_animation.intensity"),
                options=intensity_options,
                index=intensity_options.index(configured_intensity),
                format_func=lambda value: tr(f"element_animation.intensity.{value}"),
                disabled=not enabled,
                key="element_animation_intensity",
            )
            prompt = st.text_input(
                tr("element_animation.prompt"),
                value=configured.prompt or "",
                disabled=not enabled,
                key="element_animation_prompt",
            )
            workflow = st.text_input(
                tr("element_animation.workflow"),
                value=configured.workflow or "image_sam31_segment.json",
                disabled=not enabled,
                key="element_animation_workflow",
            )

    return {
        "element_animation_enabled": enabled,
        "element_animation_backend": backend,
        "element_animation_subject_count": subject_count,
        "element_animation_candidate_limit": candidate_limit,
        "element_animation_prompt": prompt.strip() or None,
        "element_animation_intensity": intensity,
        "element_animation_workflow": workflow.strip() or "image_sam31_segment.json",
    }


def render_render_backend_selector() -> str:
    """Render the per-task render backend selector for Web UI."""
    options = list(SUPPORTED_RENDER_BACKENDS)
    configured_backend = get_render_backend_default(config_manager.config.render.backend)

    selected_backend = st.radio(
        tr("render_backend.label"),
        options,
        index=options.index(configured_backend),
        horizontal=True,
        format_func=lambda value: tr(f"render_backend.option.{value}"),
        key="render_backend_select",
        help=tr("render_backend.help"),
    )
    st.caption(tr(f"render_backend.caption.{selected_backend}"))
    return selected_backend


def _render_tts_inline_radio(
    label: str,
    options: Sequence[str],
    *,
    index: int,
    format_func: Callable[[str], str],
    key: str,
    help_text: str,
) -> str:
    """Render compact TTS choice controls with one shared layout contract."""
    return st.radio(
        label,
        options,
        index=index,
        horizontal=True,
        format_func=format_func,
        key=key,
        help=help_text,
    )


def render_tts_audio_strategy_selector() -> str:
    """Render the per-task TTS audio strategy selector for Web UI."""
    options = list(SUPPORTED_TTS_AUDIO_STRATEGIES)
    configured_strategy = get_tts_audio_strategy_default(
        config_manager.config.render.timing.tts_audio_strategy
    )

    selected_strategy = _render_tts_inline_radio(
        tr("tts_audio_strategy.label"),
        options,
        index=options.index(configured_strategy),
        format_func=lambda value: tr(f"tts_audio_strategy.option.{value}"),
        key="tts_audio_strategy_select",
        help_text=tr("tts_audio_strategy.help"),
    )
    st.caption(tr(f"tts_audio_strategy.caption.{selected_strategy}"))
    return selected_strategy


def render_tts_split_settings() -> dict:
    """Render advanced TTS text segmentation settings for Web UI."""
    timing_config = config_manager.config.render.timing
    options = list(SUPPORTED_TTS_SPLIT_MODES)
    configured_mode = get_tts_split_mode_default(timing_config.tts_split_mode)

    selected_mode = _render_tts_inline_radio(
        tr("tts_split_mode.label"),
        options,
        index=options.index(configured_mode),
        format_func=lambda value: tr(f"tts_split_mode.option.{value}"),
        key="tts_split_mode_select",
        help_text=tr("tts_split_mode.help"),
    )
    st.caption(tr(f"tts_split_mode.caption.{selected_mode}"))

    settings = {
        "tts_split_mode": selected_mode,
        "max_chars_per_tts_segment": timing_config.max_chars_per_tts_segment,
        "tts_split_overflow_policy": timing_config.tts_split_overflow_policy,
        "tts_boundary_search_radius": timing_config.tts_boundary_search_radius,
        "tts_soft_overflow_chars": timing_config.tts_soft_overflow_chars,
        "tts_audio_boundary_fade_ms": timing_config.tts_audio_boundary_fade_ms,
        "tts_sentence_joiner_mode": timing_config.tts_sentence_joiner_mode,
        "caption_punctuation_mode": timing_config.caption_punctuation_mode,
        "preserve_natural_punctuation": timing_config.preserve_natural_punctuation,
    }

    settings["preserve_natural_punctuation"] = bool(
        st.checkbox(
            tr("tts_text_policy.preserve_natural_punctuation"),
            value=bool(timing_config.preserve_natural_punctuation),
            key="preserve_natural_punctuation",
            help=tr("tts_text_policy.preserve_natural_punctuation_help"),
        )
    )

    joiner_options = list(SUPPORTED_TTS_SENTENCE_JOINER_MODES)
    joiner_default = (
        timing_config.tts_sentence_joiner_mode
        if timing_config.tts_sentence_joiner_mode in joiner_options
        else "direct"
    )
    settings["tts_sentence_joiner_mode"] = st.selectbox(
        tr("tts_text_policy.joiner_mode"),
        joiner_options,
        index=joiner_options.index(joiner_default),
        format_func=lambda value: tr(f"tts_text_policy.joiner_mode.{value}"),
        key="tts_sentence_joiner_mode",
        help=tr("tts_text_policy.joiner_mode_help"),
    )

    caption_options = list(SUPPORTED_CAPTION_PUNCTUATION_MODES)
    caption_default = (
        timing_config.caption_punctuation_mode
        if timing_config.caption_punctuation_mode in caption_options
        else "strip_all"
    )
    settings["caption_punctuation_mode"] = st.selectbox(
        tr("tts_text_policy.caption_punctuation_mode"),
        caption_options,
        index=caption_options.index(caption_default),
        format_func=lambda value: tr(f"tts_text_policy.caption_punctuation_mode.{value}"),
        key="caption_punctuation_mode",
        help=tr("tts_text_policy.caption_punctuation_mode_help"),
    )

    if selected_mode != "internal_only":
        settings["max_chars_per_tts_segment"] = int(
            st.number_input(
                tr("tts_split_mode.max_chars"),
                min_value=1,
                value=int(timing_config.max_chars_per_tts_segment),
                step=1,
                key="max_chars_per_tts_segment",
            )
        )

    settings["tts_audio_boundary_fade_ms"] = int(
        st.number_input(
            tr("tts_split_mode.boundary_fade_ms"),
            min_value=0,
            value=int(timing_config.tts_audio_boundary_fade_ms),
            step=1,
            key="tts_audio_boundary_fade_ms",
        )
    )
    return settings
