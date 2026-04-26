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

"""Streamlit controls for reusable ComfyUI TTS reference voices."""

import streamlit as st

from pixelle_video.services.tts_voice_profiles import (
    list_voice_profiles,
    save_voice_profile,
)
from web.i18n import tr

NO_VOICE_PROFILE = "__none__"


def _profile_by_name(profiles: list[dict], name: str) -> dict | None:
    return next((profile for profile in profiles if profile.get("name") == name), None)


def render_tts_voice_profile_controls(
    workflow_key: str | None,
    *,
    key_prefix: str = "tts",
) -> tuple[str | None, str | None]:
    """Render saved voice selection plus upload-and-save controls."""
    profiles = list_voice_profiles(workflow_key)
    profile_names = [str(profile["name"]) for profile in profiles]
    selected_name = st.selectbox(
        tr("tts.voice_profile_select"),
        [NO_VOICE_PROFILE, *profile_names],
        key=f"{key_prefix}_voice_profile_select",
        format_func=lambda value: (
            tr("tts.voice_profile_none") if value == NO_VOICE_PROFILE else value
        ),
    )
    selected_profile = (
        None if selected_name == NO_VOICE_PROFILE else _profile_by_name(profiles, selected_name)
    )

    default_ref_audio_text = (
        str(selected_profile.get("ref_audio_text") or "") if selected_profile else ""
    )
    ref_audio_text = st.text_area(
        tr("tts.ref_audio_text"),
        value=default_ref_audio_text,
        placeholder=tr("tts.ref_audio_text_placeholder"),
        help=tr("tts.ref_audio_text_help"),
        key=f"{key_prefix}_ref_audio_text",
        height=90,
    )

    uploaded_file = st.file_uploader(
        tr("tts.ref_audio"),
        type=["mp3", "wav", "flac", "m4a", "aac", "ogg"],
        help=tr("tts.ref_audio_help"),
        key=f"{key_prefix}_ref_audio_upload",
    )

    if uploaded_file is not None:
        st.audio(uploaded_file)
        base_name = st.text_input(
            tr("tts.voice_profile_name"),
            placeholder=tr("tts.voice_profile_name_placeholder"),
            key=f"{key_prefix}_voice_profile_name",
        )
        if st.button(tr("tts.voice_profile_save"), key=f"{key_prefix}_voice_profile_save"):
            if not str(base_name or "").strip():
                st.warning(tr("tts.voice_profile_name_required"))
                return (
                    str(selected_profile.get("audio_path")) if selected_profile else None,
                    ref_audio_text or None,
                )

            saved_profile = save_voice_profile(
                upload=uploaded_file,
                base_name=base_name,
                workflow_key=workflow_key,
                ref_audio_text=ref_audio_text,
            )
            st.success(tr("tts.voice_profile_saved", name=saved_profile["name"]))
            return str(saved_profile["audio_path"]), ref_audio_text or None

    if selected_profile:
        return str(selected_profile["audio_path"]), ref_audio_text or None
    return None, ref_audio_text or None
