# Storyboard Workbench Client Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Storyboard Workbench UI depend on a `StoryboardWorkbenchClient` contract that also owns artifact display and capability exposure, so local Streamlit no longer depends on `8001` or `api_base_url`.

**Architecture:** Introduce a client interface with explicit capability and display contracts, plus HTTP and in-process implementations. Streamlit components receive or resolve one client, render `image_display` payloads, and stop importing transport or display URL helpers directly. Factory lifecycle is keyed by mode and core identity, and local regenerate is capability-gated instead of optimistic.

**Tech Stack:** Python, Streamlit, FastAPI service contracts, pytest, ruff.

---

## File Structure

- Create `web/workbench/__init__.py`
  - Exports client protocol and concrete clients.
- Create `web/workbench/client.py`
  - Defines the operation contract, capability contract, and error type.
- Create `web/workbench/display.py`
  - Normalizes and validates `image_display` payloads.
- Create `web/workbench/http_client.py`
  - Wraps existing `web.utils.storyboard_workbench_api` / `web.utils.stale_api` and converts candidate URLs into display payloads.
- Create `web/workbench/inprocess_protocols.py`
  - Declares optional local-only dependency protocols for artifact display and regenerate submission.
- Create `web/workbench/inprocess_client.py`
  - Calls local platform services and stores directly, consumes artifacts registered by `StoryboardWorkbenchArtifactBridge`, and builds local display payloads without `api_base_url`.
- Create `web/state/workbench_client.py`
  - Resolves mode and caches only fully configured clients.
- Modify `web/components/storyboard_workbench_panel.py`
  - Replace direct HTTP loader/selector/regenerator defaults with a client and capability-gated regenerate button.
- Modify `web/components/storyboard_workbench_stale.py`
  - Replace direct stale HTTP loader with a client.
- Modify `web/components/storyboard_preview.py`
  - Pass `workbench_client` through to Workbench and stale components.
- Modify `web/pages/3_🧭_Storyboard_Workbench.py`
  - Resolve mode, load local `PixelleVideoCore` when needed, then resolve one client.
- Test `tests/test_storyboard_workbench_client.py`
  - Client contract, display contract, factory lifecycle, HTTP adapter, in-process adapter behavior.
- Test updates:
  - `tests/test_storyboard_workbench_stale_ui.py`
  - `tests/test_storyboard_workbench_page.py`
  - `tests/test_storyboard_workbench_panel_ui.py`

---

## Task 1: Define Client, Display, And HTTP Contracts

**Files:**
- Create: `web/workbench/__init__.py`
- Create: `web/workbench/client.py`
- Create: `web/workbench/display.py`
- Create: `web/workbench/http_client.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write failing tests for HTTP display normalization and capabilities**

Add to `tests/test_storyboard_workbench_client.py`:

```python
from web.workbench.http_client import HttpStoryboardWorkbenchClient


def test_http_workbench_client_normalizes_candidate_display_urls():
    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api/",
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
        candidate_selector=lambda **_kwargs: {"success": True},
        frame_regenerator=lambda **_kwargs: {"success": True, "task_id": "task_1"},
        stale_summary_loader=lambda **_kwargs: {"success": True, "stale_summary": {"is_stale": False}},
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


def test_http_workbench_client_reports_regenerate_capability():
    client = HttpStoryboardWorkbenchClient(
        api_base_url="http://localhost:8001/api",
        candidate_loader=lambda **_kwargs: {"candidates": []},
        candidate_selector=lambda **_kwargs: {"success": True},
        frame_regenerator=lambda **_kwargs: {"success": True, "task_id": "task_1"},
        stale_summary_loader=lambda **_kwargs: {"success": True, "stale_summary": {"is_stale": False}},
    )

    assert client.get_capabilities() == {
        "can_regenerate_frame_image": True,
        "regenerate_unavailable_reason": None,
    }
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: fail with `ModuleNotFoundError: No module named 'web.workbench'`.

- [ ] **Step 3: Implement the client, display, and HTTP modules**

