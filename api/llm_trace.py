from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import Request

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.platform_context import resolve_workspace_id
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder


def build_api_llm_trace_recorder(
    http_request: Request,
    *,
    route: str,
) -> LLMInteractionRecorder:
    trace_repository = getattr(http_request.app.state, "trace_repository", None)
    raw_payload_store = getattr(http_request.app.state, "raw_payload_store", None)
    if trace_repository is None or raw_payload_store is None:
        raise RuntimeError(
            f"trace_repository and raw_payload_store are required for {route} trace capture"
        )
    return LLMInteractionRecorder(
        trace_repository=trace_repository,
        raw_payload_store=raw_payload_store,
    )


def build_api_llm_trace_context(
    http_request: Request,
    *,
    route: str,
    operation: str,
    stage: str | None = None,
    task_id_prefix: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> LLMTraceContext:
    task_id = http_request.headers.get("x-task-id") or (
        f"{task_id_prefix or operation}_{uuid4().hex}"
    )
    resolved_metadata = {
        "chain_id": f"{task_id}:{operation}",
        "route": route,
    }
    request_id = http_request.headers.get("x-request-id")
    if request_id:
        resolved_metadata["request_id"] = request_id
    session_id = http_request.headers.get("x-session-id")
    if session_id:
        resolved_metadata["session_id"] = session_id
    api_task_id = http_request.headers.get("x-api-task-id")
    if api_task_id:
        resolved_metadata["api_task_id"] = api_task_id
    if metadata:
        resolved_metadata.update(dict(metadata))

    return LLMTraceContext(
        workspace_id=resolve_workspace_id(
            {"workspace_id": http_request.headers.get("x-workspace-id")}
        ),
        task_id=task_id,
        operation=operation,
        stage=stage or operation,
        metadata=resolved_metadata,
    )


__all__ = [
    "build_api_llm_trace_context",
    "build_api_llm_trace_recorder",
]
