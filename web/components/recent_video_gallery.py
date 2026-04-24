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

"""Recent video gallery for the Home page output column."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from html import escape
from typing import Any, Callable

import streamlit as st
from loguru import logger

from web.i18n import tr
from web.utils.async_helpers import run_async

RECENT_GENERATED_VIDEO_KEY = "recent_generated_video"
RECENT_VIDEO_GALLERY_KEY = "recent_video_gallery"
RECENT_VIDEO_GRID_KEY = "recent_video_grid"
RECENT_HISTORY_PAGE_SIZE = 12
RECENT_HISTORY_MAX_PAGES = 4
RECENT_VIDEO_LIMIT = 8


def _coerce_text(value: Any, fallback: str) -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def _stable_key(value: Any) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]


def normalize_recent_video_item(
    item: dict[str, Any],
    *,
    file_exists: Callable[[str], bool] = os.path.exists,
    source: str = "history",
) -> dict[str, Any] | None:
    """Normalize a task summary into a gallery item, skipping missing files."""
    video_path = item.get("video_path")
    if not video_path or not file_exists(str(video_path)):
        return None

    title = _coerce_text(item.get("title"), tr("recent_videos.untitled"))
    return {
        "task_id": item.get("task_id"),
        "title": title,
        "video_path": str(video_path),
        "duration": float(item.get("duration") or 0.0),
        "n_frames": int(item.get("n_frames") or 0),
        "created_at": item.get("created_at") or item.get("completed_at") or "",
        "completed_at": item.get("completed_at") or item.get("created_at") or "",
        "source": source,
    }


def merge_recent_video_items(
    current_item: dict[str, Any] | None,
    history_items: list[dict[str, Any]],
    *,
    limit: int = RECENT_VIDEO_LIMIT,
) -> list[dict[str, Any]]:
    """Merge current generation and history items, preserving current first."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidates = ([current_item] if current_item else []) + list(history_items)
    for item in candidates:
        if not item:
            continue
        identity = str(item.get("video_path") or item.get("task_id") or "")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def fetch_recent_history_video_items(
    pixelle_video: Any,
    *,
    runner: Callable[[Any], Any] = run_async,
    file_exists: Callable[[str], bool] = os.path.exists,
    limit: int = RECENT_VIDEO_LIMIT,
    page_size: int = RECENT_HISTORY_PAGE_SIZE,
    max_pages: int = RECENT_HISTORY_MAX_PAGES,
) -> list[dict[str, Any]]:
    """Fetch enough completed History items to fill the compact Home gallery."""
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            result = runner(
                pixelle_video.history.get_task_list(
                    page=page,
                    page_size=page_size,
                    status="completed",
                    sort_by="completed_at",
                    sort_order="desc",
                )
            )
        except Exception as exc:
            logger.warning(f"Failed to fetch recent video history: {exc}")
            break

        for task in result.get("tasks", []):
            normalized = normalize_recent_video_item(task, file_exists=file_exists)
            if normalized:
                items.append(normalized)
                if len(items) >= limit:
                    return items

        if page >= int(result.get("total_pages") or 1):
            break
    return items


def clear_recent_generated_video(session_state: dict[str, Any]) -> None:
    """Remove stale current-generation gallery state before a new valid run."""
    session_state.pop(RECENT_GENERATED_VIDEO_KEY, None)


def get_current_recent_video_item(
    session_state: dict[str, Any],
    *,
    file_exists: Callable[[str], bool] = os.path.exists,
) -> dict[str, Any] | None:
    """Return the stored current-generation item only while its file still exists."""
    current = session_state.get(RECENT_GENERATED_VIDEO_KEY)
    if not current:
        return None

    normalized = normalize_recent_video_item(
        current,
        file_exists=file_exists,
        source="current",
    )
    if normalized is None:
        clear_recent_generated_video(session_state)
    return normalized


def store_recent_generated_video(result: Any, session_state: dict[str, Any]) -> None:
    """Store a successful generation result for first-slot gallery display."""
    storyboard = getattr(result, "storyboard", None)
    config = getattr(storyboard, "config", None)
    created_at = getattr(result, "created_at", None)
    if isinstance(created_at, datetime):
        created_at_value = created_at.isoformat()
    else:
        created_at_value = str(created_at or "")

    session_state[RECENT_GENERATED_VIDEO_KEY] = {
        "task_id": getattr(config, "task_id", None),
        "title": _coerce_text(getattr(storyboard, "title", None), tr("recent_videos.untitled")),
        "video_path": str(getattr(result, "video_path")),
        "duration": float(getattr(result, "duration", 0.0) or 0.0),
        "n_frames": len(getattr(storyboard, "frames", []) or []),
        "created_at": created_at_value,
        "completed_at": created_at_value,
        "source": "current",
    }


