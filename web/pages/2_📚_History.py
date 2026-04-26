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
History Page - View generation history and manage tasks
"""
# ruff: noqa: E402

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.config import config_manager
from web.components.header import render_header
from web.components.style_config import resolve_storyboard_preset_label
from web.i18n import tr
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.utils.async_helpers import run_async
from web.utils.render_backend_ui import (
    format_task_boolean,
    get_task_caption_rendering_summary,
    get_task_image_text_policy_summary,
    get_task_render_backend,
    get_task_render_backend_fallback_reason,
    get_task_text_layer_summary,
)
from web.utils.storyboard_history import resolve_history_storyboard_scene_count

# Page config
st.set_page_config(
    page_title="History - 懒人同城",
    page_icon="📚",
    layout="wide",
)


def build_history_page_css() -> str:
    """Build scoped CSS for History task card actions."""
    return """
    <style>
    div[class*="st-key-history_card_actions_"] div[data-testid="stHorizontalBlock"] {
        width: min(12rem, 82%);
        margin-inline: auto;
        gap: 0.6rem !important;
        justify-content: space-between;
    }
    div[class*="st-key-history_card_actions_"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }
    div[class*="st-key-history_card_actions_"] .stColumn button {
        width: 2.2rem !important;
        min-height: 1.45rem;
        padding: 0;
        margin-inline: 0;
        border-radius: 6px;
        font-size: 0.72rem;
        line-height: 1;
    }
    </style>
    """


def format_duration(seconds: float) -> str:
    """Format duration in seconds to readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def format_file_size(bytes_size: int) -> str:
    """Format file size in bytes to readable string"""
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f}KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / 1024 / 1024:.1f}MB"
    else:
        return f"{bytes_size / 1024 / 1024 / 1024:.2f}GB"


def format_datetime(iso_string: str) -> str:
    """Format ISO datetime string to readable format"""
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return iso_string


def truncate_text(text: str, max_length: int = 60) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def extract_storyboard_planning_snapshot(detail: dict) -> dict:
    """Read storyboard planning snapshot from task detail payloads."""
    storyboard = detail.get("storyboard")
    storyboard_snapshot = getattr(storyboard, "planning_snapshot", None)
    if storyboard_snapshot:
        return dict(storyboard_snapshot)

    metadata = detail.get("metadata", {}) or {}
    input_snapshot = metadata.get("input", {}).get("storyboard_planning_snapshot")
    if input_snapshot:
        return dict(input_snapshot)

    result_snapshot = metadata.get("result", {}).get("storyboard_planning_snapshot")
    if result_snapshot:
        return dict(result_snapshot)

    return {}


def summarize_storyboard_planning_snapshot(snapshot: dict) -> list[tuple[str, str]]:
    """Summarize the key storyboard planning fields for History UI."""

    def _resolve_preset_label_from_snapshot(
        snapshot_preset: object | None,
        candidate_ids: list[str | None],
        library: dict,
    ) -> str | None:
        if snapshot_preset not in (None, ""):
            snapshot_label = resolve_storyboard_preset_label(snapshot_preset)
            if snapshot_label:
                return snapshot_label

        first_non_empty_candidate = None
        for preset_id in candidate_ids:
            if preset_id in (None, ""):
                continue
            if first_non_empty_candidate is None:
                first_non_empty_candidate = str(preset_id)
            for item in library.get("items", []):
                if item.get("preset_id") == preset_id:
                    return resolve_storyboard_preset_label(item)

        return first_non_empty_candidate

    def _translate_storyboard_option(category: str, value: str | None) -> str | None:
        if value in (None, ""):
            return None

        translation_key = f"storyboard.option.{category}.{value}"
        localized_value = tr(translation_key)
        if localized_value != translation_key:
            return localized_value
        return str(value)

    world_preset_label = _resolve_preset_label_from_snapshot(
        snapshot.get("world_preset"),
        [snapshot.get("world_preset_id")],
        config_manager.get_storyboard_world_preset_library(),
    )
    shot_preset_label = _resolve_preset_label_from_snapshot(
        snapshot.get("shot_preset"),
        [
            snapshot.get("requested_shot_preset_id"),
            snapshot.get("effective_final_shot_preset"),
            snapshot.get("shot_preset_id"),
        ],
        config_manager.get_storyboard_shot_preset_library(),
    )

    summary_items = [
        ("history.detail.storyboard_world_preset", world_preset_label),
        ("history.detail.storyboard_shot_preset", shot_preset_label),
        (
            "history.detail.storyboard_content_mode",
            _translate_storyboard_option(
                "content_mode",
                snapshot.get("resolved_content_mode") or snapshot.get("content_mode"),
            ),
        ),
        (
            "history.detail.storyboard_consistency",
            _translate_storyboard_option(
                "consistency",
                snapshot.get("selected_consistency_strength")
                or snapshot.get("consistency_strength"),
            ),
        ),
        (
            "history.detail.storyboard_role_strategy",
            _translate_storyboard_option(
                "role_strategy",
                snapshot.get("resolved_role_strategy") or snapshot.get("role_strategy"),
            ),
        ),
        (
            "history.detail.storyboard_role_locking",
            snapshot.get("selected_role_locking_strength")
            or snapshot.get("role_locking_strength"),
        ),
        (
            "history.detail.storyboard_shot_strategy",
            _translate_storyboard_option(
                "shot_strategy",
                snapshot.get("selected_shot_strategy") or snapshot.get("shot_strategy"),
            ),
        ),
    ]

    normalized: list[tuple[str, str]] = []
    for label_key, value in summary_items:
        if value in (None, ""):
            continue
        normalized.append((label_key, str(value)))
    return normalized


