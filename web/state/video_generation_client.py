from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any
from uuid import UUID

from pixelle_video.services.generation_coordinator import build_generation_fingerprint
from web.state.session import run_process_task_async

VIDEO_GENERATION_TASK_QUERY_PARAM = "generation_task"


def normalize_video_generation_task_id(value: Any) -> str | None:
    """Accept only canonical UUID task identifiers from browser-controlled state."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def read_video_generation_task_id(query_params: Mapping[str, Any]) -> str | None:
    return normalize_video_generation_task_id(
        query_params.get(VIDEO_GENERATION_TASK_QUERY_PARAM)
    )


def write_video_generation_task_id(
    query_params: MutableMapping[str, Any],
    task_id: str | None,
) -> None:
    if task_id is None:
        query_params.pop(VIDEO_GENERATION_TASK_QUERY_PARAM, None)
        return
    normalized = normalize_video_generation_task_id(task_id)
    if normalized is None:
        raise ValueError("task_id must be a canonical UUID")
    query_params[VIDEO_GENERATION_TASK_QUERY_PARAM] = normalized


class InProcessVideoGenerationClient:
    def __init__(self, *, submitter: Any, async_runner=run_process_task_async) -> None:
        self.submitter = submitter
        self._async_runner = async_runner

    def submit(self, request_params: Mapping[str, Any]):
        params = dict(request_params)
        text = str(params.get("text") or "")
        fingerprint = build_generation_fingerprint(
            text=text,
            pipeline="standard",
            params=params,
        )
        params["generation_fingerprint"] = fingerprint
        return self._async_runner(
            self.submitter.reserve_video_generation(
                generation_fingerprint=fingerprint,
                request_params=params,
            )
        )

    def get(self, task_id: str):
        normalized = normalize_video_generation_task_id(task_id)
        if normalized is None:
            return None
        return self._async_runner(
            self.submitter.get_video_generation_task(normalized)
        )

    def cancel(self, task_id: str) -> bool:
        normalized = normalize_video_generation_task_id(task_id)
        if normalized is None:
            return False
        return bool(
            self._async_runner(self.submitter.cancel_video_generation(normalized))
        )


def resolve_video_generation_client(pixelle_video: Any) -> InProcessVideoGenerationClient:
    submitter = getattr(pixelle_video, "video_generation_task_submitter", None)
    if submitter is None:
        raise RuntimeError("video generation task submitter is not configured")
    return InProcessVideoGenerationClient(submitter=submitter)


__all__ = [
    "InProcessVideoGenerationClient",
    "VIDEO_GENERATION_TASK_QUERY_PARAM",
    "normalize_video_generation_task_id",
    "read_video_generation_task_id",
    "resolve_video_generation_client",
    "write_video_generation_task_id",
]
