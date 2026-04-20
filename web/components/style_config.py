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

import os
from pathlib import Path
from uuid import uuid4

import streamlit as st
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.prompt_prefix_library import (
    filter_prompt_prefix_items,
    get_effective_image_prompt_prefix,
    get_prompt_prefix_category_label,
    get_prompt_prefix_preview_asset,
)
from pixelle_video.prompts.prompt_prefix_generation import (
    build_prompt_prefix_generation_prompt,
)
from pixelle_video.utils.prompt_prefix_generation import (
    PromptPrefixGenerationResult,
    build_prompt_prefix_preview_batch,
    sanitize_prompt_prefix_candidates,
)
from web.i18n import get_language, tr
from web.utils.async_helpers import run_async
from web.utils.preview_media import load_preview_media
from web.utils.prompt_prefix_ui import (
    create_prompt_prefix_item,
    get_localized_prompt_prefix_category_options,
    persist_uploaded_prompt_prefix_preview,
    sanitize_prompt_prefix_preview_selection,
    toggle_prompt_prefix_preview_selection,
)
from web.utils.streamlit_helpers import check_and_warn_selfhost_workflow, safe_rerun
from web.utils.workflow_defaults import resolve_selectbox_default_index


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
    library["items"] = [
        item for item in library.get("items", [])
        if item.get("id") != item_id
    ]
    if library.get("active_prefix_id") == item_id:
        library["active_prefix_id"] = None
    _save_image_prompt_prefix_library(library)


def _set_active_image_prompt_prefix(item_id: str):
    """Set active image prompt prefix id and persist it."""
    config_manager.set_active_image_prompt_prefix(item_id)
    config_manager.save()


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
            st.caption(f"{style_label} · {scene_label} · {item.get('source', 'manual')}")
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
                        from pixelle_video.utils.prompt_helper import build_image_prompt

                        preview_results = []
                        for item in preview_items:
                            final_prompt = build_image_prompt(test_prompt, item["content"])
                            media_result = run_async(
                                pixelle_video.media(
                                    prompt=final_prompt,
                                    workflow=workflow_key,
                                    media_type="image",
                                    width=int(media_width),
                                    height=int(media_height),
                                )
                            )
                            if media_result.url:
                                preview_results.append(
                                    {
                                        "id": item["id"],
                                        "name": item["name"],
                                        "content": item["content"],
                                        "final_prompt": final_prompt,
                                        "preview_media_path": media_result.url,
                                    }
                                )
                        st.session_state["prompt_prefix_preview_results"] = preview_results
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
    st.session_state["prompt_prefix_panel_mode"] = mode
    st.session_state["prompt_prefix_panel_item_id"] = item_id


def _close_prompt_prefix_panel():
    """Close the prompt-prefix side panel."""
    st.session_state.pop("prompt_prefix_panel_mode", None)
    st.session_state.pop("prompt_prefix_panel_item_id", None)
    st.session_state.pop("prompt_prefix_delete_confirm_id", None)


def _build_prompt_prefix_live_preview_map() -> dict[str, str]:
    """Collect session-scoped preview overrides for gallery cards."""
    preview_map: dict[str, str] = {}

    for result in st.session_state.get("prompt_prefix_preview_results", []):
        preview_path = result.get("preview_media_path")
        if preview_path:
            preview_map[result["id"]] = preview_path

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
    from pixelle_video.utils.prompt_helper import build_image_prompt

    preview_results: list[dict] = []
    for item in items:
        final_prompt = build_image_prompt(test_prompt, item["content"])
        media_result = run_async(
            pixelle_video.media(
                prompt=final_prompt,
                workflow=workflow_key,
                media_type="image",
                width=int(media_width),
                height=int(media_height),
            )
        )
        if media_result.url:
            preview_results.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "content": item["content"],
                    "final_prompt": final_prompt,
                    "preview_media_path": media_result.url,
                }
            )

    return preview_results


