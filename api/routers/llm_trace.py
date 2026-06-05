from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from api.schemas.llm_trace import (
    LLMTraceContextResponse,
    LLMTraceListResponse,
    LLMTraceRawPayloadResponse,
    LLMTraceSummary,
)

router = APIRouter(prefix="/llm-traces", tags=["LLM Trace"])


@router.get("/{workspace_id}", response_model=LLMTraceListResponse)
async def list_llm_traces(
    workspace_id: str,
    request: Request,
    task_id: str | None = None,
    operation: str | None = None,
    stage: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    api_task_id: str | None = None,
    pipeline: str | None = None,
) -> LLMTraceListResponse:
    repository = _get_trace_repository(request)
    traces = await repository.list_llm_interactions(
        workspace_id,
        filters={"task_id": task_id, "operation": operation},
    )
    summaries = [
        _to_trace_summary(trace)
        for trace in traces
    ]
    summaries = [
        summary
        for summary in summaries
        if _summary_matches(
            summary,
            stage=stage,
            request_id=request_id,
            session_id=session_id,
            api_task_id=api_task_id,
            pipeline=pipeline,
        )
    ]
    return LLMTraceListResponse(
        traces=summaries
    )


@router.get("/{workspace_id}/{trace_id}", response_model=LLMTraceSummary)
async def get_llm_trace_summary(
    workspace_id: str,
    trace_id: str,
    request: Request,
) -> LLMTraceSummary:
    repository = _get_trace_repository(request)
    traces = await repository.list_llm_interactions(
        workspace_id,
        filters={"trace_id": trace_id},
    )
    if not traces:
        raise HTTPException(status_code=404, detail="LLM trace was not found")
    return _to_trace_summary(traces[0])


@router.get("/{workspace_id}/{trace_id}/raw/{payload_kind}", response_model=LLMTraceRawPayloadResponse)
async def get_llm_trace_raw_payload(
    workspace_id: str,
    trace_id: str,
    payload_kind: str,
    request: Request,
    x_pixelle_local_debug: str | None = Header(default=None, alias="x-pixelle-local-debug"),
) -> LLMTraceRawPayloadResponse:
    if not _has_local_debug_raw_access(request, x_pixelle_local_debug):
        raise HTTPException(status_code=403, detail="raw LLM trace payload requires local debug access")
    if payload_kind not in {"request", "response"}:
        raise HTTPException(status_code=404, detail="unknown raw payload kind")

    repository = _get_trace_repository(request)
    raw_payload_store = _get_raw_payload_store(request)
    traces = await repository.list_llm_interactions(
        workspace_id,
        filters={"trace_id": trace_id},
    )
    if not traces:
        raise HTTPException(status_code=404, detail="LLM trace was not found")

    trace = traces[0]
    key_field = f"{payload_kind}_payload_key"
    storage_key = trace.get(key_field)
    if not isinstance(storage_key, str) or not storage_key:
        raise HTTPException(status_code=404, detail="raw payload object key was not found")

    payload = await raw_payload_store.get_json(storage_key)
    return LLMTraceRawPayloadResponse(
        trace_id=trace_id,
        payload_kind=payload_kind,
        payload=payload,
    )


def _get_trace_repository(request: Request):
    repository = getattr(request.app.state, "trace_repository", None)
    if repository is None:
        raise HTTPException(status_code=503, detail="trace repository is not configured")
    return repository


def _get_raw_payload_store(request: Request):
    raw_payload_store = getattr(request.app.state, "raw_payload_store", None)
    if raw_payload_store is None:
        raise HTTPException(status_code=503, detail="raw payload store is not configured")
    return raw_payload_store


def _has_local_debug_raw_access(request: Request, debug_header: str | None) -> bool:
    if str(debug_header or "").lower() != "true":
        return False
    if getattr(request.app.state, "local_debug_enabled", False) is not True:
        return False
    return _is_loopback_client(request)


def _is_loopback_client(request: Request) -> bool:
    if request.client is None or not request.client.host:
        return False
    try:
        remote_address = ip_address(request.client.host)
    except ValueError:
        return False
    if remote_address.is_loopback:
        return True
    ipv4_mapped = getattr(remote_address, "ipv4_mapped", None)
    return ipv4_mapped is not None and ipv4_mapped.is_loopback


def _summary_matches(
    summary: LLMTraceSummary,
    *,
    stage: str | None,
    request_id: str | None,
    session_id: str | None,
    api_task_id: str | None,
    pipeline: str | None,
) -> bool:
    context = summary.context
    metadata = context.metadata or {}
    if stage is not None and context.stage != stage:
        return False
    if request_id is not None and str(metadata.get("request_id", "")) != request_id:
        return False
    if session_id is not None and str(metadata.get("session_id", "")) != session_id:
        return False
    if api_task_id is not None and str(metadata.get("api_task_id", "")) != api_task_id:
        return False
    if pipeline is not None and str(metadata.get("pipeline", "")) != pipeline:
        return False
    return True


def _to_trace_summary(trace: Mapping[str, Any]) -> LLMTraceSummary:
    context_payload = _mapping_or_empty(trace.get("context"))
    return LLMTraceSummary(
        trace_id=str(trace.get("trace_id", "")),
        context=LLMTraceContextResponse(
            workspace_id=str(context_payload.get("workspace_id", "")),
            task_id=str(context_payload.get("task_id", "")),
            operation=str(context_payload.get("operation", "")),
            stage=_optional_str(context_payload.get("stage")),
            frame_id=_optional_str(context_payload.get("frame_id")),
            metadata=dict(_mapping_or_empty(context_payload.get("metadata"))),
        ),
        provider=str(trace.get("provider", "")),
        model=str(trace.get("model", "")),
        status=str(trace.get("status", "")),
        request_sha256=str(trace.get("request_sha256", "")),
        request_preview=str(trace.get("request_preview", "")),
        response_sha256=_optional_str(trace.get("response_sha256")),
        response_preview=_optional_str(trace.get("response_preview")),
        elapsed_ms=trace.get("elapsed_ms"),
        token_usage=(
            dict(_mapping_or_empty(trace.get("token_usage")))
            if trace.get("token_usage") is not None
            else None
        ),
        parse_error=str(trace.get("parse_error", "")),
        error_message=str(trace.get("error_message", "")),
        validation_errors=[
            dict(_mapping_or_empty(error))
            for error in trace.get("validation_errors") or []
        ],
        created_at=str(trace.get("created_at", "")),
    )


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


__all__ = ["router"]
