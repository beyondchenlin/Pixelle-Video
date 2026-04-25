"""Single-flight coordination for expensive video generation requests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from loguru import logger

VOLATILE_GENERATION_PARAM_NAMES = frozenset(
    {
        "api_task_id",
        "progress_callback",
        "request_id",
        "session_id",
    }
)


def _canonicalize_generation_value(value: Any) -> Any:
    """Normalize generation params into a stable JSON-compatible shape."""
    if value is None:
        return None
    if callable(value):
        return None
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _canonicalize_generation_value(asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _canonicalize_generation_value(model_dump(exclude_none=True))

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            key_text = str(key)
            if key_text in VOLATILE_GENERATION_PARAM_NAMES:
                continue
            normalized_item = _canonicalize_generation_value(item)
            if normalized_item is None:
                continue
            normalized[key_text] = normalized_item
        return normalized

    if isinstance(value, tuple | list):
        return [_canonicalize_generation_value(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(
            (_canonicalize_generation_value(item) for item in value),
            key=repr,
        )
    if isinstance(value, str | int | float | bool):
        return value

    return str(value)


def build_generation_fingerprint(
    *,
    text: str,
    pipeline: str,
    params: Mapping[str, Any],
) -> str:
    """Build a stable fingerprint for output-affecting generation inputs."""
    payload = {
        "version": 1,
        "pipeline": pipeline,
        "text": text,
        "params": _canonicalize_generation_value(params),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class GenerationCoordinator:
    """Share one running generation task for identical in-flight requests."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    async def run(
        self,
        fingerprint: str,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        async with self._lock:
            task = self._inflight.get(fingerprint)
            if task is None:
                task = asyncio.create_task(factory())
                self._inflight[fingerprint] = task
                task.add_done_callback(
                    lambda completed_task, key=fingerprint: asyncio.create_task(
                        self._release_if_current(key, completed_task)
                    )
                )
            else:
                logger.info(f"Reusing in-flight video generation: {fingerprint[:12]}")

        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                await self._release_if_current(fingerprint, task)

    async def _release_if_current(
        self,
        fingerprint: str,
        task: asyncio.Task[Any],
    ) -> None:
        async with self._lock:
            if self._inflight.get(fingerprint) is task:
                self._inflight.pop(fingerprint, None)

    def inflight_count(self) -> int:
        return len(self._inflight)