Create `web/workbench/client.py`:

```python
from __future__ import annotations

from typing import Any, Protocol


class StoryboardWorkbenchClientError(RuntimeError):
    """Raised when a Workbench client cannot complete a requested operation."""


class StoryboardWorkbenchClient(Protocol):
    def get_capabilities(self) -> dict[str, Any]: ...

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

Create `web/workbench/display.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from web.utils.artifact_display_urls import artifact_url_for_streamlit


def build_remote_image_display(value: str | None, *, api_base_url: str) -> dict[str, str] | None:
    display_url = artifact_url_for_streamlit(value, api_base_url=api_base_url)
    if not display_url:
        return None
    return {"kind": "url", "url": display_url}


def normalize_candidate_with_remote_display(
    candidate: Mapping[str, Any],
    *,
    api_base_url: str,
) -> dict[str, Any]:
    payload = dict(candidate)
    payload.pop("url", None)
    image_display = build_remote_image_display(candidate.get("url"), api_base_url=api_base_url)
    if image_display is not None:
        payload["image_display"] = image_display
    return payload
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
from web.workbench.display import normalize_candidate_with_remote_display


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

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "can_regenerate_frame_image": True,
            "regenerate_unavailable_reason": None,
        }

    def list_image_candidates(self, **kwargs) -> dict[str, Any]:
        response = dict(self._candidate_loader(api_base_url=self.api_base_url, **kwargs))
        response["candidates"] = [
            normalize_candidate_with_remote_display(candidate, api_base_url=self.api_base_url)
            for candidate in response.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        return response

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
git add -- web/workbench/__init__.py web/workbench/client.py web/workbench/display.py web/workbench/http_client.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 增加分镜工作台客户端与显示合同"
```

---

## Task 2: Add In-process Dependency Protocols And Safe Factory Lifecycle

**Files:**
- Create: `web/workbench/inprocess_protocols.py`
- Create: `web/state/workbench_client.py`
- Create: `web/workbench/inprocess_client.py`
- Modify: `web/workbench/__init__.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write failing factory lifecycle tests**

Add to `tests/test_storyboard_workbench_client.py`:

```python
def test_workbench_client_factory_does_not_cache_inprocess_client_without_core(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    client = resolve_storyboard_workbench_client(session_state, pixelle_video=None)

    assert client is None
    assert "storyboard_workbench_client" not in session_state


def test_workbench_client_factory_rebuilds_when_core_identity_changes(monkeypatch):
    from web.state.workbench_client import resolve_storyboard_workbench_client

    monkeypatch.delenv("PIXELLE_WORKBENCH_CLIENT_MODE", raising=False)
    session_state = {}

    first = resolve_storyboard_workbench_client(session_state, pixelle_video=object())
    second = resolve_storyboard_workbench_client(session_state, pixelle_video=object())

    assert first is not None
    assert second is not None
    assert first is not second
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py::test_workbench_client_factory_does_not_cache_inprocess_client_without_core tests/test_storyboard_workbench_client.py::test_workbench_client_factory_rebuilds_when_core_identity_changes
```

Expected: fail because the factory and in-process client do not exist yet.

- [ ] **Step 3: Implement local-only protocols, skeleton in-process client, and lifecycle-safe factory**

Create `web/workbench/inprocess_protocols.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LocalReadableArtifactSource(Protocol):
    async def get_local_file_uri(self, storage_key: str) -> str: ...


@runtime_checkable
class StoryboardWorkbenchTaskSubmitter(Protocol):
    async def reserve_frame_image_regeneration(
        self,
        *,
        generation_fingerprint: str,
        request_params: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
```

Create `web/workbench/inprocess_client.py`:

```python
from __future__ import annotations

from typing import Any

from web.workbench.client import StoryboardWorkbenchClientError


class InProcessStoryboardWorkbenchClient:
    def __init__(self, *, pixelle_video: Any) -> None:
        self.pixelle_video = pixelle_video

    def get_capabilities(self) -> dict[str, Any]:
        submitter = getattr(self.pixelle_video, "storyboard_workbench_task_submitter", None)
        if submitter is None:
            return {
                "can_regenerate_frame_image": False,
                "regenerate_unavailable_reason": "task submitter is not configured",
            }
        return {
            "can_regenerate_frame_image": True,
            "regenerate_unavailable_reason": None,
        }

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
STORYBOARD_WORKBENCH_CLIENT_CACHE_KEY = "storyboard_workbench_client_cache_key"


def resolve_workbench_client_mode(session_state: MutableMapping[str, Any]) -> str:
    return str(
        session_state.get("workbench_client_mode")
        or os.getenv("PIXELLE_WORKBENCH_CLIENT_MODE")
        or "inprocess"
    ).strip().lower()


def resolve_storyboard_workbench_client(
    session_state: MutableMapping[str, Any],
    *,
    pixelle_video: Any | None = None,
):
    mode = resolve_workbench_client_mode(session_state)
    if mode == "http":
        cache_key = ("http", resolve_api_base_url(session_state, default=DEFAULT_API_BASE_URL))
        existing = session_state.get(STORYBOARD_WORKBENCH_CLIENT_KEY)
        if existing is not None and session_state.get(STORYBOARD_WORKBENCH_CLIENT_CACHE_KEY) == cache_key:
            return existing
        client = HttpStoryboardWorkbenchClient(api_base_url=cache_key[1])
        session_state[STORYBOARD_WORKBENCH_CLIENT_KEY] = client
        session_state[STORYBOARD_WORKBENCH_CLIENT_CACHE_KEY] = cache_key
        return client

    if pixelle_video is None:
        return None

    cache_key = ("inprocess", id(pixelle_video))
    existing = session_state.get(STORYBOARD_WORKBENCH_CLIENT_KEY)
    if existing is not None and session_state.get(STORYBOARD_WORKBENCH_CLIENT_CACHE_KEY) == cache_key:
        return existing

    client = InProcessStoryboardWorkbenchClient(pixelle_video=pixelle_video)
    session_state[STORYBOARD_WORKBENCH_CLIENT_KEY] = client
    session_state[STORYBOARD_WORKBENCH_CLIENT_CACHE_KEY] = cache_key
    return client
```

Update `web/workbench/__init__.py` to export `InProcessStoryboardWorkbenchClient`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/workbench/inprocess_protocols.py web/workbench/inprocess_client.py web/state/workbench_client.py web/workbench/__init__.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 增加分镜工作台客户端生命周期与本地依赖协议"
```

---

## Task 3: Rewire Workbench UI To The Client And Display Contract

**Files:**
- Modify: `web/components/storyboard_workbench_panel.py`
- Modify: `web/components/storyboard_workbench_stale.py`
- Modify: `web/components/storyboard_preview.py`
- Modify: `web/pages/3_🧭_Storyboard_Workbench.py`
- Test: `tests/test_storyboard_workbench_panel_ui.py`
- Test: `tests/test_storyboard_workbench_stale_ui.py`
- Test: `tests/test_storyboard_workbench_page.py`

- [ ] **Step 1: Write failing UI tests for client-only rendering**

Add to `tests/test_storyboard_workbench_panel_ui.py`:

```python
def test_storyboard_workbench_panel_renders_bytes_display_without_api_base_url():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    class FakeClient:
        def get_capabilities(self):
            return {
                "can_regenerate_frame_image": False,
                "regenerate_unavailable_reason": "task submitter is not configured",
            }

        def list_image_candidates(self, **_kwargs):
            return {
                "candidates": [
                    {
                        "artifact_id": "artifact_1",
                        "version_id": "version_1",
                        "frame_id": "frame_1",
                        "status": "ready",
                        "image_display": {
                            "kind": "bytes",
                            "data": b"fake-image",
                            "mime_type": "image/png",
                        },
                    }
                ]
            }

        def select_image_candidate(self, **_kwargs):
            return {"success": True}

        def regenerate_frame_image(self, **_kwargs):
            return {"success": False, "code": "regenerate_unavailable"}

    fake_ui = _WorkbenchFakeUI()

    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=FakeClient(),
    )

    assert fake_ui.images[0]["image"] == b"fake-image"
    assert all("api_base_url" not in button for button in fake_ui.buttons)
