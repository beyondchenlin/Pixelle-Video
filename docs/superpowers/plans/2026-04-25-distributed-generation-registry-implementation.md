# Distributed Generation Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PostgreSQL + Redis backed video-generation idempotency, persistent task state, worker execution, and shared artifact handling.

**Architecture:** Keep the existing in-memory path as the local development backend, but introduce explicit task-store, lease, registry, artifact-store, and worker boundaries. PostgreSQL becomes the task truth source, Redis provides submit locks and execution leases with fencing tokens, and production async generation creates tasks in the API while workers claim and execute them.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest, SQLAlchemy asyncio, asyncpg, Alembic, redis.asyncio, Docker Compose, optional S3-compatible artifact storage.

---

## File Structure

- Modify `api/tasks/models.py`
  - Add `generation_fingerprint`, `owner_id`, `lease_token`, `artifact_status`, and `updated_at` fields to `Task`.
  - Add `ArtifactStatus`, `ReserveOutcome`, `ExecutionLease`, and `ClaimedTask` models.
- Create `api/tasks/store.py`
  - Defines `TaskStore` protocol and `InMemoryTaskStore`.
  - Owns create/get/list/find reusable/update status/update progress/claim pending behavior.
- Create `api/tasks/lease.py`
  - Defines `GenerationLease` protocol, `InMemoryGenerationLease`, and `RedisGenerationLease`.
  - Uses owner/token compare-and-delete and compare-and-expire semantics.
- Create `api/tasks/artifacts.py`
  - Defines `ArtifactStore`, `LocalArtifactStore`, and artifact result helpers.
- Create `api/tasks/registry.py`
  - Implements `GenerationRegistry.reserve_or_reuse()`, `claim_next_pending()`, heartbeat, completion, failure, and cancellation orchestration.
- Create `api/tasks/postgres.py`
  - Implements SQLAlchemy async `generation_tasks` table mapping and `PostgresTaskStore`.
- Create `api/tasks/migrate.py`
  - Runs Alembic migrations through a stable CLI command used by Docker Compose.
- Create `api/tasks/worker.py`
  - Runs the production worker loop, claims tasks, invokes `PixelleVideoCore`, persists artifacts, and heartbeats Redis leases.
- Modify `api/tasks/manager.py`
  - Convert `TaskManager` into a facade over the registry and store while preserving current methods used by routers.
- Modify `api/tasks/__init__.py`
  - Export new models and initialization helpers.
- Modify `api/config.py`
  - Add environment-backed task, Redis, PostgreSQL, execution, and artifact settings.
- Modify `api/app.py`
  - Initialize backend dependencies at startup and fail fast in production mode when required services are unavailable.
- Modify `api/routers/video.py`
  - Route async generation through `TaskManager.reserve_or_reuse_generation_task()` and use embedded execution only when configured.
- Modify `api/routers/tasks.py`
  - Read list/get/cancel from the store-backed facade.
- Modify `api/routers/files.py`
  - Keep local artifact serving compatible with `LocalArtifactStore`.
- Modify `pyproject.toml`
  - Add `redis`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, and optional `boto3`.
- Modify `docker-compose.yml`
  - Add postgres, redis, migrate, and worker services with health checks and shared output volume for single-host local compose.
- Create tests:
  - `tests/test_task_store_memory.py`
  - `tests/test_generation_registry.py`
  - `tests/test_artifact_store.py`
  - `tests/test_redis_generation_lease.py`
  - `tests/test_task_manager_registry_facade.py`
  - `tests/test_async_video_registry_integration.py`
  - `tests/test_worker_execution.py`
  - `tests/test_distributed_config.py`

## Task 1: Task Models and In-Memory Store

**Files:**
- Modify: `api/tasks/models.py`
- Create: `api/tasks/store.py`
- Create: `tests/test_task_store_memory.py`

- [ ] **Step 1: Write failing tests for task-store behavior**

