from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from pixelle_video.models.llm_interaction_trace import (
    LLMInteractionTrace,
    LLMTraceContext,
    LLMTraceStatus,
)
from pixelle_video.repositories.trace import TraceRepository
from pixelle_video.storage.object_store import RawPayloadStore


class LLMInteractionRecorder:
    def __init__(
        self,
        *,
        trace_repository: TraceRepository,
        raw_payload_store: RawPayloadStore,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._trace_repository = trace_repository
        self._raw_payload_store = raw_payload_store
        self._trace_id_factory = trace_id_factory or _default_trace_id

    async def record_interaction(
        self,
        *,
        context: LLMTraceContext,
        provider: str,
        model: str,
        request_payload: Mapping[str, Any],
        response_payload: Mapping[str, Any] | None,
        status: LLMTraceStatus | str,
        elapsed_ms: int | None = None,
        token_usage: Mapping[str, int] | None = None,
        parse_error: str = "",
        error_message: str = "",
        validation_errors: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
    ) -> LLMInteractionTrace:
        request_payload_key = await self._raw_payload_store.put_json(
            context.workspace_id,
            request_payload,
        )
        response_payload_key = None
        if response_payload is not None:
            response_payload_key = await self._raw_payload_store.put_json(
                context.workspace_id,
                response_payload,
            )

        trace = LLMInteractionTrace.create(
            trace_id=self._trace_id_factory(),
            context=context,
            provider=provider,
            model=model,
            request_payload_key=request_payload_key,
            response_payload_key=response_payload_key,
            request_payload=request_payload,
            response_payload=response_payload,
            status=status,
            elapsed_ms=elapsed_ms,
            token_usage=token_usage,
            parse_error=parse_error,
            error_message=error_message,
            validation_errors=validation_errors,
        )
        await self._trace_repository.append_llm_interaction(
            context.workspace_id,
            trace.to_dict(),
        )
        return trace


def _default_trace_id() -> str:
    return f"llm_trace_{uuid4().hex}"


__all__ = ["LLMInteractionRecorder"]
