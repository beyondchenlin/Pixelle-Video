# Home Recent Video Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the responsive recent video gallery in the Home page right column so History videos fill the empty preview area and the newest successful generation appears first.

**Architecture:** Add a focused `web/components/recent_video_gallery.py` component that owns recent-video data normalization, History pagination, current-result merging, scoped CSS, and Streamlit rendering. Keep `web/components/output_preview.py` responsible for the generate button and generation progress, but route successful results into session state and render the gallery after the button branch. Update i18n and tests around the helper behavior and output preview integration.

**Tech Stack:** Python, Streamlit, pytest, repository i18n JSON files.

---

## File Structure

- Create `web/components/recent_video_gallery.py`
  - Defines `RECENT_GENERATED_VIDEO_KEY`, gallery CSS, data normalization helpers, History pagination, current-result session helpers, and Streamlit gallery rendering.
- Create `tests/test_recent_video_gallery.py`
  - Covers filtering missing files, merge dedupe, paginated History scanning, current-result clear/store, and scoped CSS.
- Modify `web/components/output_preview.py`
  - Imports gallery helpers.
  - Replaces old single preview rendering in the standard quick-create path with current-result storage and gallery rendering.
  - Avoids `st.stop()` in validation and exception paths so the gallery still renders.
- Modify `tests/test_output_preview.py`
  - Updates existing standard generation tests to assert gallery integration instead of old single-preview calls.
  - Adds regression coverage for clearing stale current result on valid generation.
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`
  - Adds Home gallery title, empty state, action labels, and fallback strings.

## Task 1: Recent Video Data Helpers

**Files:**
- Create: `web/components/recent_video_gallery.py`
- Create: `tests/test_recent_video_gallery.py`

- [ ] **Step 1: Write failing tests for normalization, merge, pagination, and session helpers**

Add tests with this shape:

```python
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from web.components import recent_video_gallery as gallery


def test_normalize_history_task_skips_missing_video_file(tmp_path):
    task = {
        "task_id": "task-1",
        "title": "Missing",
        "video_path": str(tmp_path / "missing.mp4"),
        "duration": 1.2,
        "n_frames": 3,
        "created_at": "2026-04-24T01:00:00",
        "completed_at": "2026-04-24T01:01:00",
    }

    assert gallery.normalize_recent_video_item(task, file_exists=Path.exists) is None


