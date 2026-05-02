# Progress Stage Contract Source Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pixelle progress reporting reflect real generation stages, so HyperFrames audio synthesis is reported before HyperFrames rendering and async tasks persist structured, lease-safe progress.

**Architecture:** Add a dispatcher/sink progress contract around existing `ProgressEvent` objects. Pipelines emit stage events through one dispatcher-compatible path; embedded and worker executors attach a task progress sink only after they own the task lease.

**Tech Stack:** Python dataclasses/protocols, Pydantic models, existing `GenerationRegistry`/`TaskStore`, existing `ProgressEvent`, pytest, Streamlit i18n helpers.

---

## Governing Spec

- `docs/superpowers/specs/2026-05-02-progress-stage-contract-source-fix-design.md`

## Repository Rules

```text
Keep changes atomic.
Commit messages must be Chinese and use a type prefix.
Push each commit to GitHub after committing.
Do not mix unrelated diffs.
Use tests first for behavior changes.
```

## File Structure

- Modify `pixelle_video/models/progress.py`: add stage event types, i18n-key mappings, and dispatcher/sink primitives.
- Modify `web/i18n/locales/zh_CN.json`: add Chinese labels for new progress events.
- Modify `web/i18n/locales/en_US.json`: add English labels for new progress events.
- Modify `api/tasks/models.py`: extend `TaskProgress` with stable persisted event fields.
- Modify `api/tasks/registry.py`: add lease-checked `update_progress(...)`.
- Create `api/tasks/progress.py`: convert `ProgressEvent` to `TaskProgress` and bridge sync progress emission to async registry writes.
- Modify `pixelle_video/pipelines/linear.py`: combine legacy callback and optional dispatcher into one `ProgressDispatcher`, then store it in `PipelineContext`.
- Modify `pixelle_video/pipelines/base.py`: make `_report_progress(...)` accept either a direct callback or a dispatcher-like sink.
- Modify `pixelle_video/pipelines/standard.py`: report HyperFrames audio synthesis, manifest preparation, and renderer execution in source order.
- Modify `pixelle_video/services/generation_coordinator.py`: mark `progress_dispatcher` volatile so task fingerprints do not depend on runtime objects.
- Modify `api/routers/video.py`: let the embedded executor pass its runtime dispatcher into generation.
- Modify `api/tasks/manager.py`: create task progress sink in embedded registry execution after lease creation.
- Modify `api/tasks/worker.py`: create task progress sink in worker execution after claim lease.
- Tests:
  - `tests/test_progress_dispatcher.py`
  - `tests/test_task_progress_sink.py`
  - `tests/test_task_store_memory.py`
  - `tests/test_worker_execution.py`
  - `tests/test_async_video_registry_integration.py`
  - `tests/test_standard_pipeline_hyperframes_mode.py`
  - `tests/test_video_api.py`
  - `tests/test_generation_coordinator.py`
  - `tests/test_i18n.py`

## Task 1: Progress Event Contract And Dispatcher

**Files:**

- Modify: `pixelle_video/models/progress.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: `tests/test_progress_dispatcher.py`
- Test: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing dispatcher tests**

Create or update `tests/test_progress_dispatcher.py`:

```python
from pixelle_video.models.progress import (
    CallbackProgressSink,
    ProgressDispatcher,
    ProgressEvent,
    ProgressEventType,
)


class RecordingSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def test_progress_dispatcher_emits_same_event_to_all_sinks():
    first = RecordingSink()
    second = RecordingSink()
    event = ProgressEvent(
        event_type=ProgressEventType.SYNTHESIZING_AUDIO,
        progress=0.82,
    )

    ProgressDispatcher([first, second]).emit(event)

    assert first.events == [event]
    assert second.events == [event]


def test_progress_dispatcher_isolates_sink_failures():
    event = ProgressEvent(
        event_type=ProgressEventType.SYNTHESIZING_AUDIO,
        progress=0.82,
    )
    receiver = RecordingSink()

    class FailingSink:
        def emit(self, _event):
            raise RuntimeError("sink failed")

    ProgressDispatcher([FailingSink(), receiver]).emit(event)

    assert receiver.events == [event]


def test_callback_progress_sink_preserves_legacy_callback_shape():
    events = []
    sink = CallbackProgressSink(events.append)
    event = ProgressEvent(
        event_type=ProgressEventType.PREPARING_RENDER_MANIFEST,
        progress=0.86,
    )

    sink.emit(event)

    assert events == [event]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest tests/test_progress_dispatcher.py -v
