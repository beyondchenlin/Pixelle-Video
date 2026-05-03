# Storyboard Workbench Client Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Storyboard Workbench depend on a first-class client boundary with honest display, capability, task submission, and execution contracts, so local Streamlit no longer depends on `8001` and no regenerate path is fake.

**Architecture:** Introduce a backend `StoryboardWorkbenchTaskSubmitter` on top of a general-purpose `TaskExecutorRegistry`, then wire embedded and worker execution capability through shared task infrastructure instead of Workbench-specific `TaskManager` fields. Expose honest backend capabilities over HTTP, then introduce HTTP and in-process Workbench clients. The Workbench page resolves one client and passes it downward; child components consume `image_display` payloads and capabilities only. Every intermediate commit keeps existing behavior working or adds a new unused capability behind tests.

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
- Create `api/tasks/executors.py`
  - Defines `TaskExecutor`, `TaskExecutionCapability`, `TaskExecutorRegistry`, and static worker capability registry primitives.
- Modify `api/tasks/manager.py`
  - Delegates execution capability and embedded auto-execution to the general task executor registry.
- Modify `api/tasks/factory.py`
  - Builds `TaskManager` with executor registry and worker capability registry.
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
  - Claims and executes `FRAME_IMAGE_REGENERATION` tasks in worker mode.
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

## Execution Notes

- Do not switch UI default mode before the in-process client supports list/select/stale/display/regenerate submission.
- Do not claim regenerate is available unless a submitter and executor path exist.
- Do not add `frame_image_regeneration_executor`, `tts_executor`, or similar product-specific fields to `TaskManager`; all newly added task execution capability must go through `TaskExecutorRegistry`.
- Do not call `request.app.state.task_manager` from the Storyboard Workbench router after Task 2.
- Do not use `api.tasks.manager.task_manager` global as a local shortcut.
- Keep commits atomic and pushable. Use `git push origin <current-branch>` after each commit per repository policy.
- Ignore unrelated dirty files, especially `tests/test_style_config_layered_template_ui.py`, unless they become directly relevant.

---

## Task 1: Add General Task Executor Registry And First-Class Submitter

**Files:**
- Create: `api/tasks/executors.py`
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

- [ ] **Step 1: Write failing executor registry and submitter tests**

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

    def can_execute_task_type(self, task_type: TaskType) -> bool:
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


def test_worker_capability_registry_is_explicit_and_task_type_scoped():
    from api.tasks.executors import StaticWorkerCapabilityRegistry

    empty = StaticWorkerCapabilityRegistry()
    configured = StaticWorkerCapabilityRegistry({TaskType.FRAME_IMAGE_REGENERATION})

    assert empty.supports(TaskType.FRAME_IMAGE_REGENERATION) is False
    assert configured.supports(TaskType.FRAME_IMAGE_REGENERATION) is True
    assert configured.supports(TaskType.VIDEO_GENERATION) is False


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


def test_task_manager_reports_frame_regeneration_unavailable_by_default():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(TaskManager())

    assert submitter.get_capabilities().to_dict() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "frame image regeneration execution is not configured",
    }


def test_task_manager_embedded_capability_comes_from_executor_registry():
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

    assert submitter.get_capabilities().to_dict() == {
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }


