"""Process-wide, bounded warmup for Home editor import dependencies."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from threading import Lock, Thread
from typing import Callable

from loguru import logger

from web.pipelines.catalog import get_pipeline_catalog_entry

HOME_EDITOR_WARMUP_DELAY_SECONDS = 0.5
_CORE_IMPORT_MODULES = (
    "api.config",
    "api.platform_dependencies",
    "api.tasks.factory",
    "api.video.executor_factory",
    "api.workbench.executor_factory",
    "pixelle_video.service",
)


class HomeEditorWarmupStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class HomeEditorWarmupSnapshot:
    target: str | None
    status: HomeEditorWarmupStatus
    import_duration_ms: int | None = None


_WARMUP_LOCK = Lock()
_WARMUP_QUEUE: deque[str | None] = deque()
_WARMUP_SNAPSHOTS: dict[str | None, HomeEditorWarmupSnapshot] = {}
_WARMUP_WORKER_RUNNING = False


def _trusted_warmup_modules(target: str | None) -> tuple[str, ...] | None:
    if target is None:
        return _CORE_IMPORT_MODULES
    entry = get_pipeline_catalog_entry(target)
    if entry is None:
        return None
    return (*_CORE_IMPORT_MODULES, entry.module_name)


def _execute_home_editor_warmup(
    target: str | None,
    *,
    module_importer: Callable[[str], object] = import_module,
) -> HomeEditorWarmupSnapshot:
    modules = _trusted_warmup_modules(target)
    if modules is None:
        return HomeEditorWarmupSnapshot(
            target=target,
            status=HomeEditorWarmupStatus.FAILED,
        )

    started_at = time.perf_counter()
    try:
        for module_name in modules:
            module_importer(module_name)
    except Exception:
        logger.exception("Home editor import warmup failed")
        return HomeEditorWarmupSnapshot(
            target=target,
            status=HomeEditorWarmupStatus.FAILED,
        )

    return HomeEditorWarmupSnapshot(
        target=target,
        status=HomeEditorWarmupStatus.SUCCEEDED,
        import_duration_ms=round((time.perf_counter() - started_at) * 1000),
    )


def _discard_pending_warmups_locked() -> None:
    while _WARMUP_QUEUE:
        target = _WARMUP_QUEUE.popleft()
        snapshot = _WARMUP_SNAPSHOTS.get(target)
        if snapshot is not None and snapshot.status is HomeEditorWarmupStatus.PENDING:
            _WARMUP_SNAPSHOTS.pop(target, None)


def _run_home_editor_warmup_queue(*, initial_delay_seconds: float) -> None:
    global _WARMUP_WORKER_RUNNING

    try:
        if initial_delay_seconds > 0:
            time.sleep(initial_delay_seconds)

        while True:
            with _WARMUP_LOCK:
                if not _WARMUP_QUEUE:
                    _WARMUP_WORKER_RUNNING = False
                    return
                target = _WARMUP_QUEUE.popleft()
                _WARMUP_SNAPSHOTS[target] = HomeEditorWarmupSnapshot(
                    target=target,
                    status=HomeEditorWarmupStatus.RUNNING,
                )

            try:
                snapshot = _execute_home_editor_warmup(target)
            except Exception:
                logger.exception("Home editor warmup worker failed unexpectedly")
                snapshot = HomeEditorWarmupSnapshot(
                    target=target,
                    status=HomeEditorWarmupStatus.FAILED,
                )
            with _WARMUP_LOCK:
                _WARMUP_SNAPSHOTS[target] = snapshot
            if snapshot.status is HomeEditorWarmupStatus.SUCCEEDED:
                logger.info(
                    f"Home editor imports warmed in {snapshot.import_duration_ms} ms"
                )
    except Exception:
        with _WARMUP_LOCK:
            _discard_pending_warmups_locked()
            _WARMUP_WORKER_RUNNING = False
        logger.exception("Home editor warmup worker stopped unexpectedly")


def schedule_home_editor_warmup(
    target: str | None = "quick_create",
    *,
    initial_delay_seconds: float = HOME_EDITOR_WARMUP_DELAY_SECONDS,
) -> bool:
    """Queue one bounded warmup without constructing runtime services."""
    global _WARMUP_WORKER_RUNNING

    if _trusted_warmup_modules(target) is None:
        logger.warning("Ignored Home editor warmup request for unknown pipeline")
        return False

    with _WARMUP_LOCK:
        if target in _WARMUP_SNAPSHOTS:
            return False
        _WARMUP_SNAPSHOTS[target] = HomeEditorWarmupSnapshot(
            target=target,
            status=HomeEditorWarmupStatus.PENDING,
        )
        _WARMUP_QUEUE.append(target)
        if _WARMUP_WORKER_RUNNING:
            return True
        _WARMUP_WORKER_RUNNING = True

    try:
        worker = Thread(
            target=_run_home_editor_warmup_queue,
            kwargs={"initial_delay_seconds": max(0.0, initial_delay_seconds)},
            name="pixelle-home-editor-warmup",
            daemon=True,
        )
        worker.start()
    except Exception:
        with _WARMUP_LOCK:
            _discard_pending_warmups_locked()
            _WARMUP_WORKER_RUNNING = False
        logger.exception("Unable to start Home editor warmup worker")
        return False
    return True


def get_home_editor_warmup_snapshot(
    target: str | None,
) -> HomeEditorWarmupSnapshot | None:
    with _WARMUP_LOCK:
        return _WARMUP_SNAPSHOTS.get(target)


__all__ = [
    "HOME_EDITOR_WARMUP_DELAY_SECONDS",
    "HomeEditorWarmupSnapshot",
    "HomeEditorWarmupStatus",
    "get_home_editor_warmup_snapshot",
    "schedule_home_editor_warmup",
]
