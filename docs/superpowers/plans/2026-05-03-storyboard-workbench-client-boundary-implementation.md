# Storyboard Workbench Client Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Storyboard Workbench UI depend on a `StoryboardWorkbenchClient` contract instead of directly depending on `8001`/HTTP helpers.

**Architecture:** Introduce a small client interface with HTTP and in-process implementations. Streamlit components receive or resolve a client and no longer import `web.utils.storyboard_workbench_api` / `web.utils.stale_api` directly. Local Streamlit defaults to in-process; remote / flowgram deployment explicitly uses HTTP.

**Tech Stack:** Python, Streamlit, FastAPI service contracts, pytest, ruff.

---

## File Structure

- Create `web/workbench/__init__.py`
  - Exports client protocol and concrete clients.
- Create `web/workbench/client.py`
  - Defines `StoryboardWorkbenchClient` protocol and `StoryboardWorkbenchClientError`.
- Create `web/workbench/http_client.py`
  - Wraps existing `web.utils.storyboard_workbench_api` and `web.utils.stale_api`.
- Create `web/workbench/inprocess_client.py`
  - Calls local platform services and stores directly.
- Create `web/state/workbench_client.py`
  - Resolves and caches the current client from Streamlit session/config.
- Modify `web/components/storyboard_workbench_panel.py`
  - Replace direct HTTP loader/selector/regenerator defaults with a client.
- Modify `web/components/storyboard_workbench_stale.py`
  - Replace direct stale HTTP loader with a client.
- Modify `web/components/storyboard_preview.py`
  - Pass `workbench_client` through to Workbench and stale components.
- Modify `web/pages/3_🧭_Storyboard_Workbench.py`
  - Resolve one client and pass it to preview renderer.
- Test `tests/test_storyboard_workbench_client.py`
  - Client protocol/factory/http adapter/in-process adapter behavior.
- Test updates:
  - `tests/test_storyboard_workbench_stale_ui.py`
  - `tests/test_storyboard_workbench_page.py`
  - Existing API helper tests remain valid.

---

## Task 1: Define Client Contract And HTTP Adapter

**Files:**
- Create: `web/workbench/__init__.py`
- Create: `web/workbench/client.py`
- Create: `web/workbench/http_client.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write failing tests for HTTP client wrapper**

Add to `tests/test_storyboard_workbench_client.py`:

```python
from web.workbench.http_client import HttpStoryboardWorkbenchClient


def test_http_workbench_client_delegates_candidate_actions(monkeypatch):
    calls = []

    def list_candidates(**kwargs):
        calls.append(("list", kwargs))
        return {"candidates": []}

    def select_candidate(**kwargs):
        calls.append(("select", kwargs))
        return {"success": True, "state": {"selected_image_version_id": "version_1"}}

    def regenerate(**kwargs):
        calls.append(("regenerate", kwargs))
        return {"success": True, "task_id": "task_1"}

    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api",
        candidate_loader=list_candidates,
        candidate_selector=select_candidate,
        frame_regenerator=regenerate,
        stale_summary_loader=lambda **_kwargs: {"success": True, "stale_summary": {"is_stale": False}},
    )

    assert client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    ) == {"candidates": []}
    assert client.select_image_candidate(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
        version_id="version_1",
        actor_id="actor_1",
    )["success"] is True
    assert client.regenerate_frame_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )["task_id"] == "task_1"

    assert calls == [
        (
            "list",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_1",
                "frame_id": "frame_1",
                "artifact_id": "artifact_1",
            },
        ),
        (
            "select",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_1",
                "frame_id": "frame_1",
                "artifact_id": "artifact_1",
                "version_id": "version_1",
                "actor_id": "actor_1",
            },
        ),
        (
            "regenerate",
            {
                "api_base_url": "http://localhost:8001/api",
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_1",
                "frame_id": "frame_1",
                "artifact_id": "artifact_1",
            },
        ),
    ]


