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
Output preview components for web UI (right column)
"""

import os

import streamlit as st
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.config.tts_defaults import resolve_tts_inference_mode
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.video_generation_contract import is_plan_frame_override_payload
from pixelle_video.utils.logging_util import build_content_observability, new_correlation_id
from web.components.prompt_generation_performance import (
    copy_prompt_generation_performance_params,
)
from web.components.recent_video_gallery import (
    render_recent_video_gallery,
    store_recent_generated_video,
)
from web.i18n import tr
from web.utils.async_helpers import run_async
from web.utils.render_backend_ui import copy_render_backend
from web.utils.streamlit_helpers import RefreshableSlot
from web.utils.tts_audio_strategy_ui import copy_tts_audio_strategy
from web.utils.tts_split_mode_ui import TTS_SPLIT_SETTING_KEYS, copy_tts_split_settings

VIDEO_PREVIEW_CONTAINER_KEY = "output_video_preview"
VIDEO_PREVIEW_WIDTH = "50%"


def _resolve_video_tts_mode(video_params):
    return resolve_tts_inference_mode(None, video_params.get("tts_inference_mode"))


ELEMENT_ANIMATION_OPTION_KEYS = (
    "element_animation_enabled",
    "element_animation_backend",
    "element_animation_subject_count",
    "element_animation_candidate_limit",
    "element_animation_prompt",
    "element_animation_intensity",
    "element_animation_workflow",
)
STORYBOARD_GENERATION_OPTION_KEYS = (
    "storyboard_mode",
    "storyboard_count_mode",
    "storyboard_scene_count",
    "script_length_mode",
    "script_target_words",
)
SINGLE_VIDEO_GENERATING_KEY = "single_video_is_generating"
SINGLE_VIDEO_REQUESTED_KEY = "single_video_generation_requested"
SINGLE_VIDEO_DUPLICATE_CLICK_KEY = "single_video_duplicate_click"
SINGLE_VIDEO_BUTTON_KEY = "single_video_generate_button"


def _plan_identity_frame_overrides(video_params):
    return [
        dict(override)
        for override in video_params.get("frame_overrides") or []
        if isinstance(override, dict) and is_plan_frame_override_payload(override)
    ]


def _get_or_create_log_session_id(session_state) -> str:
    session_id = session_state.get("log_session_id")
    if not session_id:
        session_id = new_correlation_id("sess")
        session_state["log_session_id"] = session_id
    return session_id


def _request_single_video_generation() -> None:
    """Mark a single-video generation request unless one is already running."""
    if st.session_state.get(SINGLE_VIDEO_GENERATING_KEY):
        st.session_state[SINGLE_VIDEO_DUPLICATE_CLICK_KEY] = True
        return

    st.session_state[SINGLE_VIDEO_GENERATING_KEY] = True
    st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = True


def _reset_single_video_generation_state() -> None:
    st.session_state[SINGLE_VIDEO_GENERATING_KEY] = False
    st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = False


def build_video_preview_css(
    container_key: str = VIDEO_PREVIEW_CONTAINER_KEY,
    *,
    width: str = VIDEO_PREVIEW_WIDTH,
) -> str:
    """Build scoped CSS that shrinks the generated video preview inside one container."""
    return f"""
    <style>
    .st-key-{container_key} [data-testid="stVideo"] {{
        width: {width} !important;
        max-width: 100% !important;
        display: block;
        margin-inline: auto;
        height: auto;
    }}
    </style>
    """


def render_scaled_video_preview(video_path: str) -> None:
    """Render the generated video preview at a smaller, centered size."""
    st.markdown(build_video_preview_css(), unsafe_allow_html=True)
    with st.container(key=VIDEO_PREVIEW_CONTAINER_KEY):
        st.video(video_path, width="stretch")


def copy_element_animation_options(source, target):
    """Copy element animation UI params into a generation request dict."""
    for key in ELEMENT_ANIMATION_OPTION_KEYS:
        if key in source and source[key] is not None:
            target[key] = source[key]


def copy_storyboard_generation_options(source, target):
    """Copy storyboard generation contract params into a generation request dict."""
    defaults = {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "auto",
        "script_length_mode": "auto",
    }
    for key, default in defaults.items():
        target[key] = source.get(key) or default
    for key in ("storyboard_scene_count", "script_target_words"):
        if source.get(key) is not None:
            target[key] = source[key]


def render_output_preview(pixelle_video, video_params):
    """Render output preview section (right column)"""
    # Check if batch mode
    is_batch = video_params.get("batch_mode", False)

    if is_batch:
        # Batch generation mode
        render_batch_output(pixelle_video, video_params)
    else:
        # Single video generation mode (original logic)
        render_single_output(pixelle_video, video_params)


def build_single_generation_request(video_params, *, progress_callback, session_state):
    """Build a single generate_video() request from UI params."""
    request = {
        "text": video_params.get("text", ""),
        "mode": video_params.get("mode", "generate"),
        "title": video_params.get("title") if video_params.get("title") else None,
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix", ""),
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume", 0.2)
        if video_params.get("bgm_path")
        else 0.2,
        "progress_callback": progress_callback,
        "media_width": session_state.get("template_media_width"),
        "media_height": session_state.get("template_media_height"),
        "tts_inference_mode": _resolve_video_tts_mode(video_params),
        "world_preset_id": video_params.get("world_preset_id"),
        "shot_preset_id": video_params.get("shot_preset_id"),
        "consistency_strength": video_params.get("consistency_strength") or "standard",
        "content_mode": video_params.get("content_mode"),
        "role_strategy": video_params.get("role_strategy"),
        "role_locking_strength": video_params.get("role_locking_strength"),
        "shot_strategy": video_params.get("shot_strategy"),
    }
    plan_frame_overrides = _plan_identity_frame_overrides(video_params)
    if plan_frame_overrides:
        request["frame_overrides"] = plan_frame_overrides

    if request["tts_inference_mode"] == "local":
        request["tts_voice"] = video_params.get("tts_voice")
    else:
        request["tts_workflow"] = video_params.get("tts_workflow")
        ref_audio_path = video_params.get("ref_audio")
        if ref_audio_path:
            request["ref_audio"] = str(ref_audio_path)
        ref_audio_text = video_params.get("ref_audio_text")
        if ref_audio_text:
            request["ref_audio_text"] = ref_audio_text

    tts_speed = video_params.get("tts_speed")
    if tts_speed is not None:
        request["tts_speed"] = tts_speed

    template_params = video_params.get("template_params", {})
    if template_params:
        request["template_params"] = template_params

    copy_render_backend(video_params, request)
    copy_tts_audio_strategy(video_params, request)
    copy_tts_split_settings(video_params, request)
    copy_storyboard_generation_options(video_params, request)
    copy_element_animation_options(video_params, request)
    copy_prompt_generation_performance_params(video_params, request)
    if video_params.get("text_rendering") is not None:
        request["text_rendering"] = video_params["text_rendering"]

    if video_params.get("request_id"):
        request["request_id"] = video_params["request_id"]
    if video_params.get("session_id"):
        request["session_id"] = video_params["session_id"]
    return request


def build_batch_shared_config(video_params):
    """Build batch shared_config from Web UI params."""
    shared_config = {
        "title_prefix": video_params.get("title_prefix"),
        "media_workflow": video_params.get("media_workflow"),
        "frame_template": video_params.get("frame_template"),
        "prompt_prefix": video_params.get("prompt_prefix") or "",
        "bgm_path": video_params.get("bgm_path"),
        "bgm_volume": video_params.get("bgm_volume") or 0.2,
        "tts_inference_mode": _resolve_video_tts_mode(video_params),
        "media_width": video_params.get("media_width"),
        "media_height": video_params.get("media_height"),
        "world_preset_id": video_params.get("world_preset_id"),
        "shot_preset_id": video_params.get("shot_preset_id"),
        "consistency_strength": video_params.get("consistency_strength") or "standard",
        "content_mode": video_params.get("content_mode"),
        "role_strategy": video_params.get("role_strategy"),
        "role_locking_strength": video_params.get("role_locking_strength"),
        "shot_strategy": video_params.get("shot_strategy"),
    }
    plan_frame_overrides = _plan_identity_frame_overrides(video_params)
    if plan_frame_overrides:
        shared_config["frame_overrides"] = plan_frame_overrides

    tts_speed = video_params.get("tts_speed")
    if tts_speed is not None:
        shared_config["tts_speed"] = tts_speed

    if shared_config["tts_inference_mode"] == "local":
        tts_voice = video_params.get("tts_voice")
        if tts_voice:
            shared_config["tts_voice"] = tts_voice
    else:
        tts_workflow = video_params.get("tts_workflow")
        if tts_workflow:
            shared_config["tts_workflow"] = tts_workflow
        ref_audio = video_params.get("ref_audio")
        if ref_audio:
            shared_config["ref_audio"] = str(ref_audio)
        ref_audio_text = video_params.get("ref_audio_text")
        if ref_audio_text:
            shared_config["ref_audio_text"] = ref_audio_text

    if video_params.get("template_params"):
        shared_config["template_params"] = video_params["template_params"]

    if video_params.get("session_id"):
        shared_config["session_id"] = video_params["session_id"]

    copy_render_backend(video_params, shared_config)
    copy_tts_audio_strategy(video_params, shared_config)
    copy_tts_split_settings(video_params, shared_config)
    copy_storyboard_generation_options(video_params, shared_config)
    copy_element_animation_options(video_params, shared_config)
    copy_prompt_generation_performance_params(video_params, shared_config)
    if video_params.get("text_rendering") is not None:
        shared_config["text_rendering"] = video_params["text_rendering"]
    return shared_config


def render_single_output(pixelle_video, video_params):
    """Render single video generation output with a recent-video gallery."""
    # Extract parameters from video_params dict
    text = video_params.get("text", "")
    mode = video_params.get("mode", "generate")
    title = video_params.get("title")
    bgm_path = video_params.get("bgm_path")
    bgm_volume = video_params.get("bgm_volume", 0.2)

    tts_mode = _resolve_video_tts_mode(video_params)
    selected_voice = video_params.get("tts_voice")
    tts_speed = video_params.get("tts_speed")
    tts_workflow_key = video_params.get("tts_workflow")
    ref_audio_path = video_params.get("ref_audio")
    ref_audio_text = video_params.get("ref_audio_text")

    frame_template = video_params.get("frame_template")
    custom_values_for_video = video_params.get("template_params", {})
    workflow_key = video_params.get("media_workflow")
    prompt_prefix = video_params.get("prompt_prefix", "")

    with st.container(border=True):
        st.markdown(f"**{tr('section.video_generation')}**")

        # Check if system is configured
        if not config_manager.validate():
            st.warning(tr("settings.not_configured"))

        # Generate Button
        button_slot = RefreshableSlot(st.empty())
        was_generating = bool(st.session_state.get(SINGLE_VIDEO_GENERATING_KEY, False))

        def render_generate_button(*, disabled: bool, refresh: bool = False) -> bool:
            def render_button(key_suffix: str) -> bool:
                return st.button(
                    tr("btn.generate"),
                    key=f"{SINGLE_VIDEO_BUTTON_KEY}{key_suffix}",
                    type="primary",
                    width="stretch",
                    disabled=disabled,
                    on_click=_request_single_video_generation,
                )

            return button_slot.render(render_button, refresh=refresh)

        button_clicked = render_generate_button(disabled=was_generating)
        generation_requested = bool(st.session_state.pop(SINGLE_VIDEO_REQUESTED_KEY, False))
        st.session_state[SINGLE_VIDEO_REQUESTED_KEY] = False
        if button_clicked and not generation_requested:
            if was_generating:
                st.session_state[SINGLE_VIDEO_DUPLICATE_CLICK_KEY] = True
            else:
                st.session_state[SINGLE_VIDEO_GENERATING_KEY] = True
                generation_requested = True

        if (
            st.session_state.pop(SINGLE_VIDEO_DUPLICATE_CLICK_KEY, False)
            and not generation_requested
        ):
            st.info(tr("status.generation_in_progress"))

        gallery_slot = None
        gallery_rendered = False

        def render_gallery(*, refresh: bool = False) -> None:
            nonlocal gallery_rendered

            if gallery_slot is None:
                render_recent_video_gallery(pixelle_video)
                gallery_rendered = True
                return

            gallery_slot.render(
                lambda key_suffix: render_recent_video_gallery(
                    pixelle_video,
                    key_suffix=key_suffix,
                ),
                refresh=refresh,
            )
            gallery_rendered = True

        if generation_requested:
            can_generate = True
            # Validate system configuration
            if not config_manager.validate():
                st.error(tr("settings.not_configured"))
                can_generate = False

            # Validate input
            if not text:
                st.error(tr("error.input_required"))
                can_generate = False

            if can_generate:
                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                gallery_slot = RefreshableSlot(st.empty())
                render_gallery()

                # Record start time for generation
                import time
                start_time = time.time()

                try:
                    request_id = new_correlation_id("req")
                    session_id = _get_or_create_log_session_id(st.session_state)
                    logger.bind(
                        channel="runtime",
                        request_id=request_id,
                        session_id=session_id,
                        content=build_content_observability(text),
                    ).info("web single generation request received")

                    # Progress callback to update UI
                    def update_progress(event: ProgressEvent):
                        """Update progress bar and status text from ProgressEvent"""
                        # Translate event to user-facing message
                        if event.event_type == "frame_step":
                            # Frame step: "分镜 3/5 - 步骤 2/4: 生成插图"
                            action_key = f"progress.step_{event.action}"
                            action_text = tr(action_key)
                            message = tr(
                                "progress.frame_step",
                                current=event.frame_current,
                                total=event.frame_total,
                                step=event.step,
                                action=action_text
                            )
                        elif event.event_type == "processing_frame":
                            # Processing frame: "分镜 3/5"
                            message = tr(
                                "progress.frame",
                                current=event.frame_current,
                                total=event.frame_total
                            )
                        else:
                            # Simple events: use i18n key directly
                            message = tr(f"progress.{event.event_type}")

                        # Append extra_info if available (e.g., batch progress)
                        if event.extra_info:
                            message = f"{message} - {tr(event.extra_info)}"

                        status_text.text(message)
                        progress_bar.progress(min(int(event.progress * 100), 99))  # Cap at 99% until complete

                    generation_request = build_single_generation_request(
                        {
                            "text": text,
                            "mode": mode,
                            "title": title,
                            **{
                                key: video_params.get(key)
                                for key in STORYBOARD_GENERATION_OPTION_KEYS
                            },
                            "media_workflow": workflow_key,
                            "frame_template": frame_template,
                            "prompt_prefix": prompt_prefix,
                            "bgm_path": bgm_path,
                            "bgm_volume": bgm_volume,
                            "tts_inference_mode": tts_mode,
                            "tts_voice": selected_voice,
                            "tts_speed": tts_speed,
                            "tts_workflow": tts_workflow_key,
                            "ref_audio": ref_audio_path,
                            "ref_audio_text": ref_audio_text,
                            "template_params": custom_values_for_video,
                            "request_id": request_id,
                            "session_id": session_id,
                            "render_backend": video_params.get("render_backend"),
                            "tts_audio_strategy": video_params.get("tts_audio_strategy"),
                            "world_preset_id": video_params.get("world_preset_id"),
                            "shot_preset_id": video_params.get("shot_preset_id"),
                            "consistency_strength": video_params.get("consistency_strength"),
                            "content_mode": video_params.get("content_mode"),
                            "role_strategy": video_params.get("role_strategy"),
                            "role_locking_strength": video_params.get("role_locking_strength"),
                            "shot_strategy": video_params.get("shot_strategy"),
                            "frame_overrides": video_params.get("frame_overrides"),
                            "text_rendering": video_params.get("text_rendering"),
                            **{
                                key: video_params.get(key)
                                for key in TTS_SPLIT_SETTING_KEYS
                            },
                            **{
                                key: video_params.get(key)
                                for key in ELEMENT_ANIMATION_OPTION_KEYS
                            },
                        },
                        progress_callback=update_progress,
                        session_state=st.session_state,
                    )

                    result = run_async(pixelle_video.generate_video(**generation_request))
                    st.session_state["storyboard_preview_snapshot"] = getattr(
                        result.storyboard,
                        "planning_snapshot",
                        None,
                    )

                    # Calculate total generation time
                    total_generation_time = time.time() - start_time

                    progress_bar.progress(100)
                    status_text.text(tr("status.success"))

                    # Display success message
                    st.success(tr("status.video_generated", path=result.video_path))

                    st.markdown("---")

                    # Video information (compact display)
                    file_size_mb = result.file_size / (1024 * 1024)

                    # Parse video size from template path
                    from pixelle_video.utils.template_util import (
                        parse_template_size,
                        resolve_template_path,
                    )
                    template_path = resolve_template_path(result.storyboard.config.frame_template)
                    video_width, video_height = parse_template_size(template_path)

                    info_text = (
                        f"⏱️ {tr('info.generation_time')} {total_generation_time:.1f}s   "
                        f"📦 {file_size_mb:.2f}MB   "
                        f"🎬 {len(result.storyboard.frames)}{tr('info.scenes_unit')}   "
                        f"📐 {video_width}x{video_height}"
                    )
                    st.caption(info_text)

                    if os.path.exists(result.video_path):
                        store_recent_generated_video(result, st.session_state)
                        render_gallery(refresh=True)
                    else:
                        st.error(tr("status.video_not_found", path=result.video_path))

                except Exception as e:
                    status_text.text("")
                    progress_bar.empty()
                    st.error(tr("status.error", error=str(e)))
                    logger.exception(e)
                finally:
                    _reset_single_video_generation_state()
                    render_generate_button(disabled=False, refresh=True)
            else:
                _reset_single_video_generation_state()
                render_generate_button(disabled=False, refresh=True)

        if not gallery_rendered:
            render_gallery()


def render_batch_output(pixelle_video, video_params):
    """Render batch generation output (minimal, redirect to History)"""
    topics = video_params.get("topics", [])

    with st.container(border=True):
        st.markdown(f"**{tr('batch.section_generation')}**")

        # Check if topics are provided
        if not topics:
            st.warning(tr("batch.no_topics"))
            return

        # Check system configuration
        if not config_manager.validate():
            st.warning(tr("settings.not_configured"))
            return

        batch_count = len(topics)

        # Display batch info
        st.info(tr("batch.prepare_info", count=batch_count))

        # Estimated time (optional)
        estimated_minutes = batch_count * 3  # Assume 3 minutes per video
        st.caption(tr("batch.estimated_time", minutes=estimated_minutes))

        # Generate button with batch semantics
        if st.button(
            tr("batch.generate_button", count=batch_count),
            type="primary",
            width="stretch",
            help=tr("batch.generate_help")
        ):
            session_id = _get_or_create_log_session_id(st.session_state)
            video_params = {**video_params, "session_id": session_id}
            # Prepare shared config
            shared_config = build_batch_shared_config(video_params)

            # UI containers
            overall_progress_container = st.container()
            current_task_container = st.container()

            # Overall progress UI
            overall_progress_bar = overall_progress_container.progress(0)
            overall_status = overall_progress_container.empty()

            # Current task progress UI
            current_task_title = current_task_container.empty()
            current_task_progress = current_task_container.progress(0)
            current_task_status = current_task_container.empty()

            # Overall progress callback
            def update_overall_progress(current, total, topic):
                progress = (current - 1) / total
                overall_progress_bar.progress(progress)
                overall_status.markdown(
                    f"📊 **{tr('batch.overall_progress')}**: {current}/{total} ({int(progress * 100)}%)"
                )

            # Single task progress callback factory
            def make_task_progress_callback(task_idx, topic):
                def callback(event: ProgressEvent):
                    # Display current task title
                    current_task_title.markdown(f"🎬 **{tr('batch.current_task')} {task_idx}**: {topic}")

                    # Update task detailed progress
                    if event.event_type == "frame_step":
                        action_key = f"progress.step_{event.action}"
                        action_text = tr(action_key)
                        message = tr(
                            "progress.frame_step",
                            current=event.frame_current,
                            total=event.frame_total,
                            step=event.step,
                            action=action_text
                        )
                    elif event.event_type == "processing_frame":
                        message = tr(
                            "progress.frame",
                            current=event.frame_current,
                            total=event.frame_total
                        )
                    else:
                        message = tr(f"progress.{event.event_type}")

                    if event.extra_info:
                        message = f"{message} - {tr(event.extra_info)}"

                    current_task_progress.progress(event.progress)
                    current_task_status.text(message)

                return callback

            # Execute batch generation
            import time

            from web.utils.batch_manager import SimpleBatchManager

            batch_manager = SimpleBatchManager()
            start_time = time.time()

            batch_result = batch_manager.execute_batch(
                pixelle_video=pixelle_video,
                topics=topics,
                shared_config=shared_config,
                overall_progress_callback=update_overall_progress,
                task_progress_callback_factory=make_task_progress_callback
            )

            latest_planning_snapshot = None
            for item in batch_result.get("results", []):
                planning_snapshot = item.get("planning_snapshot")
                if planning_snapshot is not None:
                    latest_planning_snapshot = planning_snapshot

            if latest_planning_snapshot is not None:
                st.session_state["storyboard_preview_snapshot"] = latest_planning_snapshot
            else:
                st.session_state["storyboard_preview_snapshot"] = None

            total_time = time.time() - start_time

            # Clear progress displays
            overall_progress_bar.progress(1.0)
            overall_status.markdown(f"✅ **{tr('batch.completed')}**")
            current_task_title.empty()
            current_task_progress.empty()
            current_task_status.empty()

            # Display results summary
            st.markdown("---")
            st.markdown(f"**{tr('batch.results_title')}**")

            col1, col2, col3 = st.columns(3)
            col1.metric(tr("batch.total"), batch_result["total_count"])
            col2.metric(f"✅ {tr('batch.success')}", batch_result["success_count"])
            col3.metric(f"❌ {tr('batch.failed')}", batch_result["failed_count"])

            # Display total time
            minutes = int(total_time / 60)
            seconds = int(total_time % 60)
            st.caption(f"⏱️ {tr('batch.total_time')}: {minutes}{tr('batch.minutes')}{seconds}{tr('batch.seconds')}")

            # Redirect to History page
            st.markdown("---")
            st.success(tr("batch.success_message"))
            st.info(tr("batch.view_in_history"))

            # Button to go to History page using JavaScript URL navigation
            st.markdown(
                f"""
                <a href="/History" target="_blank">
                    <button style="
                        width: 100%;
                        padding: 0.5rem 1rem;
                        background-color: white;
                        color: rgb(49, 51, 63);
                        border: 1px solid rgba(49, 51, 63, 0.2);
                        border-radius: 0.5rem;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 400;
                        text-align: center;
                    ">
                        📚 {tr('batch.goto_history')}
                    </button>
                </a>
                """,
                unsafe_allow_html=True
            )

            # Show failed tasks if any
            if batch_result["errors"]:
                st.markdown("---")
                st.markdown(f"#### {tr('batch.failed_list')}")

                for item in batch_result["errors"]:
                    with st.expander(f"🔴 {tr('batch.task')} {item['index']}: {item['topic']}", expanded=False):
                        st.error(f"**{tr('batch.error')}**: {item['error']}")

                        # Detailed error (collapsed)
                        with st.expander(tr("batch.error_detail")):
                            st.code(item['traceback'], language="python")
