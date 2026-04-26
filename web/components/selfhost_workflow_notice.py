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

"""Inline Streamlit guidance for local ComfyUI workflow selections."""

import streamlit as st

from pixelle_video.config import config_manager
from web.i18n import tr


def is_selfhost_workflow(workflow_path: str | None) -> bool:
    """Return whether a workflow key points at the local ComfyUI folder."""
    return bool(workflow_path and str(workflow_path).startswith("selfhost/"))


def display_workflow_path(workflow_path: str) -> str:
    """Convert a workflow key to the project-relative path users can load."""
    normalized = str(workflow_path).strip()
    if normalized.startswith("workflows/"):
        return normalized
    return f"workflows/{normalized}"


def render_selfhost_workflow_notice(
    workflow_path: str | None,
    *,
    expanded: bool = True,
) -> bool:
    """Render local ComfyUI preflight guidance next to a selected workflow."""
    if not expanded or not is_selfhost_workflow(workflow_path):
        return False

    workflow_display_path = display_workflow_path(str(workflow_path))
    comfyui_config = config_manager.get_comfyui_config()
    comfyui_url = comfyui_config.get("comfyui_url", "http://127.0.0.1:8188")

    with st.container(border=True):
        st.markdown(f"**{tr('selfhost.warning.inline_title')}**")
        st.markdown(f"`{workflow_display_path}`")
        st.markdown(
            tr(
                "selfhost.warning.message",
                comfyui_url=comfyui_url,
                workflow_path=workflow_display_path,
            )
        )
        st.warning(tr("selfhost.warning.hint"))
    return True