def render_sidebar_controls(pixelle_video):
    """Render sidebar with statistics and filters"""
    with st.sidebar:
        # Statistics
        st.markdown(f"**📊 {tr('history.total_tasks')}**")
        stats = run_async(pixelle_video.history.get_statistics())
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(tr("history.completed_count"), stats.get("completed", 0))
        with col2:
            st.metric(tr("history.failed_count"), stats.get("failed", 0))
        
        st.divider()
        
        # Filters
        st.markdown(f"**🔍 {tr('history.filter_status')}**")
        status_options = {
            "all": tr("history.status_all"),
            "completed": tr("history.status_completed"),
            "failed": tr("history.status_failed"),
            "running": tr("history.status_running"),
            "pending": tr("history.status_pending"),
        }
        
        selected_status = st.selectbox(
            tr("history.filter_status"),
            options=list(status_options.keys()),
            format_func=lambda x: status_options[x],
            key="filter_status",
            label_visibility="collapsed"
        )
        
        filter_status = None if selected_status == "all" else selected_status
        
        # Sort
        st.markdown(f"**📊 {tr('history.sort_by')}**")
        
        sort_options = {
            "created_at": tr("history.sort_created_at"),
            "completed_at": tr("history.sort_completed_at"),
            "title": tr("history.sort_title"),
            "duration": tr("history.sort_duration"),
        }
        
        sort_by = st.selectbox(
            tr("history.sort_by"),
            options=list(sort_options.keys()),
            format_func=lambda x: sort_options[x],
            key="sort_by",
            label_visibility="collapsed"
        )
        
        sort_order_options = {
            "desc": tr("history.sort_order_desc"),
            "asc": tr("history.sort_order_asc"),
        }
        
        sort_order = st.radio(
            "Sort Order",
            options=list(sort_order_options.keys()),
            format_func=lambda x: sort_order_options[x],
            key="sort_order",
            label_visibility="collapsed",
            horizontal=True
        )
        
        # Page size
        page_size = st.selectbox(
            tr("history.page_size"),
            options=[15, 30, 60],
            index=0,
            key="page_size"
        )
        
        return filter_status, sort_by, sort_order, page_size