```

Expected: fail because `ProgressDispatcher`, `CallbackProgressSink`, and the new event types do not exist.

- [ ] **Step 3: Implement progress contract primitives**

In `pixelle_video/models/progress.py`, add:

```python
from loguru import logger
from typing import Callable, Protocol, Sequence


class ProgressEventType(StrEnum):
    SYNTHESIZING_AUDIO = "synthesizing_audio"
    PREPARING_RENDER_MANIFEST = "preparing_render_manifest"
    RENDERING_FFMPEG_MANIFEST = "rendering_ffmpeg_manifest"
    RENDERING_HYPERFRAMES = "rendering_hyperframes"
```

Add the new i18n mappings next to the existing progress keys:

```python
ProgressEventType.SYNTHESIZING_AUDIO.value: "progress.synthesizing_audio",
ProgressEventType.PREPARING_RENDER_MANIFEST.value: "progress.preparing_render_manifest",
```

Add the sink contract:

```python
class ProgressSink(Protocol):
    """Receives structured progress events."""

    def emit(self, event: ProgressEvent) -> None:
        ...


class CallbackProgressSink:
    """Adapts the legacy progress callback shape to the sink contract."""

    def __init__(self, callback: Callable[[ProgressEvent], None]) -> None:
        self._callback = callback

    def emit(self, event: ProgressEvent) -> None:
        self._callback(event)


class ProgressDispatcher:
    """Fan out one progress event to every registered sink."""

    def __init__(self, sinks: Sequence[ProgressSink] | None = None) -> None:
        self._sinks = list(sinks or [])

    def emit(self, event: ProgressEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                logger.warning(f"Progress sink failed: {exc}")

    @property
    def sinks(self) -> tuple[ProgressSink, ...]:
        return tuple(self._sinks)
```

- [ ] **Step 4: Add translations**

In `web/i18n/locales/zh_CN.json`:

```json
"progress.synthesizing_audio": "正在生成音频...",
"progress.preparing_render_manifest": "正在准备渲染清单..."
```

In `web/i18n/locales/en_US.json`:

```json
"progress.synthesizing_audio": "Generating audio...",
"progress.preparing_render_manifest": "Preparing render manifest..."
```

- [ ] **Step 5: Verify dispatcher and i18n tests pass**

Run:

```bash
pytest tests/test_progress_dispatcher.py tests/test_i18n.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit and push**

```bash
git add pixelle_video/models/progress.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_progress_dispatcher.py tests/test_i18n.py
git commit -m "feat: 建立进度阶段分发契约"
git push origin dev
```

## Task 2: Stable TaskProgress And Lease-Checked Registry Update

**Files:**

- Modify: `api/tasks/models.py`
- Modify: `api/tasks/registry.py`
- Test: `tests/test_task_store_memory.py`

- [ ] **Step 1: Write the failing TaskProgress structure tests**

Update `tests/test_task_store_memory.py::test_memory_store_progress_update_requires_current_lease`:

```python
await store.update_progress(
    task_id="task-1",
    progress=TaskProgress(
        current=2,
        total=5,
        percentage=40.0,
        message="Generating audio...",
        event_type="synthesizing_audio",
    ),
    expected_owner_id="worker-current",
    expected_lease_token="token-current",
)

task = await store.get_task("task-1")
assert task.progress.message == "Generating audio..."
assert task.progress.event_type == "synthesizing_audio"
```

Add a registry-level lease test:

```python
@pytest.mark.asyncio
async def test_registry_update_progress_requires_current_lease():
    store = InMemoryTaskStore()
    registry = GenerationRegistry(
        store=store,
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "demo"},
        reuse_completed_within_seconds=86400,
    )
    claim = await registry.claim_next_pending(worker_id="worker-current")

    with pytest.raises(LostTaskLeaseError):
        await registry.update_progress(
            task_id="task-1",
            progress=TaskProgress(event_type="synthesizing_audio", percentage=82.0),
            owner_id="worker-old",
            lease_token="token-old",
        )

    await registry.update_progress(
        task_id="task-1",
        progress=TaskProgress(event_type="synthesizing_audio", percentage=82.0),
        owner_id=claim.lease.owner_id,
        lease_token=claim.lease.lease_token,
    )

    task = await registry.get_task("task-1")
    assert task.progress.event_type == "synthesizing_audio"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_task_store_memory.py -v
```

Expected: fail because `TaskProgress.event_type` and `GenerationRegistry.update_progress` do not exist.

- [ ] **Step 3: Extend TaskProgress**

In `api/tasks/models.py`:

```python
class TaskProgress(BaseModel):
    """Task progress information"""
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    message: str = ""
    event_type: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
```

Keep defaults backward-compatible so stored JSON without the new fields still loads.

- [ ] **Step 4: Add registry update_progress**

In `api/tasks/registry.py`:

```python
async def update_progress(
    self,
    *,
    task_id: str,
    progress: TaskProgress,
    owner_id: str,
    lease_token: str,
) -> None:
    await self.heartbeat(task_id=task_id, owner_id=owner_id, lease_token=lease_token)
    await self.store.update_progress(
        task_id=task_id,
        progress=progress,
        expected_owner_id=owner_id,
        expected_lease_token=lease_token,
    )
```

PostgreSQL needs no schema migration because task progress is stored as JSONB and the Pydantic defaults handle historical records.

- [ ] **Step 5: Verify task progress tests pass**

Run:

```bash
pytest tests/test_task_store_memory.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit and push**

```bash
git add api/tasks/models.py api/tasks/registry.py tests/test_task_store_memory.py
git commit -m "feat: 增加任务进度阶段字段"
git push origin dev
```

## Task 3: Task Progress Sink

**Files:**

- Create: `api/tasks/progress.py`
- Test: `tests/test_task_progress_sink.py`

- [ ] **Step 1: Write the failing sink tests**

Create `tests/test_task_progress_sink.py`:

```python
import asyncio

import pytest

from api.tasks.progress import TaskProgressSink, progress_event_to_task_progress
from pixelle_video.models.progress import ProgressEvent, ProgressEventType


def test_progress_event_to_task_progress_preserves_stable_event_type():
    progress = progress_event_to_task_progress(
        ProgressEvent(
            event_type=ProgressEventType.SYNTHESIZING_AUDIO,
            progress=0.823,
        )
    )

    assert progress.event_type == "synthesizing_audio"
    assert progress.percentage == 82.3
    assert progress.message == "Generating audio..."


@pytest.mark.asyncio
async def test_task_progress_sink_writes_with_owner_and_lease():
    class RecordingRegistry:
        def __init__(self):
            self.calls = []

        async def update_progress(self, **kwargs):
            self.calls.append(kwargs)

    registry = RecordingRegistry()
    sink = TaskProgressSink(
        registry=registry,
        task_id="task-1",
        owner_id="worker-1",
        lease_token="token-1",
    )

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.RENDERING_HYPERFRAMES,
            progress=0.9,
        )
    )
    await sink.drain()

    assert registry.calls[0]["task_id"] == "task-1"
    assert registry.calls[0]["owner_id"] == "worker-1"
    assert registry.calls[0]["lease_token"] == "token-1"
    assert registry.calls[0]["progress"].event_type == "rendering_hyperframes"


