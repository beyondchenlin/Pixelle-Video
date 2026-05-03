# Storyboard Workbench Client Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Storyboard Workbench and the existing async video path depend on one first-class task execution boundary with honest display, capability, task submission, and execution contracts, so local Streamlit no longer depends on `8001`, no regenerate path is fake, and no async task path remains on legacy execution rails.

**Architecture:** Introduce a backend `StoryboardWorkbenchTaskSubmitter` on top of a general-purpose `TaskExecutorRegistry`, migrate both frame regeneration and async video execution onto that registry, and replace static worker capability declarations with a heartbeat-backed worker registry. Expose honest backend capabilities over HTTP, keep transport-specific URL derivation out of persisted task results, then introduce HTTP and in-process Workbench clients. The Workbench page resolves one client and passes it downward; child components consume `image_display` payloads and capabilities only.

**Tech Stack:** Python, Streamlit, FastAPI, Pydantic, pytest, ruff.

---

## File Structure

- Create `api/workbench/__init__.py`
  - Exports backend Workbench runtime adapters.
- Create `api/workbench/task_submitter.py`
  - Defines `StoryboardWorkbenchTaskSubmitter`, capability model, task submission DTO, `TaskManagerStoryboardWorkbenchTaskSubmitter`, and `NoopStoryboardWorkbenchTaskSubmitter`.
- Create `api/workbench/frame_image_regeneration.py`
  - Executes a reserved frame image regeneration task by loading state, prompt plan, generating media, storing the artifact version, and saving updated Workbench state.
- Create `api/workbench/executor_factory.py`
  - Registers Workbench task executors in a shared `TaskExecutorRegistry` using a lazy core provider closure.
- Create `api/video/executor_factory.py`
  - Registers the existing async video generation executor in the same `TaskExecutorRegistry`.
- Create `api/tasks/executors.py`
  - Defines `TaskExecutor`, `TaskExecutionCapability`, `TaskExecutorRegistry`, and worker capability protocols.
- Create `api/tasks/worker_registry.py`
  - Defines heartbeat-backed worker capability source and in-memory implementation for tests and single-process memory backend.
- Create `api/tasks/alembic/versions/0002_create_worker_heartbeats.py`
  - Adds the shared worker heartbeat table required by Postgres-backed API/worker deployments.
- Modify `api/tasks/postgres.py`
  - Adds `worker_heartbeats` metadata and `PostgresWorkerRegistry`.
- Modify `api/tasks/manager.py`
  - Delegates all async generation execution capability and embedded auto-execution to the general task executor registry.
- Modify `api/tasks/factory.py`
  - Builds a cohesive task runtime: `TaskManager`, executor registry, and worker registry from one backend configuration.
- Modify `api/platform_dependencies.py`
  - Adds `storyboard_workbench_task_submitter` plus shared task capability registries.
- Modify `api/dependencies.py`
  - Keeps API-scoped platform dependencies separate from Streamlit local platform dependencies.
- Modify `web/state/session.py`
  - Owns the local platform `TaskManager` and local task executor registry used when Streamlit runs without FastAPI.
- Modify `api/app.py`
  - Passes the FastAPI lifespan task manager into platform dependency construction.
- Modify `api/routers/storyboard_workbench.py`
  - Adds capability endpoint and switches regenerate endpoint from direct `task_manager` access to submitter.
- Modify `api/schemas/storyboard_workbench.py`
  - Adds capability response schema.
- Modify `api/tasks/worker.py`
  - Heartbeats supported task types and claims all registered executor task types in worker mode.
- Modify `api/routers/video.py`
  - Stops passing per-request execution closures into `TaskManager`; async video execution goes through the registered executor and task result presentation derives URLs at response time.
- Modify `api/routers/tasks.py`
  - Adds task response presentation that derives `video_url` from `storage_key` and current request without persisting transport URLs.
- Modify `api/schemas/tasks.py`
  - Adds task response DTOs if needed to keep persisted task models separate from HTTP presentation.
- Modify `web/utils/storyboard_workbench_api.py`
  - Adds `get_storyboard_workbench_capabilities(...)`.
- Create `web/workbench/__init__.py`
  - Exports client protocol and concrete clients.
- Create `web/workbench/client.py`
  - Defines the client operation contract and error type.
- Create `web/workbench/display.py`
  - Normalizes remote URL display payloads and local bytes display payloads.
- Create `web/workbench/http_client.py`
  - Wraps existing HTTP helpers and capability endpoint.
- Create `web/workbench/inprocess_protocols.py`
  - Declares local-readable artifact protocol.
- Create `web/workbench/inprocess_client.py`
  - Calls local platform services/stores and submitter directly.
- Create `web/state/workbench_client.py`
  - Resolves mode and caches only fully configured clients.
- Modify `web/components/storyboard_workbench_panel.py`
  - Replaces direct HTTP loaders with injected client and capability-gated regenerate button.
- Modify `web/components/storyboard_workbench_stale.py`
  - Replaces direct stale HTTP loader with injected client.
- Modify `web/components/storyboard_preview.py`
  - Passes `workbench_client` through to Workbench and stale components.
- Modify `web/pages/3_🧭_Storyboard_Workbench.py`
  - Resolves mode, initializes local `PixelleVideoCore` when needed, then resolves one client.
- Test `tests/test_storyboard_workbench_task_submitter.py`
  - Submitter, capability, and executor behavior.
- Test updates:
  - `tests/test_app_platform_dependencies.py`
  - `tests/test_storyboard_workbench_api.py`
  - `tests/test_storyboard_workbench_frontend_api.py`
  - `tests/test_storyboard_workbench_client.py`
  - `tests/test_storyboard_workbench_panel_ui.py`
  - `tests/test_storyboard_workbench_stale_ui.py`
  - `tests/test_storyboard_workbench_page.py`
  - `tests/test_worker_execution.py`
  - `tests/test_video_task_executor.py`
  - `tests/test_tasks_api_presentation.py`

## Execution Notes

- Do not switch UI default mode before the in-process client supports list/select/stale/display/regenerate submission.
- Do not claim regenerate is available unless a submitter and executor path exist.
- Do not add `frame_image_regeneration_executor`, `video_generation_executor`, `tts_executor`, or similar product-specific fields to `TaskManager`; all async generation execution capability must go through `TaskExecutorRegistry`.
- Do not preserve `VIDEO_GENERATION` as a legacy exception. The existing async video route must submit only; execution must come from the registered `TaskType.VIDEO_GENERATION` executor.
- Do not introduce static worker capability as production behavior. Worker capability must come from heartbeat-backed `WorkerRegistry`; tests and `PIXELLE_TASK_BACKEND=memory` single-process development may use in-memory registries, while Postgres/distributed deployments must use shared heartbeat storage.
- Do not persist request-derived URLs such as `video_url` in task results. Persist storage identity only and derive HTTP URLs at response presentation boundaries.
- Do not call `request.app.state.task_manager` from the Storyboard Workbench router after Task 2.
- Do not use `api.tasks.manager.task_manager` global as a local shortcut.
- Keep commits atomic and pushable. Use `git push origin <current-branch>` after each commit per repository policy.
- Ignore unrelated dirty files, especially `tests/test_style_config_layered_template_ui.py`, unless they become directly relevant.

---

## Task 1: Add General Task Executor And Worker Capability Registries

**Files:**
- Create: `api/tasks/executors.py`
- Create: `api/tasks/worker_registry.py`
- Create: `api/tasks/alembic/versions/0002_create_worker_heartbeats.py`
- Modify: `api/tasks/postgres.py`
- Create: `api/workbench/__init__.py`
- Create: `api/workbench/task_submitter.py`
- Modify: `api/tasks/manager.py`
- Modify: `api/tasks/factory.py`
- Modify: `api/platform_dependencies.py`
- Modify: `api/dependencies.py`
- Modify: `web/state/session.py`
- Modify: `api/app.py`
- Test: `tests/test_storyboard_workbench_task_submitter.py`
- Test: `tests/test_app_platform_dependencies.py`

- [ ] **Step 1: Write failing executor, worker registry, and submitter tests**

Create `tests/test_storyboard_workbench_task_submitter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from api.tasks.models import TaskType


@dataclass
class _Task:
    task_id: str
    task_type: TaskType


@dataclass
class _Outcome:
    task: _Task
    created: bool
    reused_reason: str | None


class _FakeTaskManager:
    def __init__(self, *, can_execute_frame_regeneration: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.can_execute_frame_regeneration = can_execute_frame_regeneration

    async def can_execute_task_type(self, task_type: TaskType) -> bool:
        return task_type is TaskType.FRAME_IMAGE_REGENERATION and self.can_execute_frame_regeneration

    async def reserve_or_reuse_generation_task(
        self,
        *,
        task_type: TaskType,
        generation_fingerprint: str,
        request_params: dict[str, Any],
    ) -> _Outcome:
        self.calls.append(
            {
                "task_type": task_type,
                "generation_fingerprint": generation_fingerprint,
                "request_params": request_params,
            }
        )
        return _Outcome(
            task=_Task("regen-task-1", task_type),
            created=True,
            reused_reason=None,
        )


@pytest.mark.asyncio
async def test_task_executor_registry_registers_capability_and_executes_task():
    from api.tasks.executors import TaskExecutorRegistry

    calls: list[dict[str, Any]] = []

    async def executor(*, task_id: str, request_params: dict[str, Any], progress_dispatcher=None):
        calls.append(
            {
                "task_id": task_id,
                "request_params": request_params,
                "has_progress": progress_dispatcher is not None,
            }
        )
        return {"ok": True}

    registry = TaskExecutorRegistry()

    assert registry.can_execute(TaskType.FRAME_IMAGE_REGENERATION).to_dict() == {
        "can_execute": False,
        "unavailable_reason": "task executor is not registered",
    }

    registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)

    assert registry.can_execute(TaskType.FRAME_IMAGE_REGENERATION).to_dict() == {
        "can_execute": True,
        "unavailable_reason": None,
    }
    assert await registry.execute(
        TaskType.FRAME_IMAGE_REGENERATION,
        task_id="regen-task-1",
        request_params={"workspace_id": "workspace_1"},
        progress_dispatcher=object(),
    ) == {"ok": True}
    assert calls == [
        {
            "task_id": "regen-task-1",
            "request_params": {"workspace_id": "workspace_1"},
            "has_progress": True,
        }
    ]


@pytest.mark.asyncio
async def test_worker_capability_registry_uses_recent_heartbeats():
    from datetime import timedelta

    from api.tasks.models import utc_now
    from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat

    now = utc_now()
    registry = InMemoryWorkerRegistry(heartbeat_ttl_seconds=30)

    assert await registry.supports(TaskType.FRAME_IMAGE_REGENERATION, now=now) is False

    await registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=now,
        )
    )

    assert await registry.supports(TaskType.FRAME_IMAGE_REGENERATION, now=now) is True
    assert await registry.supports(TaskType.VIDEO_GENERATION, now=now) is False
    assert (
        await registry.supports(
            TaskType.FRAME_IMAGE_REGENERATION,
            now=now + timedelta(seconds=31),
        )
        is False
    )

@pytest.mark.asyncio
async def test_task_manager_storyboard_submitter_reserves_frame_regeneration_task():
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    manager = _FakeTaskManager()
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)

    result = await submitter.reserve_frame_image_regeneration(
        generation_fingerprint="fingerprint-frame-0001",
        request_params={"workspace_id": "workspace_1"},
    )

    assert result.to_dict() == {
        "task_id": "regen-task-1",
        "task_type": "frame_image_regeneration",
        "created": True,
        "reused_reason": None,
    }
    assert manager.calls == [
        {
            "task_type": TaskType.FRAME_IMAGE_REGENERATION,
            "generation_fingerprint": "fingerprint-frame-0001",
            "request_params": {"workspace_id": "workspace_1"},
        }
    ]


@pytest.mark.asyncio
async def test_task_manager_reports_frame_regeneration_unavailable_by_default():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(TaskManager())

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "frame image regeneration execution is not configured",
    }


@pytest.mark.asyncio
async def test_task_manager_embedded_capability_comes_from_executor_registry():
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    async def executor(**_kwargs):
        return {"ok": True}

    registry = TaskExecutorRegistry()
    registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(
        TaskManager(executor_registry=registry)
    )

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }


@pytest.mark.asyncio
async def test_task_manager_worker_mode_uses_worker_capability_registry():
    from api.tasks.manager import TaskManager
    from api.tasks.models import utc_now
    from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat

    worker_registry = InMemoryWorkerRegistry()
    await worker_registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=utc_now(),
        )
    )
    assert (
        await TaskManager(execution_mode="worker").can_execute_task_type(
            TaskType.FRAME_IMAGE_REGENERATION
        )
        is False
    )
    assert (
        await TaskManager(
            execution_mode="worker",
            worker_capability_registry=worker_registry,
        ).can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION)
        is True
    )
```

