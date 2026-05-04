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
Style configuration components for web UI (middle column)
"""

import os

import streamlit as st
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.workflow_defaults import DEFAULT_TTS_WORKFLOW
from web.components.selfhost_workflow_notice import render_selfhost_workflow_notice
from web.components.tts_voice_profile_controls import render_tts_voice_profile_controls
from web.i18n import get_language, tr
from web.utils.async_helpers import run_async
from web.utils.tts_ui import resolve_comfyui_tts_speed, resolve_configured_tts_mode
from web.utils.workflow_defaults import resolve_selectbox_default_index


def render_style_config(pixelle_video):
    """Render style configuration section (middle column)"""
    # TTS Section (moved from left column)
    # ====================================================================
    with st.container(border=True):
        st.markdown(f"**{tr('section.tts')}**")
        
        with st.expander(tr("help.feature_description"), expanded=False):
            st.markdown(f"**{tr('help.what')}**")
            st.markdown(tr("tts.what"))
            st.markdown(f"**{tr('help.how')}**")
            st.markdown(tr("tts.how"))
        
        # Get TTS config
        comfyui_config = config_manager.get_comfyui_config()
        tts_config = comfyui_config["tts"]
        
        # Inference mode selection
        tts_mode = st.radio(
            tr("tts.inference_mode"),
            ["local", "comfyui"],
            horizontal=True,
            format_func=lambda x: tr(f"tts.mode.{x}"),
            index=0 if resolve_configured_tts_mode(tts_config) == "local" else 1,
            key="digital_tts_inference_mode"
        )
        
        # Show hint based on mode
        if tts_mode == "local":
            st.caption(tr("tts.mode.local_hint"))
        else:
            st.caption(tr("tts.mode.comfyui_hint"))
        
        # ================================================================
        # Local Mode UI
        # ================================================================
        if tts_mode == "local":
            # Import voice configuration
            from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
            
            # Get saved voice from config
            local_config = tts_config.get("local", {})
            saved_voice = local_config.get("voice", "zh-CN-YunjianNeural")
            saved_speed = local_config.get("speed", 1.2)
            
            # Build voice options with i18n
            voice_options = []
            voice_ids = []
            default_voice_index = 0
            
            for idx, voice_config in enumerate(EDGE_TTS_VOICES):
                voice_id = voice_config["id"]
                display_name = get_voice_display_name(voice_id, tr, get_language())
                voice_options.append(display_name)
                voice_ids.append(voice_id)
                
                # Set default index if matches saved voice
                if voice_id == saved_voice:
                    default_voice_index = idx
            
            # Two-column layout: Voice | Speed
            voice_col, speed_col = st.columns([1, 1])
            
            with voice_col:
                # Voice selector
                selected_voice_display = st.selectbox(
                    tr("tts.voice_selector"),
                    voice_options,
                    index=default_voice_index,
                    key="digital_tts_local_voice"
                )
                
                # Get actual voice ID
                selected_voice_index = voice_options.index(selected_voice_display)
                selected_voice = voice_ids[selected_voice_index]
            
            with speed_col:
                # Speed slider
                tts_speed = st.slider(
                    tr("tts.speed"),
                    min_value=0.5,
                    max_value=2.0,
                    value=saved_speed,
                    step=0.1,
                    format="%.1fx",
                    key="digital_tts_local_speed"
                )
                st.caption(tr("tts.speed_label", speed=f"{tts_speed:.1f}"))
            
            # Variables for video generation
            tts_workflow_key = None
            ref_audio_path = None
            ref_audio_text = None
        
        # ================================================================
        # ComfyUI Mode UI
        # ================================================================
        else:  # comfyui mode
            tts_workflows = pixelle_video.tts.list_workflows()
            tts_workflow_options = [wf["display_name"] for wf in tts_workflows]
            tts_workflow_keys = [wf["key"] for wf in tts_workflows]

            saved_tts_workflow = tts_config.get("comfyui", {}).get("default_workflow")
            default_tts_index = resolve_selectbox_default_index(
                domain="tts",
                workflow_keys=tts_workflow_keys,
                configured_workflow=saved_tts_workflow,
            )

            tts_workflow_display = st.selectbox(
                "TTS Workflow",
                tts_workflow_options if tts_workflow_options else ["No TTS workflows found"],
                index=default_tts_index,
                label_visibility="collapsed",
                key="digital_tts_workflow_select",
            )

            if tts_workflow_options:
                tts_selected_index = tts_workflow_options.index(tts_workflow_display)
                tts_workflow_key = tts_workflow_keys[tts_selected_index]
            else:
                tts_workflow_key = DEFAULT_TTS_WORKFLOW

            render_selfhost_workflow_notice(tts_workflow_key)
            ref_audio_path, ref_audio_text = render_tts_voice_profile_controls(
                tts_workflow_key,
                key_prefix="digital_tts",
            )
            
            # Variables for video generation
            selected_voice = None
            tts_speed = resolve_comfyui_tts_speed(tts_config)
        
        # ================================================================
        # TTS Preview (works for both modes)
        # ================================================================
        with st.expander(tr("tts.preview_title"), expanded=False):
            # Preview text input
            preview_text = st.text_input(
                tr("tts.preview_text"),
                value="大家好，这是一段测试语音。",
                placeholder=tr("tts.preview_text_placeholder"),
                key="digital_tts_preview_text"
            )
            
            # Preview button
            if st.button(tr("tts.preview_button"), key="gidital_preview_tts", width="stretch"):
                with st.spinner(tr("tts.previewing")):
                    try:
                        # Build TTS params based on mode
                        tts_params = {
                            "text": preview_text,
                            "inference_mode": tts_mode
                        }
                        
                        if tts_mode == "local":
                            tts_params["voice"] = selected_voice
                            tts_params["speed"] = tts_speed
                        else:  # comfyui
                            tts_params["workflow"] = tts_workflow_key
                            tts_params["speed"] = tts_speed
                            if ref_audio_path:
                                tts_params["ref_audio"] = str(ref_audio_path)
                            if ref_audio_text:
                                tts_params["ref_audio_text"] = ref_audio_text
                        
                        audio_path = run_async(pixelle_video.tts(**tts_params))
                        
                        # Play the audio
                        if audio_path:
                            st.success(tr("tts.preview_success"))
                            if os.path.exists(audio_path):
                                st.audio(audio_path, format="audio/mp3")
                            elif audio_path.startswith('http'):
                                st.audio(audio_path)
                            else:
                                st.error("Failed to generate preview audio")
                            
                            # Show file path
                            st.caption(f"📁 {audio_path}")
                        else:
                            st.error("Failed to generate preview audio")
                    except Exception as e:
                        st.error(tr("tts.preview_failed", error=str(e)))
                        logger.exception(e)
    
    # Return all style configuration parameters (Simplified version only local TTS)
    return {
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice if tts_mode == "local" else None,
        "tts_speed": tts_speed,
        "tts_workflow": tts_workflow_key if tts_mode == "comfyui" else None,
        "ref_audio": str(ref_audio_path) if ref_audio_path else None,
        "ref_audio_text": ref_audio_text if tts_mode == "comfyui" and ref_audio_text else None,
    }