@pytest.mark.asyncio
async def test_task_progress_sink_drain_surfaces_fast_unexpected_failures():
    class FailingRegistry:
        async def update_progress(self, **_kwargs):
            raise RuntimeError("progress backend failed")

    sink = TaskProgressSink(
        registry=FailingRegistry(),
        task_id="task-1",
        owner_id="worker-1",
        lease_token="token-1",
    )

    sink.emit(
        ProgressEvent(
            event_type=ProgressEventType.RENDERING_HYPERFRAMES,
            progress=0.9,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="progress backend failed"):
        await sink.drain()
```

- [ ] **Step 2: Run sink tests and verify RED**

Run:

```bash
pytest tests/test_task_progress_sink.py -v
```

Expected: fail because `api.tasks.progress` does not exist. After the first sink version exists, the fast-failure test must fail if completed tasks are discarded before `drain()` retrieves their exceptions.

- [ ] **Step 3: Implement sink module**

Create `api/tasks/progress.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from api.tasks.models import TaskProgress
from api.tasks.store import LostTaskLeaseError
from pixelle_video.models.progress import ProgressEvent

PROGRESS_EVENT_FALLBACK_MESSAGES = {
    "synthesizing_audio": "Generating audio...",
    "preparing_render_manifest": "Preparing render manifest...",
    "rendering_hyperframes": "Rendering with HyperFrames...",
    "rendering_ffmpeg_manifest": "Rendering with FFmpeg...",
    "concatenating": "Concatenating video...",
    "completed": "Completed",
}


def progress_event_to_task_progress(event: ProgressEvent) -> TaskProgress:
    extra: dict[str, Any] = {}
    if event.frame_current is not None:
        extra["frame_current"] = event.frame_current
    if event.frame_total is not None:
        extra["frame_total"] = event.frame_total
    if event.step is not None:
        extra["step"] = event.step
    if event.action is not None:
        extra["action"] = event.action
    if event.extra_info is not None:
        extra["extra_info"] = str(event.extra_info)

    event_type = str(event.event_type)
    return TaskProgress(
        current=int(event.frame_current or 0),
        total=int(event.frame_total or 0),
        percentage=round(float(event.progress) * 100, 2),
        message=PROGRESS_EVENT_FALLBACK_MESSAGES.get(
            event_type,
            event_type.replace("_", " "),
        ),
        event_type=event_type,
        extra=extra,
    )


class TaskProgressSink:
    """Writes pipeline progress to the registry with the current execution lease."""

    def __init__(
        self,
        *,
        registry,
        task_id: str,
        owner_id: str,
        lease_token: str,
    ) -> None:
        self.registry = registry
        self.task_id = task_id
        self.owner_id = owner_id
        self.lease_token = lease_token
        self._tasks: set[asyncio.Task] = set()
        self._completed_tasks: list[asyncio.Task] = []

    def emit(self, event: ProgressEvent) -> None:
        task = asyncio.create_task(self._write(event))
        self._tasks.add(task)
        task.add_done_callback(self._track_completed)

    def _track_completed(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        self._completed_tasks.append(task)

    async def _write(self, event: ProgressEvent) -> None:
        try:
            await self.registry.update_progress(
                task_id=self.task_id,
                progress=progress_event_to_task_progress(event),
                owner_id=self.owner_id,
                lease_token=self.lease_token,
            )
        except LostTaskLeaseError:
            logger.warning(f"Task {self.task_id} lease was lost before progress could be recorded")

    async def drain(self) -> None:
        if not self._tasks and not self._completed_tasks:
            return
        tasks = [*self._completed_tasks, *self._tasks]
        self._completed_tasks.clear()
        await asyncio.gather(*tasks)
```

Only `LostTaskLeaseError` is suppressed. Unexpected registry or store failures remain visible through `drain()`.

- [ ] **Step 4: Verify sink tests pass**

Run:

```bash
pytest tests/test_task_progress_sink.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit and push**

```bash
git add api/tasks/progress.py tests/test_task_progress_sink.py
git commit -m "feat: 增加任务进度写入 sink"
git push origin dev
```

## Task 4: Pipeline Dispatcher Wiring

**Files:**

- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/base.py`
- Modify: `pixelle_video/services/generation_coordinator.py`
- Test: `tests/test_progress_dispatcher.py`
- Test: `tests/test_generation_coordinator.py`

- [ ] **Step 1: Write the failing dispatcher wiring tests**

Append to `tests/test_progress_dispatcher.py`:

```python
from types import SimpleNamespace

import pytest

from pixelle_video.models.progress import ProgressDispatcher, ProgressEventType
from pixelle_video.pipelines.linear import LinearVideoPipeline


class RecordingPipeline(LinearVideoPipeline):
    async def setup_environment(self, ctx):
        pass

    async def generate_content(self, ctx):
        pass

    async def determine_title(self, ctx):
        pass

    async def plan_visuals(self, ctx):
        pass

    async def initialize_storyboard(self, ctx):
        pass

    async def produce_assets(self, ctx):
        self._report_progress(
            ctx.progress_dispatcher,
            ProgressEventType.SYNTHESIZING_AUDIO,
            0.82,
        )

    async def post_production(self, ctx):
        pass

    async def finalize(self, ctx):
        return "ok"


@pytest.mark.asyncio
async def test_linear_pipeline_combines_legacy_callback_and_dispatcher():
    legacy_events = []
    dispatcher_events = []

    class RecordingSink:
        def emit(self, event):
            dispatcher_events.append(event)

    pipeline = RecordingPipeline(SimpleNamespace(llm=None, tts=None, media=None, video=None))

    result = await pipeline(
        text="demo",
        progress_callback=legacy_events.append,
        progress_dispatcher=ProgressDispatcher([RecordingSink()]),
    )

    assert result == "ok"
    assert [event.event_type for event in legacy_events] == ["synthesizing_audio"]
    assert [event.event_type for event in dispatcher_events] == ["synthesizing_audio"]


@pytest.mark.asyncio
async def test_linear_pipeline_excludes_progress_dispatcher_from_ctx_params():
    captured = {}

    class ParamInspectingPipeline(RecordingPipeline):
        async def setup_environment(self, ctx):
            captured["params"] = dict(ctx.params)

    pipeline = ParamInspectingPipeline(SimpleNamespace(llm=None, tts=None, media=None, video=None))

    await pipeline(
        text="demo",
        progress_dispatcher=ProgressDispatcher([RecordingSink()]),
    )

    assert "progress_dispatcher" not in captured["params"]
```

Append to `tests/test_generation_coordinator.py`:

```python
def test_generation_fingerprint_ignores_progress_dispatcher():
    first = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={"progress_dispatcher": object(), "frame_template": "a.html"},
    )
    second = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={"progress_dispatcher": object(), "frame_template": "a.html"},
    )

    assert first == second
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_progress_dispatcher.py tests/test_generation_coordinator.py -v
```

Expected: dispatcher wiring fails because `PipelineContext.progress_dispatcher` is missing or because `progress_dispatcher` still affects fingerprints.

- [ ] **Step 3: Update PipelineContext and LinearVideoPipeline**

In `pixelle_video/pipelines/linear.py`:

```python
progress_dispatcher: Optional[ProgressDispatcher] = None
```

In `LinearVideoPipeline.__call__`:

```python
incoming_dispatcher = kwargs.get("progress_dispatcher")
sinks = []
if progress_callback is not None:
    sinks.append(CallbackProgressSink(progress_callback))
