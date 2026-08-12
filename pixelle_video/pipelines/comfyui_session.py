"""Compatibility helpers for optional local ComfyUI lifecycle scopes."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def maybe_local_comfyui_task_scope(core: Any):
    factory = getattr(core, "local_comfyui_task_scope", None)
    if callable(factory):
        async with factory():
            yield
        return
    yield


@asynccontextmanager
async def maybe_local_comfyui_workflow_session(
    core: Any,
    *,
    backend_role: str = "default",
    stop_after_session: bool = False,
):
    factory = getattr(core, "local_comfyui_workflow_session", None)
    if not callable(factory):
        yield
        return

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        supports_stop_after_session = True
        supports_legacy_release_after_session = False
        supports_backend_role = True
    else:
        supports_variadic_keywords = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        supports_stop_after_session = (
            "stop_after_session" in signature.parameters
            or supports_variadic_keywords
        )
        supports_legacy_release_after_session = (
            "release_after_session" in signature.parameters
            or supports_variadic_keywords
        )
        supports_backend_role = (
            "backend_role" in signature.parameters
            or supports_variadic_keywords
        )

    session_kwargs = {}
    if supports_stop_after_session:
        session_kwargs["stop_after_session"] = stop_after_session
    elif supports_legacy_release_after_session:
        session_kwargs["release_after_session"] = stop_after_session
    if supports_backend_role:
        session_kwargs["backend_role"] = backend_role

    session_context = factory(**session_kwargs) if session_kwargs else factory()
    async with session_context:
        yield
