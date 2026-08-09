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
import json
import os
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any, Callable

import streamlit as st
from loguru import logger

from pixelle_video.platform_context import CONFIGURED_API_BASE_URL
from pixelle_video.utils.os_util import get_output_path
from web.i18n import tr
from web.utils.async_helpers import run_async
from web.utils.output_media_urls import build_output_media_urls

RECENT_GENERATED_VIDEO_KEY = "recent_generated_video"
RECENT_VIDEO_GALLERY_KEY = "recent_video_gallery"
RECENT_VIDEO_GRID_KEY = "recent_video_grid"
RECENT_HISTORY_PAGE_SIZE = 12
RECENT_HISTORY_MAX_PAGES = 4
RECENT_VIDEO_LIMIT = 9


@lru_cache(maxsize=8)
def _read_recent_index_snapshot(
    index_path: str,
    modified_ns: int,
    size_bytes: int,
) -> Any:
    """Cache immutable index snapshots across browser sessions until the file changes."""
    del modified_ns, size_bytes
    return json.loads(Path(index_path).read_text(encoding="utf-8"))


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
        "cover_path": item.get("cover_path"),
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


def fetch_recent_history_video_items_from_index(
    *,
    output_root: str | Path | None = None,
    file_exists: Callable[[str], bool] = os.path.exists,
    limit: int = RECENT_VIDEO_LIMIT,
) -> list[dict[str, Any]]:
    """Read the rebuildable history index without initializing generation services."""
    root = Path(output_root or get_output_path()).resolve()
    index_path = root / ".index.json"
    try:
        stat = index_path.stat()
        payload = _read_recent_index_snapshot(
            str(index_path),
            stat.st_mtime_ns,
            stat.st_size,
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Unable to read lightweight recent-video index: {type(exc).__name__}")
        return []
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return []

    completed_tasks = [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("status") == "completed"
    ]
    completed_tasks.sort(
        key=lambda task: str(task.get("completed_at") or task.get("created_at") or ""),
        reverse=True,
    )
    items: list[dict[str, Any]] = []
    for task in completed_tasks:
        video_path = Path(str(task.get("video_path") or ""))
        if not video_path.is_absolute():
            parts = video_path.parts
            if parts and parts[0].casefold() == "output":
                video_path = Path(*parts[1:])
            video_path = root / video_path
        try:
            resolved_video = video_path.resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            continue
        if not resolved_video.is_file() or not resolved_video.is_relative_to(root):
            continue
        normalized = normalize_recent_video_item(
            {**task, "video_path": str(resolved_video)},
            file_exists=file_exists,
        )
        if normalized is not None:
            items.append(normalized)
            if len(items) >= limit:
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
        "cover_path": getattr(result, "cover_path", None),
        "duration": float(getattr(result, "duration", 0.0) or 0.0),
        "n_frames": len(getattr(storyboard, "frames", []) or []),
        "created_at": created_at_value,
        "completed_at": created_at_value,
        "source": "current",
    }