Create `tests/test_task_store_memory.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from api.tasks.models import ArtifactStatus, Task, TaskProgress, TaskStatus, TaskType
from api.tasks.store import InMemoryTaskStore, LostTaskLeaseError


@pytest.mark.asyncio
async def test_memory_store_reuses_active_task_by_fingerprint():
    store = InMemoryTaskStore()
    task = await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
            request_params={"text": "same"},
        )
    )

    reusable = await store.find_reusable_by_fingerprint(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        active_statuses={TaskStatus.PENDING, TaskStatus.RUNNING},
        completed_after=None,
    )

    assert reusable == task


@pytest.mark.asyncio
async def test_memory_store_reuses_recent_completed_task():
    store = InMemoryTaskStore()
    completed = await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
            status=TaskStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            artifact_status=ArtifactStatus.PERSISTED,
            result={"storage_key": "task-1/final.mp4"},
        )
    )

    reusable = await store.find_reusable_by_fingerprint(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        active_statuses={TaskStatus.PENDING, TaskStatus.RUNNING},
        completed_after=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    assert reusable == completed


@pytest.mark.asyncio
async def test_memory_store_rejects_stale_owner_status_update():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.RUNNING,
            owner_id="worker-current",
            lease_token="token-current",
        )
    )

    with pytest.raises(LostTaskLeaseError):
        await store.update_status(
            task_id="task-1",
            status=TaskStatus.COMPLETED,
            expected_owner_id="worker-old",
            expected_lease_token="token-old",
            result={"video_url": "/api/files/task-1/final.mp4"},
        )

    task = await store.get_task("task-1")
    assert task.status == TaskStatus.RUNNING
    assert task.result is None


@pytest.mark.asyncio
async def test_memory_store_claims_pending_task_once():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            generation_fingerprint="fp-1",
        )
    )

    first = await store.claim_next_pending(
        owner_id="worker-1",
        lease_token="token-1",
        task_types={TaskType.VIDEO_GENERATION},
    )
    second = await store.claim_next_pending(
        owner_id="worker-2",
        lease_token="token-2",
        task_types={TaskType.VIDEO_GENERATION},
    )

    assert first is not None
    assert first.task_id == "task-1"
    assert second is None
    claimed = await store.get_task("task-1")
    assert claimed.status == TaskStatus.RUNNING
    assert claimed.owner_id == "worker-1"
    assert claimed.lease_token == "token-1"


@pytest.mark.asyncio
async def test_memory_store_progress_update_requires_current_lease():
    store = InMemoryTaskStore()
    await store.create_task(
        Task(
            task_id="task-1",
            task_type=TaskType.VIDEO_GENERATION,
            status=TaskStatus.RUNNING,
            owner_id="worker-current",
            lease_token="token-current",
        )
    )

    with pytest.raises(LostTaskLeaseError):
        await store.update_progress(
            task_id="task-1",
            progress=TaskProgress(current=1, total=5, percentage=20.0, message="bad"),
            expected_owner_id="worker-old",
            expected_lease_token="token-old",
        )

    await store.update_progress(
        task_id="task-1",
        progress=TaskProgress(current=2, total=5, percentage=40.0, message="ok"),
        expected_owner_id="worker-current",
        expected_lease_token="token-current",
    )

    task = await store.get_task("task-1")
    assert task.progress.message == "ok"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_task_store_memory.py -q
```

Expected: FAIL because `api.tasks.store` and new model fields do not exist.

- [ ] **Step 3: Add models**

Update `api/tasks/models.py` with:

```python
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactStatus(str, Enum):
    NONE = "none"
    PERSISTED = "persisted"
    MISSING = "missing"


class Task(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    progress: Optional[TaskProgress] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)
    request_params: Optional[dict] = None
    generation_fingerprint: Optional[str] = None
    owner_id: Optional[str] = None
    lease_token: Optional[str] = None
    artifact_status: ArtifactStatus = ArtifactStatus.NONE
```

Add:

```python
class ReserveOutcome(BaseModel):
    task: Task
    created: bool
    reused_reason: Literal["active", "recent_completed"] | None = None


class ExecutionLease(BaseModel):
    task_id: str
    owner_id: str
    lease_token: str
    lease_expires_at: datetime


class ClaimedTask(BaseModel):
    task: Task
    lease: ExecutionLease
```

- [ ] **Step 4: Implement in-memory store**

Create `api/tasks/store.py` with an async protocol and implementation:

```python
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Protocol

from api.tasks.models import Task, TaskProgress, TaskStatus, TaskType, utc_now


class TaskStoreError(RuntimeError):
    pass


class TaskAlreadyExistsError(TaskStoreError):
    pass


class LostTaskLeaseError(TaskStoreError):
    pass


class TaskStore(Protocol):
    async def create_task(self, task: Task) -> Task: ...
    async def get_task(self, task_id: str) -> Task | None: ...
    async def find_reusable_by_fingerprint(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        active_statuses: set[TaskStatus],
        completed_after: datetime | None,
    ) -> Task | None: ...
    async def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        owner_id: str | None = None,
        lease_token: str | None = None,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
        artifact_status=None,
    ) -> None: ...
    async def update_progress(
        self,
        *,
        task_id: str,
        progress: TaskProgress,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None: ...
    async def claim_next_pending(
        self,
        *,
        owner_id: str,
        lease_token: str,
        task_types: set[TaskType] | None = None,
    ) -> Task | None: ...
    async def list_tasks(self, status: TaskStatus | None, limit: int) -> list[Task]: ...
    async def cancel_task(self, task_id: str) -> bool: ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task: Task) -> Task:
        async with self._lock:
            if task.task_id in self._tasks:
                raise TaskAlreadyExistsError(task.task_id)
            now = utc_now()
            task.created_at = task.created_at or now
            task.updated_at = now
            self._tasks[task.task_id] = task.model_copy(deep=True)
            return self._tasks[task.task_id].model_copy(deep=True)
```

Complete the methods so they satisfy the tests:

- return deep copies from read methods;
- sort `list_tasks()` by `created_at DESC`;
- check active tasks before recent completed tasks in `find_reusable_by_fingerprint()`;
- call `_assert_expected_lease()` before status/progress writes when expected owner/token is provided;
- update `updated_at` on every mutation;
- in `claim_next_pending()`, pick the oldest pending task whose type matches, set `RUNNING`, owner/token, and `started_at`.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
pytest tests/test_task_store_memory.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add api/tasks/models.py api/tasks/store.py tests/test_task_store_memory.py
git commit -m "feat: add task store contract"
git push origin dev
```

## Task 2: Artifact Store and Registry Orchestration

**Files:**
- Create: `api/tasks/artifacts.py`
- Create: `api/tasks/lease.py`
- Create: `api/tasks/registry.py`
- Create: `tests/test_artifact_store.py`
- Create: `tests/test_generation_registry.py`

- [ ] **Step 1: Write failing artifact tests**

Create `tests/test_artifact_store.py`:

```python
from pathlib import Path