- [ ] **Step 2: Write failing platform dependency tests**

Append to `tests/test_app_platform_dependencies.py`:

```python
def test_dev_platform_dependencies_mount_storyboard_workbench_task_submitter(tmp_path):
    from api.platform_dependencies import configure_platform_dependencies
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    app = FastAPI()
    manager = TaskManager()
    dependencies = configure_platform_dependencies(
        app,
        APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output")),
        task_manager=manager,
    )

    assert isinstance(
        dependencies.storyboard_workbench_task_submitter,
        TaskManagerStoryboardWorkbenchTaskSubmitter,
    )
    assert app.state.storyboard_workbench_task_submitter is (
        dependencies.storyboard_workbench_task_submitter
    )


def test_api_app_lifespan_mounts_storyboard_workbench_task_submitter(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import api.app as api_app
    import api.dependencies as dependencies_module

    monkeypatch.setattr(api_app.api_config, "artifact_base_path", str(tmp_path / "output"))
    dependencies_module._platform_dependencies = None

    with TestClient(api_app.app) as client:
        assert hasattr(client.app.state, "storyboard_workbench_task_submitter")
        assert dependencies_module.get_or_create_platform_dependencies().storyboard_workbench_task_submitter is (
            client.app.state.storyboard_workbench_task_submitter
        )


def test_web_session_pixelle_video_mounts_storyboard_workbench_task_submitter(monkeypatch, tmp_path):
    from api.config import api_config
    from web.state import session as web_session
    from web.state.async_runtime import shutdown_all_async_runtimes

    monkeypatch.setattr(api_config, "artifact_base_path", str(tmp_path / "output"))
    web_session._LOCAL_PLATFORM_DEPENDENCIES = None
    web_session._LOCAL_PLATFORM_TASK_MANAGER = None
    web_session._PIXELLE_VIDEO_SESSIONS.clear()
    monkeypatch.setattr(web_session, "get_current_session_key", lambda: "test_web_session_submitter")
    monkeypatch.setattr(web_session, "register_async_cleanup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(web_session, "session_exists", lambda _session_key: True)

    core = None
    try:
        core = web_session.get_pixelle_video()
        dependencies = web_session.get_or_create_local_platform_dependencies()

        assert core.storyboard_workbench_task_submitter is (
            dependencies.storyboard_workbench_task_submitter
        )
        assert core.storyboard_workbench_task_submitter is not None
    finally:
        if core is not None:
            web_session.run_async(core.cleanup())
        web_session._PIXELLE_VIDEO_SESSIONS.clear()
        shutdown_all_async_runtimes()
        if web_session._LOCAL_PLATFORM_TASK_MANAGER is not None:
            web_session.run_async(web_session._LOCAL_PLATFORM_TASK_MANAGER.stop())
        web_session._LOCAL_PLATFORM_TASK_MANAGER = None
        web_session._LOCAL_PLATFORM_DEPENDENCIES = None


def test_platform_dependencies_store_task_registries_without_pixelle_provider(tmp_path):
    from api.platform_dependencies import build_platform_dependencies
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.worker_registry import InMemoryWorkerRegistry

    executor_registry = TaskExecutorRegistry()
    worker_capabilities = InMemoryWorkerRegistry()

    dependencies = build_platform_dependencies(
        APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output")),
        task_executor_registry=executor_registry,
        worker_capability_registry=worker_capabilities,
        worker_registry=worker_capabilities,
    )

    assert dependencies.task_executor_registry is executor_registry
    assert dependencies.worker_capability_registry is worker_capabilities
    assert dependencies.worker_registry is worker_capabilities
    assert not hasattr(dependencies, "pixelle_video_core_provider")
```

Append to `tests/test_postgres_task_store_schema.py`:

```python
def test_worker_heartbeat_migration_contains_shared_capability_table():
    from pathlib import Path

    migration = Path(
        "api/tasks/alembic/versions/0002_create_worker_heartbeats.py"
    ).read_text(encoding="utf-8")

    assert "worker_heartbeats" in migration
    assert "worker_id" in migration
    assert "supported_task_types" in migration
    assert "heartbeat_at" in migration
    assert "idx_worker_heartbeats_heartbeat_at" in migration


def test_postgres_worker_registry_exposes_shared_heartbeat_methods():
    from api.tasks.postgres import PostgresWorkerRegistry

    assert hasattr(PostgresWorkerRegistry, "heartbeat")
    assert hasattr(PostgresWorkerRegistry, "supports")
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py::test_dev_platform_dependencies_mount_storyboard_workbench_task_submitter tests/test_app_platform_dependencies.py::test_api_app_lifespan_mounts_storyboard_workbench_task_submitter tests/test_app_platform_dependencies.py::test_web_session_pixelle_video_mounts_storyboard_workbench_task_submitter tests/test_postgres_task_store_schema.py::test_worker_heartbeat_migration_contains_shared_capability_table tests/test_postgres_task_store_schema.py::test_postgres_worker_registry_exposes_shared_heartbeat_methods
```

Expected: fail because `api.tasks.executors`, `api.workbench`, `TaskManager.can_execute_task_type(...)`, and submitter wiring do not exist.

- [ ] **Step 4: Add executor registry and submitter modules**

Create `api/tasks/executors.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from api.tasks.models import TaskType


@runtime_checkable
class TaskExecutor(Protocol):
    async def __call__(
        self,
        *,
        task_id: str,
        request_params: Mapping[str, Any],
        progress_dispatcher: Any | None = None,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class TaskExecutionCapability:
    can_execute: bool
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_execute": self.can_execute,
            "unavailable_reason": self.unavailable_reason,
        }


class TaskExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[TaskType, TaskExecutor] = {}

    def register(self, task_type: TaskType, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def supported_task_types(self) -> set[TaskType]:
        return set(self._executors)

    def can_execute(self, task_type: TaskType) -> TaskExecutionCapability:
        if task_type in self._executors:
            return TaskExecutionCapability(can_execute=True)
        return TaskExecutionCapability(
            can_execute=False,
            unavailable_reason="task executor is not registered",
        )

    async def execute(
        self,
        task_type: TaskType,
        *,
        task_id: str,
        request_params: Mapping[str, Any],
        progress_dispatcher: Any | None = None,
    ) -> dict[str, Any]:
        executor = self._executors.get(task_type)
        if executor is None:
            raise RuntimeError("task executor is not registered")
        result = await executor(
            task_id=task_id,
            request_params=request_params,
            progress_dispatcher=progress_dispatcher,
        )
        return dict(result)


@runtime_checkable
class WorkerCapabilityRegistry(Protocol):
    async def supports(self, task_type: TaskType) -> bool: ...


__all__ = [
    "TaskExecutionCapability",
    "TaskExecutor",
    "TaskExecutorRegistry",
    "WorkerCapabilityRegistry",
]
```

Create `api/tasks/worker_registry.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from api.tasks.models import TaskType, utc_now


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    supported_task_types: set[TaskType]
    heartbeat_at: datetime


@runtime_checkable
class WorkerRegistry(Protocol):
    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None: ...
    async def supports(self, task_type: TaskType, *, now: datetime | None = None) -> bool: ...


class InMemoryWorkerRegistry:
    def __init__(self, heartbeat_ttl_seconds: int = 60) -> None:
        self.heartbeat_ttl = timedelta(seconds=heartbeat_ttl_seconds)
        self._heartbeats: dict[str, WorkerHeartbeat] = {}
        self._lock = asyncio.Lock()

    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        async with self._lock:
            self._heartbeats[heartbeat.worker_id] = heartbeat

    async def supports(self, task_type: TaskType, *, now: datetime | None = None) -> bool:
        cutoff = (now or utc_now()) - self.heartbeat_ttl
        async with self._lock:
            return any(
                heartbeat.heartbeat_at >= cutoff
                and task_type in heartbeat.supported_task_types
                for heartbeat in self._heartbeats.values()
            )


__all__ = [
    "InMemoryWorkerRegistry",
    "WorkerHeartbeat",
    "WorkerRegistry",
]
```

Create `api/tasks/alembic/versions/0002_create_worker_heartbeats.py`:

```python
"""Create worker heartbeat capability table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_create_worker_heartbeats"
down_revision = "0001_create_generation_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.Text(), primary_key=True),
        sa.Column(
            "supported_task_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_worker_heartbeats_heartbeat_at",
        "worker_heartbeats",
        ["heartbeat_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_worker_heartbeats_heartbeat_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
```

Modify `api/tasks/postgres.py`:

```python
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.tasks.worker_registry import WorkerHeartbeat
```

Add table metadata next to `generation_tasks`:

```python
worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_id", Text, primary_key=True),
    Column("supported_task_types", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

Index("idx_worker_heartbeats_heartbeat_at", worker_heartbeats.c.heartbeat_at)
```

Add shared registry implementation:

```python
class PostgresWorkerRegistry:
    def __init__(self, engine: AsyncEngine, *, heartbeat_ttl_seconds: int = 60) -> None:
        self.engine = engine
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        values = {
            "worker_id": heartbeat.worker_id,
            "supported_task_types": [
                task_type.value for task_type in heartbeat.supported_task_types
            ],
            "heartbeat_at": heartbeat.heartbeat_at,
            "updated_at": utc_now(),
        }
        statement = pg_insert(worker_heartbeats).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[worker_heartbeats.c.worker_id],
            set_=values,
        )
        async with self.session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def supports(self, task_type: TaskType, *, now: datetime | None = None) -> bool:
        cutoff = (now or utc_now()) - timedelta(seconds=self.heartbeat_ttl_seconds)
        async with self.session_factory() as session:
            result = await session.execute(
                select(worker_heartbeats.c.worker_id)
                .where(worker_heartbeats.c.heartbeat_at >= cutoff)
                .where(worker_heartbeats.c.supported_task_types.contains([task_type.value]))
                .limit(1)
            )
            return result.first() is not None
```

Create `api/workbench/task_submitter.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from api.tasks.models import TaskType


@dataclass(frozen=True)
class StoryboardWorkbenchTaskSubmission:
    task_id: str
    task_type: str
    created: bool
    reused_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "created": self.created,
            "reused_reason": self.reused_reason,
        }


@dataclass(frozen=True)
class StoryboardWorkbenchCapabilities:
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_regenerate_frame_image": self.can_regenerate_frame_image,
            "regenerate_unavailable_reason": self.regenerate_unavailable_reason,
        }


@runtime_checkable
class StoryboardWorkbenchTaskSubmitter(Protocol):
    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities: ...

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission: ...


class TaskManagerStoryboardWorkbenchTaskSubmitter:
    def __init__(self, task_manager: Any) -> None:
        self.task_manager = task_manager

    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
        can_execute_task_type = getattr(self.task_manager, "can_execute_task_type", None)
        can_execute = (
            bool(await can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION))
            if can_execute_task_type is not None
            else False
        )
        if not can_execute:
            return StoryboardWorkbenchCapabilities(
                can_regenerate_frame_image=False,
                regenerate_unavailable_reason="frame image regeneration execution is not configured",
            )
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=True,
            regenerate_unavailable_reason=None,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission:
        capabilities = await self.get_capabilities()
        if not capabilities.can_regenerate_frame_image:
            raise RuntimeError(
                capabilities.regenerate_unavailable_reason
                or "frame image regeneration execution is not configured"
            )
        outcome = await self.task_manager.reserve_or_reuse_generation_task(
            task_type=TaskType.FRAME_IMAGE_REGENERATION,
            generation_fingerprint=generation_fingerprint,
            request_params=dict(request_params),
        )
        return StoryboardWorkbenchTaskSubmission(
            task_id=outcome.task.task_id,
            task_type=outcome.task.task_type.value,
            created=outcome.created,
            reused_reason=outcome.reused_reason,
        )


class NoopStoryboardWorkbenchTaskSubmitter:
    def __init__(self, reason: str = "task submitter is not configured") -> None:
        self.reason = reason

    async def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=False,
            regenerate_unavailable_reason=self.reason,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission:
        raise RuntimeError(self.reason)


async def get_storyboard_workbench_capabilities(
    submitter: StoryboardWorkbenchTaskSubmitter | None,
) -> StoryboardWorkbenchCapabilities:
    if submitter is None:
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=False,
            regenerate_unavailable_reason="task submitter is not configured",
        )
    return await submitter.get_capabilities()


__all__ = [
    "NoopStoryboardWorkbenchTaskSubmitter",
    "StoryboardWorkbenchCapabilities",
    "StoryboardWorkbenchTaskSubmission",
    "StoryboardWorkbenchTaskSubmitter",
    "TaskManagerStoryboardWorkbenchTaskSubmitter",
    "get_storyboard_workbench_capabilities",
]
```

Create `api/workbench/__init__.py`:

```python
from api.workbench.task_submitter import (
    NoopStoryboardWorkbenchTaskSubmitter,
    StoryboardWorkbenchCapabilities,
    StoryboardWorkbenchTaskSubmission,
    StoryboardWorkbenchTaskSubmitter,
    TaskManagerStoryboardWorkbenchTaskSubmitter,
    get_storyboard_workbench_capabilities,
)

__all__ = [
    "NoopStoryboardWorkbenchTaskSubmitter",
    "StoryboardWorkbenchCapabilities",
    "StoryboardWorkbenchTaskSubmission",
    "StoryboardWorkbenchTaskSubmitter",
    "TaskManagerStoryboardWorkbenchTaskSubmitter",
    "get_storyboard_workbench_capabilities",
]
```

- [ ] **Step 5: Wire platform dependencies**

Modify `api/platform_dependencies.py`:

```python
from api.tasks.executors import (
    TaskExecutorRegistry,
    WorkerCapabilityRegistry,
)
from api.tasks.worker_registry import WorkerRegistry
from api.workbench.task_submitter import (
    StoryboardWorkbenchTaskSubmitter,
    TaskManagerStoryboardWorkbenchTaskSubmitter,
)
```

Extend `PlatformDependencies`:

```python
task_executor_registry: TaskExecutorRegistry | None = None
worker_capability_registry: WorkerCapabilityRegistry | None = None
worker_registry: WorkerRegistry | None = None
storyboard_workbench_task_submitter: StoryboardWorkbenchTaskSubmitter | None = None
```

Change signatures:

```python
def configure_platform_dependencies(
    app: FastAPI,
    config: APIConfig,
    *,
    core: Any | None = None,
    task_manager: Any | None = None,
    task_executor_registry: TaskExecutorRegistry | None = None,
    worker_capability_registry: WorkerCapabilityRegistry | None = None,
    worker_registry: WorkerRegistry | None = None,
) -> PlatformDependencies:
    dependencies = build_platform_dependencies(
        config,
        task_manager=task_manager,
        task_executor_registry=task_executor_registry,
        worker_capability_registry=worker_capability_registry,
        worker_registry=worker_registry,
    )
```

```python
def build_platform_dependencies(
    config: APIConfig,
    *,
    task_manager: Any | None = None,
    task_executor_registry: TaskExecutorRegistry | None = None,
    worker_capability_registry: WorkerCapabilityRegistry | None = None,
    worker_registry: WorkerRegistry | None = None,
) -> PlatformDependencies:
```

Inside `build_platform_dependencies(...)`:

```python
task_submitter = (
    TaskManagerStoryboardWorkbenchTaskSubmitter(task_manager)
    if task_manager is not None
    else None
)
```

Include fields in `PlatformDependencies(...)`.

Keep `api/dependencies.py.get_or_create_platform_dependencies()` API-scoped. It should continue to return dependencies installed by FastAPI lifespan when available, and should not create a Streamlit-local task manager as a hidden side effect.

Do not add a `PixelleVideoCore` provider to `PlatformDependencies`. Lazy core access belongs only inside concrete executor factory closures introduced in Task 3.

Modify `web/state/session.py` instead:

```python
_LOCAL_PLATFORM_DEPENDENCIES = None
_LOCAL_PLATFORM_TASK_MANAGER = None
_LOCAL_TASK_EXECUTOR_REGISTRY = None
_LOCAL_WORKER_REGISTRY = None


def get_or_create_local_platform_dependencies():
    global _LOCAL_PLATFORM_DEPENDENCIES, _LOCAL_PLATFORM_TASK_MANAGER
    global _LOCAL_TASK_EXECUTOR_REGISTRY, _LOCAL_WORKER_REGISTRY
    if _LOCAL_PLATFORM_DEPENDENCIES is None:
        from api.config import api_config
        from api.platform_dependencies import build_platform_dependencies
        from api.tasks.factory import build_local_task_runtime

        runtime = build_local_task_runtime(api_config)
        _LOCAL_TASK_EXECUTOR_REGISTRY = runtime.executor_registry
        _LOCAL_WORKER_REGISTRY = runtime.worker_registry
        _LOCAL_PLATFORM_TASK_MANAGER = runtime.task_manager
        run_async(_LOCAL_PLATFORM_TASK_MANAGER.start())
        _LOCAL_PLATFORM_DEPENDENCIES = build_platform_dependencies(
            api_config,
            task_manager=_LOCAL_PLATFORM_TASK_MANAGER,
            task_executor_registry=_LOCAL_TASK_EXECUTOR_REGISTRY,
            worker_capability_registry=_LOCAL_WORKER_REGISTRY,
            worker_registry=_LOCAL_WORKER_REGISTRY,
        )
    return _LOCAL_PLATFORM_DEPENDENCIES
```

In `get_pixelle_video()`, replace `get_or_create_platform_dependencies()` with `get_or_create_local_platform_dependencies()`.

Update `_cleanup_pixelle_video_session(...)` so when the last session is cleaned up it also stops `_LOCAL_PLATFORM_TASK_MANAGER` and clears `_LOCAL_PLATFORM_DEPENDENCIES`, `_LOCAL_TASK_EXECUTOR_REGISTRY`, and `_LOCAL_WORKER_REGISTRY`.

Modify `api/app.py`:

```python
from api.tasks.factory import build_api_task_runtime

runtime = build_api_task_runtime(api_config)
manager = runtime.task_manager
platform_dependencies = configure_platform_dependencies(
    app,
    api_config,
    task_manager=manager,
    task_executor_registry=runtime.executor_registry,
    worker_capability_registry=runtime.worker_registry,
    worker_registry=runtime.worker_registry,
)
```

Task 1 may create empty registries. `FRAME_IMAGE_REGENERATION` remains unavailable until Task 3 registers its executor.

- [ ] **Step 6: Add honest TaskManager capability declarations**

Modify `api/tasks/manager.py` imports:

```python
from api.tasks.executors import (
    TaskExecutorRegistry,
    WorkerCapabilityRegistry,
)
```

Change constructor:

```python
def __init__(
    self,
    *,
    store: TaskStore | None = None,
    registry: GenerationRegistry | None = None,
    execution_mode: str = "embedded",
    executor_registry: TaskExecutorRegistry | None = None,
    worker_capability_registry: WorkerCapabilityRegistry | None = None,
) -> None:
```

Set fields after `self.execution_mode = execution_mode`:

```python
self.executor_registry = executor_registry or TaskExecutorRegistry()
self.worker_capability_registry = worker_capability_registry
```

Add:

```python
async def can_execute_task_type(self, task_type: TaskType) -> bool:
    if self.execution_mode == "embedded":
        return self.executor_registry.can_execute(task_type).can_execute
    if self.execution_mode == "worker" and self.worker_capability_registry is not None:
        return await self.worker_capability_registry.supports(task_type)
    return False


async def wait_for_task_completion_for_test(self, task_id: str) -> None:
    future = self._task_futures.get(task_id)
    if future is not None:
        await future
```

Important: Task 1 only lays down the runtime boundary and keeps default `TaskManager()` fail closed for both `FRAME_IMAGE_REGENERATION` and `VIDEO_GENERATION` until Task 3 registers executors. Do not keep the current per-request async video closure execution route.

