from __future__ import annotations

import os
from collections.abc import MutableMapping
from typing import Any

from pixelle_video.platform_context import CONFIGURED_API_BASE_URL, resolve_api_base_url
from web.workbench.http_client import HttpStoryboardWorkbenchClient
from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

WORKBENCH_CLIENT_KEY = "storyboard_workbench_client"
WORKBENCH_CLIENT_CACHE_KEY = "storyboard_workbench_client_cache_key"
WORKBENCH_CLIENT_MODE_KEY = "workbench_client_mode"


def resolve_workbench_client_mode(session_state: MutableMapping[str, Any] | None) -> str:
    state = session_state or {}
    explicit_mode = str(
        os.getenv("PIXELLE_WORKBENCH_CLIENT_MODE")
        or state.get(WORKBENCH_CLIENT_MODE_KEY)
        or ""
    ).strip().lower()
    if explicit_mode == "http":
        return "http"
    return "inprocess"


def resolve_storyboard_workbench_client(
    session_state: MutableMapping[str, Any],
    *,
    pixelle_video: Any | None = None,
):
    mode = resolve_workbench_client_mode(session_state)
    if mode == "http":
        api_base_url = resolve_api_base_url(
            session_state,
            default=os.getenv("PIXELLE_API_BASE_URL") or CONFIGURED_API_BASE_URL,
        )
        return _cached_client(
            session_state,
            cache_key=("http", api_base_url),
            factory=lambda: HttpStoryboardWorkbenchClient(api_base_url=api_base_url),
        )

    if pixelle_video is None:
        session_state.pop(WORKBENCH_CLIENT_KEY, None)
        session_state.pop(WORKBENCH_CLIENT_CACHE_KEY, None)
        return None

    return _cached_client(
        session_state,
        cache_key=("inprocess", id(pixelle_video)),
        factory=lambda: InProcessStoryboardWorkbenchClient(
            pixelle_video=pixelle_video,
            task_async_runner=_process_task_runner,
        ),
    )


def _process_task_runner(coro):
    from web.state.session import run_process_task_async

    return run_process_task_async(coro)


def _cached_client(
    session_state: MutableMapping[str, Any],
    *,
    cache_key: tuple[Any, ...],
    factory,
):
    if session_state.get(WORKBENCH_CLIENT_CACHE_KEY) != cache_key:
        session_state[WORKBENCH_CLIENT_KEY] = factory()
        session_state[WORKBENCH_CLIENT_CACHE_KEY] = cache_key
    return session_state[WORKBENCH_CLIENT_KEY]


__all__ = [
    "resolve_storyboard_workbench_client",
    "resolve_workbench_client_mode",
]