import pytest

from api.tasks.artifacts import LocalArtifactStore


@pytest.mark.asyncio
async def test_local_artifact_store_persists_existing_video(tmp_path):
    source_dir = tmp_path / "work"
    source_dir.mkdir()
    source = source_dir / "final.mp4"
    source.write_bytes(b"video")
    store = LocalArtifactStore(output_root=tmp_path / "output", base_url="http://test/api/files")

    result = await store.persist_video(task_id="task-1", source_path=source, duration=3.5)

    assert result["storage_backend"] == "local"
    assert result["storage_key"] == "task-1/final.mp4"
    assert result["video_url"] == "http://test/api/files/task-1/final.mp4"
    assert result["file_size"] == 5
    assert await store.exists(result["storage_key"]) is True


@pytest.mark.asyncio
async def test_local_artifact_store_reports_missing_key(tmp_path):
    store = LocalArtifactStore(output_root=tmp_path / "output", base_url="/api/files")

    assert await store.exists("missing/final.mp4") is False
```

- [ ] **Step 2: Write failing registry tests**

Create `tests/test_generation_registry.py`:

```python
from datetime import timedelta

import pytest

from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import ArtifactStatus, TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore, LostTaskLeaseError


@pytest.mark.asyncio
async def test_registry_reuses_active_task():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
    )

    first = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    second = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert first.created is True
    assert second.created is False
    assert second.reused_reason == "active"
    assert second.task.task_id == first.task.task_id


@pytest.mark.asyncio
async def test_registry_reuses_completed_only_when_artifact_exists(tmp_path):
    artifact_store = MissingArtifactStore(existing_keys={"task-1/final.mp4"})
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: "task-1",
    )
    created = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")
    await registry.mark_completed(
        task_id=created.task.task_id,
        result={"storage_key": "task-1/final.mp4"},
        owner_id=claim.lease.owner_id,
        lease_token=claim.lease.lease_token,
    )

    reused = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert reused.created is False
    assert reused.reused_reason == "recent_completed"
    assert reused.task.artifact_status == ArtifactStatus.PERSISTED


@pytest.mark.asyncio
async def test_registry_marks_completed_missing_artifact_failed_before_regenerating():
    artifact_store = MissingArtifactStore(existing_keys=set())
    ids = iter(["task-old", "task-new"])
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: next(ids),
    )
    old = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")
    await registry.mark_completed(
        task_id=old.task.task_id,
        result={"storage_key": "task-old/final.mp4"},
        owner_id=claim.lease.owner_id,
        lease_token=claim.lease.lease_token,
    )

    new = await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "same"},
        reuse_completed_within_seconds=86400,
    )

    assert new.created is True
    assert new.task.task_id == "task-new"
    failed_old = await registry.get_task("task-old")
    assert failed_old.status == TaskStatus.FAILED
    assert failed_old.artifact_status == ArtifactStatus.MISSING


@pytest.mark.asyncio
async def test_registry_rejects_stale_completion_after_lost_lease():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(existing_keys={"task-1/final.mp4"}),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={},
        reuse_completed_within_seconds=int(timedelta(days=1).total_seconds()),
    )
    claim = await registry.claim_next_pending(worker_id="worker-1")

    with pytest.raises(LostTaskLeaseError):
        await registry.mark_completed(
            task_id="task-1",
            result={"storage_key": "task-1/final.mp4"},
            owner_id=claim.lease.owner_id,
            lease_token="stale-token",
        )
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
pytest tests/test_artifact_store.py tests/test_generation_registry.py -q
```

Expected: FAIL because artifact, lease, and registry modules do not exist.

- [ ] **Step 4: Implement artifact store**

Create `api/tasks/artifacts.py` with:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class ArtifactStore(Protocol):
    async def persist_video(self, *, task_id: str, source_path: str | Path, duration: float) -> dict: ...
    async def exists(self, storage_key: str | None) -> bool: ...


class LocalArtifactStore:
    def __init__(self, *, output_root: str | Path = "output", base_url: str = "/api/files") -> None:
        self.output_root = Path(output_root)
        self.base_url = base_url.rstrip("/")

    async def persist_video(self, *, task_id: str, source_path: str | Path, duration: float) -> dict:
        source = Path(source_path)
        target_dir = self.output_root / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        storage_key = f"{task_id}/{target.name}"
        return {
            "storage_backend": "local",
            "storage_key": storage_key,
            "video_url": f"{self.base_url}/{storage_key}",
            "file_size": target.stat().st_size,
            "duration": duration,
        }

    async def exists(self, storage_key: str | None) -> bool:
        if not storage_key:
            return False
        return (self.output_root / storage_key).is_file()


class MissingArtifactStore:
    def __init__(self, existing_keys: set[str] | None = None) -> None:
        self.existing_keys = existing_keys or set()

    async def persist_video(self, *, task_id: str, source_path: str | Path, duration: float) -> dict:
        storage_key = f"{task_id}/{Path(source_path).name}"
        self.existing_keys.add(storage_key)
        return {"storage_backend": "memory", "storage_key": storage_key, "video_url": storage_key, "duration": duration, "file_size": 0}

    async def exists(self, storage_key: str | None) -> bool:
        return bool(storage_key and storage_key in self.existing_keys)
```

- [ ] **Step 5: Implement lease and registry**