if incoming_dispatcher is not None:
    sinks.extend(incoming_dispatcher.sinks)
progress_dispatcher = ProgressDispatcher(sinks) if sinks else None
effective_progress_callback = (
    progress_dispatcher.emit if progress_dispatcher is not None else progress_callback
)
pipeline_params = {
    key: value
    for key, value in kwargs.items()
    if key != "progress_dispatcher"
}
```

Pass `progress_callback=effective_progress_callback`, `progress_dispatcher=progress_dispatcher`, and `params=pipeline_params` to `PipelineContext`.

- [ ] **Step 4: Update BasePipeline `_report_progress`**

In `pixelle_video/pipelines/base.py`:

```python
def _report_progress(
    self,
    callback: Optional[Callable[[ProgressEvent], None] | ProgressSink],
    event_type: str | ProgressEventType,
    progress: float,
    **kwargs
):
    if callback:
        event = ProgressEvent(event_type=event_type, progress=progress, **kwargs)
        emit = getattr(callback, "emit", None)
        if callable(emit):
            emit(event)
        else:
            callback(event)
        logger.debug(f"Progress: {progress*100:.0f}% - {event_type}")
    else:
        logger.debug(f"Progress: {progress*100:.0f}% - {event_type}")
```

- [ ] **Step 5: Exclude runtime dispatcher from fingerprints**

In `pixelle_video/services/generation_coordinator.py`, include `"progress_dispatcher"` in `VOLATILE_GENERATION_PARAM_NAMES`.

Confirm `normalize_standard_video_generation_params()` keeps unknown runtime keys by copying the input mapping before normalizing storyboard fields. That preserves the dispatcher for execution while the pipeline context excludes it from serializable params.

- [ ] **Step 6: Verify wiring tests pass**

Run:

```bash
pytest tests/test_progress_dispatcher.py tests/test_generation_coordinator.py -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit and push**