def render_grid_task_card(task: dict, pixelle_video):
    """Render a compact grid task card"""
    task_id = task["task_id"]
    title = task.get("title", "Untitled")
    status = task.get("status", "unknown")
    created_at = task.get("created_at", "")
    duration = task.get("duration", 0)
    n_frames = task.get("n_frames", 0)
    video_path = task.get("video_path", "")
    
    # Status badge
    status_map = {
        "completed": "✅",
        "failed": "❌",
        "running": "⏳",
        "pending": "⏸️",
    }
    status_icon = status_map.get(status, "❓")
    
    # Get input text
    detail = run_async(pixelle_video.history.get_task_detail(task_id))
    input_text = ""
    if detail and detail.get("metadata"):
        input_params = detail["metadata"].get("input", {})
        input_text = input_params.get("text", "")
    
    # Card container
    with st.container():
        # Video preview at top
        if video_path and os.path.exists(video_path):
            st.video(video_path, autoplay=False, loop=False, muted=False)
        else:
            st.markdown(
                "<div style='background: #f0f0f0; height: 180px; display: flex; align-items: center; "
                "justify-content: center; border-radius: 4px; font-size: 48px;'>📹</div>",
                unsafe_allow_html=True
            )
        
        # Title + Status (compact) - show actual title from task
        st.markdown(f"**{status_icon} {truncate_text(title, 50)}**")
        
        # Input content (very short)
        if input_text:
            st.caption(truncate_text(input_text, 60))
        
        # Meta info (one line)
        st.caption(f"🕒 {format_datetime(created_at)} | ⏱️ {format_duration(duration)} | 🎬 {n_frames}")
        
        # Action buttons (compact, centered, 3 actions)
        with st.container(key=f"history_card_actions_{task_id}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👁️", key=f"view_{task_id}", help=tr("history.task_card.view_detail"), width="stretch"):
                    st.session_state[f"detail_{task_id}"] = True
                    st.rerun()
            
            with col2:
                if video_path and os.path.exists(video_path):
                    with open(video_path, "rb") as f:
                        st.download_button(
                            "⬇️",
                            data=f,
                            file_name=f"{title}.mp4",
                            mime="video/mp4",
                            key=f"download_{task_id}",
                            help=tr("history.task_card.download"),
                            width="stretch"
                        )
                else:
                    st.button("⬇️", key=f"download_disabled_{task_id}", disabled=True, width="stretch")
            
            with col3:
                if st.button("🗑️", key=f"delete_{task_id}", help=tr("history.task_card.delete"), width="stretch"):
                    st.session_state[f"confirm_delete_{task_id}"] = True
                    st.rerun()
        
        # Delete confirmation (show in modal-like way)
        if st.session_state.get(f"confirm_delete_{task_id}", False):
            st.warning("⚠️ 确认删除?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅", key=f"confirm_yes_{task_id}", width="stretch"):
                    try:
                        success = run_async(pixelle_video.history.delete_task(task_id))
                        if success:
                            st.success(tr("history.action.delete_success"))
                            st.session_state[f"confirm_delete_{task_id}"] = False
                            st.rerun()
                        else:
                            st.error("删除失败")
                    except Exception as e:
                        st.error(f"删除失败: {str(e)}")
            with col2:
                if st.button("❌", key=f"confirm_no_{task_id}", width="stretch"):
                    st.session_state[f"confirm_delete_{task_id}"] = False
                    st.rerun()