def test_http_workbench_client_delegates_stale_summary():
    calls = []
    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api/",
        candidate_loader=lambda **_kwargs: {"candidates": []},
        candidate_selector=lambda **_kwargs: {"success": True},
        frame_regenerator=lambda **_kwargs: {"success": True},
        stale_summary_loader=lambda **kwargs: calls.append(kwargs)
        or {"success": True, "stale_summary": {"target_id": "prompt_plan_1"}},
    )

    result = client.get_prompt_plan_stale_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        prompt_plan_id="prompt_plan_1",
    )

    assert result["stale_summary"]["target_id"] == "prompt_plan_1"
    assert calls == [
        {
            "api_base_url": "http://localhost:8001/api",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "target_type": "prompt_plan",
            "target_id": "prompt_plan_1",
        }
    ]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: fail with `ModuleNotFoundError: No module named 'web.workbench'`.

- [ ] **Step 3: Implement client protocol**

Create `web/workbench/client.py`:

```python
from __future__ import annotations

from typing import Any, Protocol


class StoryboardWorkbenchClientError(RuntimeError):
    """Raised when a Workbench client cannot complete a requested operation."""


class StoryboardWorkbenchClient(Protocol):
    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def select_image_candidate(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]: ...

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]: ...
```

Create `web/workbench/http_client.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pixelle_video.platform_context import DEFAULT_API_BASE_URL
from web.utils.stale_api import get_stale_target_summary
from web.utils.storyboard_workbench_api import (
    list_storyboard_image_candidates,
    regenerate_storyboard_frame_image,
    select_storyboard_image_candidate,
)


class HttpStoryboardWorkbenchClient:
    def __init__(
        self,
        *,
        api_base_url: str = DEFAULT_API_BASE_URL,
        candidate_loader: Callable[..., dict[str, Any]] = list_storyboard_image_candidates,
        candidate_selector: Callable[..., dict[str, Any]] = select_storyboard_image_candidate,
        frame_regenerator: Callable[..., dict[str, Any]] = regenerate_storyboard_frame_image,
        stale_summary_loader: Callable[..., dict[str, Any]] = get_stale_target_summary,
    ) -> None:
        self.api_base_url = str(api_base_url or DEFAULT_API_BASE_URL).strip().rstrip("/")
        self._candidate_loader = candidate_loader
        self._candidate_selector = candidate_selector
        self._frame_regenerator = frame_regenerator
        self._stale_summary_loader = stale_summary_loader

    def list_image_candidates(self, **kwargs) -> dict[str, Any]:
        return self._candidate_loader(api_base_url=self.api_base_url, **kwargs)

    def select_image_candidate(self, **kwargs) -> dict[str, Any]:
        return self._candidate_selector(api_base_url=self.api_base_url, **kwargs)

    def regenerate_frame_image(self, **kwargs) -> dict[str, Any]:
        return self._frame_regenerator(api_base_url=self.api_base_url, **kwargs)

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]:
        return self._stale_summary_loader(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            target_type="prompt_plan",
            target_id=prompt_plan_id,
        )
```

Create `web/workbench/__init__.py`:

```python
from web.workbench.client import StoryboardWorkbenchClient, StoryboardWorkbenchClientError
from web.workbench.http_client import HttpStoryboardWorkbenchClient

__all__ = [
    "HttpStoryboardWorkbenchClient",
    "StoryboardWorkbenchClient",
    "StoryboardWorkbenchClientError",
]
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/workbench/__init__.py web/workbench/client.py web/workbench/http_client.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 增加分镜工作台客户端合同"
```

---

## Task 2: Replace Workbench Panel HTTP Dependencies With Client

**Files:**
- Modify: `web/components/storyboard_workbench_panel.py`
- Test: `tests/test_storyboard_workbench_panel_client.py` or existing `tests/test_storyboard_workbench_stale_ui.py`

- [ ] **Step 1: Write failing UI test**

Add a test that passes a fake client to `render_storyboard_workbench_panel()` and asserts no `api_base_url` argument is needed:

```python
def test_storyboard_workbench_panel_uses_client_for_candidates():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    class FakeClient:
        def __init__(self):
            self.calls = []

        def list_image_candidates(self, **kwargs):
            self.calls.append(("list", kwargs))
            return {
                "candidates": [
                    {
                        "artifact_id": "artifact_1",
                        "version_id": "version_1",
                        "frame_id": "frame_1",
                        "prompt_plan_id": "prompt_plan_1",
                        "status": "ready",
                        "storage_key": "objects/frame.png",
                    }
                ]
            }

    fake_ui = _FakeUI()
    client = FakeClient()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=client,
    )

    assert client.calls == [
        (
            "list",
            {
                "workspace_id": "workspace_1",
                "storyboard_id": "storyboard_1",
                "frame_id": "frame_1",
                "artifact_id": "artifact_1",
            },
        )
    ]
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py::test_storyboard_workbench_panel_uses_client_for_candidates
```

