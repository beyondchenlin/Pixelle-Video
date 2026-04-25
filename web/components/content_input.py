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
Content input components for web UI (left column)
"""

import streamlit as st

from web.components.prompt_generation_performance import (
    render_prompt_generation_performance_controls,
)
from web.i18n import tr
from web.utils.async_helpers import get_project_version


def build_storyboard_generation_payload(
    *,
    storyboard_mode: str,
    storyboard_count_mode: str,
    storyboard_scene_count: int | None,
    script_length_mode: str,
    script_target_words: int | None,
) -> dict:
    """Normalize UI storyboard generation controls into the video request contract."""
    if storyboard_mode != "smart":
        storyboard_count_mode = "auto"
        storyboard_scene_count = None
    elif storyboard_count_mode != "manual":
        storyboard_count_mode = "auto"
        storyboard_scene_count = None

    if script_length_mode != "custom":
        script_target_words = None

    return {
        "storyboard_mode": storyboard_mode,
        "storyboard_count_mode": storyboard_count_mode,
        "storyboard_scene_count": storyboard_scene_count,
        "script_length_mode": script_length_mode,
        "script_target_words": script_target_words,
    }


def render_storyboard_generation_controls(*, mode: str, key_prefix: str) -> dict:
    """Render controls for source-text storyboard generation."""
    st.markdown(f"**{tr('section.storyboard_planning')}**")
    storyboard_mode = st.radio(
        "Storyboard Mode",
        ["smart", "punctuation", "sentence"],
        index=0,
        horizontal=True,
        key=f"{key_prefix}_storyboard_mode",
        format_func=lambda value: {
            "smart": "Smart",
            "punctuation": tr("split.mode_punctuation"),
            "sentence": tr("split.mode_sentence"),
        }[value],
    )

    storyboard_count_mode = "auto"
    storyboard_scene_count = None
    if storyboard_mode == "smart":
        storyboard_count_mode = st.radio(
            "Scene Count",
            ["auto", "manual"],
            index=0,
            horizontal=True,
            key=f"{key_prefix}_storyboard_count_mode",
            format_func=lambda value: {
                "auto": tr("storyboard.option.content_mode.auto"),
                "manual": tr("video.frames"),
            }[value],
        )
        if storyboard_count_mode == "manual":
            storyboard_scene_count = st.slider(
                tr("video.frames"),
                min_value=1,
                max_value=30,
                value=5,
                key=f"{key_prefix}_storyboard_scene_count",
                help=tr("video.frames_help"),
            )
    else:
        st.caption(tr("video.frames_fixed_mode_hint"))

    script_length_mode = "auto"
    script_target_words = None
    if mode == "generate":
        script_length_mode = st.selectbox(
            "Script Length",
            ["auto", "short", "medium", "long", "custom"],
            index=0,
            key=f"{key_prefix}_script_length_mode",
            format_func=lambda value: {
                "auto": tr("storyboard.option.content_mode.auto"),
                "short": "Short",
                "medium": "Medium",
                "long": "Long",
                "custom": tr("style.custom"),
            }[value],
        )
        if script_length_mode == "custom":
            script_target_words = int(
                st.number_input(
                    "Target Words",
                    min_value=1,
                    max_value=5000,
                    value=240,
                    step=10,
                    key=f"{key_prefix}_script_target_words",
                )
            )

    return build_storyboard_generation_payload(
        storyboard_mode=storyboard_mode,
        storyboard_count_mode=storyboard_count_mode,
        storyboard_scene_count=storyboard_scene_count,
        script_length_mode=script_length_mode,
        script_target_words=script_target_words,
    )


def render_content_input():
    """Render content input section (left column) with batch support"""
    with st.container(border=True):
        st.markdown(f"**{tr('section.content_input')}**")
        
        # ====================================================================
        # Step 1: Batch mode toggle (highest priority)
        # ====================================================================
        batch_mode = st.checkbox(
            tr("batch.mode_label"),
            value=False,
            help=tr("batch.mode_help")
        )
        
        if not batch_mode:
            # ================================================================
            # Single task mode (original logic, unchanged)
            # ================================================================
            # Processing mode selection
            mode = st.radio(
                "Processing Mode",
                ["generate", "fixed"],
                horizontal=True,
                format_func=lambda x: tr(f"mode.{x}"),
                label_visibility="collapsed"
            )
            
            # Text input (unified for both modes)
            text_placeholder = tr("input.topic_placeholder") if mode == "generate" else tr("input.content_placeholder")
            text_height = 120 if mode == "generate" else 200
            text_help = tr("input.text_help_generate") if mode == "generate" else tr("input.text_help_fixed")
            
            text = st.text_area(
                tr("input.text"),
                placeholder=text_placeholder,
                height=text_height,
                help=text_help
            )
            
            # Title input (optional for both modes)
            title = st.text_input(
                tr("input.title"),
                placeholder=tr("input.title_placeholder"),
                help=tr("input.title_help")
            )
            
            storyboard_generation = render_storyboard_generation_controls(
                mode=mode,
                key_prefix="single_video",
            )

            prompt_generation_performance = render_prompt_generation_performance_controls(
                key_prefix="single_video"
            )
            
            return {
                "batch_mode": False,
                "mode": mode,
                "text": text,
                "title": title,
                **storyboard_generation,
                **prompt_generation_performance,
            }
        
        else:
            # ================================================================
            # Batch mode (simplified YAGNI version)
            # ================================================================
            st.markdown(f"**{tr('batch.section_title')}**")
            
            # Batch rules info
            st.info(f"""