Create `api/tasks/lease.py`:

```python
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Protocol

from api.tasks.models import ExecutionLease, utc_now


class GenerationLease(Protocol):
    async def acquire_submit_lock(self, fingerprint: str, owner_id: str) -> bool: ...
    async def release_submit_lock(self, fingerprint: str, owner_id: str) -> None: ...
    async def create_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> ExecutionLease: ...
    async def heartbeat(self, task_id: str, owner_id: str, lease_token: str) -> ExecutionLease: ...
    async def release_task_lease(self, task_id: str, owner_id: str, lease_token: str) -> None: ...
    def new_token(self) -> str: ...


class InMemoryGenerationLease:
    def __init__(self, lease_ttl_seconds: int = 120) -> None:
        self.lease_ttl_seconds = lease_ttl_seconds
        self.submit_locks: dict[str, str] = {}
        self.task_leases: dict[str, tuple[str, str]] = {}

    def new_token(self) -> str:
        return secrets.token_urlsafe(24)
```

Complete methods with owner/token comparisons and `lease_expires_at=utc_now() + timedelta(seconds=self.lease_ttl_seconds)`.

Create `api/tasks/registry.py`:

```python
from __future__ import annotations

import uuid
from datetime import timedelta

from api.tasks.artifacts import ArtifactStore
from api.tasks.lease import GenerationLease
from api.tasks.models import ArtifactStatus, ClaimedTask, ExecutionLease, ReserveOutcome, Task, TaskStatus, TaskType, utc_now
from api.tasks.store import TaskStore

ACTIVE_TASK_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}


class GenerationRegistry:
    def __init__(
        self,
        *,
        store: TaskStore,
        lease: GenerationLease,
        artifact_store: ArtifactStore,
        task_id_factory=None,
    ) -> None:
        self.store = store
        self.lease = lease
        self.artifact_store = artifact_store
        self.task_id_factory = task_id_factory or (lambda: str(uuid.uuid4()))
```

Complete:

- `reserve_or_reuse()` acquires submit lock, checks active/recent completed, verifies completed artifact existence, creates pending task, and releases submit lock.
- `claim_next_pending()` creates owner/token, calls store claim, creates lease, and returns `ClaimedTask`.
- `mark_completed()` validates artifact existence from result storage key and calls store update with `ArtifactStatus.PERSISTED`.
- `mark_failed()`, `heartbeat()`, `cancel()`, `get_task()`, and `list_tasks()` delegate with CAS.

- [ ] **Step 6: Run tests and verify GREEN**

Run:

```powershell
pytest tests/test_artifact_store.py tests/test_generation_registry.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add api/tasks/artifacts.py api/tasks/lease.py api/tasks/registry.py tests/test_artifact_store.py tests/test_generation_registry.py
git commit -m "feat: add generation registry orchestration"
git push origin dev
```

## Task 3: TaskManager Facade and Embedded Execution Compatibility

**Files:**
- Modify: `api/tasks/manager.py`
- Modify: `api/tasks/__init__.py`
- Create: `tests/test_task_manager_registry_facade.py`

- [ ] **Step 1: Write failing facade tests**

Create `tests/test_task_manager_registry_facade.py`:

```python
import pytest

from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore


def build_manager():
    store = InMemoryTaskStore()
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    return TaskManager(store=store, registry=registry, execution_mode="embedded")


@pytest.mark.asyncio
async def test_manager_reserve_or_reuse_generation_task_reuses_duplicate():
    manager = build_manager()
    first = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={"text": "same"},
    )
    second = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={"text": "same"},
    )

    assert first.created is True
    assert second.created is False
    assert second.task.task_id == first.task.task_id


@pytest.mark.asyncio
async def test_manager_execute_task_updates_store_result():
    manager = build_manager()
    await manager.start()
    outcome = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-1",
        request_params={},
    )

    async def generate():
        return {"video_url": "/api/files/task-1/final.mp4", "storage_key": "task-1/final.mp4"}

    await manager.execute_task(outcome.task.task_id, generate)
    future = manager._task_futures[outcome.task.task_id]
    await future

    task = await manager.get_task(outcome.task.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result["video_url"] == "/api/files/task-1/final.mp4"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_task_manager_registry_facade.py -q
```

Expected: FAIL because `TaskManager` does not accept injected store/registry and does not expose `reserve_or_reuse_generation_task()`.

- [ ] **Step 3: Refactor TaskManager**

Update `api/tasks/manager.py`:

- Constructor accepts `store=None`, `registry=None`, `execution_mode="embedded"`.
- Existing `create_task()` delegates to `store.create_task()`.
- Existing `get_task()`, `list_tasks()`, `update_progress()`, and `cancel_task()` become async internally or provide sync wrappers only where existing callers require them.
- Add:

```python
async def reserve_or_reuse_generation_task(
    self,
    *,
    task_type: TaskType,
    generation_fingerprint: str,
    request_params: dict,
):
    return await self.registry.reserve_or_reuse(
        fingerprint=generation_fingerprint,
        task_type=task_type,
        request_params=request_params,
        reuse_completed_within_seconds=api_config.completed_reuse_seconds,
    )
```

- `execute_task()` in embedded mode claims the task through registry before running, then calls `mark_completed()` or `mark_failed()` with the claim lease.

- [ ] **Step 4: Update exports**

