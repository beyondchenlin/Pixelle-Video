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
from web.home_editor_prewarm import schedule_home_editor_prewarm
from web.i18n import tr

# Import lightweight selector metadata. Implementations are loaded on selection.
from web.pipelines import get_pipeline_selection_entries, get_pipeline_ui

# Import state management
from web.state.session import get_pixelle_video, init_i18n, init_session_state
from web.utils.streamlit_helpers import keyed_widget_default_kwargs

HOME_PIPELINE_KEY = "home_active_pipeline"
HOME_EDITOR_OPEN_KEY = "home_editor_open"
HOME_DASHBOARD_VISIBLE_COUNT_KEY = "home_dashboard_visible_video_count"
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
        visible_count = max(
            HOME_DASHBOARD_PAGE_SIZE,
            int(
                st.session_state.get(
                    HOME_DASHBOARD_VISIBLE_COUNT_KEY,
                    HOME_DASHBOARD_PAGE_SIZE,
                )
            ),
        )
        total_count = render_recent_video_gallery(
            None,
            key_suffix="_dashboard",
            show_all=True,
            render_limit=visible_count,
        )
        if total_count > visible_count:
            st.button(
                tr("recent_videos.load_more"),
                key="home_dashboard_load_more",
                on_click=_load_more_dashboard_videos,
                width="stretch",
            )
        schedule_home_editor_prewarm(
            str(st.session_state.get(HOME_PIPELINE_KEY) or "quick_create")
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


def _load_more_dashboard_videos() -> None:
    current_count = max(
        HOME_DASHBOARD_PAGE_SIZE,
        int(
            st.session_state.get(
                HOME_DASHBOARD_VISIBLE_COUNT_KEY,
                HOME_DASHBOARD_PAGE_SIZE,
            )
        ),
    )
    st.session_state[HOME_DASHBOARD_VISIBLE_COUNT_KEY] = (
        current_count + HOME_DASHBOARD_PAGE_SIZE
    )


if __name__ == "__main__":
    main()