**{tr('batch.rules_title')}**
- ✅ {tr('batch.rule_1')}
- ✅ {tr('batch.rule_2')}
- ✅ {tr('batch.rule_3')}
            """)
            
            # Batch topics input
            text_input = st.text_area(
                tr("batch.topics_label"),
                height=300,
                placeholder=tr("batch.topics_placeholder"),
                help=tr("batch.topics_help")
            )
            
            # Split topics by newline
            if text_input:
                # Simple split by newline, filter empty lines
                topics = [
                    line.strip() 
                    for line in text_input.strip().split('\n') 
                    if line.strip()
                ]
                
                if topics:
                    # Check count limit
                    if len(topics) > 100:
                        st.error(tr("batch.count_error", count=len(topics)))
                        topics = []
                    else:
                        st.success(tr("batch.count_success", count=len(topics)))
                        
                        # Preview topics list
                        with st.expander(tr("batch.preview_title"), expanded=False):
                            for i, topic in enumerate(topics, 1):
                                st.markdown(f"`{i}.` {topic}")
                else:
                    topics = []
            else:
                topics = []
            
            st.markdown("---")
            
            # Title prefix (optional)
            title_prefix = st.text_input(
                tr("batch.title_prefix_label"),
                placeholder=tr("batch.title_prefix_placeholder"),
                help=tr("batch.title_prefix_help")
            )
            
            storyboard_generation = render_storyboard_generation_controls(
                mode="generate",
                key_prefix="batch_video",
            )

            prompt_generation_performance = render_prompt_generation_performance_controls(
                key_prefix="batch_video"
            )
            
            # Config info
            st.info(f"📌 {tr('batch.config_info')}")
            
            return {
                "batch_mode": True,
                "topics": topics,
                "mode": "generate",  # Fixed to AI generate content
                "title_prefix": title_prefix,
                **storyboard_generation,
                **prompt_generation_performance,
            }


def render_version_info():
    """Render version info and GitHub link"""
    with st.container(border=True):
        st.markdown(f"**{tr('version.title')}**")
        version = get_project_version()
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        
        # Version and GitHub link in one line
        github_url = "https://github.com/AIDC-AI/Pixelle-Video"
        badge_url = "https://img.shields.io/github/stars/AIDC-AI/Pixelle-Video"

        st.markdown(
            f'{tr("version.current")}: `{version}` &nbsp;&nbsp; '
            f'<a href="{github_url}" target="_blank">'
            f'<img src="{badge_url}" alt="GitHub stars" style="vertical-align: middle;">'
            f'</a>',
            unsafe_allow_html=True)