Update `api/tasks/__init__.py` to export `ArtifactStatus`, `ReserveOutcome`, `ExecutionLease`, `ClaimedTask`, `GenerationRegistry`, and `InMemoryTaskStore`.

- [ ] **Step 5: Run facade tests**

Run:

```powershell
pytest tests/test_task_manager_registry_facade.py tests/test_task_store_memory.py tests/test_generation_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add api/tasks/manager.py api/tasks/__init__.py tests/test_task_manager_registry_facade.py
git commit -m "refactor: route task manager through registry"
git push origin dev
```

## Task 4: Async Video API Uses Registry

**Files:**
- Modify: `api/routers/video.py`
- Modify: `api/routers/tasks.py`
- Create: `tests/test_async_video_registry_integration.py`

- [ ] **Step 1: Write failing async route tests**

Create `tests/test_async_video_registry_integration.py`:

```python
from types import SimpleNamespace

import pytest

from api.routers import video
from api.schemas.video import VideoGenerateRequest
from api.tasks.models import TaskType


class FakeTaskManager:
    def __init__(self):
        self.calls = 0
        self.executed = []

    async def reserve_or_reuse_generation_task(self, *, task_type, generation_fingerprint, request_params):
        self.calls += 1
        task = SimpleNamespace(task_id="task-1", task_type=task_type, request_params=request_params)
        return SimpleNamespace(task=task, created=self.calls == 1, reused_reason=None if self.calls == 1 else "active")

    async def execute_task(self, task_id, coro_func):
        self.executed.append(task_id)


@pytest.mark.asyncio
async def test_async_video_endpoint_returns_reused_task_without_execution(monkeypatch):
    manager = FakeTaskManager()
    manager.calls = 1
    monkeypatch.setattr(video, "task_manager", manager)

    response = await video.generate_video_async(
        VideoGenerateRequest(text="demo", frame_template="1080x1920/image_default.html"),
        pixelle_video=SimpleNamespace(),
        request=SimpleNamespace(base_url="http://test/"),
    )

    assert response.task_id == "task-1"
    assert response.message == "Task already running"
    assert manager.executed == []


@pytest.mark.asyncio
async def test_async_video_endpoint_executes_new_task_in_embedded_mode(monkeypatch):
    manager = FakeTaskManager()
    monkeypatch.setattr(video, "task_manager", manager)
    monkeypatch.setattr(video, "resolve_video_media_size", lambda frame_template: (1080, 1920))

    response = await video.generate_video_async(
        VideoGenerateRequest(text="demo", frame_template="1080x1920/image_default.html"),
        pixelle_video=SimpleNamespace(),
        request=SimpleNamespace(base_url="http://test/"),
    )

    assert response.task_id == "task-1"
    assert manager.executed == ["task-1"]
    assert manager.calls == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_async_video_registry_integration.py -q
```

Expected: FAIL because the router still calls `find_active_task_by_request_fingerprint()` and `create_task()` directly.

- [ ] **Step 3: Refactor video route**

In `api/routers/video.py`:

- Extract duplicated request parameter construction into:

```python
def build_video_generation_params(request_body: VideoGenerateRequest, *, request_id: str, api_task_id: str | None = None) -> dict:
    ...
```

- Extract media size resolution into:

```python
def resolve_video_media_size(frame_template: str) -> tuple[int, int]:
    ...
```

- Replace duplicate detection with `await task_manager.reserve_or_reuse_generation_task(...)`.
- If `outcome.created is False`, return `VideoGenerateAsyncResponse(task_id=outcome.task.task_id, message="Task already running")` or `"Task already completed"` based on `reused_reason`.
- If `outcome.created is True`, call `await task_manager.execute_task(...)` only when `task_manager.execution_mode == "embedded"`.

- [ ] **Step 4: Update tasks router for async facade**

In `api/routers/tasks.py`, await async facade methods:

```python
tasks = await task_manager.list_tasks(status=status, limit=limit)
task = await task_manager.get_task(task_id)
success = await task_manager.cancel_task(task_id)
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
pytest tests/test_async_video_registry_integration.py tests/test_task_manager_registry_facade.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add api/routers/video.py api/routers/tasks.py tests/test_async_video_registry_integration.py
git commit -m "feat: route async video generation through registry"
git push origin dev
```

## Task 5: Redis Generation Lease

**Files:**
- Modify: `api/tasks/lease.py`
- Create: `tests/test_redis_generation_lease.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing Redis lease tests with a fake Redis adapter**

Create `tests/test_redis_generation_lease.py`:

```python
import pytest

from api.tasks.lease import LostLeaseError, RedisGenerationLease


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_redis_submit_lock_is_owner_scoped():
    redis = FakeRedis()
    lease = RedisGenerationLease(redis=redis)

    assert await lease.acquire_submit_lock("fp-1", "owner-1") is True
    assert await lease.acquire_submit_lock("fp-1", "owner-2") is False
    await lease.release_submit_lock("fp-1", "owner-2")
    assert await lease.acquire_submit_lock("fp-1", "owner-3") is False
    await lease.release_submit_lock("fp-1", "owner-1")
    assert await lease.acquire_submit_lock("fp-1", "owner-3") is True


@pytest.mark.asyncio
async def test_redis_heartbeat_rejects_stale_token():
    redis = FakeRedis()
    lease = RedisGenerationLease(redis=redis)
    await lease.create_task_lease("task-1", "worker-1", "token-1")

    with pytest.raises(LostLeaseError):
        await lease.heartbeat("task-1", "worker-1", "token-old")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_redis_generation_lease.py -q