```bash
git add pixelle_video/pipelines/linear.py pixelle_video/pipelines/base.py pixelle_video/services/generation_coordinator.py tests/test_progress_dispatcher.py tests/test_generation_coordinator.py
git commit -m "refactor: 接入统一进度分发器"
git push origin dev
```

## Task 5: HyperFrames Stage Order

**Files:**

- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_hyperframes_mode.py`

- [ ] **Step 1: Write the failing HyperFrames progress order test**

Add to `tests/test_standard_pipeline_hyperframes_mode.py`:

```python
@pytest.mark.asyncio
async def test_post_production_reports_audio_before_hyperframes_render(monkeypatch, tmp_path):
    monkeypatch.setattr("pixelle_video.pipelines.standard.VideoService", _NoConcatVideoService)
    core = _DummyCore(tmp_path)
    pipeline = StandardPipeline(core)
    ctx = _build_storyboard_context(tmp_path)
    ctx.final_video_path = str(tmp_path / "task-1" / "final.mp4")
    events = []
    ctx.progress_callback = events.append

    for frame in ctx.storyboard.frames:
        frame.media_type = "image"
        frame.image_path = str(tmp_path / f"{frame.index:02d}_raw.png")
        Path(frame.image_path).write_text("raw", encoding="utf-8")

    def fake_normalize_audio(input_path, output_path):
        Path(output_path).write_bytes(b"wav")
        return output_path

    def fake_concat_audio_files(audio_paths, output_path, **kwargs):
        Path(output_path).write_bytes(b"master-audio")

    monkeypatch.setattr(pipeline, "_normalize_audio_for_hyperframes", fake_normalize_audio)
    monkeypatch.setattr(pipeline, "_concat_audio_files", fake_concat_audio_files)
    monkeypatch.setattr(pipeline, "_get_audio_duration", lambda _path: 2.0)

    await pipeline.post_production(ctx)

    event_types = [event.event_type for event in events]
    assert event_types.index("synthesizing_audio") < event_types.index("rendering_hyperframes")
    assert event_types.index("preparing_render_manifest") < event_types.index("rendering_hyperframes")
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
pytest tests/test_standard_pipeline_hyperframes_mode.py::test_post_production_reports_audio_before_hyperframes_render -v
```

Expected: fail because the old path emits `rendering_hyperframes` before audio synthesis and does not emit the new stages.

- [ ] **Step 3: Add a progress target helper**

In `pixelle_video/pipelines/standard.py`:

```python
@staticmethod
def _progress_target(ctx: PipelineContext):
    dispatcher = getattr(ctx, "progress_dispatcher", None)
    if dispatcher is not None:
        return dispatcher
    return ctx.progress_callback
