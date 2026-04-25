# API Experience Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five API improvements inspired by MoneyPrinterTurbo while preserving Pixelle's stronger task execution architecture.

**Architecture:** Keep non-video `/api` routes backward-compatible and add new behavior in small, testable increments. The video generation main path follows the Storyboard Generation Contract and rejects old storyboard fields such as `n_scenes` and `split_mode`; new staged video endpoints must use that same contract from their first version. Use shared helpers for response envelopes, file path safety, task pagination, staged video diagnostics, and uploads instead of copying MoneyPrinterTurbo's lightweight thread queue.

**Tech Stack:** FastAPI, Pydantic v2, pytest, pytest-asyncio, existing Pixelle task registry/store abstractions, existing Pixelle video pipeline services.

---

## Scope And Constraints

- Do not use `git worktree`; `AGENTS.md` forbids worktree-based isolation for this repository.
- Keep the existing async generation backend: `api/tasks/registry.py`, `api/tasks/store.py`, `api/tasks/postgres.py`, `api/tasks/lease.py`, and `api/tasks/worker.py`.
- Additive API changes are preferred for non-video APIs. Existing non-video success responses should keep their current shape unless a route is newly introduced.
- Video generation is the exception: the main video path follows the Storyboard Generation Contract and may reject `n_scenes`, `split_mode`, narration-count controls, or other removed storyboard fields.
- Global error responses can be standardized because they only affect failure payload shape, not route paths or successful responses.
- Use atomic commits. Each task below ends with a commit step and only stages files owned by that task.
- Push immediately after every atomic commit. This follows `AGENTS.md`; do not defer pushes until the end unless the user explicitly requests local-only commits.
- Staged video endpoints are diagnostic/building-block endpoints. They intentionally expose a focused subset of the full `/api/video/generate/*` contract; `/api/video/generate/async` remains the canonical full-generation API.
- New staged video endpoints must not provide compatibility for `n_scenes`, `split_mode`, `min_narration_words`, `max_narration_words`, or `narrations` as storyboard upstream input. They must flow through `ScriptGenerationService -> source_text -> StoryboardGenerationService -> StoryboardPlan -> StoryboardEnhancer -> ImagePromptComposer`.

## File Structure

- Create `api/schemas/responses.py`: shared success/error envelope models and FastAPI exception handler installers.
- Modify `api/app.py`: install global exception handlers from `api/schemas/responses.py`.
- Create `tests/test_api_response_envelope.py`: tests for `HTTPException` and validation error envelopes.
- Create `api/schemas/tasks.py`: paginated task list response schema.
- Modify `api/routers/tasks.py`: keep `GET /api/tasks` list behavior and add `GET /api/tasks/page` with `page/page_size/total`.
- Modify `api/tasks/store.py`: add offset/count support to the `TaskStore` contract and in-memory implementation.
- Modify `api/tasks/postgres.py`: add offset/count support to the PostgreSQL task store.
- Modify `api/tasks/manager.py`: expose paginated list and count methods while preserving legacy fallback behavior.
- Modify `tests/test_task_store_memory.py`, `tests/test_task_manager_registry_facade.py`; create `tests/test_tasks_api_pagination.py`.
- Create `api/file_access.py`: path resolution, media type, safe filename, and file streaming helpers shared by file and upload routes.
- Modify `api/routers/files.py`: use `api/file_access.py`, add `/files/stream/{file_path:path}` and `/files/download/{file_path:path}`.
- Modify `tests/test_files_api.py`: cover traversal, range streaming, and download content disposition.
- Modify `api/schemas/resources.py`: add upload response models.
- Modify `api/routers/resources.py`: add upload endpoints for BGM, reference audio, and local materials.
- Create `tests/test_resources_upload_api.py`: upload extension, path traversal, collision, and file size tests.
- Create `api/schemas/video_stages.py`: staged video request/response schemas.
- Create `api/routers/video_stages.py`: stage endpoints for script, storyboard plan, image prompts, audio, and render.
- Modify `api/routers/__init__.py` and `api/app.py`: include the new video stages router.
- Create `tests/test_video_stages_api.py`: unit-level tests using fake Pixelle services.
- Modify `docs/en/user-guide/api.md`: document the new endpoints and response/error shape.

---

### Task 1: Shared Response Envelope And Error Handlers

**Files:**
- Create: `api/schemas/responses.py`
- Modify: `api/app.py`
- Test: `tests/test_api_response_envelope.py`

- [ ] **Step 1: Write failing tests for standardized error payloads**

Create `tests/test_api_response_envelope.py`:

```python
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from api.schemas.responses import install_exception_handlers


class DemoPayload(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def reject_bad_name(cls, value: str) -> str:
        if value == "bad":
            raise ValueError("bad name")
        return value


def build_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="demo not found")

    @app.post("/payload")
    async def payload(body: DemoPayload):
        return {"name": body.name}

    return app


def test_http_exception_uses_standard_error_envelope():
    response = TestClient(build_app()).get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "message": "demo not found",
        "error": {
            "code": "http_404",
            "details": None,
        },
    }


def test_validation_exception_uses_standard_error_envelope():
    response = TestClient(build_app()).post("/payload", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "validation error"
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "name"]


def test_validation_exception_json_encodes_validator_context():
    response = TestClient(build_app()).post("/payload", json={"name": "bad"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "validation error"
    assert body["error"]["code"] == "validation_error"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
uv run pytest tests/test_api_response_envelope.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'api.schemas.responses'`.

- [ ] **Step 3: Implement response models and handlers**

Create `api/schemas/responses.py`:

```python
from typing import Any, Generic, TypeVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


class APIErrorPayload(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code")
    details: Any = Field(None, description="Structured error details")


class APIErrorResponse(BaseModel):
    success: bool = False
    message: str
    error: APIErrorPayload


class APIEnvelope(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Success"
    data: T | None = None


def success_envelope(data: Any = None, message: str = "Success") -> dict[str, Any]:
    payload: dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def error_envelope(*, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "details": details,
        },
    }


def _detail_to_message(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if detail is None:
        return "request failed"
    return str(detail)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            code=f"http_{exc.status_code}",
            message=_detail_to_message(exc.detail),
        ),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            code="validation_error",
            message="validation error",
            details=jsonable_encoder(exc.errors()),
        ),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
```

- [ ] **Step 4: Install handlers in the app**

Modify `api/app.py`:

```python
from api.schemas.responses import install_exception_handlers
```

Add immediately after `app = FastAPI(...)`:

```python
install_exception_handlers(app)
```

- [ ] **Step 5: Run response tests**

Run:

```bash
uv run pytest tests/test_api_response_envelope.py -q
```

Expected: pass.

- [ ] **Step 6: Run focused API tests for regressions**

Run:

```bash
uv run pytest tests/test_video_api.py tests/test_files_api.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add api/schemas/responses.py api/app.py tests/test_api_response_envelope.py
git commit -m "feat(api): standardize error response envelopes"
git push
```

---

### Task 2: Paginated Task Listing

**Files:**
- Create: `api/schemas/tasks.py`
- Modify: `api/routers/tasks.py`
- Modify: `api/tasks/store.py`
- Modify: `api/tasks/postgres.py`
- Modify: `api/tasks/manager.py`
- Test: `tests/test_task_store_memory.py`
- Test: `tests/test_task_manager_registry_facade.py`
- Test: `tests/test_tasks_api_pagination.py`

- [ ] **Step 1: Write failing in-memory store pagination tests**

Append to `tests/test_task_store_memory.py`:

```python
@pytest.mark.asyncio
async def test_memory_store_lists_tasks_with_offset_and_count():
    store = InMemoryTaskStore()
    for index in range(3):
        await store.create_task(
            Task(
                task_id=f"task-{index}",
                task_type=TaskType.VIDEO_GENERATION,
                status=TaskStatus.PENDING,
                created_at=datetime(2026, 1, 1, index, tzinfo=timezone.utc),
            )
        )

    page = await store.list_tasks(status=None, limit=2, offset=1)
    total = await store.count_tasks(status=None)

    assert total == 3
    assert [task.task_id for task in page] == ["task-1", "task-0"]
```

- [ ] **Step 2: Write failing router pagination tests**

Create `tests/test_tasks_api_pagination.py`:

```python
import pytest

from api.routers import tasks as tasks_router
from api.routers.tasks import list_tasks_page
from api.tasks.models import Task, TaskStatus, TaskType


class _FakeTaskManager:
    async def list_tasks(self, *, status=None, limit=100, offset=0):
        assert status is None
        assert limit == 2
        assert offset == 2
        return [
            Task(task_id="task-3", task_type=TaskType.VIDEO_GENERATION),
            Task(task_id="task-4", task_type=TaskType.VIDEO_GENERATION),
        ]

    async def count_tasks(self, *, status=None):
        assert status is None
        return 5


@pytest.mark.asyncio
async def test_list_tasks_returns_paginated_response(monkeypatch):
    monkeypatch.setattr(tasks_router, "task_manager", _FakeTaskManager())

    response = await list_tasks_page(status=None, page=2, page_size=2)

    assert response.total == 5
    assert response.page == 2
    assert response.page_size == 2
    assert response.tasks[0].task_id == "task-3"
```

- [ ] **Step 3: Run pagination tests to verify failure**

Run:

```bash
uv run pytest tests/test_task_store_memory.py::test_memory_store_lists_tasks_with_offset_and_count tests/test_tasks_api_pagination.py -q
```

Expected: fail because `offset`, `count_tasks`, and paginated response are not implemented.

- [ ] **Step 3a: Add PostgreSQL source-level count method coverage**

Modify `tests/test_postgres_task_store_schema.py` so `test_postgres_store_exposes_required_methods` includes `count_tasks`:

```python
    for name in [
        "create_task",
        "get_task",
        "find_reusable_by_fingerprint",
        "update_status",
        "update_progress",
        "claim_next_pending",
        "list_tasks",
        "count_tasks",
        "cancel_task",
    ]:
        assert hasattr(PostgresTaskStore, name)
```

- [ ] **Step 4: Add task pagination schema**

Create `api/schemas/tasks.py`:

```python
from pydantic import BaseModel, Field

from api.tasks.models import Task


class TaskListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    tasks: list[Task] = Field(..., description="Tasks for the requested page")
    total: int = Field(..., ge=0, description="Total matching tasks")
    page: int = Field(..., ge=1, description="One-based page number")
    page_size: int = Field(..., ge=1, description="Number of tasks per page")
```

- [ ] **Step 5: Extend task store contract and in-memory store**

Modify `api/tasks/store.py`:

```python
class TaskStore(Protocol):
    async def list_tasks(
        self,
        status: TaskStatus | None,
        limit: int,
        offset: int = 0,
    ) -> list[Task]:
        raise NotImplementedError

    async def count_tasks(self, status: TaskStatus | None) -> int:
        raise NotImplementedError
```

Replace `InMemoryTaskStore.list_tasks` and add `count_tasks`:

```python
async def list_tasks(
    self,
    status: TaskStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    async with self._lock:
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return [self._clone(task) for task in tasks[offset:offset + limit]]


async def count_tasks(self, status: TaskStatus | None = None) -> int:
    async with self._lock:
        if status is None:
            return len(self._tasks)
        return sum(1 for task in self._tasks.values() if task.status == status)
```

- [ ] **Step 6: Extend PostgreSQL store**

Modify `api/tasks/postgres.py`:

```python
Keep the existing SQLAlchemy imports, including `func`, and do not remove the existing table/constraint imports.
```

Replace `PostgresTaskStore.list_tasks`:

```python
async def list_tasks(
    self,
    status: TaskStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    async with self.engine.begin() as conn:
        query = select(generation_tasks)
        if status is not None:
            query = query.where(generation_tasks.c.status == status.value)
        query = query.order_by(desc(generation_tasks.c.created_at)).offset(offset).limit(limit)
        rows = (await conn.execute(query)).mappings().all()
        return [self._row_to_task(row) for row in rows]


async def count_tasks(self, status: TaskStatus | None = None) -> int:
    async with self.engine.begin() as conn:
        query = select(func.count()).select_from(generation_tasks)
        if status is not None:
            query = query.where(generation_tasks.c.status == status.value)
        return int((await conn.execute(query)).scalar_one())
```

- [ ] **Step 7: Extend manager pagination**

Modify `api/tasks/manager.py`:

```python
async def list_tasks(
    self,
    status: Optional[TaskStatus] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    store_tasks = await self.store.list_tasks(status=status, limit=offset + limit, offset=0)
    by_id = {task.task_id: task for task in store_tasks}

    legacy_tasks = list(self._tasks.values())
    if status:
        legacy_tasks = [task for task in legacy_tasks if task.status == status]
    for task in legacy_tasks:
        by_id.setdefault(task.task_id, task)

    tasks = list(by_id.values())
    tasks.sort(key=lambda task: task.created_at, reverse=True)
    return tasks[offset:offset + limit]


async def count_tasks(self, status: Optional[TaskStatus] = None) -> int:
    total = await self.store.count_tasks(status=status)
    legacy_count = 0
    for task_id, task in self._tasks.items():
        if status is None or task.status == status:
            if await self.store.get_task(task_id) is None:
                legacy_count += 1
    return total + legacy_count
```

- [ ] **Step 8: Add paginated route while preserving existing list route**

Modify `api/routers/tasks.py`:

```python
from api.schemas.tasks import TaskListResponse
```

Keep the existing `@router.get("", response_model=List[Task])` endpoint returning a list for backward compatibility. Add this new endpoint above `@router.get("/{task_id}")`:

```python
@router.get("/page", response_model=TaskListResponse)
async def list_tasks_page(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="One-based page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Number of tasks per page"),
):
    try:
        offset = (page - 1) * page_size
        tasks = await task_manager.list_tasks(
            status=status,
            limit=page_size,
            offset=offset,
        )
        total = await task_manager.count_tasks(status=status)
        return TaskListResponse(
            tasks=tasks,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"List tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 9: Run task pagination tests**

Run:

```bash
uv run pytest tests/test_task_store_memory.py tests/test_task_manager_registry_facade.py tests/test_tasks_api_pagination.py tests/test_postgres_task_store_schema.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add api/schemas/tasks.py api/routers/tasks.py api/tasks/store.py api/tasks/postgres.py api/tasks/manager.py tests/test_task_store_memory.py tests/test_task_manager_registry_facade.py tests/test_tasks_api_pagination.py tests/test_postgres_task_store_schema.py
git commit -m "feat(api): add paginated task listing"
git push
```

---

### Task 3: File Preview Streaming And Download Routes

**Files:**
- Create: `api/file_access.py`
- Modify: `api/routers/files.py`
- Test: `tests/test_files_api.py`

- [ ] **Step 1: Write failing file stream and download tests**

Append to `tests/test_files_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.files import router as files_router


def test_stream_file_supports_range_requests(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(files_router)

    response = TestClient(app).get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=0-1"},
    )

    assert response.status_code == 206
    assert response.content == b"vi"
    assert response.headers["content-range"] == "bytes 0-1/5"
    assert response.headers["accept-ranges"] == "bytes"


def test_download_file_uses_attachment_disposition(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(files_router)

    response = TestClient(app).get("/files/download/task-1/final.mp4")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="final.mp4"'


def test_stream_file_rejects_malformed_range(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(files_router)

    response = TestClient(app).get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=a-b"},
    )

    assert response.status_code == 416


def test_stream_file_rejects_unsatisfiable_range(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(files_router)

    response = TestClient(app).get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=99-100"},
    )

    assert response.status_code == 416
```

- [ ] **Step 2: Run file tests to verify failure**

Run:

```bash
uv run pytest tests/test_files_api.py -q
```

Expected: fail because `/files/stream/...` and `/files/download/...` do not exist.

- [ ] **Step 3: Add shared file access helper**

Create `api/file_access.py`:

```python
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException

ALLOWED_PREFIXES = [
    "output/",
    "workflows/",
    "templates/",
    "bgm/",
    "data/bgm/",
    "data/reference_audio/",
    "data/materials/",
    "data/templates/",
    "resources/",
]

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".html": "text/html",
    ".json": "application/json",
}


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def resolve_allowed_file_path(file_path: str, *, cwd: Path | None = None) -> Path:
    root = (cwd or Path.cwd()).resolve()
    allowed_roots = [(root / prefix.rstrip("/")).resolve() for prefix in ALLOWED_PREFIXES]

    requested_path = None
    for prefix in ALLOWED_PREFIXES:
        if file_path.startswith(prefix):
            requested_path = file_path
            break
    if requested_path is None:
        requested_path = f"output/{file_path}"

    abs_path = (root / requested_path).resolve()
    if not any(abs_path == allowed or abs_path.is_relative_to(allowed) for allowed in allowed_roots):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: only {', '.join(p.rstrip('/') for p in ALLOWED_PREFIXES)} directories are accessible",
        )
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    if not abs_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")
    return abs_path


def parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int, int, int]:
    if not range_header:
        return 0, file_size - 1, file_size, 200
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid Range header")
    value = range_header.removeprefix("bytes=")
    start_text, _, end_text = value.partition("-")
    if start_text == "" and end_text == "":
        raise HTTPException(status_code=416, detail="Invalid Range header")
    try:
        if start_text == "":
            suffix_length = int(end_text)
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="Invalid Range header")
    if start < 0 or end >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Range not satisfiable")
    return start, end, end - start + 1, 206