def build_recent_video_gallery_css() -> str:
    """Build scoped CSS for the Home recent-video gallery."""
    return f"""
    <style>
    .st-key-{RECENT_VIDEO_GALLERY_KEY} {{
        container-type: inline-size;
        margin-top: -0.35rem;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(180px, 100%), 220px));
        gap: 0.65rem;
        justify-content: start;
        align-items: start;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} > div[data-testid="stLayoutWrapper"] {{
        min-width: 0;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} > div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"] {{
        padding: 0.5rem !important;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} div[data-testid="stVerticalBlock"] {{
        gap: 0.35rem;
    }}
    .recent-video-section-title {{
        margin: 0 0 0.55rem;
        font-size: 0.98rem;
        font-weight: 700;
        line-height: 1.25;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} div[data-testid="stMarkdownContainer"]:has(.recent-video-info) {{
        margin-bottom: 0 !important;
    }}
    .st-key-{RECENT_VIDEO_GALLERY_KEY} video[data-testid="stVideo"] {{
        width: 100% !important;
        max-width: 100% !important;
        height: auto !important;
        max-height: none !important;
        margin: 0 !important;
        display: block;
        object-fit: initial !important;
        background: transparent;
        border-radius: 8px;
    }}
    .recent-video-info {{
        display: grid;
        gap: 0.2rem;
        margin: 0.15rem 0 0;
    }}
    .recent-video-title {{
        margin: 0;
        min-height: 1.25rem;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 1;
        -webkit-box-orient: vertical;
        font-weight: 600;
        font-size: 0.82rem;
        line-height: 1.35;
    }}
    .recent-video-meta {{
        margin: 0;
        color: rgba(49, 51, 63, 0.62);
        font-size: 0.68rem;
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} div[data-testid="stHorizontalBlock"] {{
        gap: 0.55rem !important;
        justify-content: center;
    }}
    .st-key-{RECENT_VIDEO_GRID_KEY} div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }}
    .st-key-{RECENT_VIDEO_GALLERY_KEY} .stColumn button {{
        width: 2.15rem !important;
        min-height: 1.45rem;
        padding: 0;
        margin-inline: 0;
        border-radius: 6px;
        font-size: 0.72rem;
        line-height: 1;
    }}
    </style>
    """


def format_recent_video_datetime(value: Any) -> str:
    """Format an ISO datetime for compact card metadata."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).strftime("%m-%d %H:%M")
    except ValueError:
        return str(value)


def render_recent_video_gallery(pixelle_video: Any) -> None:
    """Render the compact recent-video gallery inside the Home output card."""
    st.markdown(build_recent_video_gallery_css(), unsafe_allow_html=True)
    current = get_current_recent_video_item(st.session_state)
    history_items = fetch_recent_history_video_items(pixelle_video)
    items = merge_recent_video_items(current, history_items)

    with st.container(key=RECENT_VIDEO_GALLERY_KEY):
        st.markdown(
            f'<div class="recent-video-section-title">{escape(tr("recent_videos.title"))}</div>',
            unsafe_allow_html=True,
        )
        if not items:
            st.info(tr("recent_videos.empty"))
            return

        with st.container(key=RECENT_VIDEO_GRID_KEY):
            for item in items:
                render_recent_video_card(item)


def render_recent_video_card(item: dict[str, Any]) -> None:
    """Render one recent video card."""
    item_key = _stable_key(item.get("task_id") or item.get("video_path"))
    with st.container(border=True):
        st.video(item["video_path"], autoplay=False, loop=False, muted=False)
        title = escape(str(item.get("title") or tr("recent_videos.untitled")))
        meta = " · ".join(
            part
            for part in [
                format_recent_video_datetime(item.get("completed_at") or item.get("created_at")),
                f'{float(item.get("duration") or 0.0):.1f}s',
                f'🎬 {int(item.get("n_frames") or 0)}',
            ]
            if part
        )
        st.markdown(
            (
                '<div class="recent-video-info">'
                f'<div class="recent-video-title">✅ {title}</div>'
                f'<div class="recent-video-meta">{escape(meta)}</div>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        action_columns = st.columns(2, gap="small")
        task_id = item.get("task_id")
        with action_columns[0]:
            if task_id and st.button(
                "👁️",
                key=f"recent_view_{item_key}",
                help=tr("history.task_card.view_detail"),
                width="stretch",
            ):
                st.session_state[f"detail_{task_id}"] = True
                st.switch_page("pages/2_📚_History.py")
            elif not task_id:
                st.button("👁️", key=f"recent_view_disabled_{item_key}", disabled=True, width="stretch")

        with action_columns[1]:
            with open(item["video_path"], "rb") as video_file:
                st.download_button(
                    "⬇️",
                    data=video_file,
                    file_name=f"{item.get('title') or tr('recent_videos.untitled')}.mp4",
                    mime="video/mp4",
                    key=f"recent_download_{item_key}",
                    help=tr("history.task_card.download"),
                    width="stretch",
                )