```

- [ ] **Step 4: Reorder HyperFrames post-production progress**

In `_post_production_hyperframes(...)`, after precondition checks and before `_synthesize_hyperframes_audio(ctx)`:

```python
progress_target = self._progress_target(ctx)
self._report_progress(
    progress_target,
    ProgressEventType.SYNTHESIZING_AUDIO,
    0.82,
)
master_audio_path, master_audio_duration = await self._synthesize_hyperframes_audio(ctx)
```

Before visual clip materialization and manifest/project writing:

```python
self._report_progress(
    progress_target,
    ProgressEventType.PREPARING_RENDER_MANIFEST,
    0.86,
)
```

Immediately before calling the HyperFrames renderer:

```python
self._report_progress(
    progress_target,
    ProgressEventType.RENDERING_HYPERFRAMES,
    0.90,
)
final_video_path = self.core.hyperframes_renderer.render(...)
```

- [ ] **Step 5: Verify HyperFrames tests pass**

Run:

```bash
pytest tests/test_standard_pipeline_hyperframes_mode.py::test_post_production_reports_audio_before_hyperframes_render -v
pytest tests/test_standard_pipeline_hyperframes_mode.py -v
```

Expected: all selected HyperFrames tests pass.

- [ ] **Step 6: Commit and push**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_hyperframes_mode.py
git commit -m "fix: 修正 HyperFrames 音频与渲染进度顺序"
git push origin dev
```

## Task 6: Embedded Executor Task Progress Sink

**Files:**

- Modify: `api/tasks/manager.py`
- Modify: `api/routers/video.py`
- Test: `tests/test_async_video_registry_integration.py`
- Test: `tests/test_video_api.py`

- [ ] **Step 1: Write the failing embedded progress test**

Add to `tests/test_async_video_registry_integration.py`:

```python
@pytest.mark.asyncio
async def test_embedded_registry_task_persists_progress_from_pipeline_dispatcher():
    manager = TaskManager(execution_mode="embedded")
    outcome = await manager.reserve_or_reuse_generation_task(
        task_type=TaskType.VIDEO_GENERATION,
        generation_fingerprint="fp-progress",
        request_params={"text": "demo"},
    )

    async def generate(progress_dispatcher=None):
        progress_dispatcher.emit(
            ProgressEvent(
                event_type=ProgressEventType.SYNTHESIZING_AUDIO,
                progress=0.82,
            )
        )
        return {"ok": True}

    await manager.execute_task(outcome.task.task_id, generate)
    future = manager._task_futures[outcome.task.task_id]
    await future

    task = await manager.get_task(outcome.task.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.progress.event_type == "synthesizing_audio"
```