```

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

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_panel_ui.py::test_storyboard_workbench_panel_renders_bytes_display_without_api_base_url tests/test_storyboard_workbench_stale_ui.py::test_prompt_plan_stale_panel_uses_workbench_client_without_api_base_url tests/test_storyboard_workbench_page.py::test_storyboard_workbench_page_passes_client_to_preview
```

Expected: fail because UI still depends on `api_base_url` and does not accept `workbench_client`.

- [ ] **Step 3: Modify UI components to use only the client contract**

In `web/components/storyboard_workbench_panel.py`:

- Remove imports from `web.utils.storyboard_workbench_api`.
- Remove direct use of `artifact_url_for_streamlit`.
- Add `workbench_client` parameter.
- Call `client.list_image_candidates(...)`, `client.select_image_candidate(...)`, and `client.regenerate_frame_image(...)`.
- Render `candidate["image_display"]`:

```python
def _render_candidate_image(candidate: Mapping[str, Any], *, version_id: str, ui) -> None:
    display = candidate.get("image_display")
    if isinstance(display, Mapping):
        if display.get("kind") == "url" and display.get("url"):
            ui.image(display["url"], caption=version_id, width="stretch")
            return
        if display.get("kind") == "bytes" and display.get("data"):
            ui.image(display["data"], caption=version_id, width="stretch")
            return
    ui.caption(version_id)
```