def build_recent_video_gallery_css(
    gallery_key: str = RECENT_VIDEO_GALLERY_KEY,
    grid_key: str = RECENT_VIDEO_GRID_KEY,
) -> str:
    """Build scoped CSS for the Home recent-video gallery."""
    return f"""
    <style>
    .st-key-{gallery_key} {{
        container-type: inline-size;
        margin-top: -0.35rem;
    }}
    .st-key-{grid_key} {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(220px, 100%), 1fr));
        gap: 0.65rem;
        justify-content: stretch;
        align-items: start;
    }}
    .st-key-{grid_key} > div[data-testid="stLayoutWrapper"] {{
        min-width: 0;
    }}
    .st-key-{grid_key} > div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"] {{
        padding: 0.5rem !important;
    }}
    .st-key-{grid_key} div[data-testid="stVerticalBlock"] {{
        gap: 0.35rem;
    }}
    .recent-video-section-title {{
        margin: 0 0 0.55rem;
        font-size: 0.98rem;
        font-weight: 700;
        line-height: 1.25;
    }}
    .st-key-{grid_key} div[data-testid="stMarkdownContainer"]:has(.recent-video-info) {{
        margin-bottom: 0 !important;
    }}
    .recent-video-cover-link {{
        display: block;
        aspect-ratio: 16 / 9;
        overflow: hidden;
        background: linear-gradient(135deg, rgba(110, 64, 201, 0.12), rgba(32, 171, 255, 0.10));
        border-radius: 8px;
    }}
    .recent-video-cover {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform 160ms ease, filter 160ms ease;
    }}
    .recent-video-cover-link:hover .recent-video-cover {{
        transform: scale(1.025);
        filter: brightness(0.94);
    }}
    .recent-video-placeholder {{
        display: grid;
        aspect-ratio: 16 / 9;
        place-items: center;
        color: rgba(49, 51, 63, 0.72);
        background: linear-gradient(135deg, rgba(110, 64, 201, 0.12), rgba(32, 171, 255, 0.10));
        border-radius: 8px;
        font-size: 1.45rem;
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
    .st-key-{grid_key} div[data-testid="stHorizontalBlock"] {{
        width: min(8.5rem, 72%);
        margin-inline: auto;
        gap: 0.55rem !important;
        justify-content: space-between;
    }}
    .st-key-{grid_key} div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }}
    .st-key-{gallery_key} .stColumn button,
    .st-key-{gallery_key} .stColumn a {{
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


def render_recent_video_gallery(pixelle_video: Any | None, *, key_suffix: str = "") -> None:
    """Render the compact recent-video gallery inside the Home output card."""
    gallery_key = f"{RECENT_VIDEO_GALLERY_KEY}{key_suffix}"
    grid_key = f"{RECENT_VIDEO_GRID_KEY}{key_suffix}"
    st.markdown(build_recent_video_gallery_css(gallery_key, grid_key), unsafe_allow_html=True)
    current = get_current_recent_video_item(st.session_state)
    history_items = (
        fetch_recent_history_video_items(pixelle_video)
        if pixelle_video is not None
        else fetch_recent_history_video_items_from_index()
    )
    items = merge_recent_video_items(current, history_items)

    with st.container(key=gallery_key):
        st.markdown(
            f'<div class="recent-video-section-title">{escape(tr("recent_videos.title"))}</div>',
            unsafe_allow_html=True,
        )
        if not items:
            st.info(tr("recent_videos.empty"))
            return

        with st.container(key=grid_key):
            for item in items:
                render_recent_video_card(
                    item,
                    api_base_url=st.session_state.get(
                        "api_base_url",
                        CONFIGURED_API_BASE_URL,
                    ),
                    key_suffix=key_suffix,
                )


def render_recent_video_card(
    item: dict[str, Any],
    *,
    api_base_url: str = CONFIGURED_API_BASE_URL,
    key_suffix: str = "",
) -> None:
    """Render one recent video card."""
    item_key = f"{_stable_key(item.get('task_id') or item.get('video_path'))}{key_suffix}"
    raw_title = str(item.get("title") or tr("recent_videos.untitled"))
    download_stem = raw_title[:-4] if raw_title.casefold().endswith(".mp4") else raw_title
    media_urls = build_output_media_urls(
        item["video_path"],
        api_base_url=api_base_url,
        download_name=f"{download_stem[:120]}.mp4",
    )
    with st.container(border=True):
        title = escape(raw_title)
        cover_url_value = getattr(media_urls, "cover_url", None) if media_urls is not None else None
        if media_urls is not None and cover_url_value:
            stream_url = escape(media_urls.stream_url, quote=True)
            cover_url = escape(cover_url_value, quote=True)
            st.markdown(
                (
                    f'<a class="recent-video-cover-link" href="{stream_url}" '
                    'target="_blank" rel="noopener noreferrer" '
                    f'aria-label="{escape(raw_title, quote=True)}">'
                    f'<img class="recent-video-cover" src="{cover_url}" alt="{escape(raw_title, quote=True)}" '
                    'loading="lazy" decoding="async" />'
                    '</a>'
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="recent-video-placeholder" aria-hidden="true">🎬</div>',
                unsafe_allow_html=True,
            )
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

        action_columns = st.columns(3, gap="small")
        task_id = item.get("task_id")
        with action_columns[0]:
            if media_urls is not None:
                st.link_button(
                    "▶️",
                    media_urls.stream_url,
                    help=tr("history.task_card.play"),
                    width="stretch",
                )
            else:
                st.button(
                    "▶️",
                    key=f"recent_play_disabled_{item_key}",
                    help=tr("history.task_card.play"),
                    disabled=True,
                    width="stretch",
                )

        with action_columns[1]:
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

        with action_columns[2]:
            if media_urls is not None:
                st.link_button(
                    "⬇️",
                    media_urls.download_url,
                    help=tr("history.task_card.download"),
                    width="stretch",
                )
            else:
                st.button(
                    "⬇️",
                    key=f"recent_download_disabled_{item_key}",
                    help=tr("history.task_card.download"),
                    disabled=True,
                    width="stretch",
                )