def render_task_detail_modal(task_id: str, pixelle_video):
    """Render task detail in three-column layout"""
    detail = run_async(pixelle_video.history.get_task_detail(task_id))
    
    if not detail:
        st.error("Task not found")
        return
    
    metadata = detail["metadata"]
    storyboard = detail["storyboard"]
    planning_snapshot = extract_storyboard_planning_snapshot(detail)
    
    # Close button at the top
    if st.button("❌ " + tr("history.detail.close"), key=f"close_detail_top_{task_id}"):
        st.session_state[f"detail_{task_id}"] = False
        st.rerun()
    
    st.markdown(f"**{tr('history.detail.modal_title')}**")
    st.caption(f"{tr('history.detail.task_id')}: {task_id}")
    
    # Three-column layout
    col_input, col_storyboard, col_video = st.columns([1, 1, 1])
    
    # Left column: Input and config
    with col_input:
        st.markdown(f"**📝 {tr('history.detail.input_params')}**")
        
        input_params = metadata.get("input", {})
        
        # Display input parameters
        st.markdown(f"**{tr('history.detail.mode')}:** {input_params.get('mode', 'N/A')}")
        st.markdown(
            f"**{tr('history.detail.storyboard_scene_count')}:** "
            f"{resolve_history_storyboard_scene_count(detail) or 'N/A'}"
        )
        st.markdown(f"**{tr('history.detail.tts_mode')}:** {input_params.get('tts_inference_mode', 'N/A')}")
        st.markdown(f"**{tr('history.detail.voice')}:** {input_params.get('tts_voice', 'N/A')}")
        st.markdown(
            f"**{tr('history.detail.render_backend')}:** {get_task_render_backend(metadata) or 'N/A'}"
        )
        render_backend_fallback_reason = get_task_render_backend_fallback_reason(metadata)
        if render_backend_fallback_reason:
            st.markdown(f"**{tr('history.detail.render_backend_fallback')}**")
            st.caption(
                tr(
                    "history.detail.render_backend_fallback_reason",
                    reason=render_backend_fallback_reason,
                )
            )
        caption_rendering_summary = get_task_caption_rendering_summary(metadata)
        if caption_rendering_summary:
            st.markdown(f"**{tr('history.detail.caption_rendering')}**")
            st.markdown(
                tr(
                    "history.detail.caption_rendering_summary",
                    enabled=format_task_boolean(
                        caption_rendering_summary["enabled"],
                        true_label=tr("history.detail.boolean_yes"),
                        false_label=tr("history.detail.boolean_no"),
                    ),
                    cue_count=caption_rendering_summary["caption_cue_count"],
                    style_profile=caption_rendering_summary["style_profile_id"],
                    targets=caption_rendering_summary["renderer_targets"],
                )
            )
        text_layer_summary = get_task_text_layer_summary(metadata)
        if text_layer_summary:
            st.markdown(f"**{tr('history.detail.text_layer')}**")
            st.markdown(
                tr(
                    "history.detail.text_layer_summary",
                    renderer=text_layer_summary["renderer"],
                    cue_count=text_layer_summary["cue_count"],
                    native_count=text_layer_summary["native_prompt_hint_count"],
                )
            )
        image_text_policy_summary = get_task_image_text_policy_summary(metadata)
        if image_text_policy_summary:
            st.markdown(f"**{tr('history.detail.image_text_policy')}**")
            st.markdown(
                tr(
                    "history.detail.image_text_policy_summary",
                    status=image_text_policy_summary["status"],
                    suppress_embedded_text=format_task_boolean(
                        image_text_policy_summary["suppress_embedded_text"],
                        true_label=tr("history.detail.boolean_yes"),
                        false_label=tr("history.detail.boolean_no"),
                    ),
                )
            )
        planning_summary = summarize_storyboard_planning_snapshot(planning_snapshot)
        if planning_summary:
            st.markdown(f"**{tr('history.detail.storyboard_planning')}**")
            for label_key, value in planning_summary:
                st.markdown(f"**{tr(label_key)}:** {value}")
            override_count = len(planning_snapshot.get("frame_overrides") or [])
            st.markdown(
                f"**{tr('history.detail.storyboard_override_count')}:** {override_count}"
            )
        
        # Input text
        with st.expander(tr("history.detail.text"), expanded=True):
            st.text_area(
                "Input Text",
                value=input_params.get('text', 'N/A'),
                height=200,
                disabled=True,
                label_visibility="collapsed"
            )
    
    # Middle column: Storyboard frames
    with col_storyboard:
        st.markdown(f"**🎬 {tr('history.detail.storyboard')}**")
        
        if storyboard and storyboard.frames:
            for frame in storyboard.frames:
                with st.expander(f"{tr('history.detail.frame')} {frame.index + 1}", expanded=False):
                    st.markdown(f"**{tr('history.detail.narration')}:**")
                    st.caption(frame.narration)
                    
                    if frame.image_prompt:
                        st.markdown(f"**{tr('history.detail.image_prompt')}:**")
                        st.caption(frame.image_prompt)
                    
                    # Show frame preview (small)
                    col1, col2 = st.columns(2)
                    with col1:
                        if frame.composed_image_path and os.path.exists(frame.composed_image_path):
                            st.image(frame.composed_image_path)
                        elif frame.image_path and os.path.exists(frame.image_path):
                            st.image(frame.image_path)
                    with col2:
                        if frame.video_segment_path and os.path.exists(frame.video_segment_path):
                            st.video(frame.video_segment_path)
                    
                    # Audio player (compact)
                    if frame.audio_path and os.path.exists(frame.audio_path):
                        st.audio(frame.audio_path)
        else:
            st.info("No storyboard data")
    
    # Right column: Final video
    with col_video:
        st.markdown(f"**🎥 {tr('info.video_information')}**")
        
        video_path = metadata.get("result", {}).get("video_path")
        if video_path and os.path.exists(video_path):
            st.video(video_path)
            
            # Video info
            result = metadata.get("result", {})
            st.markdown(f"**{tr('info.duration')}:** {format_duration(result.get('duration', 0))}")
            st.markdown(f"**{tr('info.frames')}:** {result.get('n_frames', 0)}")
            st.markdown(f"**{tr('info.file_size')}:** {format_file_size(result.get('file_size', 0))}")

            # Download button
            with open(video_path, "rb") as f:
                # Get title from input (which now includes the generated title)
                title = metadata.get("input", {}).get("title", "video")
                if not title:
                    title = "video"
                st.download_button(
                    tr("history.detail.download_video"),
                    data=f,
                    file_name=f"{title}.mp4",
                    mime="video/mp4",
                    width="stretch"
                )
        else:
            st.warning("Video file not found")
    
    st.divider()
    
    # Close button at the bottom
    if st.button("❌ " + tr("history.detail.close"), key=f"close_detail_bottom_{task_id}"):
        st.session_state[f"detail_{task_id}"] = False
        st.rerun()