- Use capabilities to disable regenerate:

```python
capabilities = client.get_capabilities()
can_regenerate = bool(capabilities.get("can_regenerate_frame_image"))
reason = _first_text(capabilities.get("regenerate_unavailable_reason"))
clicked = ui.button(
    translate("workbench.panel.regenerate"),
    key=f"workbench_regenerate_{context['frame_id']}",
    disabled=not can_regenerate,
)
if not can_regenerate and reason:
    ui.caption(reason)
```

In `web/components/storyboard_workbench_stale.py`:

- Remove direct import of `get_stale_target_summary`.
- Add `workbench_client` parameter.
- Call `client.get_prompt_plan_stale_summary(...)`.

In `web/components/storyboard_preview.py`:

- Replace `stale_context` with `workbench_client`.
- Pass `workbench_client` to stale and workbench renderers.
- Stop passing `api_base_url`.

In `web/pages/3_🧭_Storyboard_Workbench.py`:

- Resolve mode first.
- In `inprocess` mode call `get_pixelle_video()` before resolving the client.
- Pass `workbench_client` into `preview_renderer(...)`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
git commit -m "refactor: 让分镜工作台界面只依赖客户端合同"
```

---

## Task 4: Implement In-process Candidate, Select, Stale, And Local Display

**Files:**
- Modify: `web/workbench/inprocess_client.py`
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Write failing in-process behavior tests**

Add to `tests/test_storyboard_workbench_client.py`:

```python
from pathlib import Path


