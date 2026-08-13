"""Non-blocking dependency warmup for the Home creation editor."""

from __future__ import annotations

import time
from importlib import import_module
from threading import Lock, Thread

from loguru import logger

from web.pipelines import get_pipeline_ui

_EDITOR_DEPENDENCY_MODULES = (
    "api.config",
    "api.platform_dependencies",
    "api.tasks.factory",
    "api.video.executor_factory",
    "api.workbench.executor_factory",
    "pixelle_video.service",
)
_PREWARM_LOCK = Lock()
_PREWARMING_PIPELINES: set[str] = set()
_PREWARMED_PIPELINES: set[str] = set()


def _prewarm_home_editor_dependencies(
    pipeline_name: str,
    *,
    delay_seconds: float,
) -> None:
    started_at = time.perf_counter()
    try:
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        for module_name in _EDITOR_DEPENDENCY_MODULES:
            import_module(module_name)
        pipeline = get_pipeline_ui(pipeline_name)
        if pipeline is None:
            raise RuntimeError(f"Unknown Home pipeline: {pipeline_name}")
    except Exception:
        logger.exception("Home editor dependency prewarm failed")
        with _PREWARM_LOCK:
            _PREWARMING_PIPELINES.discard(pipeline_name)
        return

    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    with _PREWARM_LOCK:
        _PREWARMING_PIPELINES.discard(pipeline_name)
        _PREWARMED_PIPELINES.add(pipeline_name)
    logger.info(f"Home editor dependencies prewarmed in {elapsed_ms} ms")


def schedule_home_editor_prewarm(
    pipeline_name: str = "quick_create",
    *,
    delay_seconds: float = 0.15,
) -> bool:
    """Warm imports after the dashboard renders, without creating runtime services."""
    with _PREWARM_LOCK:
        if (
            pipeline_name in _PREWARMED_PIPELINES
            or pipeline_name in _PREWARMING_PIPELINES
        ):
            return False
        _PREWARMING_PIPELINES.add(pipeline_name)

    try:
        thread = Thread(
            target=_prewarm_home_editor_dependencies,
            kwargs={
                "pipeline_name": pipeline_name,
                "delay_seconds": max(0.0, delay_seconds),
            },
            name=f"pixelle-home-editor-prewarm-{pipeline_name}",
            daemon=True,
        )
        thread.start()
    except Exception:
        with _PREWARM_LOCK:
            _PREWARMING_PIPELINES.discard(pipeline_name)
        logger.exception("Unable to schedule Home editor dependency prewarm")
        return False
    return True


__all__ = ["schedule_home_editor_prewarm"]
