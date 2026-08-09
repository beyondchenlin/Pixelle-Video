from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ffmpeg
from loguru import logger

from pixelle_video.services.remote_media import (
    configured_workflow_output_origins,
    configured_workflow_output_roots,
    materialize_media_source,
)
from pixelle_video.utils.os_util import create_task_output_dir
from pixelle_video.utils.secret_redaction import (
    is_sensitive_key,
    redact_credentials_in_text,
)

GenerationOperation = Callable[["WebGenerationRun"], Awaitable[str]]


class WebGenerationRun:
    """Own the complete persisted lifecycle of one direct web generation."""

    def __init__(
        self,
        *,
        core: Any,
        pipeline: str,
        input_params: Mapping[str, Any],
        task_id: str,
        task_dir: Path,
        created_at: str,
    ) -> None:
        self.core = core
        self.pipeline = pipeline
        self.input_params = _sanitize_history_value(input_params)
        self.task_id = task_id
        self.task_dir = task_dir
        self.created_at = created_at
        self._terminal = False

    @classmethod
    async def start(
        cls,
        *,
        core: Any,
        pipeline: str,
        input_params: Mapping[str, Any],
    ) -> "WebGenerationRun":
        persistence = getattr(core, "persistence", None)
        if persistence is None:
            raise RuntimeError("generation history persistence is not initialized")

        task_dir_text, task_id = create_task_output_dir()
        created_at = _utc_now_text()
        run = cls(
            core=core,
            pipeline=pipeline,
            input_params=input_params,
            task_id=task_id,
            task_dir=Path(task_dir_text).resolve(),
            created_at=created_at,
        )
        await persistence.save_task_metadata(
            task_id,
            run._metadata(status="running"),
        )
        return run

    async def execute(self, operation: GenerationOperation) -> str:
        """Execute, finalize, and persist one generation as a single lifecycle."""

        try:
            source = await operation(self)
            return await self.complete(source)
        except BaseException as error:
            if not self._terminal:
                try:
                    await asyncio.shield(self.fail(error))
                except Exception as persistence_error:
                    logger.error(
                        "Failed to persist generation failure for {}: {}",
                        self.task_id,
                        persistence_error,
                    )
            raise

    async def complete(self, source: str) -> str:
        if self._terminal:
            raise RuntimeError("generation lifecycle is already terminal")

        final_path = self.task_dir / "final.mp4"
        await materialize_media_source(
            source,
            final_path,
            media_type="video",
            trusted_private_origins=configured_workflow_output_origins(self.core),
            trusted_local_roots=configured_workflow_output_roots(),
        )
        duration = await asyncio.to_thread(_probe_video_duration, final_path)
        file_size = final_path.stat().st_size
        completed_at = _utc_now_text()
        metadata = self._metadata(
            status="completed",
            completed_at=completed_at,
            result={
                "video_path": str(final_path),
                "duration": duration,
                "file_size": file_size,
                "n_frames": 0,
            },
        )
        await self.core.persistence.save_task_metadata(self.task_id, metadata)
        self._terminal = True
        return str(final_path)

    async def fail(self, error: BaseException) -> None:
        if self._terminal:
            return
        completed_at = _utc_now_text()
        await self.core.persistence.save_task_metadata(
            self.task_id,
            self._metadata(
                status="failed",
                completed_at=completed_at,
                error=redact_credentials_in_text(error),
            ),
        )
        self._terminal = True

    def _metadata(
        self,
        *,
        status: str,
        completed_at: str | None = None,
        error: str | None = None,
        result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "status": status,
            "input": {
                "mode": self.pipeline,
                **self.input_params,
            },
            "config": {"pipeline": self.pipeline},
        }
        if completed_at is not None:
            metadata["completed_at"] = completed_at
        if error is not None:
            metadata["error"] = error
        if result is not None:
            metadata["result"] = dict(result)
        return metadata


def _sanitize_history_value(
    value: Any,
    *,
    key: str = "",
    depth: int = 0,
) -> Any:
    if is_sensitive_key(key):
        return "***"
    if depth > 6:
        return "<omitted>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str):
        if key.endswith(("_path", "_paths")):
            return Path(value).name
        return redact_credentials_in_text(value[:10_000])
    if isinstance(value, Mapping):
        return {
            str(child_key): _sanitize_history_value(
                child_value,
                key=str(child_key),
                depth=depth + 1,
            )
            for child_key, child_value in list(value.items())[:100]
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        if key.endswith("_assets"):
            return {"count": len(value)}
        return [
            _sanitize_history_value(item, key=key, depth=depth + 1)
            for item in list(value)[:100]
        ]
    return redact_credentials_in_text(str(value)[:1_000])


def _probe_video_duration(path: Path) -> float:
    try:
        probe = ffmpeg.probe(str(path))
        duration = float(probe.get("format", {}).get("duration", 0))
        return duration if math.isfinite(duration) and duration >= 0 else 0.0
    except Exception as error:
        logger.warning("Failed to probe generated video duration: {}", error)
        return 0.0


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["WebGenerationRun"]