Add to `tests/test_video_api.py`:

```python
@pytest.mark.asyncio
async def test_generate_video_async_passes_progress_dispatcher_to_video_core(monkeypatch, tmp_path):
    captured = {}

    class FakeTaskManager:
        execution_mode = "embedded"

        async def reserve_or_reuse_generation_task(self, **_kwargs):
            task = SimpleNamespace(task_id="task-1")
            return SimpleNamespace(task=task, created=True)

        async def execute_task(self, *, task_id, coro_func):
            captured["task_id"] = task_id
            captured["result"] = await coro_func(progress_dispatcher="dispatcher-token")

    class FakePixelleVideo:
        def __init__(self):
            self.calls = []

        async def generate_video(self, **kwargs):
            self.calls.append(kwargs)
            output = tmp_path / "final.mp4"
            output.write_bytes(b"video")
            return SimpleNamespace(video_path=str(output), duration=2.0)

    fake_pixelle_video = FakePixelleVideo()
    monkeypatch.setattr("api.routers.video.task_manager", FakeTaskManager())
    monkeypatch.setattr("api.routers.video.pixelle_video", fake_pixelle_video)

    response = await generate_video_async(request_body=VideoGenerateRequest(text="demo"))

    assert response.task_id == "task-1"
    assert captured["task_id"] == "task-1"
    assert fake_pixelle_video.calls[0]["progress_dispatcher"] == "dispatcher-token"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest tests/test_async_video_registry_integration.py::test_embedded_registry_task_persists_progress_from_pipeline_dispatcher tests/test_video_api.py::test_generate_video_async_passes_progress_dispatcher_to_video_core -v
```

Expected: fail because the embedded executor and route closure do not pass a dispatcher.

- [ ] **Step 3: Inject task progress sink in embedded execution**

In `api/tasks/manager.py`, after the embedded task has a store owner and lease:

```python
progress_sink = TaskProgressSink(
    registry=self.registry,
    task_id=task_id,
    owner_id=owner_id,
    lease_token=lease_token,
)
progress_dispatcher = ProgressDispatcher([progress_sink])

try:
    result = await coro_func(
        *args,
        progress_dispatcher=progress_dispatcher,
        **kwargs,
    )
finally:
    await progress_sink.drain()
```

- [ ] **Step 4: Update API async route closure**

In `api/routers/video.py`:

```python
async def execute_video_generation(progress_dispatcher=None):
    """Execute video generation in background"""
    video_params = {
        **generation_params,
        "api_task_id": task.task_id,
    }
    if progress_dispatcher is not None:
        video_params["progress_dispatcher"] = progress_dispatcher

    result = await pixelle_video.generate_video(**video_params)
```

Keep the reserve path free of callbacks because it is not the execution owner and cannot hold a lease.

- [ ] **Step 5: Verify embedded tests pass**

Run:

```bash
pytest tests/test_async_video_registry_integration.py tests/test_video_api.py::test_generate_video_async_passes_progress_dispatcher_to_video_core -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit and push**

```bash
git add api/tasks/manager.py api/routers/video.py tests/test_async_video_registry_integration.py tests/test_video_api.py
git commit -m "feat: 在内嵌执行器写入任务进度"
git push origin dev
```

## Task 7: Worker Task Progress Sink

**Files:**

- Modify: `api/tasks/worker.py`
- Test: `tests/test_worker_execution.py`

- [ ] **Step 1: Write the failing worker progress test**

Add to `tests/test_worker_execution.py`:

```python
@pytest.mark.asyncio
async def test_worker_persists_progress_from_pipeline_dispatcher(tmp_path):
    class ProgressCore:
        async def generate_video(self, **params):
            dispatcher = params["progress_dispatcher"]
            dispatcher.emit(
                ProgressEvent(
                    event_type=ProgressEventType.SYNTHESIZING_AUDIO,
                    progress=0.82,
                )
            )
            output = Path(params["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"video")
            return SimpleNamespace(video_path=str(output), duration=2.5)

    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=LocalArtifactStore(output_root=tmp_path / "output"),
        task_id_factory=lambda: "task-1",
    )
    await registry.reserve_or_reuse(
        fingerprint="fp-1",
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"text": "demo"},
        reuse_completed_within_seconds=86400,
    )
    worker = GenerationWorker(
        registry=registry,
        core=ProgressCore(),
        artifact_store=registry.artifact_store,
        output_root=tmp_path / "work",
    )

    assert await worker.run_once() is True
    task = await registry.get_task("task-1")
    assert task.progress.event_type == "synthesizing_audio"
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
pytest tests/test_worker_execution.py::test_worker_persists_progress_from_pipeline_dispatcher -v
```

Expected: fail because worker execution does not inject `progress_dispatcher`.

- [ ] **Step 3: Inject task progress sink in worker**

In `api/tasks/worker.py`, inside `GenerationWorker.run_once()` after claiming the task:

```python
progress_sink = TaskProgressSink(
    registry=self.registry,
    task_id=task.task_id,
    owner_id=lease.owner_id,
    lease_token=lease.lease_token,
)
params["progress_dispatcher"] = ProgressDispatcher([progress_sink])
```

Drain it after generation and before artifact persistence:

```python
result = await self._generate_with_heartbeat(...)
await progress_sink.drain()
artifact = await self.artifact_store.persist_video(...)
```

On error paths, call the helper that drains the sink and logs unexpected drain failures:

```python
async def _drain_progress_sink(progress_sink: TaskProgressSink | None) -> None:
    if progress_sink is None:
        return
    try:
        await progress_sink.drain()
    except Exception as exc:
        logger.warning(f"Task progress drain failed: {exc}")