def test_merge_recent_video_items_puts_current_first_and_dedupes(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    current = {
        "task_id": "task-current",
        "title": "Current",
        "video_path": str(video),
        "duration": 9.0,
        "n_frames": 5,
        "created_at": "2026-04-24T02:00:00",
        "source": "current",
    }
    history = [
        {**current, "source": "history"},
        {
            "task_id": "task-history",
            "title": "History",
            "video_path": str(tmp_path / "history.mp4"),
            "duration": 4.0,
            "n_frames": 2,
            "created_at": "2026-04-24T01:00:00",
            "source": "history",
        },
    ]

    merged = gallery.merge_recent_video_items(current, history, limit=4)

    assert [item["task_id"] for item in merged] == ["task-current", "task-history"]


def test_fetch_recent_history_video_items_scans_pages_until_limit(tmp_path):
    valid_paths = []
    for index in range(4):
        path = tmp_path / f"valid-{index}.mp4"
        path.write_bytes(b"video")
        valid_paths.append(str(path))

    pages = {
        1: {
            "tasks": [
                {"task_id": "bad-1", "video_path": str(tmp_path / "missing-1.mp4")},
                {"task_id": "bad-2", "video_path": str(tmp_path / "missing-2.mp4")},
            ],
            "total_pages": 3,
        },
        2: {
            "tasks": [
                {
                    "task_id": f"valid-{index}",
                    "title": f"Valid {index}",
                    "video_path": valid_paths[index],
                    "duration": float(index),
                    "n_frames": index + 1,
                    "created_at": f"2026-04-24T0{index}:00:00",
                    "completed_at": f"2026-04-24T0{index}:01:00",
                }
                for index in range(3)
            ],
            "total_pages": 3,
        },
        3: {
            "tasks": [
                {
                    "task_id": "valid-3",
                    "title": "Valid 3",
                    "video_path": valid_paths[3],
                    "duration": 3.0,
                    "n_frames": 4,
                    "created_at": "2026-04-24T03:00:00",
                    "completed_at": "2026-04-24T03:01:00",
                }
            ],
            "total_pages": 3,
        },
    }

    class FakeHistory:
        async def get_task_list(self, **kwargs):
            return pages[kwargs["page"]]

    class FakePixelleVideo:
        history = FakeHistory()

    items = gallery.fetch_recent_history_video_items(
        FakePixelleVideo(),
        runner=lambda awaitable: asyncio.run(awaitable),
        file_exists=lambda value: Path(value).exists(),
    )

    assert [item["task_id"] for item in items] == ["valid-0", "valid-1", "valid-2", "valid-3"]


def test_store_and_clear_recent_generated_video(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    session_state = {}
    result = SimpleNamespace(
        video_path=str(video),
        duration=12.5,
        created_at=datetime.fromisoformat("2026-04-24T02:00:00"),
        storyboard=SimpleNamespace(
            title="Generated",
            config=SimpleNamespace(task_id="task-generated"),
            frames=[object(), object()],
        ),
    )

    gallery.store_recent_generated_video(result, session_state)
    assert session_state[gallery.RECENT_GENERATED_VIDEO_KEY]["task_id"] == "task-generated"

    gallery.clear_recent_generated_video(session_state)
    assert gallery.RECENT_GENERATED_VIDEO_KEY not in session_state
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_recent_video_gallery.py -q`

Expected: FAIL because `web.components.recent_video_gallery` does not exist.

- [ ] **Step 3: Implement helper module**

Create `web/components/recent_video_gallery.py` with:

```python
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from web.i18n import tr
from web.utils.async_helpers import run_async

RECENT_GENERATED_VIDEO_KEY = "recent_generated_video"
RECENT_VIDEO_GALLERY_KEY = "recent_video_gallery"
RECENT_HISTORY_PAGE_SIZE = 12
RECENT_HISTORY_MAX_PAGES = 4
RECENT_VIDEO_LIMIT = 4


def _coerce_text(value: Any, fallback: str) -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def normalize_recent_video_item(
    item: dict[str, Any],
    *,
    file_exists: Callable[[str], bool] = os.path.exists,
    source: str = "history",
) -> dict[str, Any] | None:
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
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        result = runner(
            pixelle_video.history.get_task_list(
                page=page,
                page_size=page_size,
                status="completed",
                sort_by="completed_at",
                sort_order="desc",
            )
        )
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
    session_state.pop(RECENT_GENERATED_VIDEO_KEY, None)


def store_recent_generated_video(result: Any, session_state: dict[str, Any]) -> None:
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
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `pytest tests/test_recent_video_gallery.py -q`

Expected: PASS.

## Task 2: Gallery CSS and Streamlit Rendering

**Files:**
- Modify: `web/components/recent_video_gallery.py`
- Modify: `tests/test_recent_video_gallery.py`

- [ ] **Step 1: Write failing tests for CSS and empty-state rendering helpers**

Append tests:

```python
def test_build_recent_video_gallery_css_is_scoped_and_responsive():
    css = gallery.build_recent_video_gallery_css()

    assert ".st-key-recent_video_gallery" in css
    assert "@container (min-width: 520px)" in css
    assert "height: clamp(180px, 46cqw, 260px)" in css
    assert "object-fit: contain" in css
```

- [ ] **Step 2: Run targeted test to verify failure**

Run: `pytest tests/test_recent_video_gallery.py::test_build_recent_video_gallery_css_is_scoped_and_responsive -q`

Expected: FAIL because `build_recent_video_gallery_css` does not exist.

- [ ] **Step 3: Add CSS and rendering functions**

Extend `recent_video_gallery.py` with:

```python
def build_recent_video_gallery_css() -> str:
    return f"""
    <style>
    .st-key-{RECENT_VIDEO_GALLERY_KEY} {{
        container-type: inline-size;
    }}
    .st-key-{RECENT_VIDEO_GALLERY_KEY} [data-testid="stHorizontalBlock"] {{
        gap: 12px;
    }}
    @container (min-width: 520px) {{
        .st-key-{RECENT_VIDEO_GALLERY_KEY} [data-testid="column"] {{
            min-width: 0 !important;
        }}
    }}
    .st-key-{RECENT_VIDEO_GALLERY_KEY} [data-testid="stVideo"] {{
        width: 100% !important;
        max-width: 100% !important;
        margin: 0 !important;
    }}
    .st-key-{RECENT_VIDEO_GALLERY_KEY} [data-testid="stVideo"] video {{
        width: 100% !important;
        height: clamp(180px, 46cqw, 260px) !important;
        max-height: 260px !important;
        object-fit: contain !important;
        background: #0f172a;
        border-radius: 8px;
    }}
    .recent-video-title {{
        min-height: 2.6rem;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        font-weight: 600;
        font-size: 0.9rem;
        line-height: 1.35;
    }}
    .recent-video-meta {{
        color: rgba(49, 51, 63, 0.62);
        font-size: 0.76rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }}
    </style>
    """


def format_recent_video_datetime(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).strftime("%m-%d %H:%M")
    except ValueError:
        return str(value)


def render_recent_video_gallery(pixelle_video: Any) -> None:
    st.markdown(build_recent_video_gallery_css(), unsafe_allow_html=True)
    current = st.session_state.get(RECENT_GENERATED_VIDEO_KEY)
    history_items = fetch_recent_history_video_items(pixelle_video)
    items = merge_recent_video_items(current, history_items)

    with st.container(key=RECENT_VIDEO_GALLERY_KEY):
        st.markdown(f"**{tr('recent_videos.title')}**")
        if not items:
            st.info(tr("recent_videos.empty"))
            return

        for row_start in range(0, len(items), 2):
            columns = st.columns(2, gap="small")
            for offset, item in enumerate(items[row_start:row_start + 2]):
                with columns[offset]:
                    render_recent_video_card(item)


def render_recent_video_card(item: dict[str, Any]) -> None:
    with st.container(border=True):
        st.video(item["video_path"], autoplay=False, loop=False, muted=False)
        st.markdown(f'<div class="recent-video-title">✅ {item["title"]}</div>', unsafe_allow_html=True)
        meta = " · ".join(
            part
            for part in [
                format_recent_video_datetime(item.get("completed_at") or item.get("created_at")),
                f'{float(item.get("duration") or 0.0):.1f}s',
                f'🎬 {int(item.get("n_frames") or 0)}',
            ]
            if part
        )
        st.markdown(f'<div class="recent-video-meta">{meta}</div>', unsafe_allow_html=True)
        action_columns = st.columns(2, gap="small")
        task_id = item.get("task_id")
        with action_columns[0]:
            if task_id and st.button("👁️", key=f"recent_view_{task_id}", help=tr("history.task_card.view_detail"), width="stretch"):
                st.session_state[f"detail_{task_id}"] = True
                st.switch_page("pages/2_📚_History.py")
            elif not task_id:
                st.button("👁️", key=f"recent_view_disabled_{item['video_path']}", disabled=True, width="stretch")
        with action_columns[1]:
            with open(item["video_path"], "rb") as video_file:
                st.download_button(
                    "⬇️",
                    data=video_file,
                    file_name=f"{item['title']}.mp4",
                    mime="video/mp4",
                    key=f"recent_download_{task_id or item['video_path']}",
                    help=tr("history.task_card.download"),
                    width="stretch",
                )
```

- [ ] **Step 4: Run helper tests**

Run: `pytest tests/test_recent_video_gallery.py -q`

Expected: PASS.

## Task 3: Output Preview Integration

**Files:**
- Modify: `web/components/output_preview.py`
- Modify: `tests/test_output_preview.py`

- [ ] **Step 1: Write failing integration tests**

Add or update tests so they assert:

```python
def test_render_single_output_stores_recent_generated_video_and_renders_gallery(monkeypatch, tmp_path):
    # Arrange FakeStreamlit.button returns True, config validates, generate_video returns an existing video.
    # Patch output_preview.store_recent_generated_video to capture the result.
    # Patch output_preview.render_recent_video_gallery to record that it ran.
    # Act: output_preview.render_single_output(...)
    # Assert: store and gallery were both called, render_scaled_video_preview was not called.
```

Also add:

```python
def test_render_single_output_does_not_stop_before_gallery_on_input_error(monkeypatch):
    # Arrange FakeStreamlit.button returns True and video_params["text"] is empty.
    # FakeStreamlit.stop raises AssertionError if called.
    # Patch render_recent_video_gallery to record that it still ran.
    # Act: render_single_output(...)
    # Assert: gallery ran and no generate_video call was made.
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_output_preview.py::test_render_single_output_stores_recent_generated_video_and_renders_gallery tests/test_output_preview.py::test_render_single_output_does_not_stop_before_gallery_on_input_error -q`

Expected: FAIL because output preview still calls `render_scaled_video_preview` and `st.stop()`.

- [ ] **Step 3: Implement output preview integration**

In `web/components/output_preview.py`:

```python
from web.components.recent_video_gallery import (
    clear_recent_generated_video,
    render_recent_video_gallery,
    store_recent_generated_video,
)
```

Inside `render_single_output`, replace validation `st.stop()` branches with `can_generate = False` flow:

```python
if st.button(tr("btn.generate"), type="primary", width="stretch"):
    can_generate = True
    if not config_manager.validate():
        st.error(tr("settings.not_configured"))
        can_generate = False
    if not text:
        st.error(tr("error.input_required"))
        can_generate = False

    if can_generate:
        clear_recent_generated_video(st.session_state)
        ...
```

After successful generation:

```python
if os.path.exists(result.video_path):
    store_recent_generated_video(result, st.session_state)
else:
    st.error(tr("status.video_not_found", path=result.video_path))
```

Remove the old `render_scaled_video_preview(...)` and single download button from this standard quick-create path.

In the exception branch, remove `st.stop()`.

At the bottom of the container, outside the button branch:

```python
st.markdown("---")
render_recent_video_gallery(pixelle_video)
```

- [ ] **Step 4: Run output preview tests**

Run: `pytest tests/test_output_preview.py -q`

Expected: PASS.

## Task 4: I18n Copy

**Files:**
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: Add locale keys**

Add near the History keys:

```json
"recent_videos.title": "最近视频",
"recent_videos.empty": "暂无可预览的视频。生成完成后会显示在这里。",
"recent_videos.untitled": "未命名视频"
```

English:

```json
"recent_videos.title": "Recent Videos",
"recent_videos.empty": "No videos to preview yet. Generated videos will appear here.",
"recent_videos.untitled": "Untitled video"
```

- [ ] **Step 2: Run JSON/import check**

Run: `python -m json.tool web/i18n/locales/zh_CN.json > $null; python -m json.tool web/i18n/locales/en_US.json > $null`

Expected: exit code 0.

## Task 5: Verification and Commit

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
pytest tests/test_recent_video_gallery.py tests/test_output_preview.py -q
```

Expected: PASS.

- [ ] **Step 2: Check staged scope**

Run:

```powershell
git diff -- web/components/recent_video_gallery.py web/components/output_preview.py tests/test_recent_video_gallery.py tests/test_output_preview.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json docs/superpowers/plans/2026-04-24-home-recent-video-gallery-implementation.md
git status --short
```

Expected: only intended files are staged for this commit; unrelated dirty files remain unstaged.

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add -- docs/superpowers/plans/2026-04-24-home-recent-video-gallery-implementation.md web/components/recent_video_gallery.py web/components/output_preview.py tests/test_recent_video_gallery.py tests/test_output_preview.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "feat: show recent videos in home preview"
git push origin dev
```

Expected: commit succeeds and push updates `origin/dev`.

## Self-Review

- Spec coverage: Covers default History display, generated-result first slot, dedupe, pagination, `completed_at` sorting, scoped responsive video sizing, no delete action, error paths without `st.stop()`, i18n, and tests.
- Placeholder scan: No incomplete placeholders are intended in this plan.
- Type consistency: Helper names are `normalize_recent_video_item`, `merge_recent_video_items`, `fetch_recent_history_video_items`, `clear_recent_generated_video`, `store_recent_generated_video`, `build_recent_video_gallery_css`, and `render_recent_video_gallery`.
