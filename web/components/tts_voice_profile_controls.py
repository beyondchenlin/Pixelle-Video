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

from hashlib import sha1

import streamlit as st

from pixelle_video.services.tts_voice_profiles import (
    infer_tts_model_slug,
    list_voice_profiles,
    save_voice_profile,
)
from web.i18n import tr

NO_VOICE_PROFILE = "__none__"
DEFAULT_INDEXTTS2_VOICE_PROFILE = "\u73ed\u54e5-indextts2"
DEFAULT_OMNIVOICE_VOICE_PROFILE = "\u59ae-omnivoice"


def _profile_by_name(profiles: list[dict], name: str) -> dict | None:
    return next((profile for profile in profiles if profile.get("name") == name), None)


def _stable_widget_token(value: object) -> str:
    return sha1(str(value or "").encode("utf-8")).hexdigest()[:12]


def render_tts_voice_profile_controls(
    workflow_key: str | None,
    *,
    key_prefix: str = "tts",
) -> tuple[str | None, str | None]:
    """Render saved voice selection plus upload-and-save controls."""
    model_slug = infer_tts_model_slug(workflow_key)
    active_profile_key = f"{key_prefix}_active_voice_profile_{model_slug}"
    select_revision_key = f"{key_prefix}_voice_profile_select_revision_{model_slug}"

    profiles = list_voice_profiles(workflow_key)
    profile_names = [str(profile["name"]) for profile in profiles]
    active_profile_name = st.session_state.get(active_profile_key)
    if active_profile_name in profile_names:
        default_name = active_profile_name
    elif model_slug == "indextts2" and DEFAULT_INDEXTTS2_VOICE_PROFILE in profile_names:
        default_name = DEFAULT_INDEXTTS2_VOICE_PROFILE
    elif model_slug == "omnivoice" and DEFAULT_OMNIVOICE_VOICE_PROFILE in profile_names:
        default_name = DEFAULT_OMNIVOICE_VOICE_PROFILE
    else:
        default_name = NO_VOICE_PROFILE
    select_options = [NO_VOICE_PROFILE, *profile_names]
    select_index = select_options.index(default_name)
    select_revision = int(st.session_state.get(select_revision_key, 0) or 0)
    selected_name = st.selectbox(
        tr("tts.voice_profile_select"),
        select_options,
        index=select_index,
        key=f"{key_prefix}_voice_profile_select_{model_slug}_{select_revision}",
        format_func=lambda value: (
            tr("tts.voice_profile_none") if value == NO_VOICE_PROFILE else value
        ),
    )
    st.session_state[active_profile_key] = selected_name
    selected_profile = (
        None if selected_name == NO_VOICE_PROFILE else _profile_by_name(profiles, selected_name)
    )

    default_ref_audio_text = (
        str(selected_profile.get("ref_audio_text") or "") if selected_profile else ""
    )
    ref_text_token = _stable_widget_token(
        (selected_profile.get("id") or selected_name) if selected_profile else selected_name
    )
    ref_audio_text = st.text_area(
        tr("tts.ref_audio_text"),
        value=default_ref_audio_text,
        placeholder=tr("tts.ref_audio_text_placeholder"),
        help=tr("tts.ref_audio_text_help"),
        key=f"{key_prefix}_ref_audio_text_{model_slug}_{ref_text_token}",
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
            st.session_state[active_profile_key] = saved_profile["name"]
            st.session_state[select_revision_key] = select_revision + 1
            st.success(tr("tts.voice_profile_saved", name=saved_profile["name"]))
            return str(saved_profile["audio_path"]), ref_audio_text or None

    if selected_profile:
        return str(selected_profile["audio_path"]), ref_audio_text or None
    return None, ref_audio_text or None