Modify `api/tasks/factory.py`:

```python
from dataclasses import dataclass

from api.tasks.executors import TaskExecutorRegistry
from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerRegistry
from api.tasks.postgres import PostgresTaskStore, PostgresWorkerRegistry, create_async_engine_from_dsn
```

Add runtime DTO and builders:

```python
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
```

Build one backend-consistent runtime:

```python
executor_registry = executor_registry or TaskExecutorRegistry()
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

registry = GenerationRegistry(...)
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
```

Expose thin wrappers:

```python
def build_api_task_runtime(config: APIConfig) -> TaskRuntime:
    return build_task_runtime(config)


def build_local_task_runtime(config: APIConfig) -> TaskRuntime:
    local_config = config.model_copy(deep=True)
    local_config.task_backend = "memory"
    local_config.execution_mode = "embedded"
    return build_task_runtime(local_config)
```

- [ ] **Step 7: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit and push**

```powershell
git add -- api/tasks/executors.py api/tasks/worker_registry.py api/tasks/alembic/versions/0002_create_worker_heartbeats.py api/tasks/postgres.py api/workbench/__init__.py api/workbench/task_submitter.py api/tasks/manager.py api/tasks/factory.py api/platform_dependencies.py api/dependencies.py api/app.py web/state/session.py tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py
git commit -m "feat: 注入分镜工作台任务注册表和提交器"
git push origin $(git branch --show-current)
```

---

## Task 2: Expose Backend Capabilities And Use Submitter In Router

**Files:**
- Modify: `api/schemas/storyboard_workbench.py`
- Modify: `api/routers/storyboard_workbench.py`
- Test: `tests/test_storyboard_workbench_api.py`

- [ ] **Step 1: Update failing API tests**

In `tests/test_storyboard_workbench_api.py`, replace `FakeTaskManager` usage in `_client(...)` with submitter injection:

```python
@dataclass
class FakeStoryboardWorkbenchTaskSubmitter:
    reserved: list[dict[str, Any]]

    async def get_capabilities(self):
        from api.workbench.task_submitter import StoryboardWorkbenchCapabilities

        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=True,
            regenerate_unavailable_reason=None,
        )

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: dict[str, Any],
    ):
        from api.workbench.task_submitter import StoryboardWorkbenchTaskSubmission

        self.reserved.append(
            {
                "generation_fingerprint": generation_fingerprint,
                "request_params": request_params,
            }
        )
        return StoryboardWorkbenchTaskSubmission(
            task_id="regen-task-1",
            task_type="frame_image_regeneration",
            created=True,
        )
```

Change `_client(...)` parameter:

```python
task_submitter: FakeStoryboardWorkbenchTaskSubmitter | None = None,
```

and injection:

```python
if task_submitter is not None:
    app.state.storyboard_workbench_task_submitter = task_submitter
```

Add:

```python
def test_storyboard_workbench_api_reports_capabilities_from_submitter():
    client = _client(task_submitter=FakeStoryboardWorkbenchTaskSubmitter(reserved=[]))

    response = client.get("/storyboards/workbench/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }


def test_storyboard_workbench_api_reports_regenerate_unavailable_without_submitter():
    client = _client()

    response = client.get("/storyboards/workbench/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Success",
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "task submitter is not configured",
    }
```

Update `test_storyboard_workbench_api_requests_frame_image_regeneration_task()`:

```python
task_submitter = FakeStoryboardWorkbenchTaskSubmitter(reserved=[])
client = _client(
    workbench_service=service,
    state_store=_state_store(),
    task_submitter=task_submitter,
)
...
assert task_submitter.reserved == [
    {
        "generation_fingerprint": "fingerprint-frame-0001",
        "request_params": {
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "prompt_plan_id": "prompt_plan_001",
            "artifact_id": "artifact_frame_0001_image",
            "provider": "comfyui",
            "model": "z-image",
            "generation_fingerprint": "fingerprint-frame-0001",
        },
    }
]
```

Add:

```python
def test_storyboard_workbench_api_regenerate_fails_without_submitter():
    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(workbench_service=service, state_store=_state_store())

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/regenerate-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 503
    assert "task submitter is not configured" in response.json()["detail"]


def test_storyboard_workbench_api_regenerate_fails_when_execution_path_is_missing():
    class UnavailableSubmitter(FakeStoryboardWorkbenchTaskSubmitter):
        async def get_capabilities(self):
            from api.workbench.task_submitter import StoryboardWorkbenchCapabilities

            return StoryboardWorkbenchCapabilities(
                can_regenerate_frame_image=False,
                regenerate_unavailable_reason="frame image regeneration execution is not configured",
            )

    service = FakeWorkbenchService(
        listed_artifacts=[],
        selected_versions=[],
        regeneration_requests=[],
    )
    client = _client(
        workbench_service=service,
        state_store=_state_store(),
        task_submitter=UnavailableSubmitter(reserved=[]),
    )

    response = client.post(
        "/storyboards/storyboard_001/frames/frame_0001/regenerate-image",
        json={
            "workspace_id": "workspace_1",
            "artifact_id": "artifact_frame_0001_image",
        },
    )

    assert response.status_code == 503
    assert "frame image regeneration execution is not configured" in response.json()["detail"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_api.py
```

Expected: fail because capability schema/endpoint and submitter router path do not exist.

- [ ] **Step 3: Add schema**

Modify `api/schemas/storyboard_workbench.py`:

```python
class StoryboardWorkbenchCapabilitiesResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    can_regenerate_frame_image: bool
    regenerate_unavailable_reason: str | None = None
```

Add it to `__all__`.

- [ ] **Step 4: Update router**

Modify imports in `api/routers/storyboard_workbench.py`:

```python
from api.schemas.storyboard_workbench import StoryboardWorkbenchCapabilitiesResponse
from api.workbench.task_submitter import get_storyboard_workbench_capabilities
```

Add endpoint before `/{storyboard_id}` routes:

```python
@router.get(
    "/workbench/capabilities",
    response_model=StoryboardWorkbenchCapabilitiesResponse,
)
async def get_workbench_capabilities(request: Request) -> StoryboardWorkbenchCapabilitiesResponse:
    capabilities = await get_storyboard_workbench_capabilities(
        _get_storyboard_workbench_task_submitter(request, required=False)
    )
    return StoryboardWorkbenchCapabilitiesResponse(**capabilities.to_dict())
```

Replace `_get_task_manager` with:

```python
def _get_storyboard_workbench_task_submitter(request: Request, *, required: bool = True):
    submitter = getattr(request.app.state, "storyboard_workbench_task_submitter", None)
    if submitter is None and required:
        raise HTTPException(status_code=503, detail="task submitter is not configured")
    return submitter
```

In `request_frame_image_regeneration(...)`, replace:

```python
task_manager = _get_task_manager(request)
```

with:

```python
task_submitter = _get_storyboard_workbench_task_submitter(request)
capabilities = await task_submitter.get_capabilities()
if not capabilities.can_regenerate_frame_image:
    raise HTTPException(
        status_code=503,
        detail=capabilities.regenerate_unavailable_reason
        or "frame image regeneration execution is not configured",
    )
```

and replace outcome mapping with:

```python
submission = await task_submitter.reserve_frame_image_regeneration(
    generation_fingerprint=task_request.generation_fingerprint,
    request_params=dict(task_request.request_params),
)
return RegenerateStoryboardFrameImageResponse(
    workspace_id=payload.workspace_id,
    storyboard_id=storyboard_id,
    frame_id=frame_id,
    artifact_id=payload.artifact_id,
    task_id=submission.task_id,
    task_type=submission.task_type,
    created=submission.created,
    reused_reason=submission.reused_reason,
    generation_fingerprint=task_request.generation_fingerprint,
)
```

Remove `from api.tasks.models import TaskType`.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_api.py
```

Expected: all tests pass.

- [ ] **Step 6: Source regression for no direct task manager**

Append to `tests/test_storyboard_workbench_api.py`:

```python
def test_storyboard_workbench_router_does_not_reach_through_to_task_manager():
    from pathlib import Path

    source = Path("api/routers/storyboard_workbench.py").read_text(encoding="utf-8")

    assert "app.state.task_manager" not in source
    assert "reserve_or_reuse_generation_task" not in source
```

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_api.py::test_storyboard_workbench_router_does_not_reach_through_to_task_manager
```

Expected: pass.

- [ ] **Step 7: Commit and push**

```powershell
git add -- api/schemas/storyboard_workbench.py api/routers/storyboard_workbench.py tests/test_storyboard_workbench_api.py
git commit -m "refactor: 让分镜工作台接口通过任务提交器重抽图"
git push origin $(git branch --show-current)
```

---

## Task 3: Migrate Video And Frame Generation To Registered Executors

**Files:**
- Create: `api/video/executor_factory.py`
- Create: `api/workbench/frame_image_regeneration.py`
- Create: `api/workbench/executor_factory.py`
- Modify: `api/tasks/artifacts.py`
- Modify: `api/tasks/manager.py`
- Modify: `api/tasks/factory.py`
- Modify: `api/tasks/worker.py`
- Modify: `api/routers/video.py`
- Modify: `api/routers/tasks.py`
- Modify: `api/schemas/tasks.py`
- Modify: `api/app.py`
- Modify: `web/state/session.py`
- Test: `tests/test_storyboard_workbench_task_submitter.py`
- Test: `tests/test_worker_execution.py`
- Test: `tests/test_video_task_executor.py`
- Test: `tests/test_tasks_api_presentation.py`
- Test: `tests/test_async_video_registry_integration.py`
- Test: `tests/test_artifact_store.py`

- [ ] **Step 1: Write failing executor unit test**

Append to `tests/test_storyboard_workbench_task_submitter.py`:

```python
from pathlib import Path


class _FakeMedia:
    def __init__(self, generated_path: Path) -> None:
        self.generated_path = generated_path
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return type("MediaResult", (), {"media_type": "image", "is_image": True, "url": str(self.generated_path)})()


class _FakePromptPlanRepository:
    async def load_prompt_plans_by_storyboard(self, workspace_id, storyboard_id):
        return [
            {
                "prompt_plan_id": "prompt_plan_001",
                "storyboard_plan_id": storyboard_id,
                "frame_id": "frame_0001",
                "image_prompt_draft_id": "draft_001",
                "prompt_sections": {"visual_goal": "A quiet lab"},
                "final_prompt": "A quiet lab, cinematic lighting",
            }
        ]


class _FakeStateStore:
    def __init__(self):
        self.saved: list[tuple[str, str, str, dict[str, Any]]] = []

    async def load_frame_state(self, workspace_id, storyboard_id, frame_id):
        return {
            "frame_id": frame_id,
            "prompt_plan_id": "prompt_plan_001",
            "selected_image_artifact_id": "artifact_frame_0001_image",
            "selected_image_version_id": "artifact_version_001",
            "candidate_image_version_ids": ["artifact_version_001"],
            "lock_policy": "unlocked",
            "stale_flags": [],
        }

    async def save_frame_state(self, workspace_id, storyboard_id, frame_id, state):
        self.saved.append((workspace_id, storyboard_id, frame_id, dict(state)))
        return state


@pytest.mark.asyncio
async def test_execute_frame_image_regeneration_generates_image_and_records_candidate(tmp_path):
    from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService
    from tests.test_storyboard_frame_regeneration import (
        RecordingArtifactRepository,
        RecordingObjectStore,
        RecordingTraceRepository,
        UnusedPromptPlanRepository,
    )
    from api.workbench.frame_image_regeneration import execute_frame_image_regeneration

    generated = tmp_path / "generated.png"
    generated.write_bytes(b"image")
    artifact_repository = RecordingArtifactRepository(created_versions=[])
    object_store = RecordingObjectStore(uploaded_files=[])
    trace_repository = RecordingTraceRepository(events=[])
    service = StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=UnusedPromptPlanRepository(),
    )
    state_store = _FakeStateStore()
    media = _FakeMedia(generated)
    core = type(
        "Core",
        (),
        {
            "media": media,
            "storyboard_workbench_service": service,
            "storyboard_workbench_state_store": state_store,
            "prompt_plan_repository": _FakePromptPlanRepository(),
        },
    )()

    result = await execute_frame_image_regeneration(
        core=core,
        task_id="regen-task-1",
        request_params={
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_001",
            "frame_id": "frame_0001",
            "prompt_plan_id": "prompt_plan_001",
            "artifact_id": "artifact_frame_0001_image",
            "provider": "comfyui",
            "model": "selfhost/image_z_image_turbo_gguf.json",
            "media_width": 768,
            "media_height": 768,
            "media_negative_prompt": "blurry",
        },
    )

    assert media.calls == [
        {
            "prompt": "A quiet lab, cinematic lighting",
            "media_type": "image",
            "workflow": "selfhost/image_z_image_turbo_gguf.json",
            "width": 768,
            "height": 768,
            "negative_prompt": "blurry",
        }
    ]
    assert result["artifact_version_id"] == artifact_repository.created_versions[-1][2]["version_id"]
    assert state_store.saved[-1][3]["last_generation_job_id"] == "regen-task-1"
```

- [ ] **Step 2: Write failing manager/worker execution tests**

Append to `tests/test_storyboard_workbench_task_submitter.py`:

```python
@pytest.mark.asyncio
async def test_task_manager_embedded_submitter_executes_frame_regeneration_when_executor_configured():
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.manager import TaskManager
    from api.tasks.models import TaskType
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    calls: list[dict[str, Any]] = []

    async def executor(*, task_id: str, request_params: dict[str, Any], progress_dispatcher=None):
        calls.append(
            {
                "task_id": task_id,
                "request_params": request_params,
                "has_progress": progress_dispatcher is not None,
            }
        )
        return {"ok": True}

    executor_registry = TaskExecutorRegistry()
    executor_registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    manager = TaskManager(executor_registry=executor_registry)
    await manager.start()
    try:
        submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)
        submission = await submitter.reserve_frame_image_regeneration(
            generation_fingerprint="fingerprint-frame-0001",
            request_params={"workspace_id": "workspace_1"},
        )
        await manager.wait_for_task_completion_for_test(submission.task_id)
    finally:
        await manager.stop()

    assert calls == [
        {
            "task_id": submission.task_id,
            "request_params": {
                "workspace_id": "workspace_1",
            },
            "has_progress": True,
        }
    ]


@pytest.mark.asyncio
async def test_task_manager_submitter_reports_unavailable_when_embedded_executor_is_missing():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    manager = TaskManager()
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)

    assert (await submitter.get_capabilities()).to_dict() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "frame image regeneration execution is not configured",
    }
```

Append to `tests/test_worker_execution.py`:

```python
@pytest.mark.asyncio
async def test_worker_claims_frame_image_regeneration_tasks(tmp_path):
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.artifacts import MissingArtifactStore
    from api.tasks.lease import InMemoryGenerationLease
    from api.tasks.models import TaskType
    from api.tasks.registry import GenerationRegistry
    from api.tasks.store import InMemoryTaskStore
    from api.tasks.worker import GenerationWorker

    store = InMemoryTaskStore()
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "regen-task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fingerprint-frame-0001",
        task_type=TaskType.FRAME_IMAGE_REGENERATION,
        request_params={"workspace_id": "workspace_1"},
        reuse_completed_within_seconds=0,
    )
    calls: list[dict[str, Any]] = []

    async def executor(*, task_id: str, request_params: dict[str, Any], progress_dispatcher=None):
        calls.append({"task_id": task_id, "request_params": request_params})
        return {"ok": True}

    executor_registry = TaskExecutorRegistry()
    executor_registry.register(TaskType.FRAME_IMAGE_REGENERATION, executor)
    worker = GenerationWorker(
        registry=registry,
        core=object(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
        worker_id="worker-1",
        executor_registry=executor_registry,
    )

    assert await worker.run_once() is True
    assert calls == [
        {
            "task_id": "regen-task-1",
            "request_params": {"workspace_id": "workspace_1"},
        }
    ]


@pytest.mark.asyncio
async def test_worker_mode_manager_reports_frame_regeneration_executable_after_worker_heartbeat():
    from api.tasks.manager import TaskManager
    from api.tasks.models import TaskType, utc_now
    from api.tasks.worker_registry import InMemoryWorkerRegistry, WorkerHeartbeat

    worker_registry = InMemoryWorkerRegistry()
    await worker_registry.heartbeat(
        WorkerHeartbeat(
            worker_id="worker-1",
            supported_task_types={TaskType.FRAME_IMAGE_REGENERATION},
            heartbeat_at=utc_now(),
        )
    )

    manager = TaskManager(
        execution_mode="worker",
        worker_capability_registry=worker_registry,
    )

    assert await manager.can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION) is True
```

Create `tests/test_video_task_executor.py`:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_video_generation_executor_persists_storage_identity_without_transport_url(tmp_path):
    from api.tasks.artifacts import LocalArtifactStore
    from api.tasks.executors import TaskExecutorRegistry
    from api.tasks.models import TaskType
    from api.video.executor_factory import register_video_generation_executor

    generated = tmp_path / "generated" / "final.mp4"

    class Core:
        def __init__(self) -> None:
            self.calls = []

        async def generate_video(self, **kwargs):
            self.calls.append(kwargs)
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_bytes(b"video")
            return SimpleNamespace(video_path=str(generated), duration=2.5)

    core = Core()
    registry = TaskExecutorRegistry()
    register_video_generation_executor(
        registry,
        core_provider=lambda: core,
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
    )

    result = await registry.execute(
        TaskType.VIDEO_GENERATION,
        task_id="task-video-1",
        request_params={"text": "demo", "request_id": "req_1"},
        progress_dispatcher=object(),
    )

    assert result["storage_key"] == "task-video-1/final.mp4"
    assert result["duration"] == 2.5
    assert result["file_size"] == 5
    assert "video_url" not in result
    assert core.calls[0]["api_task_id"] == "task-video-1"
    assert core.calls[0]["progress_dispatcher"] is not None
    assert "generation_fingerprint" not in core.calls[0]
```

Create `tests/test_tasks_api_presentation.py`:

```python
from types import SimpleNamespace

import pytest


def test_present_task_derives_video_url_from_current_request_without_mutating_result():
    from api.routers.tasks import present_task
    from api.tasks.models import TaskStatus, TaskType

    task = SimpleNamespace(
        task_id="task-video-1",
        task_type=TaskType.VIDEO_GENERATION,
        status=TaskStatus.COMPLETED,
        result={"storage_key": "task-video-1/final.mp4", "duration": 2.5, "file_size": 5},
    )
    request = SimpleNamespace(base_url="https://pixelle.example/")

    response = present_task(task, request=request)

    assert response.result["video_url"] == "https://pixelle.example/api/files/task-video-1/final.mp4"
    assert "video_url" not in task.result


def test_async_video_router_does_not_define_per_request_execution_closure():
    from pathlib import Path

    source = Path("api/routers/video.py").read_text(encoding="utf-8")

    assert "execute_video_generation" not in source
    assert "execute_task(" not in source
    assert "path_to_url(request" not in source
```

Append to `tests/test_artifact_store.py`:

```python
@pytest.mark.asyncio
async def test_local_artifact_store_does_not_return_transport_url(tmp_path):
    from api.tasks.artifacts import LocalArtifactStore

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    store = LocalArtifactStore(output_root=tmp_path / "output")

    result = await store.persist_video(
        task_id="task-1",
        source_path=source,
        duration=3.5,
    )

    assert result == {
        "storage_backend": "local",
        "storage_key": "task-1/source.mp4",
        "file_size": 5,
        "duration": 3.5,
    }
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py::test_worker_claims_frame_image_regeneration_tasks tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_artifact_store.py::test_local_artifact_store_does_not_return_transport_url
```

Expected: fail because executor factories, manager/worker hooks, URL presentation, and artifact store contract changes are missing.

- [ ] **Step 4: Implement executor**

Modify `api/tasks/artifacts.py` so `ArtifactStore.persist_video(...)`, `LocalArtifactStore.persist_video(...)`, and `MissingArtifactStore.persist_video(...)` no longer expose or return `video_url`:

```python
return {
    "storage_backend": "local",
    "storage_key": storage_key,
    "file_size": target.stat().st_size,
    "duration": duration,
}
```

Create `api/video/executor_factory.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from api.tasks.artifacts import ArtifactStore
from api.tasks.executors import TaskExecutorRegistry
from api.tasks.models import TaskType

REGISTRY_CONTROL_PARAM_NAMES = {"generation_fingerprint"}


def register_video_generation_executor(
    registry: TaskExecutorRegistry,
    *,
    core_provider: Callable[[], Any | Awaitable[Any]],
    artifact_store: ArtifactStore,
) -> TaskExecutorRegistry:
    async def _execute_video_generation_task(
        *,
        task_id: str,
        request_params: dict[str, Any],
        progress_dispatcher=None,
    ) -> dict[str, Any]:
        core = core_provider()
        if hasattr(core, "__await__"):
            core = await core
        params = dict(request_params)
        for name in REGISTRY_CONTROL_PARAM_NAMES:
            params.pop(name, None)
        params["api_task_id"] = task_id
        if progress_dispatcher is not None:
            params["progress_dispatcher"] = progress_dispatcher

        result = await core.generate_video(**params)
        return await artifact_store.persist_video(
            task_id=task_id,
            source_path=Path(result.video_path),
            duration=float(getattr(result, "duration", 0.0) or 0.0),
        )

    registry.register(TaskType.VIDEO_GENERATION, _execute_video_generation_task)
    return registry


__all__ = ["register_video_generation_executor"]
```

Create `api/workbench/frame_image_regeneration.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pixelle_video.models.progress import ProgressEvent, ProgressEventType
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.models.size_contract import GenerationSizeContract