```

Expected: FAIL because `RedisGenerationLease` does not exist.

- [ ] **Step 3: Implement Redis lease**

Update `api/tasks/lease.py`:

- Add `LostLeaseError`.
- Add `RedisGenerationLease(redis, namespace="pixelle:generation", lease_ttl_seconds=120, submit_lock_ttl_seconds=30)`.
- Store task lease values as compact JSON: `{"owner_id": "...", "lease_token": "..."}`.
- Implement compare operations by reading current value, comparing owner/token, then deleting or refreshing TTL. For real Redis, use Lua scripts once behavior is green with the fake adapter.
- Use `redis.asyncio.from_url()` in a helper:

```python
def create_redis_lease(redis_url: str, *, lease_ttl_seconds: int, submit_lock_ttl_seconds: int) -> RedisGenerationLease:
    import redis.asyncio as redis
    return RedisGenerationLease(redis=redis.from_url(redis_url), lease_ttl_seconds=lease_ttl_seconds, submit_lock_ttl_seconds=submit_lock_ttl_seconds)
```

- [ ] **Step 4: Add dependency**

In `pyproject.toml` dependencies, add:

```toml
"redis>=5.0.0",
```

- [ ] **Step 5: Run tests**

Run:

```powershell
pytest tests/test_redis_generation_lease.py tests/test_generation_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add api/tasks/lease.py tests/test_redis_generation_lease.py pyproject.toml
git commit -m "feat: add redis generation leases"
git push origin dev
```

## Task 6: PostgreSQL Task Store and Migration

**Files:**
- Create: `api/tasks/postgres.py`
- Create: `api/tasks/migrate.py`
- Create: `alembic.ini`
- Create: `api/tasks/alembic/env.py`
- Create: `api/tasks/alembic/versions/0001_create_generation_tasks.py`
- Modify: `pyproject.toml`
- Create: `tests/test_postgres_task_store_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_postgres_task_store_schema.py`:

```python
from pathlib import Path


def test_generation_tasks_migration_contains_source_level_constraints():
    migration = Path("api/tasks/alembic/versions/0001_create_generation_tasks.py").read_text(encoding="utf-8")

    assert "generation_tasks" in migration
    assert "uq_generation_tasks_active_fingerprint" in migration
    assert "postgresql_where" in migration
    assert "status IN ('pending', 'running')" in migration
    assert "lease_token" in migration
    assert "artifact_status" in migration
    assert "idx_generation_tasks_pending_claim" in migration


def test_postgres_store_exposes_required_methods():
    from api.tasks.postgres import PostgresTaskStore

    for name in [
        "create_task",
        "get_task",
        "find_reusable_by_fingerprint",
        "update_status",
        "update_progress",
        "claim_next_pending",
        "list_tasks",
        "cancel_task",
    ]:
        assert hasattr(PostgresTaskStore, name)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_postgres_task_store_schema.py -q
