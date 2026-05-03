"""Task backend factory."""

from __future__ import annotations

from dataclasses import dataclass

from api.config import APIConfig
from api.tasks.artifacts import LocalArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.lease import InMemoryGenerationLease, create_redis_lease
from api.tasks.manager import TaskManager
from api.tasks.postgres import (
    PostgresTaskStore,
    PostgresWorkerRegistry,
    create_async_engine_from_dsn,
)
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore
from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerRegistry


@dataclass(frozen=True)
class TaskRuntime:
    task_manager: TaskManager
    executor_registry: TaskExecutorRegistry
    worker_registry: WorkerRegistry


def build_task_runtime(
    config: APIConfig,
    *,
    executor_registry: TaskExecutorRegistry | None = None,
) -> TaskRuntime:
    """Build a cohesive task runtime for the configured backend."""
    if config.artifact_backend != "local":
        raise RuntimeError("Only PIXELLE_ARTIFACT_BACKEND=local is implemented")

    executor_registry = executor_registry or TaskExecutorRegistry()
    artifact_store = LocalArtifactStore(
        output_root=config.artifact_base_path,
        base_url=config.artifact_base_url,
    )

    if config.task_backend == "memory":
        store = InMemoryTaskStore()
        lease = InMemoryGenerationLease(config.generation_lease_ttl_seconds)
        worker_registry = InMemoryWorkerRegistry(config.generation_lease_ttl_seconds)
    else:
        if not config.postgres_dsn:
            raise RuntimeError("PIXELLE_POSTGRES_DSN is required for postgres task backend")
        if not config.redis_url:
            raise RuntimeError("PIXELLE_REDIS_URL is required for postgres task backend")
        engine = create_async_engine_from_dsn(config.postgres_dsn)
        store = PostgresTaskStore(engine)
        lease = create_redis_lease(
            config.redis_url,
            lease_ttl_seconds=config.generation_lease_ttl_seconds,
            submit_lock_ttl_seconds=30,
        )
        worker_registry = PostgresWorkerRegistry(
            engine,
            heartbeat_ttl_seconds=config.generation_lease_ttl_seconds,
        )

    if config.require_distributed_coordination and config.task_backend != "postgres":
        raise RuntimeError(
            "PIXELLE_TASK_BACKEND=postgres is required when distributed coordination is required"
        )

    registry = GenerationRegistry(
        store=store,
        lease=lease,
        artifact_store=artifact_store,
        submit_lock_wait_seconds=config.generation_submit_lock_wait_seconds,
        submit_lock_poll_interval_seconds=config.generation_submit_lock_poll_seconds,
    )
    manager = TaskManager(
        store=store,
        registry=registry,
        execution_mode=config.execution_mode,
        executor_registry=executor_registry,
        worker_capability_registry=worker_registry,
    )
    return TaskRuntime(
        task_manager=manager,
        executor_registry=executor_registry,
        worker_registry=worker_registry,
    )


def build_api_task_runtime(config: APIConfig) -> TaskRuntime:
    return build_task_runtime(config)


def build_local_task_runtime(config: APIConfig) -> TaskRuntime:
    local_config = config.model_copy(deep=True)
    local_config.task_backend = "memory"
    local_config.execution_mode = "embedded"
    return build_task_runtime(local_config)


def build_task_manager(config: APIConfig) -> TaskManager:
    """Build a TaskManager for the configured backend."""
    return build_task_runtime(config).task_manager