async def execute_frame_image_regeneration(
    *,
    core: Any,
    task_id: str,
    request_params: Mapping[str, Any],
    progress_dispatcher: Any | None = None,
) -> dict[str, Any]:
    workspace_id = _require_param(request_params, "workspace_id")
    storyboard_id = _require_param(request_params, "storyboard_id")
    frame_id = _require_param(request_params, "frame_id")
    prompt_plan_id = _require_param(request_params, "prompt_plan_id")
    artifact_id = _require_param(request_params, "artifact_id")

    service = _require_attr(core, "storyboard_workbench_service")
    state_store = _require_attr(core, "storyboard_workbench_state_store")
    prompt_plan_repository = _require_attr(core, "prompt_plan_repository")
    media = _require_attr(core, "media")

    state_payload = await state_store.load_frame_state(workspace_id, storyboard_id, frame_id)
    if state_payload is None:
        raise RuntimeError("storyboard frame workbench state was not found")
    state = (
        state_payload
        if isinstance(state_payload, StoryboardFrameWorkbenchState)
        else StoryboardFrameWorkbenchState.from_dict(state_payload)
    )
    prompt_plan = await _load_prompt_plan(
        prompt_plan_repository,
        workspace_id=workspace_id,
        storyboard_id=storyboard_id,
        prompt_plan_id=prompt_plan_id,
    )
    size_contract = GenerationSizeContract.from_params(request_params)
    workflow = request_params.get("model") or request_params.get("media_workflow")
    negative_prompt = request_params.get("media_negative_prompt") or request_params.get("negative_prompt")
    if progress_dispatcher is not None:
        progress_dispatcher.emit(
            ProgressEvent(event_type=ProgressEventType.GENERATION, progress=0.0)
        )
    media_result = await media(
        prompt=prompt_plan.final_prompt,
        media_type="image",
        workflow=workflow,
        width=size_contract.media_width,
        height=size_contract.media_height,
        negative_prompt=negative_prompt,
    )
    source_path = _resolve_media_source_path(media_result.url)
    result = await service.record_frame_image_regeneration_result(
        workspace_id=workspace_id,
        task_id=task_id,
        state=state,
        artifact_id=artifact_id,
        source_path=source_path,
        project_id=request_params.get("project_id"),
        prompt_plan=prompt_plan,
        provider=request_params.get("provider"),
        provider_metadata={"workflow": workflow} if workflow else {},
        width=size_contract.media_width,
        height=size_contract.media_height,
    )
    await state_store.save_frame_state(
        workspace_id,
        storyboard_id,
        frame_id,
        result.workbench_state.to_dict(),
    )
    if progress_dispatcher is not None:
        progress_dispatcher.emit(
            ProgressEvent(event_type=ProgressEventType.COMPLETED, progress=1.0)
        )
    return {
        "workspace_id": workspace_id,
        "storyboard_id": storyboard_id,
        "frame_id": frame_id,
        "artifact_id": artifact_id,
        "artifact_version_id": result.artifact_version.version_id,
        "storage_key": result.artifact_version.storage_key,
    }


async def _load_prompt_plan(
    prompt_plan_repository: Any,
    *,
    workspace_id: str,
    storyboard_id: str,
    prompt_plan_id: str,
) -> PromptPlan:
    payloads = await prompt_plan_repository.load_prompt_plans_by_storyboard(
        workspace_id,
        storyboard_id,
    )
    for payload in payloads:
        plan = payload if isinstance(payload, PromptPlan) else PromptPlan.from_dict(payload)
        if plan.prompt_plan_id == prompt_plan_id:
            return plan
    raise RuntimeError("prompt plan was not found")