```

Expected: FAIL because migration and Postgres store do not exist.

- [ ] **Step 3: Add dependencies**

In `pyproject.toml`, add:

```toml
"sqlalchemy[asyncio]>=2.0.0",
"asyncpg>=0.29.0",
"alembic>=1.13.0",
```

- [ ] **Step 4: Implement schema and migration**

Create SQLAlchemy table metadata in `api/tasks/postgres.py` with:

```python
generation_tasks = Table(
    "generation_tasks",
    metadata,
    Column("task_id", Text, primary_key=True),
    Column("task_type", Text, nullable=False),
    Column("generation_fingerprint", Text),
    Column("status", Text, nullable=False),
    Column("request_params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("progress", JSONB),
    Column("result", JSONB),
    Column("error", Text),
    Column("owner_id", Text),
    Column("lease_token", Text),
    Column("artifact_status", Text, nullable=False, server_default="none"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
```

Create Alembic migration with the same columns plus:

- check constraint for task status;
- check constraint for artifact status;
- `idx_generation_tasks_status_created_at`;
- `idx_generation_tasks_fingerprint_status`;
- `idx_generation_tasks_fingerprint_completed`;
- `idx_generation_tasks_pending_claim`;
- partial unique index `uq_generation_tasks_active_fingerprint` using `postgresql_where=sa.text("status IN ('pending', 'running') AND generation_fingerprint IS NOT NULL")`;
- `updated_at` trigger function.

- [ ] **Step 5: Implement PostgresTaskStore**

Implement methods using SQLAlchemy async sessions:

- `create_task()` catches `IntegrityError` and raises `TaskAlreadyExistsError`.
- `find_reusable_by_fingerprint()` first selects active tasks, then recent completed tasks.
- `update_status()` includes `WHERE owner_id = :expected_owner_id AND lease_token = :expected_lease_token` when expected values are supplied; if no row is updated, raise `LostTaskLeaseError`.
- `update_progress()` uses the same CAS condition.
- `claim_next_pending()` uses a transaction with `SELECT ... FOR UPDATE SKIP LOCKED` ordered by `created_at ASC`, updates status to running, and returns the claimed task.
- `cancel_task()` sets status cancelled, clears `lease_token`, and sets `completed_at`.

- [ ] **Step 6: Run schema tests**

Run:

```powershell
pytest tests/test_postgres_task_store_schema.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add api/tasks/postgres.py api/tasks/migrate.py alembic.ini api/tasks/alembic/env.py api/tasks/alembic/versions/0001_create_generation_tasks.py tests/test_postgres_task_store_schema.py pyproject.toml
git commit -m "feat: add postgres task store"
git push origin dev
```

## Task 7: Configuration, Startup, and Backend Factory

**Files:**
- Modify: `api/config.py`
- Create: `api/tasks/factory.py`
- Modify: `api/app.py`
- Create: `tests/test_distributed_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_distributed_config.py`:

```python
import pytest

from api.config import APIConfig
from api.tasks.factory import build_task_manager


def test_api_config_reads_distributed_task_environment(monkeypatch):
    monkeypatch.setenv("PIXELLE_TASK_BACKEND", "postgres")
    monkeypatch.setenv("PIXELLE_POSTGRES_DSN", "postgresql+asyncpg://u:p@postgres:5432/pixelle")
    monkeypatch.setenv("PIXELLE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION", "true")
    monkeypatch.setenv("PIXELLE_EXECUTION_MODE", "worker")

    config = APIConfig.from_env()

    assert config.task_backend == "postgres"
    assert config.postgres_dsn.startswith("postgresql+asyncpg://")
    assert config.redis_url == "redis://redis:6379/0"
    assert config.require_distributed_coordination is True
    assert config.execution_mode == "worker"


def test_production_distributed_mode_fails_without_redis(monkeypatch):
    monkeypatch.setenv("PIXELLE_TASK_BACKEND", "postgres")
    monkeypatch.delenv("PIXELLE_REDIS_URL", raising=False)
    monkeypatch.setenv("PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION", "true")

    config = APIConfig.from_env()

    with pytest.raises(RuntimeError, match="PIXELLE_REDIS_URL"):
        build_task_manager(config)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_distributed_config.py -q
```

Expected: FAIL because `APIConfig.from_env()` and `api.tasks.factory` do not exist.

- [ ] **Step 3: Implement config**

In `api/config.py`, add fields:

```python
task_backend: Literal["memory", "postgres"] = "memory"
postgres_dsn: Optional[str] = None
redis_url: Optional[str] = None
require_distributed_coordination: bool = False
generation_lease_ttl_seconds: int = 120
generation_heartbeat_seconds: int = 30
completed_reuse_seconds: int = 86400
execution_mode: Literal["embedded", "worker"] = "embedded"
artifact_backend: Literal["local", "s3"] = "local"
artifact_base_url: str = "/api/files"
artifact_base_path: str = "output"
```

Add `@classmethod from_env()` that reads `PIXELLE_*` variables and booleans from `"1"`, `"true"`, and `"yes"`.

- [ ] **Step 4: Implement backend factory**

Create `api/tasks/factory.py`:

```python
from api.config import APIConfig
from api.tasks.artifacts import LocalArtifactStore
from api.tasks.lease import InMemoryGenerationLease, create_redis_lease
from api.tasks.manager import TaskManager
from api.tasks.postgres import PostgresTaskStore, create_async_engine_from_dsn
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore


def build_task_manager(config: APIConfig) -> TaskManager:
    if config.task_backend == "memory":
        store = InMemoryTaskStore()
        lease = InMemoryGenerationLease(config.generation_lease_ttl_seconds)
    else:
        if config.require_distributed_coordination and not config.redis_url:
            raise RuntimeError("PIXELLE_REDIS_URL is required when distributed coordination is required")
        if config.require_distributed_coordination and not config.postgres_dsn:
            raise RuntimeError("PIXELLE_POSTGRES_DSN is required when distributed coordination is required")
        store = PostgresTaskStore(create_async_engine_from_dsn(config.postgres_dsn))
        lease = create_redis_lease(
            config.redis_url,
            lease_ttl_seconds=config.generation_lease_ttl_seconds,
            submit_lock_ttl_seconds=30,
        )
    artifact_store = LocalArtifactStore(output_root=config.artifact_base_path, base_url=config.artifact_base_url)
    registry = GenerationRegistry(store=store, lease=lease, artifact_store=artifact_store)
    return TaskManager(store=store, registry=registry, execution_mode=config.execution_mode)
```

- [ ] **Step 5: Wire app startup**

In `api/app.py`, replace direct global manager startup with a startup factory call that sets `api.tasks.manager.task_manager` to the configured manager before `start()`.

- [ ] **Step 6: Run config tests**

Run:

```powershell
pytest tests/test_distributed_config.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add api/config.py api/tasks/factory.py api/app.py tests/test_distributed_config.py
git commit -m "feat: configure distributed task backend"
git push origin dev
```

## Task 8: Worker Execution

**Files:**
- Create: `api/tasks/worker.py`
- Create: `tests/test_worker_execution.py`

- [ ] **Step 1: Write failing worker tests**

Create `tests/test_worker_execution.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.tasks.artifacts import LocalArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.models import TaskStatus, TaskType
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore
from api.tasks.worker import GenerationWorker


class FakeCore:
    async def generate_video(self, **params):
        output = Path(params["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        return SimpleNamespace(video_path=str(output), duration=2.5)


@pytest.mark.asyncio
async def test_worker_claims_pending_task_and_marks_completed(tmp_path):
    store = InMemoryTaskStore()
    artifact_store = LocalArtifactStore(output_root=tmp_path / "output", base_url="/api/files")
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=artifact_store,
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "demo", "frame_template": "1080x1920/image_default.html"},
        reuse_completed_within_seconds=86400,
    )
    worker = GenerationWorker(registry=registry, core=FakeCore(), artifact_store=artifact_store, output_root=tmp_path / "work")

    did_work = await worker.run_once()

    assert did_work is True
    task = await registry.get_task("task-1")
    assert task.status == TaskStatus.COMPLETED
    assert task.result["storage_key"] == "task-1/final.mp4"


@pytest.mark.asyncio
async def test_worker_returns_false_when_no_pending_task(tmp_path):
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
    )
    worker = GenerationWorker(registry=registry, core=FakeCore(), artifact_store=registry.artifact_store, output_root=tmp_path / "work")

    assert await worker.run_once() is False
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pytest tests/test_worker_execution.py -q
```

Expected: FAIL because `GenerationWorker` does not exist.

- [ ] **Step 3: Implement worker**

Create `api/tasks/worker.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from api.tasks.artifacts import ArtifactStore
from api.tasks.registry import GenerationRegistry


class GenerationWorker:
    def __init__(self, *, registry: GenerationRegistry, core, artifact_store: ArtifactStore, output_root: str | Path = "output", worker_id: str = "worker") -> None:
        self.registry = registry
        self.core = core
        self.artifact_store = artifact_store
        self.output_root = Path(output_root)
        self.worker_id = worker_id

    async def run_once(self) -> bool:
        claim = await self.registry.claim_next_pending(worker_id=self.worker_id)
        if claim is None:
            return False
        task = claim.task
        lease = claim.lease
        try:
            params = dict(task.request_params or {})
            params["api_task_id"] = task.task_id
            params["output_path"] = str(self.output_root / task.task_id / "final.mp4")
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
```

Add CLI `main()` that builds config, initializes `PixelleVideoCore`, and loops with `PIXELLE_WORKER_POLL_INTERVAL_SECONDS`.

- [ ] **Step 4: Run worker tests**

Run:

```powershell
pytest tests/test_worker_execution.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

Run:

```powershell
git add api/tasks/worker.py tests/test_worker_execution.py
git commit -m "feat: add generation worker"
git push origin dev
```

## Task 9: Docker Compose and Final Verification

**Files:**
- Modify: `docker-compose.yml`
- Modify: `pyproject.toml`
- Modify: `docs/superpowers/specs/2026-04-25-distributed-generation-registry-design.md` if implementation details changed during execution.

- [ ] **Step 1: Update Docker Compose**

Modify `docker-compose.yml`:

- add `postgres` service using `postgres:16` with `POSTGRES_DB=pixelle`, `POSTGRES_USER=pixelle`, `POSTGRES_PASSWORD=pixelle`, healthcheck `pg_isready -U pixelle -d pixelle`;
- add `redis` service using `redis:7` with AOF and `redis-cli ping` healthcheck;
- add `migrate` service running `.venv/bin/python -m api.tasks.migrate upgrade`;
- add `worker` service running `.venv/bin/python -m api.tasks.worker`;
- add `PIXELLE_TASK_BACKEND=postgres`, `PIXELLE_POSTGRES_DSN`, `PIXELLE_REDIS_URL`, `PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION=true`, `PIXELLE_EXECUTION_MODE=worker`, and `PIXELLE_ARTIFACT_BACKEND=local` to api/web/worker;
- keep `./output:/app/output` mounted on api/web/worker for single-host compose.

- [ ] **Step 2: Run focused test suite**

Run:

```powershell
pytest tests/test_task_store_memory.py tests/test_artifact_store.py tests/test_generation_registry.py tests/test_task_manager_registry_facade.py tests/test_async_video_registry_integration.py tests/test_redis_generation_lease.py tests/test_postgres_task_store_schema.py tests/test_distributed_config.py tests/test_worker_execution.py -q
```

Expected: PASS.

- [ ] **Step 3: Run existing regression tests for touched areas**

Run:

```powershell
pytest tests/test_generation_coordinator.py tests/test_history_card_actions_layout.py -q
```

Expected: PASS.

- [ ] **Step 4: Run lint/import check**

Run:

```powershell
python -m compileall api pixelle_video tests -q
```

Expected: exit code 0.

- [ ] **Step 5: Check diff scope**

Run:

```powershell
git status --short
git diff --check
```

Expected: no whitespace errors and only files from this plan are modified.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add docker-compose.yml pyproject.toml docs/superpowers/specs/2026-04-25-distributed-generation-registry-design.md
git commit -m "chore: wire distributed generation deployment"
git push origin dev
```

## Self-Review

- Spec coverage: The plan covers task persistence, active unique enforcement through migration, Redis submit locks and task leases, fencing token CAS, worker execution, artifact persistence/existence checks, API task querying, cancel semantics, Docker services, production fail-fast configuration, tests, and regression checks.
- Scope decomposition: This is a large feature, but tasks are ordered so each commit is independently understandable: contracts, registry, facade, API, Redis, PostgreSQL, config, worker, deployment.
- Placeholder scan: The plan names concrete files, classes, methods, commands, and expected outcomes, with no unfinished sections.
- Type consistency: Core names are `TaskStore`, `InMemoryTaskStore`, `GenerationLease`, `InMemoryGenerationLease`, `RedisGenerationLease`, `ArtifactStore`, `LocalArtifactStore`, `GenerationRegistry`, `TaskManager`, `PostgresTaskStore`, and `GenerationWorker`.