def test_inprocess_client_lists_candidates_with_local_bytes_display(tmp_path):
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"png-bytes")

    class Service:
        async def list_image_candidates(self, *, workspace_id, artifact_id):
            return [
                {
                    "artifact_id": artifact_id,
                    "version_id": "version_1",
                    "frame_id": "frame_1",
                    "prompt_plan_id": "prompt_plan_1",
                    "storage_key": "artifacts/workspace_1/frame.png",
                    "status": "ready",
                }
            ]

    class ObjectStore:
        async def get_local_file_uri(self, storage_key):
            assert storage_key == "artifacts/workspace_1/frame.png"
            return image_path.as_uri()

    core = type(
        "Core",
        (),
        {
            "storyboard_workbench_service": Service(),
            "artifact_object_store": ObjectStore(),
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


def test_inprocess_client_reads_stale_summary_from_local_service():
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    class EdgeRepository:
        async def list_downstream_edges(self, *args, **kwargs):
            return []

    class StaleRepository:
        async def list_stale_marks(self, *args, **kwargs):
            return []

    core = type(
        "Core",
        (),
        {
            "dependency_edge_repository": EdgeRepository(),
            "stale_mark_repository": StaleRepository(),
        },
    )()

    client = InProcessStoryboardWorkbenchClient(pixelle_video=core)
    response = client.get_prompt_plan_stale_summary(
        workspace_id="workspace_1",
        project_id="project_1",
        prompt_plan_id="prompt_plan_1",
    )

    assert response["success"] is True
    assert response["stale_summary"]["target_id"] == "prompt_plan_1"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py::test_inprocess_client_lists_candidates_with_local_bytes_display tests/test_storyboard_workbench_client.py::test_inprocess_client_reads_stale_summary_from_local_service
```

Expected: fail because in-process methods are not implemented.

- [ ] **Step 3: Implement local candidate display, stale summary, and selection flow**

In `web/workbench/inprocess_client.py`:

- Use `web.utils.async_helpers.run_async()` to call async services from Streamlit sync context.
- Treat `StoryboardWorkbenchArtifactBridge` as the generation-side registration boundary. The in-process client reads already registered artifact versions and must not create or re-register Workbench artifacts while listing candidates.
- Implement local display loading from `get_local_file_uri(...)`:

```python
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


def _load_image_display_bytes(object_store, storage_key: str) -> dict[str, Any]:
    uri = run_async(object_store.get_local_file_uri(storage_key))
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise StoryboardWorkbenchClientError("local artifact source must return a file URI")
    path = Path(url2pathname(parsed.path))
    data = path.read_bytes()
    return {
        "kind": "bytes",
        "data": data,
        "mime_type": _guess_mime_type(path.suffix.lower()),
    }
```

- Implement `list_image_candidates()` by calling the local service and enriching each candidate with `image_display`.
- Implement `get_prompt_plan_stale_summary()` with `StaleDependencyReadService`.
- Implement `select_image_candidate()` with local state store load/save.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/workbench/inprocess_client.py tests/test_storyboard_workbench_client.py
git commit -m "feat: 实现本地分镜工作台候选图与依赖查询"
```

---

## Task 5: Implement Honest Regenerate Capability Gating

**Files:**
- Modify: `web/workbench/inprocess_client.py`
- Modify: `web/components/storyboard_workbench_panel.py`
- Test: `tests/test_storyboard_workbench_client.py`
- Test: `tests/test_storyboard_workbench_panel_ui.py`

- [ ] **Step 1: Write failing regenerate capability tests**

Add to `tests/test_storyboard_workbench_client.py`:

```python
def test_inprocess_client_reports_regenerate_unavailable_without_submitter():
    from web.workbench.inprocess_client import InProcessStoryboardWorkbenchClient

    client = InProcessStoryboardWorkbenchClient(pixelle_video=object())

    assert client.get_capabilities() == {
        "can_regenerate_frame_image": False,
        "regenerate_unavailable_reason": "task submitter is not configured",
    }


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
                "stale_flags": [],
                "source_prompt_plan_id": "prompt_plan_1",
            }

    class Submitter:
        async def reserve_frame_image_regeneration(self, **kwargs):
            return {
                "success": True,
                "task_id": "task_1",
                "task_type": "frame_image_regeneration",
                "created": True,
                **kwargs,
            }

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
    response = client.regenerate_frame_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
    )

    assert response["success"] is True
    assert response["task_id"] == "task_1"
```

Add to `tests/test_storyboard_workbench_panel_ui.py`:

```python
def test_storyboard_workbench_panel_disables_regenerate_when_capability_missing():
    from web.components.storyboard_workbench_panel import render_storyboard_workbench_panel

    class FakeClient:
        def get_capabilities(self):
            return {
                "can_regenerate_frame_image": False,
                "regenerate_unavailable_reason": "task submitter is not configured",
            }

        def list_image_candidates(self, **_kwargs):
            return {"candidates": []}

    fake_ui = _WorkbenchFakeUI()
    render_storyboard_workbench_panel(
        workspace_id="workspace_1",
        storyboard_id="storyboard_1",
        frame_id="frame_1",
        artifact_id="artifact_1",
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
        workbench_client=FakeClient(),
    )

    regenerate_button = next(button for button in fake_ui.buttons if button["key"] == "workbench_regenerate_frame_1")
    assert regenerate_button["disabled"] is True
    assert "task submitter is not configured" in fake_ui.captions
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py::test_inprocess_client_reports_regenerate_unavailable_without_submitter tests/test_storyboard_workbench_client.py::test_inprocess_client_uses_task_submitter_for_regenerate tests/test_storyboard_workbench_panel_ui.py::test_storyboard_workbench_panel_disables_regenerate_when_capability_missing
```

Expected: fail because regenerate flow and disabled state are not implemented.

- [ ] **Step 3: Implement structured regenerate behavior**

In `web/workbench/inprocess_client.py`:

- If `storyboard_workbench_task_submitter` is absent, return:

```python
{
    "success": False,
    "code": "regenerate_unavailable",
    "reason": "task submitter is not configured",
}
```

- If present:
  - load local state
  - build task request through `StoryboardWorkbenchService.build_frame_image_regeneration_task_request(...)`
  - call `submitter.reserve_frame_image_regeneration(...)`
  - return the submitter response as a plain dict

In `web/components/storyboard_workbench_panel.py`:

- Use capability to disable the button before click.
- If a call still returns `success=False` with `code="regenerate_unavailable"`, show a caption or warning instead of a generic error.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- web/workbench/inprocess_client.py web/components/storyboard_workbench_panel.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py
git commit -m "feat: 让分镜重抽能力按配置显式暴露"
```

---

## Task 6: Lock In The No-8001 Regression Boundary

**Files:**
- Modify tests only unless regression fails.
- Test: `tests/test_storyboard_workbench_client.py`

- [ ] **Step 1: Add source-level regression tests**

Add to `tests/test_storyboard_workbench_client.py`:

```python
from pathlib import Path


def test_storyboard_workbench_ui_does_not_import_transport_or_display_helpers():
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
        "web.utils.artifact_display_urls",
        "httpx",
        "localhost:8001",
        "api_base_url",
    )

    for path in ui_files:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{path} must not depend on {token}"
```

- [ ] **Step 2: Run the Workbench-focused test set**

Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py
```

Expected: all tests pass.

- [ ] **Step 3: Run lint and diff checks**

Run:

```powershell
ruff check web/workbench web/state/workbench_client.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
git diff --check
```

Expected: pass.

- [ ] **Step 4: Commit**

```powershell
git add -- tests/test_storyboard_workbench_client.py
git commit -m "test: 防止分镜工作台重新依赖端口与显示拼接"
```

---

## Final Verification

- [ ] Run:

```powershell
python -m pytest -q tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py tests/test_storyboard_workbench_navigation.py tests/test_storyboard_overrides_state.py tests/test_storyboard_preview_ui.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py
```

Expected: pass.

- [ ] Run:

```powershell
ruff check web/workbench web/state/workbench_client.py web/components/storyboard_workbench_panel.py web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
git diff --check
```

Expected: pass.

- [ ] Push after the final atomic commit:

```powershell
git push origin dev
```

---

## Self-Review

- Spec coverage: covers client contract, display contract, HTTP mode, in-process mode, factory lifecycle, capability-gated regenerate, and no-port regression.
- Placeholder scan: no unfinished placeholder content.
- Type consistency: method names are stable across tasks: `get_capabilities`, `list_image_candidates`, `select_image_candidate`, `regenerate_frame_image`, `get_prompt_plan_stale_summary`.
- Scope: Storyboard Workbench only. AssetBible / Stage2 HTTP clients are left untouched.