```

- [ ] **Step 4: Verify worker tests pass**

Run:

```bash
pytest tests/test_worker_execution.py -v
```

Expected: all worker tests pass.

- [ ] **Step 5: Commit and push**

```bash
git add api/tasks/worker.py tests/test_worker_execution.py
git commit -m "feat: 在 worker 执行器写入任务进度"
git push origin dev
```

## Task 8: Final Verification

**Files:**

- No production edits expected unless verification reveals a concrete defect.

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
pytest tests/test_progress_dispatcher.py tests/test_task_progress_sink.py tests/test_task_store_memory.py tests/test_worker_execution.py tests/test_async_video_registry_integration.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_i18n.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run API and fingerprint compatibility tests**

Run:

```bash
pytest tests/test_video_api.py tests/test_generation_coordinator.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run code-quality checks**

Run:

```bash
ruff check api/tasks/progress.py api/tasks/manager.py api/tasks/worker.py api/routers/video.py pixelle_video/models/progress.py pixelle_video/pipelines/base.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/services/generation_coordinator.py tests/test_progress_dispatcher.py tests/test_task_progress_sink.py tests/test_task_store_memory.py tests/test_worker_execution.py tests/test_async_video_registry_integration.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_video_api.py tests/test_generation_coordinator.py tests/test_i18n.py
python -m compileall api pixelle_video tests
git diff --check
```

Expected: each command exits with status 0.

- [ ] **Step 4: Inspect git state before each commit**

Run:

```bash
git status --short
git diff --stat
```

Expected: only the current atomic change is staged. Existing unrelated worktree changes remain unstaged.

- [ ] **Step 5: Manual behavior checklist**

Confirm from tests and code inspection:

```text
HyperFrames emits synthesizing_audio before preparing_render_manifest and rendering_hyperframes.
TaskProgress persists stable event_type and extra fields.
Progress writes go through owner_id plus lease_token.
The API async reserve path does not create cross-process callbacks.
The embedded executor and worker executor create progress sinks only after owning a lease.
progress_dispatcher does not affect generation fingerprints or serializable pipeline params.
Unexpected async progress write failures are retrievable through drain.
```

## Review Gates

- First review gate: inspect the full source path from API route or worker claim to pipeline progress emission and registry persistence. Check task ownership, volatile parameter handling, event ordering, and tests that would fail under the old behavior.
- Second review gate: rerun focused tests, lint, compile, and diff checks after any review fix. Re-scan the plan and source for accidental unrelated edits before committing.

## Plan Self-Review

- Spec coverage:
  - New progress events: Task 1.
  - Dispatcher/sink contract: Tasks 1 and 4.
  - HyperFrames stage order: Task 5.
  - Executor-owned task progress sink: Tasks 6 and 7.
  - Stable task progress fields: Task 2.
  - Lease-safe progress writes: Tasks 2, 3, 6, and 7.
  - Async sink exception retrieval: Task 3.
- Placeholder scan result: no unresolved marker patterns remain.
- Type consistency:
  - `ProgressDispatcher.emit(event)` is the common fan-out method.
  - `TaskProgress.event_type` is the stable persisted stage field.
  - `progress_dispatcher` is runtime-only and excluded from task identity.