def test_task_manager_worker_mode_uses_worker_capability_registry():
    from api.tasks.executors import StaticWorkerCapabilityRegistry
    from api.tasks.manager import TaskManager

    assert (
        TaskManager(execution_mode="worker").can_execute_task_type(
            TaskType.FRAME_IMAGE_REGENERATION
        )
        is False
    )
    assert (
        TaskManager(
            execution_mode="worker",
            worker_capability_registry=StaticWorkerCapabilityRegistry(
                {TaskType.FRAME_IMAGE_REGENERATION}
            ),
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
    from api.tasks.executors import StaticWorkerCapabilityRegistry, TaskExecutorRegistry

    executor_registry = TaskExecutorRegistry()
    worker_capabilities = StaticWorkerCapabilityRegistry({TaskType.FRAME_IMAGE_REGENERATION})

    dependencies = build_platform_dependencies(
        APIConfig(runtime_profile="dev", artifact_base_path=str(tmp_path / "output")),
        task_executor_registry=executor_registry,
        worker_capability_registry=worker_capabilities,
    )

    assert dependencies.task_executor_registry is executor_registry
    assert dependencies.worker_capability_registry is worker_capabilities
    assert not hasattr(dependencies, "pixelle_video_core_provider")
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py::test_dev_platform_dependencies_mount_storyboard_workbench_task_submitter tests/test_app_platform_dependencies.py::test_api_app_lifespan_mounts_storyboard_workbench_task_submitter tests/test_app_platform_dependencies.py::test_web_session_pixelle_video_mounts_storyboard_workbench_task_submitter
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
    def supports(self, task_type: TaskType) -> bool: ...


class StaticWorkerCapabilityRegistry:
    def __init__(self, supported_task_types: set[TaskType] | None = None) -> None:
        self._supported_task_types = set(supported_task_types or ())

    def supports(self, task_type: TaskType) -> bool:
        return task_type in self._supported_task_types


__all__ = [
    "StaticWorkerCapabilityRegistry",
    "TaskExecutionCapability",
    "TaskExecutor",
    "TaskExecutorRegistry",
    "WorkerCapabilityRegistry",
]
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
    def get_capabilities(self) -> StoryboardWorkbenchCapabilities: ...

    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> StoryboardWorkbenchTaskSubmission: ...


class TaskManagerStoryboardWorkbenchTaskSubmitter:
    def __init__(self, task_manager: Any) -> None:
        self.task_manager = task_manager

    def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
        can_execute = bool(
            getattr(self.task_manager, "can_execute_task_type", lambda _task_type: False)(
                TaskType.FRAME_IMAGE_REGENERATION
            )
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
        capabilities = self.get_capabilities()
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

    def get_capabilities(self) -> StoryboardWorkbenchCapabilities:
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


def get_storyboard_workbench_capabilities(
    submitter: StoryboardWorkbenchTaskSubmitter | None,
) -> StoryboardWorkbenchCapabilities:
    if submitter is None:
        return StoryboardWorkbenchCapabilities(
            can_regenerate_frame_image=False,
            regenerate_unavailable_reason="task submitter is not configured",
        )
    return submitter.get_capabilities()


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
from api.workbench.task_submitter import (
    StoryboardWorkbenchTaskSubmitter,
    TaskManagerStoryboardWorkbenchTaskSubmitter,
)
```

Extend `PlatformDependencies`:

```python
task_executor_registry: TaskExecutorRegistry | None = None
worker_capability_registry: WorkerCapabilityRegistry | None = None
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
) -> PlatformDependencies:
    dependencies = build_platform_dependencies(
        config,
        task_manager=task_manager,
        task_executor_registry=task_executor_registry,
        worker_capability_registry=worker_capability_registry,
    )
```

```python
def build_platform_dependencies(
    config: APIConfig,
    *,
    task_manager: Any | None = None,
    task_executor_registry: TaskExecutorRegistry | None = None,
    worker_capability_registry: WorkerCapabilityRegistry | None = None,
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
_LOCAL_WORKER_CAPABILITY_REGISTRY = None


def get_or_create_local_platform_dependencies():
    global _LOCAL_PLATFORM_DEPENDENCIES, _LOCAL_PLATFORM_TASK_MANAGER
    global _LOCAL_TASK_EXECUTOR_REGISTRY, _LOCAL_WORKER_CAPABILITY_REGISTRY
    if _LOCAL_PLATFORM_DEPENDENCIES is None:
        from api.config import api_config
        from api.platform_dependencies import build_platform_dependencies
        from api.tasks.executors import (
            StaticWorkerCapabilityRegistry,
            TaskExecutorRegistry,
        )
        from api.tasks.factory import build_task_manager

        _LOCAL_TASK_EXECUTOR_REGISTRY = TaskExecutorRegistry()
        _LOCAL_WORKER_CAPABILITY_REGISTRY = StaticWorkerCapabilityRegistry()
        _LOCAL_PLATFORM_TASK_MANAGER = build_task_manager(
            api_config,
            executor_registry=_LOCAL_TASK_EXECUTOR_REGISTRY,
            worker_capability_registry=_LOCAL_WORKER_CAPABILITY_REGISTRY,
        )
        run_async(_LOCAL_PLATFORM_TASK_MANAGER.start())
        _LOCAL_PLATFORM_DEPENDENCIES = build_platform_dependencies(
            api_config,
            task_manager=_LOCAL_PLATFORM_TASK_MANAGER,
            task_executor_registry=_LOCAL_TASK_EXECUTOR_REGISTRY,
            worker_capability_registry=_LOCAL_WORKER_CAPABILITY_REGISTRY,
        )
    return _LOCAL_PLATFORM_DEPENDENCIES
```

In `get_pixelle_video()`, replace `get_or_create_platform_dependencies()` with `get_or_create_local_platform_dependencies()`.

Update `_cleanup_pixelle_video_session(...)` so when the last session is cleaned up it also stops `_LOCAL_PLATFORM_TASK_MANAGER` and clears `_LOCAL_PLATFORM_DEPENDENCIES`, `_LOCAL_TASK_EXECUTOR_REGISTRY`, and `_LOCAL_WORKER_CAPABILITY_REGISTRY`.

Modify `api/app.py`:

```python
from api.tasks.executors import StaticWorkerCapabilityRegistry, TaskExecutorRegistry

task_executor_registry = TaskExecutorRegistry()
worker_capability_registry = StaticWorkerCapabilityRegistry()
manager = build_task_manager(
    api_config,
    executor_registry=task_executor_registry,
    worker_capability_registry=worker_capability_registry,
)
platform_dependencies = configure_platform_dependencies(
    app,
    api_config,
    task_manager=manager,
    task_executor_registry=task_executor_registry,
    worker_capability_registry=worker_capability_registry,
)
```

Task 1 may create empty registries. `FRAME_IMAGE_REGENERATION` remains unavailable until Task 3 registers its executor.

- [ ] **Step 6: Add honest TaskManager capability declarations**

Modify `api/tasks/manager.py` imports:

```python
from api.tasks.executors import (
    StaticWorkerCapabilityRegistry,
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
self.worker_capability_registry = (
    worker_capability_registry or StaticWorkerCapabilityRegistry()
)
```

Add:

```python
def can_execute_task_type(self, task_type: TaskType) -> bool:
    if task_type is TaskType.VIDEO_GENERATION:
        return True
    if task_type is TaskType.FRAME_IMAGE_REGENERATION:
        if self.execution_mode == "embedded":
            return self.executor_registry.can_execute(task_type).can_execute
        if self.execution_mode == "worker":
            return self.worker_capability_registry.supports(task_type)
    return False


async def wait_for_task_completion_for_test(self, task_id: str) -> None:
    future = self._task_futures.get(task_id)
    if future is not None:
        await future
```

Important: Task 1 only declares capability and keeps default `TaskManager()` fail closed for frame regeneration. Do not enqueue or execute frame regeneration yet; that is Task 3.
Preserve the current `VIDEO_GENERATION` legacy path unchanged in this task; executor-registry migration for existing video generation is separate follow-up work and must not be mixed into this boundary plan.

Modify `api/tasks/factory.py`:

```python
from api.tasks.executors import TaskExecutorRegistry, WorkerCapabilityRegistry
```

Change `build_task_manager(...)`:

```python
def build_task_manager(
    config: APIConfig,
    *,
    executor_registry: TaskExecutorRegistry | None = None,
    worker_capability_registry: WorkerCapabilityRegistry | None = None,
) -> TaskManager:
```

Pass both registries into `TaskManager(...)`:

```python
return TaskManager(
    store=store,
    registry=registry,
    execution_mode=config.execution_mode,
    executor_registry=executor_registry,
    worker_capability_registry=worker_capability_registry,
)
```

- [ ] **Step 7: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py
```

Expected: all tests pass.

- [ ] **Step 8: Commit and push**

```powershell
git add -- api/tasks/executors.py api/workbench/__init__.py api/workbench/task_submitter.py api/tasks/manager.py api/tasks/factory.py api/platform_dependencies.py api/dependencies.py api/app.py web/state/session.py tests/test_storyboard_workbench_task_submitter.py tests/test_app_platform_dependencies.py
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

    def get_capabilities(self):
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
        def get_capabilities(self):
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
    capabilities = get_storyboard_workbench_capabilities(
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
capabilities = task_submitter.get_capabilities()
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

## Task 3: Add Frame Image Regeneration Executor

**Files:**
- Create: `api/workbench/frame_image_regeneration.py`
- Create: `api/workbench/executor_factory.py`
- Modify: `api/tasks/manager.py`
- Modify: `api/tasks/factory.py`
- Modify: `api/tasks/worker.py`
- Modify: `api/app.py`
- Modify: `web/state/session.py`
- Test: `tests/test_storyboard_workbench_task_submitter.py`
- Test: `tests/test_worker_execution.py`

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


def test_task_manager_submitter_reports_unavailable_when_embedded_executor_is_missing():
    from api.tasks.manager import TaskManager
    from api.workbench.task_submitter import TaskManagerStoryboardWorkbenchTaskSubmitter

    manager = TaskManager()
    submitter = TaskManagerStoryboardWorkbenchTaskSubmitter(manager)

    assert submitter.get_capabilities().to_dict() == {
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


def test_worker_mode_manager_reports_frame_regeneration_executable_after_worker_hook():
    from api.tasks.executors import StaticWorkerCapabilityRegistry
    from api.tasks.manager import TaskManager
    from api.tasks.models import TaskType

    manager = TaskManager(
        execution_mode="worker",
        worker_capability_registry=StaticWorkerCapabilityRegistry(
            {TaskType.FRAME_IMAGE_REGENERATION}
        ),
    )

    assert manager.can_execute_task_type(TaskType.FRAME_IMAGE_REGENERATION) is True
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py::test_worker_claims_frame_image_regeneration_tasks
```

Expected: fail because executor and manager/worker hooks are missing.

- [ ] **Step 4: Implement executor**

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

Reuse the `executor_registry`, `can_execute_task_type(...)`, and `wait_for_task_completion_for_test(...)` fields added in Task 1. Task 3 only adds embedded auto-execution for newly created tasks whose task type has a registered executor:

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

- [ ] **Step 6: Wire executor factory**

Build and share a registry in `api/app.py`:

```python
from api.tasks.executors import StaticWorkerCapabilityRegistry, TaskExecutorRegistry
from api.workbench.executor_factory import register_storyboard_workbench_executors

task_executor_registry = TaskExecutorRegistry()
worker_capability_registry = StaticWorkerCapabilityRegistry()
register_storyboard_workbench_executors(
    task_executor_registry,
    core_provider=get_pixelle_video,
)
manager = build_task_manager(
    api_config,
    executor_registry=task_executor_registry,
    worker_capability_registry=worker_capability_registry,
)
```

Pass the same registries into `configure_platform_dependencies(...)`:

```python
platform_dependencies = configure_platform_dependencies(
    app,
    api_config,
    task_manager=manager,
    task_executor_registry=task_executor_registry,
    worker_capability_registry=worker_capability_registry,
)
```

Modify `web/state/session.py` local dependency creation to call `register_storyboard_workbench_executors(_LOCAL_TASK_EXECUTOR_REGISTRY, core_provider=get_pixelle_video)` before constructing the local manager. The provider stays inside the executor factory closure and must not be stored on `PlatformDependencies`.

- [ ] **Step 7: Hook worker mode**

Modify `api/tasks/worker.py` `GenerationWorker` constructor:

```python
executor_registry: TaskExecutorRegistry | None = None,
```

Set:

```python
self.executor_registry = executor_registry or TaskExecutorRegistry()
```

When no registry is provided by tests or worker bootstrap, register the default frame image regeneration executor around `execute_frame_image_regeneration(core=self.core, ...)` before `run_once()` claims tasks.

Change claim types:

```python
task_types={TaskType.VIDEO_GENERATION} | self.executor_registry.supported_task_types()
```

Document in code comments and tests that worker mode counts as executable only because
`GenerationWorker` now claims and runs `TaskType.FRAME_IMAGE_REGENERATION` through the shared executor registry. Do not return `True` for worker mode unless `WorkerCapabilityRegistry` declares the deployment can run that task type.

When constructing the worker-process `TaskManager` or API control-plane manager for worker mode, pass:

```python
worker_capability_registry=StaticWorkerCapabilityRegistry(
    {TaskType.FRAME_IMAGE_REGENERATION}
)
```

Do not set this declaration in API embedded mode or local Streamlit mode. The static declaration is a stage-one deployment configuration; the long-term replacement is worker heartbeat capability.

In `run_once`, branch:

```python
if task.task_type is TaskType.FRAME_IMAGE_REGENERATION:
    result = await self.executor_registry.execute(
        task.task_type,
        task_id=task.task_id,
        request_params=task.request_params or {},
        progress_dispatcher=ProgressDispatcher([progress_sink]),
    )
else:
    params = self._build_generation_params(...)
    result = await self.core.generate_video(**params)
```

- [ ] **Step 8: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py::test_worker_claims_frame_image_regeneration_tasks
```

Expected: all tests pass.

- [ ] **Step 9: Commit and push**

```powershell
git add -- api/workbench/frame_image_regeneration.py api/workbench/executor_factory.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py api/app.py web/state/session.py tests/test_storyboard_workbench_task_submitter.py tests/test_worker_execution.py
git commit -m "feat: 执行分镜帧图片重抽任务"
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
        def get_capabilities(self):
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
- `InProcessStoryboardWorkbenchClient.get_capabilities()` must call `pixelle_video.storyboard_workbench_task_submitter.get_capabilities()` when a submitter exists, and report unavailable when it does not.
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

- [ ] **Step 1: Run Workbench focused test set**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_app_platform_dependencies.py tests/test_worker_execution.py
```

Expected: pass.

- [ ] **Step 2: Run lint and diff checks**

Run:

```powershell
ruff check api/workbench api/platform_dependencies.py api/dependencies.py api/app.py api/routers/storyboard_workbench.py api/schemas/storyboard_workbench.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py web/state/session.py web/workbench web/state/workbench_client.py web/utils/storyboard_workbench_api.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
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
python -m pytest -q tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_app_platform_dependencies.py tests/test_worker_execution.py tests/test_style_config_storyboard_planning_ui.py
```

Expected: pass.

- [ ] Run:

```powershell
ruff check api/workbench api/platform_dependencies.py api/dependencies.py api/app.py api/routers/storyboard_workbench.py api/schemas/storyboard_workbench.py api/tasks/manager.py api/tasks/factory.py api/tasks/worker.py web/state/session.py web/workbench web/state/workbench_client.py web/utils/storyboard_workbench_api.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_task_submitter.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
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

- Spec coverage: covers client contract, display contract, HTTP mode, in-process mode, factory lifecycle, submitter injection, capability endpoint, and real task execution.
- Placeholder scan: no unfinished placeholder content and no fake local disablement as final state.
- Type consistency: stable names are `StoryboardWorkbenchTaskSubmitter`, `TaskManagerStoryboardWorkbenchTaskSubmitter`, `get_capabilities`, `list_image_candidates`, `select_image_candidate`, `regenerate_frame_image`, and `get_prompt_plan_stale_summary`.
- Scope: Storyboard Workbench only. AssetBible / Stage2 HTTP clients are left untouched.
- Atomicity check: no task leaves Workbench UI switched to a local skeleton that cannot satisfy existing list/select/stale/regenerate submission flows.
- Debt check: regenerate availability is sourced from real submitter/executor wiring, not hardcoded booleans or disabled-button workaround.
