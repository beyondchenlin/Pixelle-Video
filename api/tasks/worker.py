"""Generation worker process."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from api.config import APIConfig, api_config
from api.platform_dependencies import attach_platform_dependencies, build_platform_dependencies
from api.runtime_context import resolve_api_configured_path
from api.tasks.artifacts import ArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.factory import build_task_runtime
from api.tasks.models import utc_now
from api.tasks.progress import TaskProgressSink
from api.tasks.registry import GenerationRegistry
from api.tasks.store import LostTaskLeaseError
from api.tasks.worker_registry import WorkerHeartbeat, WorkerRegistry
from api.video.executor_factory import register_video_generation_executor
from api.workbench.executor_factory import register_storyboard_workbench_executors
from pixelle_video.models.progress import ProgressDispatcher
from pixelle_video.service import PixelleVideoCore


async def _drain_progress_sink(progress_sink: TaskProgressSink | None) -> None:
    if progress_sink is None:
        return
    try:
        await progress_sink.drain()
    except Exception as exc:
        logger.warning(f"Task progress drain failed: {exc}")


class GenerationWorker:
    """Claims pending generation tasks and executes them outside the API process."""

    def __init__(
        self,
        *,
        registry: GenerationRegistry,
        core: Any,
        artifact_store: ArtifactStore,
        output_root: str | Path,
        worker_id: str | None = None,
        heartbeat_interval_seconds: float = 30.0,
        executor_registry: TaskExecutorRegistry | None = None,
        worker_registry: WorkerRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.core = core
        self.artifact_store = artifact_store
        configured_output_root = Path(output_root).expanduser()
        if not configured_output_root.is_absolute():
            raise ValueError("GenerationWorker output_root must be absolute")
        self.output_root = configured_output_root.resolve()
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.executor_registry = executor_registry or TaskExecutorRegistry()
        self.worker_registry = worker_registry

    async def heartbeat_capabilities(self) -> None:
        if self.worker_registry is None:
            return
        await self.worker_registry.heartbeat(
            WorkerHeartbeat(
                worker_id=self.worker_id,
                supported_task_types=self.executor_registry.supported_task_types(),
                heartbeat_at=utc_now(),
            )
        )

    async def run_once(self) -> bool:
        await self.heartbeat_capabilities()
        task_types = self.executor_registry.supported_task_types()
        if not task_types:
            return False
        claim = await self.registry.claim_next_pending(
            worker_id=self.worker_id,
            task_types=task_types,
        )
        if claim is None:
            return False

        task = claim.task
        lease = claim.lease
        progress_sink = None
        try:
            progress_sink = TaskProgressSink(
                registry=self.registry,
                task_id=task.task_id,
                owner_id=lease.owner_id,
                lease_token=lease.lease_token,
            )
            result = await self._execute_with_heartbeat(
                task_type=task.task_type,
                task_id=task.task_id,
                request_params=task.request_params or {},
                progress_dispatcher=ProgressDispatcher([progress_sink]),
                owner_id=lease.owner_id,
                lease_token=lease.lease_token,
            )
            await progress_sink.drain()
            await self.registry.mark_completed(
                task_id=task.task_id,
                result=result,
                owner_id=lease.owner_id,
                lease_token=lease.lease_token,
            )
            return True
        except LostTaskLeaseError:
            await _drain_progress_sink(progress_sink)
            logger.warning(f"Task {task.task_id} lease was lost; leaving persisted state unchanged")
            return True
        except Exception as exc:
            logger.exception(exc)
            await _drain_progress_sink(progress_sink)
            try:
                await self.registry.mark_failed(
                    task_id=task.task_id,
                    error=str(exc),
                    owner_id=lease.owner_id,
                    lease_token=lease.lease_token,
                )
            except LostTaskLeaseError:
                logger.warning(f"Task {task.task_id} lease was lost before failure could be recorded")
            return True

    async def _execute_with_heartbeat(
        self,
        *,
        task_type,
        task_id: str,
        request_params: dict,
        progress_dispatcher: ProgressDispatcher,
        owner_id: str,
        lease_token: str,
    ) -> dict[str, Any]:
        execution_task = asyncio.create_task(
            self.executor_registry.execute(
                task_type,
                task_id=task_id,
                request_params=request_params,
                progress_dispatcher=progress_dispatcher,
            )
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {execution_task},
                    timeout=self.heartbeat_interval_seconds,
                )
                if execution_task in done:
                    return await execution_task
                await self.registry.heartbeat(
                    task_id=task_id,
                    owner_id=owner_id,
                    lease_token=lease_token,
                )
                await self.heartbeat_capabilities()
        except LostTaskLeaseError:
            execution_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await execution_task
            raise


async def run_worker_forever(config: APIConfig = api_config) -> None:
    runtime = build_task_runtime(config)
    core = await build_worker_core(config=config)
    register_video_generation_executor(
        runtime.executor_registry,
        core_provider=lambda: core,
        artifact_store=runtime.task_manager.registry.artifact_store,
    )
    register_storyboard_workbench_executors(
        runtime.executor_registry,
        core_provider=lambda: core,
    )
    worker = GenerationWorker(
        registry=runtime.task_manager.registry,
        core=core,
        artifact_store=runtime.task_manager.registry.artifact_store,
        output_root=resolve_api_configured_path(
            config.artifact_base_path,
            setting_name="PIXELLE_ARTIFACT_BASE_PATH",
        ),
        heartbeat_interval_seconds=config.generation_heartbeat_seconds,
        executor_registry=runtime.executor_registry,
        worker_registry=runtime.worker_registry,
    )

    try:
        while True:
            did_work = await worker.run_once()
            if not did_work:
                await worker.heartbeat_capabilities()
                await asyncio.sleep(config.worker_poll_interval_seconds)
    finally:
        await core.cleanup()


async def build_worker_core(*, config: APIConfig = api_config) -> PixelleVideoCore:
    core = PixelleVideoCore()
    attach_platform_dependencies(core, build_platform_dependencies(config))
    await core.initialize()
    return core


def main() -> None:
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