Expected: fail because `workbench_client` is not accepted.

- [ ] **Step 3: Modify panel implementation**

In `web/components/storyboard_workbench_panel.py`:

- Remove imports from `web.utils.storyboard_workbench_api`.
- Add `workbench_client` parameter.
- Resolve default via `web.state.workbench_client.resolve_storyboard_workbench_client`.
- Call `client.list_image_candidates(...)`, `client.select_image_candidate(...)`, and `client.regenerate_frame_image(...)`.
- Keep `api_base_url` only as deprecated compatibility input if needed for image display until Task 4; do not pass it to client operations.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_client.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/components/storyboard_workbench_panel.py tests/test_storyboard_workbench_stale_ui.py
git commit -m "refactor: 让分镜候选图面板依赖客户端合同"
```

---

## Task 3: Replace Stale Panel HTTP Dependency With Client

**Files:**
- Modify: `web/components/storyboard_workbench_stale.py`
- Test: `tests/test_storyboard_workbench_stale_ui.py`

- [ ] **Step 1: Write failing stale panel client test**

Add:

```python
def test_prompt_plan_stale_panel_uses_workbench_client():
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

    rendered = []

    render_prompt_plan_stale_panel(
        "prompt_plan_1",
        ui=_FakeUI(),
        translate=lambda key, **_kwargs: key,
        workbench_client=FakeClient(),
        panel_renderer=lambda stale_summary, **_kwargs: rendered.append(stale_summary),
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
    assert rendered[0]["target_id"] == "prompt_plan_1"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py::test_prompt_plan_stale_panel_uses_workbench_client
```

Expected: fail because `workbench_client` is not accepted.

- [ ] **Step 3: Modify stale component**

In `web/components/storyboard_workbench_stale.py`:

- Remove direct import of `get_stale_target_summary`.
- Add `workbench_client` parameter.
- Resolve default via `resolve_storyboard_workbench_client`.
- Call `client.get_prompt_plan_stale_summary(...)`.
- Keep fail-closed behavior.

- [ ] **Step 4: Run focused tests**

```powershell
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_client.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/components/storyboard_workbench_stale.py tests/test_storyboard_workbench_stale_ui.py
git commit -m "refactor: 让分镜依赖雷达依赖客户端合同"
```

---

## Task 4: Client Factory With HTTP Mode And Default In-process Mode

**Files:**
- Create: `web/state/workbench_client.py`
- Modify: `web/workbench/__init__.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write factory tests**

Add:

```python
def test_workbench_client_factory_defaults_to_inprocess(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=object())

    assert isinstance(client, InProcessStoryboardWorkbenchClient)
    assert session_state["storyboard_workbench_client"] is client


def test_workbench_client_factory_uses_http_when_configured(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client
    from web.workbench.http_client import HttpStoryboardWorkbenchClient

    monkeypatch.setenv("PIXELLE_WORKBENCH_CLIENT_MODE", "http")
    session_state = {"api_base_url": "http://remote.example/api"}

    client = resolve_storyboard_workbench_client(session_state)

    assert isinstance(client, HttpStoryboardWorkbenchClient)
    assert client.api_base_url == "http://remote.example/api"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py::test_workbench_client_factory_defaults_to_inprocess tests/test_storyboard_workbench_client.py::test_workbench_client_factory_uses_http_when_configured
```

Expected: fail because factory/in-process client does not exist.

- [ ] **Step 3: Add minimal InProcess client shell**

Create `web/workbench/inprocess_client.py` with class skeleton:

```python
from __future__ import annotations

from typing import Any

from web.workbench.client import StoryboardWorkbenchClientError


class InProcessStoryboardWorkbenchClient:
    def __init__(self, *, pixelle_video: Any | None = None) -> None:
        self.pixelle_video = pixelle_video

    def list_image_candidates(self, **_kwargs) -> dict[str, Any]:
        raise StoryboardWorkbenchClientError("in-process workbench client is not fully configured")

    def select_image_candidate(self, **_kwargs) -> dict[str, Any]:
        raise StoryboardWorkbenchClientError("in-process workbench client is not fully configured")

    def regenerate_frame_image(self, **_kwargs) -> dict[str, Any]:
        raise StoryboardWorkbenchClientError("in-process workbench client is not fully configured")

    def get_prompt_plan_stale_summary(self, **_kwargs) -> dict[str, Any]:
        raise StoryboardWorkbenchClientError("in-process workbench client is not fully configured")
```

Create `web/state/workbench_client.py`:

```python
from __future__ import annotations

import os
from collections.abc import MutableMapping
from typing import Any

from pixelle_video.platform_context import DEFAULT_API_BASE_URL, resolve_api_base_url
from web.workbench.http_client import HttpStoryboardWorkbenchClient
from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

STORYBOARD_WORKBENCH_CLIENT_KEY = "storyboard_workbench_client"


def resolve_storyboard_workbench_client(
    session_state: MutableMapping[str, Any],
    *,
    pixelle_video: Any | None = None,
):
    existing = session_state.get(STORYBOARD_WORKBENCH_CLIENT_KEY)
    if existing is not None:
        return existing

    mode = str(
        session_state.get("workbench_client_mode")
        or os.getenv("PIXELLE_WORKBENCH_CLIENT_MODE")
        or "inprocess"
    ).strip().lower()
    if mode == "http":
        client = HttpStoryboardWorkbenchClient(
            api_base_url=resolve_api_base_url(session_state, default=DEFAULT_API_BASE_URL)
        )
    else:
        client = InProcessStoryboardWorkbenchClient(pixelle_video=pixelle_video)
    session_state[STORYBOARD_WORKBENCH_CLIENT_KEY] = client
    return client
```

Update `web/workbench/__init__.py` to export `InProcessStoryboardWorkbenchClient`.

- [ ] **Step 4: Run factory tests**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/workbench/inprocess_client.py web/state/workbench_client.py web/workbench/__init__.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 增加分镜工作台客户端工厂"
```

---

## Task 5: Wire Preview And Workbench Page To The Client

**Files:**
- Modify: `web/components/storyboard_preview.py`
- Modify: `web/pages/3_🧭_Storyboard_Workbench.py`
- Test: `tests/test_storyboard_workbench_page.py`

- [ ] **Step 1: Write failing page test**

Update page test to assert resolved client is passed to preview renderer:

```python
def test_storyboard_workbench_page_passes_workbench_client_to_preview(monkeypatch):
    page = _load_workbench_page()
    fake_ui = _FakeUI()
    fake_ui.session_state["storyboard_preview_snapshot"] = _planning_snapshot()
    client = object()
    calls = []

    monkeypatch.setattr(
        page,
        "resolve_storyboard_workbench_client",
        lambda session_state: client,
    )

    def preview_renderer(snapshot, *, stale_context=None, workbench_client=None):
        calls.append(workbench_client)
        return []

    page.render_storyboard_workbench_page(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        preview_renderer=preview_renderer,
    )

    assert calls == [client]
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_page.py::test_storyboard_workbench_page_passes_workbench_client_to_preview
```

Expected: fail because page does not pass `workbench_client`.

- [ ] **Step 3: Update preview/page signatures**

In `render_storyboard_preview()` add:

```python
workbench_client=None
```

Pass `workbench_client` to stale renderer and workbench renderer.

In Workbench page:

```python
workbench_client = resolve_storyboard_workbench_client(getattr(ui, "session_state", {}))
preview_renderer(..., workbench_client=workbench_client)
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_stale_ui.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_page.py
git commit -m "refactor: 通过客户端连接分镜工作台页面"
```

---

## Task 6: Implement In-process Client Operations

**Files:**
- Modify: `web/workbench/inprocess_client.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write in-process behavior tests**

Add tests using fake service/state store:

```python
def test_inprocess_client_lists_image_candidates_with_service():
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    class Version:
        def __init__(self):
            self.artifact_id = "artifact_1"
            self.version_id = "version_1"
            self.frame_id = "frame_1"
            self.source_prompt_plan_id = "prompt_plan_1"
            self.storage_key = "objects/frame.png"
            self.status = type("Status", (), {"value": "ready"})()
            self.provider = "comfyui"
            self.width = 1024
            self.height = 1024
            self.trace_event_id = "trace_1"
            self.created_at = "2026-05-03T00:00:00Z"
            self.metadata = {}

    class Service:
        async def list_image_candidates(self, *, workspace_id, artifact_id):
            return [
                type(
                    "Candidate",
                    (),
                    {
                        "to_dict": lambda _self: {
                            "artifact_id": artifact_id,
                            "version_id": "version_1",
                            "frame_id": "frame_1",
                            "prompt_plan_id": "prompt_plan_1",
                            "storage_key": "objects/frame.png",
                            "status": "ready",
                        }
                    },
                )()
            ]

    core = type("Core", (), {"storyboard_workbench_service": Service()})()
    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)

    result = client.list_image_candidates(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    assert result["workspace_id"] == "workspace_1"
    assert result["storyboard_id"] == "storyboard_1"
    assert result["candidates"][0]["version_id"] == "version_1"
```

Add similar tests for stale summary and missing service fail closed.

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py::test_inprocess_client_lists_image_candidates_with_service
```

Expected: fail because in-process methods are not implemented.

- [ ] **Step 3: Implement list and stale first**

Use `web.utils.async_helpers.run_async()` to call async services from Streamlit sync context.

Implement:

- `list_image_candidates()`
- `get_prompt_plan_stale_summary()`

For stale:

```python
StaleDependencyReadService(
    edge_repository=core.dependency_edge_repository,
    stale_repository=core.stale_mark_repository,
).get_target_summary(...)
```

- [ ] **Step 4: Implement select and regenerate**

Implement state load/save by using `core.storyboard_workbench_state_store`.

For regenerate:

- If `core.task_manager` exists, reserve/reuse task.
- If missing, raise `StoryboardWorkbenchClientError("task manager is not configured")`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add -- web/workbench/inprocess_client.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 实现本地分镜工作台客户端"
```

---

## Task 7: Remove UI Direct HTTP Coupling Regression

**Files:**
- Modify tests only unless regression fails.
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Add source-level regression test**

Add:

```python
from pathlib import Path


def test_storyboard_workbench_ui_does_not_import_http_helpers():
    repo_root = Path(__file__).resolve().parents[1]
    ui_files = [
        repo_root / "web" / "components" / "storyboard_workbench_panel.py",
        repo_root / "web" / "components" / "storyboard_workbench_stale.py",
        repo_root / "web" / "components" / "storyboard_preview.py",
        repo_root / "web" / "pages" / "3_🧭_Storyboard_Workbench.py",
    ]
    forbidden = (
        "web.utils.storyboard_workbench_api",
        "web.utils.stale_api",
        "httpx",
        "localhost:8001",
    )

    for path in ui_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not depend on {token}"
```

- [ ] **Step 2: Run full Workbench test set**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py
```

Expected: pass.

- [ ] **Step 3: Run lint and diff check**

Run:

```powershell
ruff check web/workbench web/state/workbench_client.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_client.py
git diff --check
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add -- tests/test_storyboard_workbench_client.py
git commit -m "test: 防止分镜工作台重新依赖 HTTP 端口"
```

---

## Final Verification

- [ ] Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py
```

Expected: pass.

- [ ] Run:

```powershell
ruff check web/workbench web/state/workbench_client.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_client.py
git diff --check
```

Expected: pass.

- [ ] Push after the final atomic commit:

```powershell
git push origin dev
```

---

## Self-Review

- Spec coverage: covers client contract, HTTP mode, in-process mode, UI rewiring, flowgram/remote boundary, and no-port regression.
- Placeholder scan: no TBD / TODO / "implement later" placeholders.
- Type consistency: method names are stable across tasks: `list_image_candidates`, `select_image_candidate`, `regenerate_frame_image`, `get_prompt_plan_stale_summary`.
- Scope: Storyboard Workbench only. AssetBible/Stage2 HTTP clients are left untouched.