def _resolve_media_source_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("media generation did not return an image path")
    if raw.startswith("file://"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        parsed = urlparse(raw)
        return str(Path(url2pathname(parsed.path)))
    return raw


def _require_param(params: Mapping[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        raise RuntimeError(f"{key} is required")
    return value


def _require_attr(target: Any, name: str) -> Any:
    value = getattr(target, name, None)
    if value is None:
        raise RuntimeError(f"{name} is not configured")
    return value


__all__ = ["execute_frame_image_regeneration"]
```

Create `api/workbench/executor_factory.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from api.tasks.executors import TaskExecutorRegistry
from api.tasks.models import TaskType
from api.workbench.frame_image_regeneration import execute_frame_image_regeneration


def register_storyboard_workbench_executors(
    registry: TaskExecutorRegistry,
    *,
    core_provider: Callable[[], Any | Awaitable[Any]],
) -> TaskExecutorRegistry:
    async def _execute_frame_image_regeneration_task(
        *,
        task_id: str,
        request_params: dict[str, Any],
        progress_dispatcher=None,
    ) -> dict[str, Any]:
        core = core_provider()
        if hasattr(core, "__await__"):
            core = await core
        return await execute_frame_image_regeneration(
            core=core,
            task_id=task_id,
            request_params=request_params,
            progress_dispatcher=progress_dispatcher,
        )

    registry.register(
        TaskType.FRAME_IMAGE_REGENERATION,
        _execute_frame_image_regeneration_task,
    )
    return registry


__all__ = ["register_storyboard_workbench_executors"]
```

- [ ] **Step 5: Hook embedded TaskManager execution**

Reuse the `executor_registry`, async `can_execute_task_type(...)`, and `wait_for_task_completion_for_test(...)` fields added in Task 1. Task 3 adds embedded auto-execution for every newly created task whose task type has a registered executor, including `VIDEO_GENERATION`:

At the end of `reserve_or_reuse_generation_task(...)`, after outcome is returned from registry:

```python
outcome = await self.registry.reserve_or_reuse(...)
if (
    outcome.created
    and self.execution_mode == "embedded"
    and self.executor_registry.can_execute(task_type).can_execute
):
    async def _run_registered_executor(*, progress_dispatcher=None):
        return await self.executor_registry.execute(
            task_type,
            task_id=outcome.task.task_id,
            request_params=dict(request_params),
            progress_dispatcher=progress_dispatcher,
        )

    await self.execute_task(
        task_id=outcome.task.task_id,
        coro_func=_run_registered_executor,
    )
return outcome
```

The test helper `wait_for_task_completion_for_test(...)` already exists from Task 1; do not duplicate it.

Modify `api/routers/video.py` async route:

- Keep request parsing, resource resolution, generation params, and fingerprint building in the router.
- Remove the per-request `execute_video_generation(...)` closure.
- Remove `pixelle_video` usage from `generate_video_async(...)`; video executor factory owns lazy core access.
- Do not call `task_manager.execute_task(...)` from the router. `TaskManager.reserve_or_reuse_generation_task(...)` starts embedded execution when the `VIDEO_GENERATION` executor is registered.
- Do not call `path_to_url(...)` in the async route. The sync route can keep response-specific URL derivation because it is not persisted task result.

The async route body after reservation should only map reserve/reuse state:

```python
outcome = await task_manager.reserve_or_reuse_generation_task(
    task_type=TaskType.VIDEO_GENERATION,
    generation_fingerprint=generation_fingerprint,
    request_params=request_params,
)
task = outcome.task
if not outcome.created:
    logger.info(f"Reusing async video generation task: {task.task_id}")
    message = (
        "Task already completed"
        if outcome.reused_reason == "recent_completed"
        else "Task already running"
    )
    return VideoGenerateAsyncResponse(task_id=task.task_id, message=message)

return VideoGenerateAsyncResponse(task_id=task.task_id)
```

Modify `api/schemas/tasks.py` to add presentation DTOs:

```python
from typing import Any

from pydantic import BaseModel

from api.tasks.models import TaskProgress, TaskStatus, TaskType


class TaskResponse(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus
    progress: TaskProgress | None = None
    result: Any = None
    error: str | None = None
```

Modify `api/routers/tasks.py`:

```python
from fastapi import Request

from api.schemas.tasks import TaskListResponse, TaskResponse
from api.tasks.models import Task, TaskType
```

Add:

```python
def task_storage_key_to_url(request: Request, storage_key: str) -> str:
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/files/{storage_key.lstrip('/')}"


def present_task(task: Task, *, request: Request) -> TaskResponse:
    result = task.result
    if (
        task.task_type is TaskType.VIDEO_GENERATION
        and isinstance(result, dict)
        and result.get("storage_key")
        and "video_url" not in result
    ):
        result = {
            **result,
            "video_url": task_storage_key_to_url(request, str(result["storage_key"])),
        }
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
        progress=task.progress,
        result=result,
        error=task.error,
    )
```

Change `GET /api/tasks/{task_id}` and list endpoints to return `TaskResponse` / `TaskListResponse` built from `present_task(...)`. Do not mutate `task.result`.

- [ ] **Step 6: Wire executor factory**

Build one runtime in `api/app.py`, then register both executor groups on its registry:

```python
from api.tasks.factory import build_api_task_runtime
from api.video.executor_factory import register_video_generation_executor
from api.workbench.executor_factory import register_storyboard_workbench_executors

runtime = build_api_task_runtime(api_config)
manager = runtime.task_manager
register_video_generation_executor(
    runtime.executor_registry,
    core_provider=get_pixelle_video,
    artifact_store=manager.registry.artifact_store,
)
register_storyboard_workbench_executors(
    runtime.executor_registry,
    core_provider=get_pixelle_video,
)
```

Pass the same registries into `configure_platform_dependencies(...)`:

```python
platform_dependencies = configure_platform_dependencies(
    app,
    api_config,
    task_manager=manager,
    task_executor_registry=runtime.executor_registry,
    worker_capability_registry=runtime.worker_registry,
    worker_registry=runtime.worker_registry,
)
```

Modify `web/state/session.py` local dependency creation to call both `register_video_generation_executor(...)` and `register_storyboard_workbench_executors(...)` on `runtime.executor_registry` before constructing platform dependencies. The provider stays inside executor factory closures and must not be stored on `PlatformDependencies`.

- [ ] **Step 7: Hook worker mode**

Modify `api/tasks/worker.py` `GenerationWorker` constructor:

```python
executor_registry: TaskExecutorRegistry | None = None,
worker_registry: WorkerRegistry | None = None,
```

Set:

```python
self.executor_registry = executor_registry or TaskExecutorRegistry()
self.worker_registry = worker_registry
```

Do not register default executors inside `run_once()`. Worker bootstrap owns executor registration, so capability and claim type calculation use the same registry.

Change claim types:

```python
task_types = self.executor_registry.supported_task_types()
claim = await self.registry.claim_next_pending(
    worker_id=self.worker_id,
    task_types=task_types,
)
```

If `task_types` is empty, `run_once()` must return `False` without claiming. Worker mode counts as executable only when heartbeat-backed `WorkerRegistry` says a recent worker supports that task type.

At the start of `run_once()` and in a separate idle loop used by `run_worker_forever(...)`, publish worker capability:

```python
if self.worker_registry is not None:
    await self.worker_registry.heartbeat(
        WorkerHeartbeat(
            worker_id=self.worker_id,
            supported_task_types=self.executor_registry.supported_task_types(),
            heartbeat_at=utc_now(),
        )
    )
```

`run_once()` must execute every claimed task through the registry:

```python
result = await self.executor_registry.execute(
    task.task_type,
    task_id=task.task_id,
    request_params=task.request_params or {},
    progress_dispatcher=ProgressDispatcher([progress_sink]),
)
```

Remove worker-local calls to `self.core.generate_video(...)` from `run_once()`. Video generation is now just another registered executor.

Add source regression to `tests/test_worker_execution.py`:

```python
def test_generation_worker_executes_only_through_task_executor_registry():
    from pathlib import Path

    source = Path("api/tasks/worker.py").read_text(encoding="utf-8")

    assert "core.generate_video" not in source
    assert "TaskType.VIDEO_GENERATION}" not in source
    assert ".execute(" in source
    assert "WorkerHeartbeat" in source
```

Modify `run_worker_forever(...)`:

```python
runtime = build_task_runtime(config)
core = await build_worker_core(config=config)
register_video_generation_executor(
    runtime.executor_registry,
    core_provider=lambda: core,
    artifact_store=runtime.task_manager.registry.artifact_store,
)
register_storyboard_workbench_executors(runtime.executor_registry, core_provider=lambda: core)
worker = GenerationWorker(
    registry=runtime.task_manager.registry,
    core=core,
    artifact_store=runtime.task_manager.registry.artifact_store,
    output_root=config.artifact_base_path,
    heartbeat_interval_seconds=config.generation_heartbeat_seconds,
    executor_registry=runtime.executor_registry,
    worker_registry=runtime.worker_registry,
)
```

- [ ] **Step 8: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit and push**

```powershell
git add -- api/video/executor_factory.py api/workbench/frame_image_regeneration.py api/workbench/executor_factory.py api/tasks/artifacts.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py api/routers/video.py api/routers/tasks.py api/schemas/tasks.py api/app.py web/state/session.py tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py
git commit -m "feat: 统一异步生成任务执行注册表"
git push origin $(git branch --show-current)
```

---

## Task 4: Add Frontend Capability Helper And Client Boundary

**Files:**
- Modify: `web/utils/storyboard_workbench_api.py`
- Create: `web/workbench/__init__.py`
- Create: `web/workbench/client.py`
- Create: `web/workbench/display.py`
- Create: `web/workbench/http_client.py`
- Create: `web/workbench/inprocess_protocols.py`
- Create: `web/workbench/inprocess_client.py`
- Create: `web/state/workbench_client.py`
- Test: `tests/test_storyboard_workbench_frontend_api.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Add failing frontend helper tests**

Append to `tests/test_storyboard_workbench_frontend_api.py`:

```python
def test_get_storyboard_workbench_capabilities_uses_backend_endpoint(monkeypatch):
    from web.utils import storyboard_workbench_api

    captured: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "message": "Success",
                "can_regenerate_frame_image": True,
                "regenerate_unavailable_reason": None,
            }

    def fake_get(endpoint, timeout):
        captured["endpoint"] = endpoint
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(storyboard_workbench_api.httpx, "get", fake_get)

    result = storyboard_workbench_api.get_storyboard_workbench_capabilities(
        api_base_url="http://localhost:8000/api/",
    )

    assert captured == {
        "endpoint": "http://localhost:8000/api/storyboards/workbench/capabilities",
        "timeout": 30.0,
    }
    assert result["can_regenerate_frame_image"] is True
```

- [ ] **Step 2: Add failing client tests**

Create `tests/test_storyboard_workbench_client.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


def test_http_workbench_client_reads_capabilities_from_backend():
    from web.workbench.http_client import HttpStoryboardWorkbenchClient

    calls: list[dict[str, Any]] = []
    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api",
        capability_loader=lambda **kwargs: calls.append(kwargs)
        or {
            "success": True,
            "can_regenerate_frame_image": False,
            "regenerate_unavailable_reason": "task submitter is not configured",
        },
    )

    assert client.get_capabilities() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "task submitter is not configured",
    }
    assert calls == [{"api_base_url": "http://localhost:8001/api"}]


def test_http_workbench_client_normalizes_candidate_display_urls():
    from web.workbench.http_client import HttpStoryboardWorkbenchClient

    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api/",
        capability_loader=lambda **_kwargs: {
            "can_regenerate_frame_image": True,
            "regenerate_unavailable_reason": None,
        },
        candidate_loader=lambda **_kwargs: {
            "workspace_id": "workspace_1",
            "storyboard_id": "storyboard_1",
            "frame_id": "frame_1",
            "artifact_id": "artifact_1",
            "candidates": [
                {
                    "artifact_id": "artifact_1",
                    "version_id": "version_1",
                    "frame_id": "frame_1",
                    "prompt_plan_id": "prompt_plan_1",
                    "storage_key": "artifacts/workspace_1/file.png",
                    "status": "ready",
                    "url": "/api/files/artifacts/workspace_1/file.png",
                }
            ],
        },
    )

    response = client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    candidate = response["candidates"][0]
    assert candidate["image_display"] == {
        "kind": "url",
        "url": "http://localhost:8001/api/files/artifacts/workspace_1/file.png",
    }
    assert "url" not in candidate


def test_workbench_client_factory_does_not_cache_inprocess_client_without_core(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=None)

    assert client is None
    assert "storyboard_workbench_client" not in session_state


def test_workbench_client_factory_defaults_to_inprocess_without_reading_api_base_url(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    monkeypatch.setenv("PIXELLE_API_BASE_URL", "http://localhost:8001/api")
    session_state = {}
    core = object()

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=core)

    assert client is not None
    assert session_state["storyboard_workbench_client_cache_key"] == (
        "inprocess",
        id(core),
    )


def test_workbench_client_factory_rebuilds_when_core_identity_changes(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    first = resolve_storyboard_workbench_client(session_state, pixelle_video=object())
    second = resolve_storyboard_workbench_client(session_state, pixelle_video=object())

    assert first is not None
    assert second is not None
    assert first is not second


def test_inprocess_client_lists_candidates_with_local_bytes_display(tmp_path):
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    image_path = tmp_path / "0123456789abcdef0123456789abcdef.png"
    image_path.write_bytes(b"png-bytes")

    class Candidate:
        def to_dict(self):
            return {
                "artifact_id": "artifact_1",
                "version_id": "version_1",
                "frame_id": "frame_1",
                "prompt_plan_id": "prompt_plan_1",
                "storage_key": "artifacts/workspace_1/0123456789abcdef0123456789abcdef.png",
                "status": "ready",
                "url": "/api/files/artifacts/workspace_1/file.png",
            }

    class Service:
        async def list_image_candidates(self, *, workspace_id, artifact_id):
            return (Candidate(),)

    class ObjectStore:
        async def get_local_file_uri(self, storage_key):
            return image_path.as_uri()

    class StateStore:
        async def load_frame_state(self, workspace_id, storyboard_id, frame_id):
            return {
                "frame_id": frame_id,
                "prompt_plan_id": "prompt_plan_1",
                "selected_image_artifact_id": "artifact_1",
                "selected_image_version_id": "version_1",
                "candidate_image_version_ids": ["version_1"],
                "lock_policy": "unlocked",
                "stale_flags": [],
            }

    core = type(
        "Core",
        (),
        {
            "storyboard_workbench_service": Service(),
            "artifact_object_store": ObjectStore(),
            "storyboard_workbench_state_store": StateStore(),
        },
    )()

    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)
    response = client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    candidate = response["candidates"][0]
    assert candidate["image_display"] == {
        "kind": "bytes",
        "data": b"png-bytes",
        "mime_type": "image/png",
    }
    assert "url" not in candidate


def test_inprocess_client_uses_task_submitter_for_regenerate():
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    class Service:
        def build_frame_image_regeneration_task_request(self, **_kwargs):
            return type(
                "TaskRequest",
                (),
                {
                    "generation_fingerprint": "fingerprint_1",
                    "request_params": {"workspace_id": "workspace_1"},
                },
            )()

    class StateStore:
        async def load_frame_state(self, *_args, **_kwargs):
            return {
                "frame_id": "frame_1",
                "selected_image_artifact_id": "artifact_1",
                "selected_image_version_id": "version_1",
                "candidate_image_version_ids": ["version_1"],
                "lock_policy": "unlocked",
                "stale_flags": [],
                "prompt_plan_id": "prompt_plan_1",
            }

    class Submitter:
        async def get_capabilities(self):
            return type(
                "Capabilities",
                (),
                {
                    "to_dict": lambda _self: {
                        "can_regenerate_frame_image": True,
                        "regenerate_unavailable_reason": None,
                    }
                },
            )()

        async def reserve_frame_image_regeneration(self, **kwargs):
            return type(
                "Submission",
                (),
                {
                    "to_dict": lambda _self: {
                        "task_id": "task_1",
                        "task_type": "frame_image_regeneration",
                        "created": True,
                        "reused_reason": None,
                    }
                },
            )()

    core = type(
        "Core",
        (),
        {
            "storyboard_workbench_service": Service(),
            "storyboard_workbench_state_store": StateStore(),
            "storyboard_workbench_task_submitter": Submitter(),
        },
    )()

    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)

    assert client.get_capabilities()["can_regenerate_frame_image"] is True
    assert client.regenerate_frame_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )["task_id"] == "task_1"


def test_storyboard_workbench_ui_does_not_import_transport_or_display_helpers():
    ui_files = [
        Path("web/components/storyboard_workbench_panel.py"),
        Path("web/components/storyboard_workbench_stale.py"),
        Path("web/components/storyboard_preview.py"),
        Path("web/pages/3_🧭_Storyboard_Workbench.py"),
    ]
    forbidden = (
        "web.utils.storyboard_workbench_api",
        "web.utils.stale_api",
        "web.utils.artifact_display_urls",
        "httpx",
        "localhost:8001",
    )

    for path in ui_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not depend on {token}"
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_frontend_api.py::test_get_storyboard_workbench_capabilities_uses_backend_endpoint tests/test_storyboard_workbench_client.py
```

Expected: fail because helper/client modules do not exist.

- [ ] **Step 4: Implement frontend helper**

Modify `web/utils/storyboard_workbench_api.py`:

```python
def build_storyboard_workbench_capabilities_endpoint(*, api_base_url: str) -> str:
    return f"{api_base_url.rstrip('/')}/storyboards/workbench/capabilities"


def get_storyboard_workbench_capabilities(
    *,
    api_base_url: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    response = httpx.get(
        build_storyboard_workbench_capabilities_endpoint(api_base_url=api_base_url),
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("capability response must be a JSON object")
    return {
        "can_regenerate_frame_image": bool(data.get("can_regenerate_frame_image")),
        "regenerate_unavailable_reason": data.get("regenerate_unavailable_reason"),
    }
```

Add new names to `__all__`.

- [ ] **Step 5: Implement client modules**

Use the contracts from the spec. Important implementation constraints:

- `HttpStoryboardWorkbenchClient.get_capabilities()` must call `capability_loader(api_base_url=self.api_base_url)`.
- `HttpStoryboardWorkbenchClient.list_image_candidates()` must strip `url` and set `image_display`.
- `InProcessStoryboardWorkbenchClient.get_capabilities()` must use the existing Streamlit async runtime bridge to call `await pixelle_video.storyboard_workbench_task_submitter.get_capabilities()` when a submitter exists, and report unavailable when it does not.
- `InProcessStoryboardWorkbenchClient.regenerate_frame_image()` must call `submitter.reserve_frame_image_regeneration(...)`, not any task manager.
- `web/state/workbench_client.py` must not cache when `pixelle_video is None`.

- [ ] **Step 6: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit and push**

```powershell
git add -- web/utils/storyboard_workbench_api.py web/workbench/__init__.py web/workbench/client.py web/workbench/display.py web/workbench/http_client.py web/workbench/inprocess_protocols.py web/workbench/inprocess_client.py web/state/workbench_client.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 增加分镜工作台客户端边界"
git push origin $(git branch --show-current)
```

---

## Task 5: Rewire Workbench UI To Injected Client

**Files:**
- Modify: `web/components/storyboard_workbench_panel.py`
- Modify: `web/components/storyboard_workbench_stale.py`
- Modify: `web/components/storyboard_preview.py`
- Modify: `web/pages/3_🧭_Storyboard_Workbench.py`
- Test: `tests/test_storyboard_workbench_panel_ui.py`
- Test: `tests/test_storyboard_workbench_stale_ui.py`
- Test: `tests/test_storyboard_workbench_page.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Update panel UI tests to fake client**

Replace `candidate_loader`, `candidate_selector`, and `frame_regenerator` based tests in `tests/test_storyboard_workbench_panel_ui.py` with a fake client:

```python
class _FakeWorkbenchClient:
    def __init__(
        self,
        *,
        candidates: list[dict[str, Any]] | None = None,
        can_regenerate: bool = True,
    ) -> None:
        self.candidates = candidates if candidates is not None else _candidate_response()["candidates"]
        self.can_regenerate = can_regenerate
        self.calls: list[dict[str, Any]] = []

    def get_capabilities(self):
        return {
            "can_regenerate_frame_image": self.can_regenerate,
            "regenerate_unavailable_reason": None if self.can_regenerate else "task submitter is not configured",
        }

    def list_image_candidates(self, **kwargs):
        self.calls.append({"method": "list", **kwargs})
        return {**_candidate_response(), "candidates": self.candidates}

    def select_image_candidate(self, **kwargs):
        self.calls.append({"method": "select", **kwargs})
        return {
            "success": True,
            "state": {
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "selected_image_artifact_id": "artifact_frame_0001_image",
                "selected_image_version_id": kwargs["version_id"],
                "candidate_image_version_ids": ["artifact_version_001", kwargs["version_id"]],
                "lock_policy": "unlocked",
                "stale_flags": ["video_segment"],
            },
        }

    def regenerate_frame_image(self, **kwargs):
        self.calls.append({"method": "regenerate", **kwargs})
        return {
            "success": True,
            "task_id": "regen-task-1",
            "task_type": "frame_image_regeneration",
            "created": True,
            "generation_fingerprint": "fingerprint-frame-0001",
        }
```

Update `_candidate_response()` candidates to include:

```python
"image_display": {"kind": "url", "url": "..."}
```

Add a bytes test:

```python
def test_storyboard_workbench_panel_renders_bytes_display_without_api_base_url():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    fake_ui = _WorkbenchFakeUI()
    client = _FakeWorkbenchClient(
        candidates=[
            {
                "artifact_id": "artifact_frame_0001_image",
                "version_id": "artifact_version_001",
                "frame_id": "frame_0001",
                "status": "ready",
                "image_display": {
                    "kind": "bytes",
                    "data": b"fake-image",
                    "mime_type": "image/png",
                },
            }
        ],
        can_regenerate=False,
    )

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame_id="frame_0001",
        artifact_id="artifact_frame_0001_image",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert fake_ui.images[0]["image"] == b"fake-image"
    assert fake_ui.buttons[-1]["disabled"] is True
```

- [ ] **Step 2: Update stale/page tests**

Add to `tests/test_storyboard_workbench_stale_ui.py`:

```python
def test_prompt_plan_stale_panel_uses_workbench_client_without_api_base_url():
    from web.components.storyboard_workbench_stale import render_prompt_plan_stale_panel

    calls = []

    class FakeClient:
        def get_prompt_plan_stale_summary(self, **kwargs):
            calls.append(kwargs)
            return {
                "success": True,
                "stale_summary": {
                    "workspace_id": "workspace_1",
                    "project_id": "project_1",
                    "target_type": "prompt_plan",
                    "target_id": "prompt_plan_1",
                    "is_stale": False,
                    "primary_reasons": [],
                    "upstream_refs": [],
                    "stale_marks": [],
                },
            }

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=_FakeUI(),
        translate=lambda key, **_kwargs: key,
        workbench_client=FakeClient(),
        panel_renderer=lambda **_kwargs: None,
        workspace_id="workspace_1",
        project_id="project_1",
    )

    assert calls == [
        {
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "prompt_plan_id": "prompt_plan_1",
        }
    ]
```

Add to `tests/test_storyboard_workbench_page.py`:

```python
def test_storyboard_workbench_page_passes_client_to_preview(monkeypatch):
    page = _load_workbench_page()
    fake_ui = _FakeUI()
    fake_ui.session_state["storyboard_preview_snapshot"] = _planning_snapshot()
    client = object()
    calls = []

    monkeypatch.setattr(page, "resolve_workbench_client_mode", lambda _session_state: "http")
    monkeypatch.setattr(page, "resolve_storyboard_workbench_client", lambda _session_state, pixelle_video=None: client)

    def preview_renderer(snapshot, *, workbench_client=None):
        calls.append(workbench_client)
        return []

    page.render_storyboard_workbench_page(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        preview_renderer=preview_renderer,
    )

    assert calls == [client]
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_client.py::test_storyboard_workbench_ui_does_not_import_transport_or_display_helpers
```

Expected: fail because UI still accepts direct HTTP helpers.

- [ ] **Step 4: Rewire UI**

In `web/components/storyboard_workbench_panel.py`:

- Remove imports from `web.utils.storyboard_workbench_api`.
- Remove direct use of `artifact_url_for_streamlit`.
- Add `workbench_client` parameter.
- Fail closed when client is missing.
- Render only `candidate["image_display"]`.
- Disable regenerate when `client.get_capabilities()["can_regenerate_frame_image"]` is false.

In `web/components/storyboard_workbench_stale.py`:

- Remove direct import of `get_stale_target_summary`.
- Add `workbench_client` parameter.
- Call `client.get_prompt_plan_stale_summary(...)`.

In `web/components/storyboard_preview.py`:

- Add `workbench_client` parameter.
- Pass it to stale and workbench renderers.
- Stop passing `api_base_url` into Workbench children.

In `web/pages/3_🧭_Storyboard_Workbench.py`:

- Import `resolve_workbench_client_mode` and `resolve_storyboard_workbench_client`.
- Resolve mode first.
- If mode is `inprocess`, call `get_pixelle_video()` before resolving client.
- Pass `workbench_client` into `preview_renderer(...)`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add -- web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_client.py
git commit -m "refactor: 让分镜工作台界面只依赖客户端合同"
git push origin $(git branch --show-current)
```

---

## Task 6: Final Regression And Verification

**Files:**
- Modify tests only unless regressions fail.

- [ ] **Step 1: Run focused boundary test set**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_app_platform_dependencies.py tests/test_worker_execution.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py tests/test_postgres_task_store_schema.py
```

Expected: pass.

- [ ] **Step 2: Run lint and diff checks**

Run:

```powershell
ruff check api/workbench api/video/executor_factory.py api/platform_dependencies.py api/dependencies.py api/app.py api/routers/storyboard_workbench.py api/routers/video.py api/routers/tasks.py api/schemas/storyboard_workbench.py api/schemas/tasks.py api/tasks/artifacts.py api/tasks/executors.py api/tasks/worker_registry.py api/tasks/postgres.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py web/state/session.py web/workbench web/state/workbench_client.py web/utils/storyboard_workbench_api.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py tests/test_worker_execution.py tests/test_postgres_task_store_schema.py
git diff --check
```

Expected: pass.

- [ ] **Step 3: Commit any regression-only fixes and push**

If Step 1 or Step 2 required fixes:

```powershell
git add -- <fixed-files>
git commit -m "test: 固化分镜工作台客户端边界回归"
git push origin $(git branch --show-current)
```

If no fixes were needed, do not create an empty commit.

---

## Final Verification

- [ ] Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_app_platform_dependencies.py tests/test_worker_execution.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py tests/test_postgres_task_store_schema.py tests/test_style_config_storyboard_planning_ui.py
```

Expected: pass.

- [ ] Run:

```powershell
ruff check api/workbench api/video/executor_factory.py api/platform_dependencies.py api/dependencies.py api/app.py api/routers/storyboard_workbench.py api/routers/video.py api/routers/tasks.py api/schemas/storyboard_workbench.py api/schemas/tasks.py api/tasks/artifacts.py api/tasks/executors.py api/tasks/worker_registry.py api/tasks/postgres.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py web/state/session.py web/workbench web/state/workbench_client.py web/utils/storyboard_workbench_api.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_video_task_executor.py tests/test_tasks_api_presentation.py tests/test_async_video_registry_integration.py tests/test_artifact_store.py tests/test_worker_execution.py tests/test_postgres_task_store_schema.py
git diff --check
```

Expected: pass.

- [ ] Confirm branch status:

```powershell
git status --short --branch
```

Expected: no uncommitted changes from this plan. Unrelated pre-existing dirty files must remain unstaged.

---

## Self-Review

- Spec coverage: covers client contract, display contract, HTTP mode, in-process mode, factory lifecycle, submitter injection, capability endpoint, unified async video/frame execution, heartbeat-backed worker capability, and task result presentation.
- Placeholder scan: no unfinished placeholder content and no fake local disablement as final state.
- Type consistency: stable names are `TaskRuntime`, `TaskExecutorRegistry`, `WorkerRegistry`, `WorkerHeartbeat`, `StoryboardWorkbenchTaskSubmitter`, `TaskManagerStoryboardWorkbenchTaskSubmitter`, `get_capabilities`, `list_image_candidates`, `select_image_candidate`, `regenerate_frame_image`, and `get_prompt_plan_stale_summary`.
- Scope: Storyboard Workbench only. AssetBible / Stage2 HTTP clients are left untouched.
- Atomicity check: no task leaves Workbench UI switched to a local skeleton that cannot satisfy existing list/select/stale/regenerate submission flows.
- Debt check: regenerate availability is sourced from real submitter/executor/worker-heartbeat wiring, async video is not left on legacy closure execution, and task results do not persist transport URLs.
