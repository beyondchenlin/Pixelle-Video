from __future__ import annotations

import os
from collections.abc import MutableMapping
from typing import Any

from pixelle_video.platform_context import CONFIGURED_API_BASE_URL, resolve_api_base_url
from web.ip_design.http_client import HttpIPDesignClient
from web.ip_design.inprocess_client import InProcessIPDesignClient
from web.state.workbench_client import resolve_workbench_client_mode

IP_DESIGN_CLIENT_KEY = "ip_design_client"
IP_DESIGN_CLIENT_CACHE_KEY = "ip_design_client_cache_key"


def resolve_ip_design_client(
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
            factory=lambda: HttpIPDesignClient(api_base_url=api_base_url),
        )

    if pixelle_video is None:
        session_state.pop(IP_DESIGN_CLIENT_KEY, None)
        session_state.pop(IP_DESIGN_CLIENT_CACHE_KEY, None)
        return None

    return _cached_client(
        session_state,
        cache_key=("inprocess", id(pixelle_video)),
        factory=lambda: InProcessIPDesignClient(pixelle_video=pixelle_video),
    )


def _cached_client(
    session_state: MutableMapping[str, Any],
    *,
    cache_key: tuple[Any, ...],
    factory,
):
    if session_state.get(IP_DESIGN_CLIENT_CACHE_KEY) != cache_key:
        session_state[IP_DESIGN_CLIENT_KEY] = factory()
        session_state[IP_DESIGN_CLIENT_CACHE_KEY] = cache_key
    return session_state[IP_DESIGN_CLIENT_KEY]


__all__ = ["resolve_ip_design_client"]
