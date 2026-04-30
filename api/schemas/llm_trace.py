from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMTraceContextResponse(BaseModel):
    workspace_id: str
    task_id: str
    operation: str
    stage: str | None = None
    frame_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMTraceSummary(BaseModel):
    trace_id: str
    context: LLMTraceContextResponse
    provider: str
    model: str
    status: str
    request_sha256: str
    request_preview: str
    response_sha256: str | None = None
    response_preview: str | None = None
    elapsed_ms: int | None = None
    token_usage: dict[str, int] | None = None
    parse_error: str = ""
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class LLMTraceListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    traces: list[LLMTraceSummary] = Field(default_factory=list)


class LLMTraceRawPayloadResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    trace_id: str
    payload_kind: str
    payload: dict[str, Any]


__all__ = [
    "LLMTraceContextResponse",
    "LLMTraceListResponse",
    "LLMTraceRawPayloadResponse",
    "LLMTraceSummary",
]
