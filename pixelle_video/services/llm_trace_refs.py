from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder


class LLMTraceCollector:
    def __init__(self, delegate: LLMInteractionRecorder):
        self._delegate = delegate
        self.records: list[Any] = []

    async def record_interaction(self, **kwargs):
        trace = await self._delegate.record_interaction(**kwargs)
        self.records.append(trace)
        return trace


def llm_trace_refs_from_records(records: Sequence[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for trace in records:
        trace_id = str(getattr(trace, "trace_id", "") or "").strip()
        context = getattr(trace, "context", None)
        stage = str(getattr(context, "stage", "") or "").strip()
        if not trace_id or not stage:
            continue
        if _trace_status_value(trace) != "success":
            continue
        identity = (trace_id, stage)
        if identity in seen:
            continue
        seen.add(identity)
        refs.append({"trace_id": trace_id, "stage": stage})
    return refs


def merge_llm_trace_refs(*groups: object) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        if not isinstance(group, Sequence) or isinstance(group, (str, bytes)):
            continue
        for value in group:
            if not isinstance(value, Mapping):
                continue
            trace_id = str(value.get("trace_id") or "").strip()
            stage = str(value.get("stage") or "").strip()
            if not trace_id or not stage:
                continue
            identity = (trace_id, stage)
            if identity in seen:
                continue
            seen.add(identity)
            refs.append({"trace_id": trace_id, "stage": stage})
    return refs


def _trace_status_value(trace: Any) -> str:
    status = getattr(trace, "status", "")
    return str(getattr(status, "value", status) or "")


__all__ = [
    "LLMTraceCollector",
    "llm_trace_refs_from_records",
    "merge_llm_trace_refs",
]