def main():
    """Main entry point for History page"""
    # Initialize
    init_session_state()
    init_i18n()
    st.markdown(build_history_page_css(), unsafe_allow_html=True)
    
    # Render header
    render_header()
    
    # Initialize Pixelle-Video
    pixelle_video = get_pixelle_video()
    
    # Sidebar: Statistics + Filters
    filter_status, sort_by, sort_order, page_size = render_sidebar_controls(pixelle_video)
    
    # Initialize pagination in session state
    if "history_page" not in st.session_state:
        st.session_state.history_page = 1
    
    # Check if we need to show a detail view
    show_detail_for = None
    for key in st.session_state.keys():
        if key.startswith("detail_") and st.session_state[key]:
            show_detail_for = key.replace("detail_", "")
            break
    
    # If showing detail, render it
    if show_detail_for:
        render_task_detail_modal(show_detail_for, pixelle_video)
        return
    
    # Otherwise, show the grid list
    # Get task list
    result = run_async(pixelle_video.history.get_task_list(
        page=st.session_state.history_page,
        page_size=page_size,
        status=filter_status,
        sort_by=sort_by,
        sort_order=sort_order
    ))
    
    tasks = result["tasks"]
    total = result["total"]
    total_pages = result["total_pages"]
    
    # Page title with count
    st.markdown(f"##### 📚 {tr('history.page_title')} ({total})")
    
    # Show task cards in grid layout (4 columns)
    if not tasks:
        st.info(tr("history.no_tasks"))
    else:
        # Grid layout: 4 cards per row
        CARDS_PER_ROW = 4
        
        # Process tasks in batches of CARDS_PER_ROW
        for i in range(0, len(tasks), CARDS_PER_ROW):
            cols = st.columns(CARDS_PER_ROW)
            
            # Fill each column with a task card
            for j in range(CARDS_PER_ROW):
                task_idx = i + j
                if task_idx < len(tasks):
                    with cols[j]:
                        render_grid_task_card(tasks[task_idx], pixelle_video)
    
    # Pagination
    if total_pages > 1:
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if st.button("⬅️ Previous", disabled=st.session_state.history_page == 1, width="stretch"):
                st.session_state.history_page -= 1
                st.rerun()
        
        with col2:
            st.markdown(
                f"<div style='text-align: center; padding-top: 8px;'>"
                f"{tr('history.page_info').format(page=st.session_state.history_page, total_pages=total_pages)}"
                f"</div>",
                unsafe_allow_html=True
            )
        
        with col3:
            if st.button("Next ➡️", disabled=st.session_state.history_page == total_pages, width="stretch"):
                st.session_state.history_page += 1
                st.rerun()


if __name__ == "__main__":
    main()
