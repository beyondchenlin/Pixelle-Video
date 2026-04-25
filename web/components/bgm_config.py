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
Background music configuration components for web UI.
"""

import streamlit as st

from pixelle_video.utils import os_util
from web.i18n import tr

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg")


def render_bgm_section(key_prefix="", *, collapsible=False):
    """Render the shared background music configuration section."""
    if collapsible:
        with st.expander(tr("section.bgm"), expanded=False):
            return _render_bgm_controls(key_prefix=key_prefix, help_display="popover")

    with st.container(border=True):
        st.markdown(f"**{tr('section.bgm')}**")
        return _render_bgm_controls(key_prefix=key_prefix, help_display="expander")


def _render_bgm_feature_description(help_display: str) -> None:
    help_context = (
        st.popover(tr("help.feature_description"))
        if help_display == "popover"
        else st.expander(tr("help.feature_description"), expanded=False)
    )
    with help_context:
        st.markdown(f"**{tr('help.what')}**")
        st.markdown(tr("bgm.what"))
        st.markdown(f"**{tr('help.how')}**")
        st.markdown(tr("bgm.how"))


def _render_bgm_controls(key_prefix="", *, help_display="expander"):
    _render_bgm_feature_description(help_display)

    try:
        all_files = os_util.list_resource_files("bgm")
        bgm_files = sorted([f for f in all_files if f.lower().endswith(AUDIO_EXTENSIONS)])
    except Exception as e:
        st.warning(f"Failed to load BGM files: {e}")
        bgm_files = []

    bgm_options = [tr("bgm.none")] + bgm_files

    default_index = 0
    if "default.mp3" in bgm_files:
        default_index = bgm_options.index("default.mp3")

    bgm_choice = st.selectbox(
        "BGM",
        bgm_options,
        index=default_index,
        label_visibility="collapsed",
        key=f"{key_prefix}bgm_selector",
    )

    if bgm_choice != tr("bgm.none"):
        bgm_volume = st.slider(
            tr("bgm.volume"),
            min_value=0.0,
            max_value=0.5,
            value=0.2,
            step=0.01,
            format="%.2f",
            key=f"{key_prefix}bgm_volume_slider",
            help=tr("bgm.volume_help"),
        )
    else:
        bgm_volume = 0.2

    if bgm_choice != tr("bgm.none"):
        if st.button(tr("bgm.preview"), key=f"{key_prefix}preview_bgm", width="stretch"):
            try:
                if os_util.resource_exists("bgm", bgm_choice):
                    bgm_file_path = os_util.get_resource_path("bgm", bgm_choice)
                    st.audio(bgm_file_path)
                else:
                    st.error(tr("bgm.preview_failed", file=bgm_choice))
            except Exception as e:
                st.error(f"{tr('bgm.preview_failed', file=bgm_choice)}: {e}")

    bgm_path = None if bgm_choice == tr("bgm.none") else bgm_choice

    return {
        "bgm_path": bgm_path,
        "bgm_volume": bgm_volume,
    }