def iter_file_range(path: Path, *, start: int, length: int, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    remaining = length
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def sanitize_upload_filename(filename: str) -> str:
    safe_name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return safe_name
```

- [ ] **Step 4: Refactor files router and add stream/download**

Modify `api/routers/files.py`:

```python
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from api.file_access import (
    iter_file_range,
    media_type_for,
    parse_range_header,
    resolve_allowed_file_path,
)
```

Define stream and download routes before `@router.get("/{file_path:path}")`:

```python
@router.get("/stream/{file_path:path}")
async def stream_file(file_path: str, request: Request):
    abs_path = resolve_allowed_file_path(file_path)
    file_size = abs_path.stat().st_size
    start, end, length, status_code = parse_range_header(request.headers.get("Range"), file_size)
    response = StreamingResponse(
        iter_file_range(abs_path, start=start, length=length),
        media_type=media_type_for(abs_path),
        status_code=status_code,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = str(length)
    if status_code == 206:
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return response


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    abs_path = resolve_allowed_file_path(file_path)
    return FileResponse(
        path=str(abs_path),
        media_type=media_type_for(abs_path),
        filename=abs_path.name,
        headers={"Content-Disposition": f'attachment; filename="{abs_path.name}"'},
    )
```

Replace `get_file` internals with:

```python
abs_path = resolve_allowed_file_path(file_path)
return FileResponse(
    path=str(abs_path),
    media_type=media_type_for(abs_path),
    headers={"Content-Disposition": f'inline; filename="{abs_path.name}"'},
)
```

- [ ] **Step 5: Run file tests**

Run:

```bash
uv run pytest tests/test_files_api.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add api/file_access.py api/routers/files.py tests/test_files_api.py
git commit -m "feat(api): add file stream and download endpoints"
git push
```

---

### Task 4: Resource Upload Endpoints

**Files:**
- Modify: `api/schemas/resources.py`
- Modify: `api/routers/resources.py`
- Modify: `api/file_access.py`
- Test: `tests/test_resources_upload_api.py`

- [ ] **Step 1: Write failing upload tests**

Create `tests/test_resources_upload_api.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.config import api_config
from api.routers.resources import router as resources_router


def build_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    app.include_router(resources_router)
    return TestClient(app)


def test_upload_bgm_saves_safe_file_to_data_bgm(monkeypatch, tmp_path):
    response = build_client(tmp_path, monkeypatch).post(
        "/resources/bgm",
        files={"file": ("song.mp3", b"audio-bytes", "audio/mpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "data/bgm/song.mp3"
    assert (tmp_path / "data" / "bgm" / "song.mp3").read_bytes() == b"audio-bytes"


def test_upload_material_rejects_path_traversal_filename(monkeypatch, tmp_path):
    response = build_client(tmp_path, monkeypatch).post(
        "/resources/materials",
        files={"file": ("../secret.mp4", b"video", "video/mp4")},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "secret.mp4"
    assert (tmp_path / "data" / "materials" / "secret.mp4").is_file()


def test_upload_reference_audio_rejects_invalid_extension(monkeypatch, tmp_path):
    response = build_client(tmp_path, monkeypatch).post(
        "/resources/reference-audio",
        files={"file": ("voice.txt", b"text", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_upload_bgm_uses_collision_suffix(monkeypatch, tmp_path):
    client = build_client(tmp_path, monkeypatch)
    client.post("/resources/bgm", files={"file": ("song.mp3", b"first", "audio/mpeg")})
    response = client.post("/resources/bgm", files={"file": ("song.mp3", b"second", "audio/mpeg")})

    assert response.status_code == 200
    assert response.json()["path"] == "data/bgm/song_1.mp3"
    assert (tmp_path / "data" / "bgm" / "song.mp3").read_bytes() == b"first"
    assert (tmp_path / "data" / "bgm" / "song_1.mp3").read_bytes() == b"second"


def test_upload_rejects_oversized_file_and_removes_partial(monkeypatch, tmp_path):
    client = build_client(tmp_path, monkeypatch)
    monkeypatch.setattr(api_config, "max_upload_size", 3)

    response = client.post(
        "/resources/bgm",
        files={"file": ("large.mp3", b"too-large", "audio/mpeg")},
    )

    assert response.status_code == 413
    assert not list((tmp_path / "data" / "bgm").glob("large*"))
```

- [ ] **Step 2: Run upload tests to verify failure**

Run:

```bash
uv run pytest tests/test_resources_upload_api.py -q
```

Expected: fail because upload endpoints do not exist.

- [ ] **Step 3: Add upload response schema**

Append to `api/schemas/resources.py`:

```python
class ResourceUploadResponse(BaseModel):
    """Uploaded resource response"""
    success: bool = True
    message: str = "Success"
    name: str = Field(..., description="Stored filename")
    path: str = Field(..., description="Path usable by API requests")
    size: int = Field(..., ge=0, description="Stored file size in bytes")
    source: str = Field("custom", description="Resource source")
```

- [ ] **Step 4: Add collision-safe upload helper**

Append to `api/file_access.py`:

```python
def ensure_allowed_extension(filename: str, allowed_extensions: tuple[str, ...]) -> None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {suffix or '<none>'}",
        )


def resolve_collision_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        next_candidate = directory / f"{stem}_{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1
```

- [ ] **Step 5: Implement resource upload endpoints**

Modify `api/routers/resources.py` imports by adding to the existing imports. Do not replace the existing `PixelleVideoDep`, `BGMInfo`, `TemplateInfo`, `WorkflowInfo`, and response schema imports that current routes need:

```python
from fastapi import APIRouter, File, HTTPException, UploadFile

from api.config import api_config
from api.file_access import (
    ensure_allowed_extension,
    resolve_collision_path,
    sanitize_upload_filename,
)
from api.schemas.resources import (
    BGMInfo,
    BGMListResponse,
    ResourceUploadResponse,
    TemplateInfo,
    TemplateListResponse,
    WorkflowInfo,
    WorkflowListResponse,
)
```

Add helper and endpoints after `router = APIRouter(...)`:

```python
AUDIO_EXTENSIONS = ("mp3", "wav", "flac", "m4a", "aac", "ogg")
MATERIAL_EXTENSIONS = ("mp4", "mov", "avi", "mkv", "webm", "jpg", "jpeg", "png")


async def _save_upload(
    *,
    file: UploadFile,
    target_subdir: str,
    allowed_extensions: tuple[str, ...],
) -> ResourceUploadResponse:
    safe_name = sanitize_upload_filename(file.filename or "")
    ensure_allowed_extension(safe_name, allowed_extensions)

    target_dir = Path("data") / target_subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = resolve_collision_path(target_dir, safe_name)

    size = 0
    with target_path.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > api_config.max_upload_size:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large")
            output.write(chunk)

    relative_path = target_path.as_posix()
    return ResourceUploadResponse(
        name=target_path.name,
        path=relative_path,
        size=size,
    )


@router.post("/bgm", response_model=ResourceUploadResponse)
async def upload_bgm(file: UploadFile = File(...)):
    return await _save_upload(
        file=file,
        target_subdir="bgm",
        allowed_extensions=AUDIO_EXTENSIONS,
    )


@router.post("/reference-audio", response_model=ResourceUploadResponse)
async def upload_reference_audio(file: UploadFile = File(...)):
    return await _save_upload(
        file=file,
        target_subdir="reference_audio",
        allowed_extensions=AUDIO_EXTENSIONS,
    )


@router.post("/materials", response_model=ResourceUploadResponse)
async def upload_material(file: UploadFile = File(...)):
    return await _save_upload(
        file=file,
        target_subdir="materials",
        allowed_extensions=MATERIAL_EXTENSIONS,
    )
```

- [ ] **Step 6: Run upload and resource tests**

Run:

```bash
uv run pytest tests/test_resources_upload_api.py tests/test_files_api.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add api/schemas/resources.py api/routers/resources.py api/file_access.py tests/test_resources_upload_api.py
git commit -m "feat(api): add resource upload endpoints"
git push
```

---

### Task 5: Staged Video API On StoryboardPlan Contract

**Dependency:** This task depends on Storyboard Generation Contract phases 1-4 from `docs/superpowers/plans/2026-04-25-storyboard-generation-logic-implementation.md`. Do not implement these endpoints with legacy narration-first utilities while the new storyboard services are pending.

Before starting Step 1, verify these imports exist and are the public integration points:

```python
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.script_generation import ScriptGenerationService
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
from pixelle_video.services.storyboard_enhancer import StoryboardEnhancer
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
```

If any import is missing, stop Task 5. Do not implement the staged video router, do not document these staged endpoints as active API surface, and do not substitute legacy narration utilities to make the task pass.

**Files:**
- Create: `api/schemas/video_stages.py`
- Create: `api/routers/video_stages.py`
- Modify: `api/routers/__init__.py`
- Modify: `api/app.py`
- Test: `tests/test_video_stages_api.py`

- [ ] **Step 1: Write failing staged API tests against the new storyboard contract**

Create `tests/test_video_stages_api.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routers.video_stages import (
    generate_audio_stage,
    generate_image_prompts_stage,
    generate_script_stage,
    generate_storyboard_plan_stage,
    render_segments_stage,
)
from api.schemas.video_stages import (
    AudioStageRequest,
    ImagePromptStageRequest,
    RenderStageRequest,
    ScriptStageRequest,
    StoryboardPlanStageRequest,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame


def _plan(*, mode="smart", count_mode="auto", requested_scene_count=None, frame_count=2):
    source_text = "First sentence. Second sentence."
    frames = []
    for index in range(1, frame_count + 1):
        frames.append(
            StoryboardPlanFrame(
                index=index,
                source_text=f"source {index}",
                narration_text=f"voiceover {index}",
                visual_goal=f"visual goal {index}",
                prompt_intent=f"prompt intent {index}",
            )
        )
    return StoryboardPlan.build(
        mode=mode,
        count_mode=count_mode,
        requested_scene_count=requested_scene_count,
        source_text=source_text,
        frames=frames,
    )


class _FakeScriptService:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            title="Generated Title",
            source_text="Generated full source text.",
            metadata={"script_length_mode": kwargs["script_length_mode"]},
        )


class _FakeStoryboardService:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        count_mode = kwargs["storyboard_count_mode"]
        requested_scene_count = kwargs["storyboard_scene_count"]
        frame_count = requested_scene_count if count_mode == "manual" else 2
        return _plan(
            mode=kwargs["storyboard_mode"],
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            frame_count=frame_count,
        )


class _FakeEnhancer:
    def __init__(self):
        self.calls = []

    async def enhance(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["storyboard_plan"]


class _FakeImagePromptComposer:
    def __init__(self):
        self.calls = []

    async def compose(self, **kwargs):
        self.calls.append(kwargs)
        return [f"prompt for {frame.frame_id}" for frame in kwargs["storyboard_plan"].frames]


class _FakeTTS:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        path = self.output_dir / f"audio-{len(self.calls)}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return str(path)


class _FakeVideo:
    def __init__(self):
        self.calls = []

    def concat_videos(self, videos, output, **kwargs):
        self.calls.append({"videos": videos, "output": output, **kwargs})
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"video")
        return output


@pytest.mark.asyncio
async def test_script_stage_returns_source_text(monkeypatch):
    fake_service = _FakeScriptService()
    monkeypatch.setattr("api.routers.video_stages.ScriptGenerationService", lambda config=None: fake_service)

    response = await generate_script_stage(
        ScriptStageRequest(text="demo topic", mode="generate", script_length_mode="short"),
        SimpleNamespace(llm=object(), config={"storyboard": {}}),
    )

    assert response.title == "Generated Title"
    assert response.source_text == "Generated full source text."
    assert response.script_generation["script_length_mode"] == "short"
    assert fake_service.calls[0]["topic"] == "demo topic"


def test_script_stage_rejects_illegal_fixed_length_controls():
    with pytest.raises(ValidationError):
        ScriptStageRequest(text="fixed source", mode="fixed", script_length_mode="short")

    with pytest.raises(ValidationError):
        ScriptStageRequest(text="fixed source", mode="fixed", script_target_words=120)

    with pytest.raises(ValidationError):
        ScriptStageRequest(text="demo", n_scenes=2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("storyboard_mode", "storyboard_count_mode", "storyboard_scene_count"),
    [
        ("smart", "auto", None),
        ("smart", "manual", 2),
        ("punctuation", "auto", None),
        ("sentence", "auto", None),
    ],
)
async def test_storyboard_plan_stage_supports_contract_modes(
    monkeypatch,
    storyboard_mode,
    storyboard_count_mode,
    storyboard_scene_count,
):
    fake_service = _FakeStoryboardService()
    monkeypatch.setattr("api.routers.video_stages.StoryboardGenerationService", lambda config=None: fake_service)

    response = await generate_storyboard_plan_stage(
        StoryboardPlanStageRequest(
            source_text="First sentence. Second sentence.",
            storyboard_mode=storyboard_mode,
            storyboard_count_mode=storyboard_count_mode,
            storyboard_scene_count=storyboard_scene_count,
        ),
        SimpleNamespace(llm=object(), config={"storyboard": {}}),
    )

    assert response.storyboard_plan["mode"] == storyboard_mode
    assert response.storyboard_plan["count_mode"] == storyboard_count_mode
    assert response.resolved_scene_count == len(response.frames)
    assert fake_service.calls[0]["source_text"] == "First sentence. Second sentence."


@pytest.mark.asyncio
async def test_image_prompt_stage_returns_one_prompt_per_plan_frame(monkeypatch):
    fake_enhancer = _FakeEnhancer()
    fake_composer = _FakeImagePromptComposer()
    monkeypatch.setattr("api.routers.video_stages.StoryboardEnhancer", lambda config=None: fake_enhancer)
    monkeypatch.setattr("api.routers.video_stages.ImagePromptComposer", lambda config=None: fake_composer)
    plan = _plan()

    response = await generate_image_prompts_stage(
        ImagePromptStageRequest(
            storyboard_plan=plan.to_dict(),
            prompt_prefix="cinematic documentary",
            media_workflow="selfhost/image.json",
        ),
        SimpleNamespace(llm=object(), media=object(), config={"comfyui": {"image": {}}}),
    )

    assert len(response.image_prompts) == len(plan.frames)
    assert response.frames[0]["frame_id"] == plan.frames[0].frame_id
    assert fake_composer.calls[0]["prompt_prefix"] == "cinematic documentary"


@pytest.mark.asyncio
async def test_audio_stage_uses_storyboard_plan_frame_voiceover(monkeypatch, tmp_path):
    monkeypatch.setattr("api.routers.video_stages.get_audio_duration", lambda path: 1.25)
    fake_tts = _FakeTTS(tmp_path)
    plan = _plan()

    response = await generate_audio_stage(
        AudioStageRequest(storyboard_plan=plan.to_dict(), tts_workflow="selfhost/tts_edge.json"),
        SimpleNamespace(tts=fake_tts),
    )

    assert [segment.text for segment in response.voiceover_segments] == ["voiceover 1", "voiceover 2"]
    assert fake_tts.calls[0] == {"text": "voiceover 1", "workflow": "selfhost/tts_edge.json"}
    assert response.voiceover_segments[0].duration == 1.25


def test_staged_video_schemas_reject_legacy_storyboard_inputs():
    with pytest.raises(ValidationError):
        StoryboardPlanStageRequest(source_text="demo", split_mode="sentence")

    with pytest.raises(ValidationError):
        ImagePromptStageRequest(storyboard_plan=_plan().to_dict(), narrations=["legacy"])

    with pytest.raises(ValidationError):
        AudioStageRequest(narrations=["legacy"])


@pytest.mark.asyncio
async def test_render_stage_concatenates_segments(monkeypatch, tmp_path):
    segment = tmp_path / "output" / "task-1" / "segment.mp4"
    segment.parent.mkdir(parents=True)
    segment.write_bytes(b"segment")
    monkeypatch.chdir(tmp_path)
    fake_video = _FakeVideo()

    response = await render_segments_stage(
        RenderStageRequest(video_segment_paths=["task-1/segment.mp4"], output_name="final.mp4"),
        SimpleNamespace(video=fake_video),
    )

    assert response.video_path == "output/staged/final.mp4"
    assert (tmp_path / response.video_path).read_bytes() == b"video"


def test_staged_video_router_does_not_import_legacy_content_generators():
    source = Path("api/routers/video_stages.py").read_text(encoding="utf-8")

    assert "generate_narrations_from_topic" not in source
    assert "split_narration_script" not in source
    assert "generate_styled_image_prompt_batch" not in source
    assert "narrations=" not in source
```

- [ ] **Step 2: Run staged API tests to verify failure**

Run:

```bash
uv run pytest tests/test_video_stages_api.py -q
```

Expected: fail because staged API schemas and router do not exist, or because the Storyboard Contract services are not ready yet. If the failure is an import error for `ScriptGenerationService`, `StoryboardEnhancer`, or `ImagePromptComposer`, stop this task and return to the storyboard contract implementation plan instead of adding compatibility shims.

- [ ] **Step 3: Add staged video schemas**

Create `api/schemas/video_stages.py`:

```python
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pixelle_video.models.storyboard_plan import (
    ScriptLengthMode,
    StoryboardCountMode,
    StoryboardGenerationMode,
)


class ScriptStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    mode: Literal["generate", "fixed"] = "generate"
    script_length_mode: ScriptLengthMode = ScriptLengthMode.AUTO
    script_target_words: int | None = Field(None, ge=1)
    title: Optional[str] = None

    @model_validator(mode="after")
    def validate_script_controls(self):
        if self.mode == "fixed":
            if self.script_length_mode != ScriptLengthMode.AUTO:
                raise ValueError("fixed mode requires script_length_mode=auto")
            if self.script_target_words is not None:
                raise ValueError("script_target_words is valid only for generate mode")
        elif self.script_length_mode == ScriptLengthMode.CUSTOM:
            if self.script_target_words is None:
                raise ValueError("script_target_words is required with script_length_mode=custom")
        elif self.script_target_words is not None:
            raise ValueError("script_target_words is valid only with script_length_mode=custom")
        return self


class ScriptStageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    title: str | None = None
    source_text: str
    script_generation: dict[str, Any] = Field(default_factory=dict)


class StoryboardPlanStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_text: str = Field(..., min_length=1)
    storyboard_mode: StoryboardGenerationMode = StoryboardGenerationMode.SMART
    storyboard_count_mode: StoryboardCountMode = StoryboardCountMode.AUTO
    storyboard_scene_count: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_storyboard_controls(self):
        is_manual_smart = (
            self.storyboard_mode == StoryboardGenerationMode.SMART
            and self.storyboard_count_mode == StoryboardCountMode.MANUAL
        )
        if self.storyboard_count_mode == StoryboardCountMode.MANUAL and self.storyboard_mode != StoryboardGenerationMode.SMART:
            raise ValueError("manual storyboard count is valid only for smart mode")
        if is_manual_smart and self.storyboard_scene_count is None:
            raise ValueError("storyboard_scene_count is required with smart manual mode")
        if not is_manual_smart and self.storyboard_scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only with smart manual mode")
        return self


class StoryboardPlanStageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    storyboard_plan: dict[str, Any]
    resolved_scene_count: int
    frames: list[dict[str, Any]]


class ImagePromptStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storyboard_plan: dict[str, Any]
    prompt_prefix: Optional[str] = None
    media_workflow: Optional[str] = None
    image_style_config: dict[str, Any] = Field(default_factory=dict)


class ImagePromptStageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    image_prompts: list[str | None]
    frames: list[dict[str, Any]]


class AudioStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storyboard_plan: dict[str, Any]
    tts_workflow: Optional[str] = None
    ref_audio: Optional[str] = None


class VoiceoverSegmentInfo(BaseModel):
    frame_id: str
    index: int
    text: str
    audio_path: str
    duration: float


class AudioStageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    voiceover_segments: list[VoiceoverSegmentInfo]


class RenderStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_segment_paths: list[str] = Field(..., min_length=1)
    output_name: str = Field("final.mp4")
    method: Literal["demuxer", "filter"] = "demuxer"
    bgm_path: Optional[str] = None
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0)


class RenderStageResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    video_path: str
    file_size: int
```

- [ ] **Step 4: Implement staged video router with StoryboardPlan-first services**

Create `api/routers/video_stages.py`:

```python
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.file_access import resolve_allowed_file_path, sanitize_upload_filename
from api.schemas.video_stages import (
    AudioStageRequest,
    AudioStageResponse,
    ImagePromptStageRequest,
    ImagePromptStageResponse,
    RenderStageRequest,
    RenderStageResponse,
    ScriptStageRequest,
    ScriptStageResponse,
    StoryboardPlanStageRequest,
    StoryboardPlanStageResponse,
    VoiceoverSegmentInfo,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
from pixelle_video.services.script_generation import ScriptGenerationService
from pixelle_video.services.storyboard_enhancer import StoryboardEnhancer
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
from pixelle_video.utils.tts_util import get_audio_duration

router = APIRouter(prefix="/video/stages", tags=["Video Generation"])


def _storyboard_config(pixelle_video: PixelleVideoDep) -> dict[str, Any]:
    return dict(getattr(pixelle_video, "config", {}).get("storyboard", {}))


def _plan_from_payload(payload: dict[str, Any]) -> StoryboardPlan:
    frames = [
        StoryboardPlanFrame(
            frame_id=frame.get("frame_id", ""),
            index=frame["index"],
            source_text=frame["source_text"],
            narration_text=frame["narration_text"],
            visual_goal=frame["visual_goal"],
            prompt_intent=frame["prompt_intent"],
            shot_type=frame.get("shot_type"),
            shot_purpose=frame.get("shot_purpose"),
            primary_subject=frame.get("primary_subject"),
            secondary_subjects=tuple(frame.get("secondary_subjects") or ()),
            continuity_anchors=tuple(frame.get("continuity_anchors") or ()),
            world_elements=tuple(frame.get("world_elements") or ()),
            source_start=frame.get("source_start"),
            source_end=frame.get("source_end"),
            metadata=frame.get("metadata") or {},
        )
        for frame in payload["frames"]
    ]
    return StoryboardPlan.build(
        plan_id=payload.get("plan_id"),
        revision=payload.get("revision", 1),
        mode=payload["mode"],
        count_mode=payload["count_mode"],
        requested_scene_count=payload.get("requested_scene_count"),
        source_text=payload["source_text"],
        frames=frames,
        diagnostics=payload.get("diagnostics") or {},
    )


@router.post("/script", response_model=ScriptStageResponse)
async def generate_script_stage(request: ScriptStageRequest, pixelle_video: PixelleVideoDep):
    try:
        if request.mode == "fixed":
            source_text = request.text.strip()
            title = request.title
            metadata = {"mode": "fixed"}
        else:
            result = await ScriptGenerationService(config=_storyboard_config(pixelle_video)).generate(
                llm_service=pixelle_video.llm,
                topic=request.text,
                title=request.title,
                script_length_mode=request.script_length_mode.value,
                script_target_words=request.script_target_words,
            )
            source_text = result.source_text
            title = result.title
            metadata = dict(getattr(result, "metadata", {}))
        return ScriptStageResponse(title=title, source_text=source_text, script_generation=metadata)
    except Exception as exc:
        logger.error(f"Script stage error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/storyboard-plan", response_model=StoryboardPlanStageResponse)
async def generate_storyboard_plan_stage(request: StoryboardPlanStageRequest, pixelle_video: PixelleVideoDep):
    try:
        plan = await StoryboardGenerationService(config=_storyboard_config(pixelle_video)).generate(
            llm_service=pixelle_video.llm,
            source_text=request.source_text,
            storyboard_mode=request.storyboard_mode.value,
            storyboard_count_mode=request.storyboard_count_mode.value,
            storyboard_scene_count=request.storyboard_scene_count,
        )
        payload = plan.to_dict()
        return StoryboardPlanStageResponse(
            storyboard_plan=payload,
            resolved_scene_count=plan.resolved_scene_count,
            frames=payload["frames"],
        )
    except Exception as exc:
        logger.error(f"Storyboard plan stage error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/image-prompts", response_model=ImagePromptStageResponse)
async def generate_image_prompts_stage(request: ImagePromptStageRequest, pixelle_video: PixelleVideoDep):
    try:
        plan = _plan_from_payload(request.storyboard_plan)
        enhanced_plan = await StoryboardEnhancer(config=_storyboard_config(pixelle_video)).enhance(
            llm_service=pixelle_video.llm,
            storyboard_plan=plan,
        )
        image_config = dict(getattr(pixelle_video, "config", {}).get("comfyui", {}).get("image", {}))
        image_config.update(request.image_style_config)
        prompts = await ImagePromptComposer(config=image_config).compose(
            storyboard_plan=enhanced_plan,
            prompt_prefix=request.prompt_prefix,
            media_workflow=request.media_workflow,
            media_service=pixelle_video.media,
        )
        plan_payload = enhanced_plan.to_dict()
        return ImagePromptStageResponse(
            image_prompts=list(prompts),
            frames=plan_payload["frames"],
        )
    except Exception as exc:
        logger.error(f"Image prompt stage error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/audio", response_model=AudioStageResponse)
async def generate_audio_stage(request: AudioStageRequest, pixelle_video: PixelleVideoDep):
    try:
        plan = _plan_from_payload(request.storyboard_plan)
        segments = []
        for frame in plan.frames:
            params = {"text": frame.narration_text}
            if request.tts_workflow:
                params["workflow"] = request.tts_workflow
            if request.ref_audio:
                params["ref_audio"] = request.ref_audio
            audio_path = await pixelle_video.tts(**params)
            segments.append(
                VoiceoverSegmentInfo(
                    frame_id=frame.frame_id,
                    index=frame.index,
                    text=frame.narration_text,
                    audio_path=audio_path,
                    duration=get_audio_duration(audio_path),
                )
            )
        return AudioStageResponse(voiceover_segments=segments)
    except Exception as exc:
        logger.error(f"Audio stage error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/render", response_model=RenderStageResponse)
async def render_segments_stage(request: RenderStageRequest, pixelle_video: PixelleVideoDep):
    try:
        safe_output = sanitize_upload_filename(request.output_name)
        if not safe_output.lower().endswith(".mp4"):
            raise HTTPException(status_code=400, detail="output_name must end with .mp4")
        output_path = Path("output") / "staged" / safe_output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        segment_paths = [str(resolve_allowed_file_path(path)) for path in request.video_segment_paths]
        pixelle_video.video.concat_videos(
            segment_paths,
            str(output_path),
            method=request.method,
            bgm_path=request.bgm_path,
            bgm_volume=request.bgm_volume,
        )
        return RenderStageResponse(
            video_path=output_path.as_posix(),
            file_size=output_path.stat().st_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Render stage error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
```

Do not import or call `generate_narrations_from_topic`, `split_narration_script`, or `generate_styled_image_prompt_batch` from this router. The only acceptable source for voiceover text is `StoryboardPlan.frames[*].narration_text`.

- [ ] **Step 5: Register staged video router**

Modify `api/routers/__init__.py`:

```python
from api.routers.video_stages import router as video_stages_router
```

Add `"video_stages_router"` to `__all__`.

Modify `api/app.py` router imports:

```python
from api.routers import (
    content_router,
    files_router,
    frame_router,
    health_router,
    image_router,
    llm_router,
    resources_router,
    tasks_router,
    tts_router,
    video_router,
    video_stages_router,
)
```

Include after `video_router`:

```python
app.include_router(video_stages_router, prefix=api_config.api_prefix)
```

- [ ] **Step 6: Run staged API tests**

Run:

```bash
uv run pytest tests/test_video_stages_api.py tests/test_video_api.py -q
```

Expected: pass after Storyboard Generation Contract phases 1-4 are implemented. If the contract services are still missing, this task remains deferred and must not be implemented with legacy content generator shortcuts.

- [ ] **Step 7: Commit**

```bash
git add api/schemas/video_stages.py api/routers/video_stages.py api/routers/__init__.py api/app.py tests/test_video_stages_api.py
git commit -m "feat(api): add storyboard-plan staged video endpoints"
git push
```

---

### Task 6: Documentation And Final Verification

**Files:**
- Modify: `docs/en/user-guide/api.md`

- [ ] **Step 1: Update API documentation**

Before editing `docs/en/user-guide/api.md`, check whether Task 5 was actually implemented:

```bash
test -f api/routers/video_stages.py && test -f api/schemas/video_stages.py
```

If both files exist because Task 5 passed with the Storyboard Generation Contract services, replace the short current `docs/en/user-guide/api.md` content with sections for:

```markdown
# API Usage

Pixelle-Video exposes FastAPI endpoints for content generation, video generation, task tracking, resource upload, and generated file access.

## Error Response Shape

Errors use a common envelope:

```json
{
  "success": false,
  "message": "validation error",
  "error": {
    "code": "validation_error",
    "details": []
  }
}
```

## Async Video Generation

Submit:

```http
POST /api/video/generate/async
```

Poll:

```http
GET /api/tasks/{task_id}
```

List with pagination:

```http
GET /api/tasks/page?page=1&page_size=20&status=completed
```

## Staged Video Endpoints

These endpoints are diagnostic building blocks. They use the Storyboard Generation Contract from their first version and do not accept legacy storyboard fields such as `n_scenes`, `split_mode`, or `narrations` as storyboard input. Use `/api/video/generate/async` for complete production generation.

Generate script:

```http
POST /api/video/stages/script
```

Generate a storyboard plan:

```http
POST /api/video/stages/storyboard-plan
```

Generate image prompts from a storyboard plan:

```http
POST /api/video/stages/image-prompts
```

Generate audio from `StoryboardPlan.frames[*].narration_text`:

```http
POST /api/video/stages/audio
```

Render prepared segments:

```http
POST /api/video/stages/render
```

## Files

Preview:

```http
GET /api/files/{path}
GET /api/files/stream/{path}
```

Download:

```http
GET /api/files/download/{path}
```

## Uploads

```http
POST /api/resources/bgm
POST /api/resources/reference-audio
POST /api/resources/materials
```
```

If Task 5 was deferred because `ScriptGenerationService`, `StoryboardEnhancer`, or `ImagePromptComposer` was missing, do not document staged endpoints as active API surface. Use this staged section instead:

```markdown
## Staged Video Endpoints

Staged video endpoints are deferred until the Storyboard Generation Contract services are complete. They must be implemented around `StoryboardPlan`; they must not expose `n_scenes`, `split_mode`, or `narrations` as storyboard input.
```

- [ ] **Step 2: Run the focused verification suite**

Run:

```bash
uv run pytest tests/test_api_response_envelope.py tests/test_tasks_api_pagination.py tests/test_files_api.py tests/test_resources_upload_api.py tests/test_video_stages_api.py tests/test_video_api.py tests/test_task_manager_registry_facade.py tests/test_task_store_memory.py tests/test_postgres_task_store_schema.py -q
```

Expected: pass.

- [ ] **Step 3: Run lint on touched Python files**

Run:

```bash
uv run ruff check api tests/test_api_response_envelope.py tests/test_tasks_api_pagination.py tests/test_files_api.py tests/test_resources_upload_api.py tests/test_video_stages_api.py tests/test_postgres_task_store_schema.py
```

Expected: pass.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/en/user-guide/api.md
git commit -m "docs(api): document api experience improvements"
git push
```

- [ ] **Step 5: Verify branch is pushed**

```bash
git push
```

Expected: `Everything up-to-date` because each atomic commit has already been pushed. If the branch has no upstream, use `git push -u origin <current-branch>`.

---

## Self-Review

- Spec coverage: the plan covers the five requested areas: staged generation API, unified error envelope, task pagination, file stream/download split, and resource uploads.
- Backward compatibility: non-video route paths and successful response shapes remain stable where routes already exist. Video generation follows the Storyboard Generation Contract and intentionally rejects removed storyboard fields such as `n_scenes`, `split_mode`, and narration-count controls.
- Type consistency: route response models are defined in `api/schemas/*`; routers import those schemas directly; task pagination updates manager/store/router signatures consistently; staged video schemas use `source_text`, `StoryboardPlan`, `voiceover_segments`, and image prompts instead of legacy narration-first inputs.
- Scope control: the plan keeps Pixelle's existing task registry and worker model. It does not copy MoneyPrinterTurbo's thread queue.
- Risk: Task 2 touches both memory and PostgreSQL task stores. Task 5 is intentionally gated on Storyboard Generation Contract phases 1-4 and must remain deferred rather than being implemented with legacy `generate_narrations_from_topic`, `split_narration_script`, or `generate_styled_image_prompt_batch` shortcuts.
