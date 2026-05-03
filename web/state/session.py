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
Session state management for web UI.
"""

import hashlib
import json
from dataclasses import dataclass

import streamlit as st
from loguru import logger

from pixelle_video.platform_context import (
    DEFAULT_API_BASE_URL,
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
)
from web.i18n import get_language, set_language
from web.state.async_runtime import (
    DEFAULT_SESSION_KEY,
    get_current_session_key,
    register_async_cleanup,
    session_exists,
)
from web.utils.async_helpers import run_async


@dataclass
class _PixelleVideoSessionState:
    pixelle_video: object | None = None
    config_hash: str | None = None


_PIXELLE_VIDEO_SESSIONS: dict[str, _PixelleVideoSessionState] = {}
_LOCAL_PLATFORM_DEPENDENCIES = None
_LOCAL_PLATFORM_TASK_MANAGER = None
_LOCAL_TASK_EXECUTOR_REGISTRY = None
_LOCAL_WORKER_REGISTRY = None


async def _cleanup_pixelle_video_session(session_key: str):
    global _LOCAL_PLATFORM_DEPENDENCIES, _LOCAL_PLATFORM_TASK_MANAGER
    global _LOCAL_TASK_EXECUTOR_REGISTRY, _LOCAL_WORKER_REGISTRY

    from pixelle_video.services.frame_html import HTMLFrameGenerator

    state = _PIXELLE_VIDEO_SESSIONS.get(session_key)
    if state is not None and state.pixelle_video is not None:
        await state.pixelle_video.cleanup()
    await HTMLFrameGenerator.close_browser()
    _PIXELLE_VIDEO_SESSIONS.pop(session_key, None)
    if not _PIXELLE_VIDEO_SESSIONS and _LOCAL_PLATFORM_TASK_MANAGER is not None:
        await _LOCAL_PLATFORM_TASK_MANAGER.stop()
        _LOCAL_PLATFORM_TASK_MANAGER = None
        _LOCAL_PLATFORM_DEPENDENCIES = None
        _LOCAL_TASK_EXECUTOR_REGISTRY = None
        _LOCAL_WORKER_REGISTRY = None


def _cleanup_stale_pixelle_video_sessions(current_session_key: str):
    stale_session_keys = [
        session_key
        for session_key in _PIXELLE_VIDEO_SESSIONS
        if session_key not in {DEFAULT_SESSION_KEY, current_session_key}
        and not session_exists(session_key)
    ]

    for session_key in stale_session_keys:
        _PIXELLE_VIDEO_SESSIONS.pop(session_key, None)


def init_session_state():
    """Initialize session state variables."""
    if "language" not in st.session_state:
        st.session_state.language = get_language()
    if "workspace_id" not in st.session_state:
        st.session_state.workspace_id = DEFAULT_WORKSPACE_ID
    if "project_id" not in st.session_state:
        st.session_state.project_id = DEFAULT_PROJECT_ID
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = DEFAULT_API_BASE_URL


def init_i18n():
    """Initialize internationalization."""
    if "language" not in st.session_state:
        st.session_state.language = get_language()

    set_language(st.session_state.language)


def get_or_create_local_platform_dependencies():
    """Build Streamlit-local platform dependencies without falling back to API globals."""
    global _LOCAL_PLATFORM_DEPENDENCIES, _LOCAL_PLATFORM_TASK_MANAGER
    global _LOCAL_TASK_EXECUTOR_REGISTRY, _LOCAL_WORKER_REGISTRY

    if _LOCAL_PLATFORM_DEPENDENCIES is None:
        from api.config import api_config
        from api.platform_dependencies import build_platform_dependencies
        from api.tasks.factory import build_local_task_runtime
        from api.video.executor_factory import register_video_generation_executor
        from api.workbench.executor_factory import register_storyboard_workbench_executors

        runtime = build_local_task_runtime(api_config)
        _LOCAL_TASK_EXECUTOR_REGISTRY = runtime.executor_registry
        _LOCAL_WORKER_REGISTRY = runtime.worker_registry
        _LOCAL_PLATFORM_TASK_MANAGER = runtime.task_manager

        def provider():
            return get_pixelle_video()

        register_video_generation_executor(
            _LOCAL_TASK_EXECUTOR_REGISTRY,
            core_provider=provider,
            artifact_store=_LOCAL_PLATFORM_TASK_MANAGER.registry.artifact_store,
        )
        register_storyboard_workbench_executors(
            _LOCAL_TASK_EXECUTOR_REGISTRY,
            core_provider=provider,
        )
        run_async(_LOCAL_PLATFORM_TASK_MANAGER.start())
        _LOCAL_PLATFORM_DEPENDENCIES = build_platform_dependencies(
            api_config,
            task_manager=_LOCAL_PLATFORM_TASK_MANAGER,
            task_executor_registry=_LOCAL_TASK_EXECUTOR_REGISTRY,
            worker_capability_registry=_LOCAL_WORKER_REGISTRY,
            worker_registry=_LOCAL_WORKER_REGISTRY,
        )
    return _LOCAL_PLATFORM_DEPENDENCIES


def get_pixelle_video():
    """
    Get initialized Pixelle-Video instance with session-scoped async resource management.
    """
    from api.platform_dependencies import attach_platform_dependencies
    from pixelle_video.config import config_manager
    from pixelle_video.service import PixelleVideoCore

    session_key = get_current_session_key()
    register_async_cleanup(
        lambda: _cleanup_pixelle_video_session(session_key),
        session_key=session_key,
    )
    _cleanup_stale_pixelle_video_sessions(session_key)

    config_dict = config_manager.config.to_dict()
    comfyui_config = config_dict.get("comfyui", {})
    config_hash = hashlib.md5(json.dumps(comfyui_config, sort_keys=True).encode()).hexdigest()

    state = _PIXELLE_VIDEO_SESSIONS.setdefault(session_key, _PixelleVideoSessionState())

    need_recreate = False
    if state.pixelle_video is None:
        need_recreate = True
        logger.info("Creating new PixelleVideoCore instance (first time)")
    elif state.config_hash != config_hash:
        need_recreate = True
        logger.info("Configuration changed, recreating PixelleVideoCore instance")
        try:
            run_async(state.pixelle_video.cleanup())
        except Exception as e:
            logger.warning(f"Failed to cleanup old PixelleVideoCore: {e}")

    if need_recreate:
        pixelle_video = PixelleVideoCore()
        attach_platform_dependencies(
            pixelle_video,
            get_or_create_local_platform_dependencies(),
        )
        run_async(pixelle_video.initialize())
        state.pixelle_video = pixelle_video
        state.config_hash = config_hash
        logger.info("鉁?PixelleVideoCore initialized and cached")
    else:
        pixelle_video = state.pixelle_video
        logger.debug("Reusing cached PixelleVideoCore instance")

    return pixelle_video
