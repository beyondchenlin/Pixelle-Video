"""Generation worker process."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from api.config import APIConfig, api_config
from api.tasks.artifacts import ArtifactStore
from api.tasks.factory import build_task_manager
from api.tasks.models import TaskType
from api.tasks.registry import GenerationRegistry
from pixelle_video.service import PixelleVideoCore

REGISTRY_CONTROL_PARAM_NAMES = {
    "generation_fingerprint",
}


class GenerationWorker:
    """Claims pending generation tasks and executes them outside the API process."""

    def __init__(
        self,
        *,
        registry: GenerationRegistry,
        core: Any,
        artifact_store: ArtifactStore,
        output_root: str | Path = "output",
        worker_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.core = core
        self.artifact_store = artifact_store
        self.output_root = Path(output_root)
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"

    async def run_once(self) -> bool:
        claim = await self.registry.claim_next_pending(
            worker_id=self.worker_id,
            task_types={TaskType.VIDEO_GENERATION},
        )
        if claim is None:
            return False

        task = claim.task
        lease = claim.lease
        try:
            params = self._build_generation_params(task_id=task.task_id, request_params=task.request_params)
            result = await self.core.generate_video(**params)
            artifact = await self.artifact_store.persist_video(
                task_id=task.task_id,
                source_path=result.video_path,
                duration=float(getattr(result, "duration", 0.0) or 0.0),
            )
            await self.registry.mark_completed(
                task_id=task.task_id,
                result=artifact,
                owner_id=lease.owner_id,
                lease_token=lease.lease_token,
            )
            return True
        except Exception as exc:
            logger.exception(exc)
            await self.registry.mark_failed(
                task_id=task.task_id,
                error=str(exc),
                owner_id=lease.owner_id,
                lease_token=lease.lease_token,
            )
            return True

    def _build_generation_params(self, *, task_id: str, request_params: dict | None) -> dict:
        params = dict(request_params or {})
        for name in REGISTRY_CONTROL_PARAM_NAMES:
            params.pop(name, None)
        params["api_task_id"] = task_id
        params["output_path"] = str(self.output_root / task_id / "final.mp4")
        return params


async def run_worker_forever(config: APIConfig = api_config) -> None:
    manager = build_task_manager(config)
    core = PixelleVideoCore()
    await core.initialize()
    worker = GenerationWorker(
        registry=manager.registry,
        core=core,
        artifact_store=manager.registry.artifact_store,
        output_root=config.artifact_base_path,
    )

    try:
        while True:
            did_work = await worker.run_once()
            if not did_work:
                await asyncio.sleep(config.worker_poll_interval_seconds)
    finally:
        await core.cleanup()


def main() -> None:
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
