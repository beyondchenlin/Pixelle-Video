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

# ruff: noqa: E402
"""
Home Page - Main video generation interface
"""

import sys
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.faq import render_faq_sidebar

# Import components
from web.components.header import render_header
from web.components.recent_video_gallery import render_recent_video_gallery
from web.components.settings import render_advanced_settings
from web.home_dashboard import (
    change_dashboard_page,
    normalize_dashboard_page,
    resolve_dashboard_warmup_target,
)
from web.home_editor_warmup import schedule_home_editor_warmup
from web.i18n import tr

# Import lightweight selector metadata. Implementations are loaded on selection.
from web.pipelines import get_pipeline_selection_entries, get_pipeline_ui

# Import state management
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.utils.streamlit_helpers import keyed_widget_default_kwargs

HOME_PIPELINE_KEY = "home_active_pipeline"
HOME_EDITOR_OPEN_KEY = "home_editor_open"
HOME_DASHBOARD_PAGE_KEY = "home_dashboard_video_page"
HOME_DASHBOARD_PAGE_SIZE = 12

# Page config
st.set_page_config(
    page_title="Home - 懒人同城",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main():
    """Main UI entry point"""
    # Initialize session state and i18n
    init_session_state()
    init_i18n()
    
    # Render header (title + language selector)
    render_header()
    
    # Render FAQ in sidebar
    render_faq_sidebar()
    
    # Render system configuration (LLM + ComfyUI)
    render_advanced_settings()

    editor_open = st.toggle(
        tr("home.editor.open"),
        value=False,
        key=HOME_EDITOR_OPEN_KEY,
        help=tr("home.editor.open_help"),
    )
    if not editor_open:
        st.caption(tr("home.dashboard.caption"))
        page = normalize_dashboard_page(st.session_state.get(HOME_DASHBOARD_PAGE_KEY))
        gallery_result = render_recent_video_gallery(
            None,
            key_suffix="_dashboard",
            show_all=True,
            item_offset=page * HOME_DASHBOARD_PAGE_SIZE,
            page_size=HOME_DASHBOARD_PAGE_SIZE,
        )
        if gallery_result.rendered_count == 0 and page > 0:
            st.session_state[HOME_DASHBOARD_PAGE_KEY] = 0
            st.rerun()
        if gallery_result.has_previous or gallery_result.has_next:
            previous_col, page_col, next_col = st.columns((1, 2, 1))
            with previous_col:
                st.button(
                    tr("recent_videos.previous_page"),
                    key="home_dashboard_previous_page",
                    on_click=change_dashboard_page,
                    args=(st.session_state,),
                    kwargs={"state_key": HOME_DASHBOARD_PAGE_KEY, "delta": -1},
                    disabled=not gallery_result.has_previous,
                    width="stretch",
                )
            with page_col:
                st.caption(tr("recent_videos.page", page=page + 1))
            with next_col:
                st.button(
                    tr("recent_videos.next_page"),
                    key="home_dashboard_next_page",
                    on_click=change_dashboard_page,
                    args=(st.session_state,),
                    kwargs={"state_key": HOME_DASHBOARD_PAGE_KEY, "delta": 1},
                    disabled=not gallery_result.has_next,
                    width="stretch",
                )
        schedule_home_editor_warmup(
            resolve_dashboard_warmup_target(st.session_state.get(HOME_PIPELINE_KEY))
        )
        return

    # ========================================================================
    # Pipeline Selection & Delegation
    # ========================================================================

    selection_entries = get_pipeline_selection_entries()
    pipeline_names = [entry.name for entry in selection_entries]
    current_name = st.session_state.get(HOME_PIPELINE_KEY)
    if current_name not in pipeline_names:
        current_name = pipeline_names[0]
        st.session_state.pop(HOME_PIPELINE_KEY, None)

    entry_by_name = {entry.name: entry for entry in selection_entries}
    selected_name = st.segmented_control(
        tr("pipeline.select"),
        options=pipeline_names,
        format_func=lambda name: (
            f"{entry_by_name[name].icon} {entry_by_name[name].display_name}"
        ),
        key=HOME_PIPELINE_KEY,
        label_visibility="collapsed",
        width="stretch",
        **keyed_widget_default_kwargs(
            st.session_state,
            HOME_PIPELINE_KEY,
            default=current_name,
        ),
    )
    selected_name = selected_name or current_name
    selected_entry = entry_by_name[selected_name]
    if selected_entry.description:
        st.caption(selected_entry.description)

    # The visible shell and selector render before heavyweight runtime creation.
    pixelle_video = get_pixelle_video()
    pipeline = get_pipeline_ui(selected_name)
    if pipeline is None:  # pragma: no cover - entries resolve to registered pipelines
        raise RuntimeError(f"Selected pipeline {selected_name!r} is unavailable")
    pipeline.render(pixelle_video)


if __name__ == "__main__":
    main()