def _render_image_prompt_prefix_library(pixelle_video, workflow_key: str, media_width: int, media_height: int) -> str:
    """Render the gallery-style image prompt prefix library UI and return effective prefix content."""
    language = get_language()
    image_config = config_manager.config.comfyui.image
    library = config_manager.get_image_prompt_prefix_library()
    library_items = library.get("items", [])
    library_items_by_id = {item["id"]: item for item in library_items}
    active_prefix_id = library.get("active_prefix_id")
    active_item = library_items_by_id.get(active_prefix_id)
    effective_prefix = get_effective_image_prompt_prefix(image_config)

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

    st.markdown(f"**{tr('style.prompt_prefix')}**")
    st.caption(tr("style.prefix_library.title"))

    with st.container(border=True):
        active_info_col, active_action_col = st.columns([2.3, 1], gap="large")
        with active_info_col:
            if active_item:
                st.markdown(f"### {active_item['name']}")
                st.caption(
                    f"{tr('style.prefix_library.active')} · "
                    f"{get_prompt_prefix_category_label(active_item['style_category_id'], 'style', language)} · "
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
                _open_prompt_prefix_panel("details", active_item["id"])
                safe_rerun()
            st.caption(tr("style.prefix_library.reference_cover"))

    filter_style_col, filter_scene_col, filter_keyword_col, add_style_col, ai_generate_col = st.columns(
        [1, 1, 1.2, 0.8, 0.9],
        gap="small",
    )
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
    with add_style_col:
        if st.button(tr("style.prefix_library.toolbar_add"), key="prompt_prefix_toolbar_add", width="stretch"):
            _open_prompt_prefix_panel("manual")
            safe_rerun()
    with ai_generate_col:
        if st.button(tr("style.prefix_library.toolbar_ai"), key="prompt_prefix_toolbar_ai", width="stretch"):
            _open_prompt_prefix_panel("ai")
            safe_rerun()

    st.caption(tr("style.prefix_library.compare_count", count=len(selected_preview_ids)))

    filtered_items = filter_prompt_prefix_items(
        library_items,
        style_category_id=selected_style or None,
        scene_category_id=selected_scene or None,
        keyword=keyword,
    )

    gallery_col, panel_col = st.columns([2.25, 1.05], gap="large")
    with gallery_col:
        if not filtered_items:
            st.caption(tr("style.prefix_library.no_items"))
        else:
            num_cols = 4
            gallery_columns = st.columns(num_cols)
            for idx, item in enumerate(filtered_items):
                style_label = get_prompt_prefix_category_label(item["style_category_id"], "style", language)
                scene_label = get_prompt_prefix_category_label(item["scene_category_id"], "scene", language)
                cover_asset = live_preview_map.get(item["id"]) or get_prompt_prefix_preview_asset(item)
                is_active = item["id"] == active_prefix_id
                in_preview = item["id"] in selected_preview_ids

                with gallery_columns[idx % num_cols]:
                    with st.container(border=True):
                        badge_col, compare_col = st.columns([1.2, 1], gap="small")
                        with badge_col:
                            st.caption(item.get("source", "manual"))
                        with compare_col:
                            compare_label = (
                                tr("style.prefix_library.compare_chip_active")
                                if in_preview
                                else tr("style.prefix_library.compare_chip_add")
                            )
                            if st.button(
                                compare_label,
                                key=f"compare_prefix_card_{item['id']}",
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

                        st.image(cover_asset, width="stretch")
                        if st.button(
                            item["name"],
                            key=f"open_prefix_details_{item['id']}",
                            width="stretch",
                            type="tertiary",
                        ):
                            _open_prompt_prefix_panel("details", item["id"])
                            safe_rerun()
                        st.caption(f"{style_label} · {scene_label}")
                        if item.get("note"):
                            st.caption(item["note"])
                        if st.button(
                            tr("template.selected") if is_active else tr("template.select_button"),
                            key=f"select_prefix_card_{item['id']}",
                            width="stretch",
                            type="primary" if is_active else "secondary",
                        ):
                            _set_active_image_prompt_prefix(item["id"])
                            safe_rerun()

    with panel_col:
        with st.container(border=True):
            panel_header_col, panel_close_col = st.columns([2.2, 1], gap="small")
            with panel_header_col:
                if panel_mode == "details" and panel_item:
                    st.markdown(f"### {tr('style.prefix_library.view_details')}")
                elif panel_mode == "edit" and panel_item:
                    st.markdown(f"### {tr('style.prefix_library.edit')}")
                elif panel_mode == "manual":
                    st.markdown(f"### {tr('style.prefix_library.manual_create')}")
                elif panel_mode == "ai":
                    st.markdown(f"### {tr('style.prefix_library.ai_generate')}")
                else:
                    st.markdown(f"### {tr('style.prefix_library.panel_empty')}")
            with panel_close_col:
                if panel_mode and st.button(
                    tr("style.prefix_library.close_panel"),
                    key="prompt_prefix_close_panel",
                    width="stretch",
                ):
                    _close_prompt_prefix_panel()
                    safe_rerun()

            if panel_mode == "details" and panel_item:
                detail_cover_asset = live_preview_map.get(panel_item["id"]) or get_prompt_prefix_preview_asset(panel_item)
                st.image(detail_cover_asset, width="stretch")
                st.caption(
                    f"{get_prompt_prefix_category_label(panel_item['style_category_id'], 'style', language)} · "
                    f"{get_prompt_prefix_category_label(panel_item['scene_category_id'], 'scene', language)} · "
                    f"{panel_item.get('source', 'manual')}"
                )
                if panel_item.get("note"):
                    st.caption(panel_item["note"])
                st.caption(
                    tr("style.prefix_library.workflow_preview_hint")
                    if panel_item["id"] in live_preview_map
                    else tr("style.prefix_library.reference_cover")
                )
                st.code(panel_item["content"], language=None)

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
                        duplicated_item = create_prompt_prefix_item(
                            name=f"{panel_item['name']} Copy",
                            content=panel_item["content"],
                            style_category_id=panel_item["style_category_id"],
                            scene_category_id=panel_item["scene_category_id"],
                            note=panel_item.get("note", ""),
                            source="manual",
                            preview_asset_path=panel_item.get("preview_asset_path"),
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

            elif panel_mode in {"manual", "edit"}:
                editing_item = panel_item if panel_mode == "edit" else None
                form_item_id = editing_item["id"] if editing_item else f"manual-{uuid4().hex[:12]}"
                form_suffix = f"{panel_mode}_{form_item_id}"
                current_cover = live_preview_map.get(form_item_id)
                if editing_item:
                    current_cover = current_cover or get_prompt_prefix_preview_asset(editing_item)
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
                        uploaded_preview_path = persist_uploaded_prompt_prefix_preview(uploaded_preview, form_item_id)
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
                        )
                        _upsert_image_prompt_prefix_item(saved_item, set_active=set_active_on_save)
                        _open_prompt_prefix_panel("details", saved_item["id"])
                        safe_rerun()

            elif panel_mode == "ai":
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
                generate_col, preview_col = st.columns(2, gap="small")
                with generate_col:
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
                with preview_col:
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
                        candidate_cover = candidate_preview_map.get(candidate["id"]) or get_prompt_prefix_preview_asset(candidate)
                        with st.container(border=True):
                            st.image(candidate_cover, width="stretch")
                            st.markdown(f"**{candidate['name']}**")
                            st.caption(
                                f"{get_prompt_prefix_category_label(candidate['style_category_id'], 'style', language)} · "
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
                                    _upsert_image_prompt_prefix_item(candidate)
                                    safe_rerun()
                            with active_col:
                                if st.button(
                                    tr("style.prefix_library.set_active"),
                                    key=f"set_generated_active_prefix_{candidate['id']}",
                                    width="stretch",
                                ):
                                    _upsert_image_prompt_prefix_item(candidate, set_active=True)
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

            else:
                st.caption(tr("style.prefix_library.panel_empty_hint"))

    preview_title = tr("style.preview_title")
    with st.expander(preview_title, expanded=False):
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
                                _upsert_image_prompt_prefix_item(candidate_item, set_active=True)
                            else:
                                _set_active_image_prompt_prefix(preview_result["id"])
                            safe_rerun()
                    st.info(f"**{tr('style.final_prompt_label')}**\n{preview_result['final_prompt']}")

    return effective_prefix


def render_style_config(pixelle_video):
    """Render style configuration section (middle column)"""
    # TTS Section (moved from left column)
    # ====================================================================
    with st.container(border=True):
        st.markdown(f"**{tr('section.tts')}**")
        
        with st.expander(tr("help.feature_description"), expanded=False):
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
            index=0 if tts_config.get("inference_mode", "local") == "local" else 1,
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
                tts_workflow_key = "selfhost/tts_edge.json"  # fallback
            
            # Check and warn for selfhost TTS workflow (auto popup if not confirmed)
            check_and_warn_selfhost_workflow(tts_workflow_key)
            
            # Reference audio upload (optional, for voice cloning)
            ref_audio_file = st.file_uploader(
                tr("tts.ref_audio"),
                type=["mp3", "wav", "flac", "m4a", "aac", "ogg"],
                help=tr("tts.ref_audio_help"),
                key="ref_audio_upload"
            )
            
            # Save uploaded ref_audio to temp file if provided
            ref_audio_path = None
            if ref_audio_file is not None:
                # Audio preview player (directly play uploaded file)
                st.audio(ref_audio_file)
                
                # Save to temp directory
                temp_dir = Path("temp")
                temp_dir.mkdir(exist_ok=True)
                ref_audio_path = temp_dir / f"ref_audio_{ref_audio_file.name}"
                with open(ref_audio_path, "wb") as f:
                    f.write(ref_audio_file.getbuffer())
            
            # Variables for video generation
            selected_voice = None
            tts_speed = None
        
        # ================================================================
        # TTS Preview (works for both modes)
        # ================================================================
        with st.expander(tr("tts.preview_title"), expanded=False):
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
                            if ref_audio_path:
                                tts_params["ref_audio"] = str(ref_audio_path)
                        
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
    
    with st.container(border=True):
        st.markdown(f"**{tr('section.template')}**")
        
        with st.expander(tr("help.feature_description"), expanded=False):
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
        with st.expander(tr("template.gallery_view"), expanded=True):
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
                                    st.image(preview_path, width="stretch")
                                else:
                                    # Placeholder for templates without preview (fixed height, compact layout)
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
                                            ">{template.display_info.name}</div>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )
                                
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
        with st.expander(tr("template.preview_title"), expanded=False):
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
        with st.container(border=True):
            # Dynamic section title based on template type
            if template_media_type == "video":
                section_title = tr('section.video')
            else:
                section_title = tr('section.image')
            
            st.markdown(f"**{section_title}**")
        
            # 1. ComfyUI Workflow selection
            with st.expander(tr("help.feature_description"), expanded=False):
                st.markdown(f"**{tr('help.what')}**")
                if template_media_type == "video":
                    st.markdown(tr('style.video_workflow_what'))
                else:
                    st.markdown(tr("style.workflow_what"))
                st.markdown(f"**{tr('help.how')}**")
                if template_media_type == "video":
                    st.markdown(tr('style.video_workflow_how'))
                else:
                    st.markdown(tr("style.workflow_how"))
        
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
            
            # Check and warn for selfhost media workflow (auto popup if not confirmed)
            check_and_warn_selfhost_workflow(workflow_key)
        
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

                with st.expander(tr("style.video_preview_title"), expanded=False):
                    test_prompt = st.text_input(
                        tr("style.test_video_prompt"),
                        value="a dog running in the park",
                        help=tr("style.test_prompt_help"),
                        key="style_test_prompt"
                    )

                    if st.button(tr("style.video_preview"), key="preview_style", width="stretch"):
                        with st.spinner(tr("style.video_previewing")):
                            try:
                                from pixelle_video.utils.prompt_helper import build_image_prompt

                                final_prompt = build_image_prompt(test_prompt, prompt_prefix)
                                media_result = run_async(pixelle_video.media(
                                    prompt=final_prompt,
                                    workflow=workflow_key,
                                    media_type=template_media_type,
                                    width=int(media_width),
                                    height=int(media_height)
                                ))
                                preview_media_path = media_result.url

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
                prompt_prefix = _render_image_prompt_prefix_library(
                    pixelle_video=pixelle_video,
                    workflow_key=workflow_key,
                    media_width=int(media_width),
                    media_height=int(media_height),
                )
        
    
    else:
        # Template doesn't need images - show simplified message
        with st.container(border=True):
            st.markdown(f"**{tr('section.image')}**")
            st.info("ℹ️ " + tr("image.not_required"))
            st.caption(tr("image.not_required_hint"))
            
            # Get media size from template (even though not used, for consistency)
            media_width = st.session_state.get('template_media_width')
            media_height = st.session_state.get('template_media_height')
            
            # Set default values for later use
            workflow_key = None
            prompt_prefix = ""
    
    # Return all style configuration parameters
    return {
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice if tts_mode == "local" else None,
        "tts_speed": tts_speed if tts_mode == "local" else None,
        "tts_workflow": tts_workflow_key if tts_mode == "comfyui" else None,
        "ref_audio": str(ref_audio_path) if ref_audio_path else None,
        "frame_template": frame_template,
        "template_params": custom_values_for_video if custom_values_for_video else None,
        "media_workflow": workflow_key,
        "prompt_prefix": prompt_prefix if prompt_prefix else "",
        "media_width": media_width,
        "media_height": media_height
    }
