# Log Persistence and AI Creation Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add global and task-scoped log persistence, correlation IDs, and structured AI creation stage logs so `Quick Create -> AI Creation` slowness can be diagnosed from saved artifacts instead of console output alone.

**Architecture:** Introduce one centralized logging utility that bootstraps `loguru`, redacts sensitive fields before serialization, binds request and task context, and writes flat project-owned JSONL records for both process-wide logs and task-local logs. Add a task-log session lifecycle so task sinks are attached when `task_id` becomes known and detached in `finally`, then extend the standard pipeline and persistence layer so AI creation stages emit structured events, `metadata.json` keeps an `observability` summary for both success and failure, and history detail loaders can return that summary without parsing raw log files.

**Tech Stack:** Python 3.12, Loguru, FastAPI, Streamlit, Pydantic, pytest, JSONL

---

Repository note: `AGENTS.md` forbids `git worktree`, so execute this plan on the current branch and stage only the files listed in each task for each atomic commit. Push after each commit.

## File Structure

- Create: `pixelle_video/utils/logging_util.py`
  Central logging bootstrap, redaction, flat JSONL serialization, correlation helpers, task sink attachment and detachment, and stage-event helpers.
- Modify: `pixelle_video/config/schema.py`
  Add the `logging` config schema.
- Modify: `config.yaml`
  Add the default `logging` section.
- Modify: `api/app.py`
  Bootstrap API logging at process startup.
- Modify: `web/app.py`
  Bootstrap web logging at process startup.
- Modify: `api/routers/video.py`
  Create and propagate `request_id`; bind `api_task_id` for async requests.
- Modify: `api/tasks/manager.py`
  Bind `api_task_id` into task lifecycle logs.
- Modify: `web/components/output_preview.py`
  Create or reuse `session_id`, create `request_id`, and pass both into generation requests.
- Modify: `pixelle_video/pipelines/linear.py`
  Extend `PipelineContext` with correlation and observability fields.
- Modify: `pixelle_video/pipelines/standard.py`
  Attach task log sinks, aggregate AI creation summaries, and persist `metadata.json.observability`.
- Modify: `pixelle_video/services/persistence.py`
  Add task log path helpers under `output/<task_id>/logs/`.
- Modify: `pixelle_video/services/history_manager.py`
  Return `observability` in task detail payloads.
- Modify: `pixelle_video/utils/content_generators.py`
  Emit structured AI creation stage events and forward stage summaries back to the pipeline.
- Create: `tests/test_logging_util.py`
  Lock the logging bootstrap and redaction contract.
- Create: `tests/test_task_log_persistence.py`
  Lock task log path helpers and persisted observability metadata.
- Modify: `tests/test_output_preview.py`
  Lock request and session correlation propagation from the web UI.
- Modify: `tests/test_storyboard_snapshot_persistence.py`
  Lock history-detail observability exposure.
- Modify: `tests/test_standard_pipeline_staged_mode.py`
  Lock pipeline-level observability persistence.
- Modify: `tests/test_content_generators_structured_output.py`
  Lock AI creation stage callback emission from content generators.

Initial implementation scope note: global and task-scoped runtime log persistence applies to all generation entrypoints, but the detailed `ai_creation` stage summary in this plan is intentionally limited to the `standard` pipeline that powers the current quick-create flow.

### Task 1: Add logging bootstrap, redaction, and config defaults

**Files:**
- Create: `pixelle_video/utils/logging_util.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `config.yaml`
- Create: `tests/test_logging_util.py`

- [ ] **Step 1: Write the failing logging utility tests**

```python
import json

from loguru import logger

from pixelle_video.utils.logging_util import redact_mapping, setup_logging, teardown_logging


def test_redact_mapping_masks_sensitive_keys():
    payload = {
        "api_key": "sk-secret",
        "nested": {"token": "abc123"},
        "model": "qwen-max",
    }

    redacted = redact_mapping(payload)

    assert redacted["api_key"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["model"] == "qwen-max"


def test_setup_logging_writes_flat_jsonl_record(tmp_path):
    sink_ids = setup_logging(
        service_name="web",
        config={
            "enabled": True,
            "level": "INFO",
            "log_dir": str(tmp_path),
            "rotation_mb": 50,
            "retention_days": 14,
            "task_logs_enabled": True,
            "ai_creation_logs_enabled": True,
            "preview_chars": 120,
        },
    )
    try:
        logger.bind(channel="runtime", service="web").info("hello logging")
    finally:
        teardown_logging(sink_ids)

    lines = (tmp_path / "web.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])

    assert payload["service"] == "web"
    assert payload["channel"] == "runtime"
    assert payload["message"] == "hello logging"


def test_setup_logging_redacts_bound_extra_before_disk_write(tmp_path):
    sink_ids = setup_logging(
        service_name="api",
        config={
            "enabled": True,
            "level": "INFO",
            "log_dir": str(tmp_path),
            "rotation_mb": 50,
            "retention_days": 14,
            "task_logs_enabled": True,
            "ai_creation_logs_enabled": True,
            "preview_chars": 120,
        },
    )
    try:
        logger.bind(config={"api_key": "sk-secret", "model": "qwen-max"}).info("config snapshot")
    finally:
        teardown_logging(sink_ids)

    payload = json.loads((tmp_path / "api.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert payload["extra"]["config"]["api_key"] == "***"
    assert payload["extra"]["config"]["model"] == "qwen-max"
```

- [ ] **Step 2: Run the logging utility tests to verify they fail**

Run: `uv run pytest tests/test_logging_util.py -v`

Expected: FAIL because `pixelle_video.utils.logging_util` and the new `logging` config do not exist yet.

- [ ] **Step 3: Add the logging config model and utility implementation**

```python
class LoggingConfig(BaseModel):
    enabled: bool = Field(default=True)
    level: str = Field(default="INFO")
    log_dir: str = Field(default="logs")
    rotation_mb: int = Field(default=50, ge=1)
    retention_days: int = Field(default=14, ge=1)
    task_logs_enabled: bool = Field(default=True)
    ai_creation_logs_enabled: bool = Field(default=True)
    preview_chars: int = Field(default=120, ge=20)
```

```python
_SENSITIVE_KEYS = {"api_key", "authorization", "bearer", "token", "secret", "password"}


def redact_mapping(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("***" if key.lower() in _SENSITIVE_KEYS else redact_mapping(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_mapping(item) for item in payload]
    return payload


def build_log_payload(record: dict[str, Any], *, service_name: str) -> dict[str, Any]:
    extra = redact_mapping(dict(record["extra"]))
    return {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "service": extra.get("service") or service_name,
        "channel": extra.get("channel", "runtime"),
        "message": record["message"],
        "request_id": extra.get("request_id"),
        "session_id": extra.get("session_id"),
        "api_task_id": extra.get("api_task_id"),
        "task_id": extra.get("task_id"),
        "pipeline": extra.get("pipeline"),
        "stage": extra.get("stage"),
        "event": extra.get("event"),
        "status": extra.get("status"),
        "latency_ms": extra.get("latency_ms"),
        "extra": extra,
    }


def setup_logging(service_name: str, config: dict[str, Any] | None = None) -> list[int]:
    resolved = _resolve_logging_config(config)
    log_dir = Path(resolved["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(
        extra={"service": service_name},
        patcher=lambda record: record["extra"].__setitem__(
            "jsonl_payload",
            json.dumps(build_log_payload(record, service_name=service_name), ensure_ascii=False),
        ),
    )
    console_sink = logger.add(sys.stderr, level=resolved["level"])
    file_sink = logger.add(
        log_dir / f"{service_name}.jsonl",
        level=resolved["level"],
        format="{extra[jsonl_payload]}\n",
        rotation=f"{resolved['rotation_mb']} MB",
        retention=f"{resolved['retention_days']} days",
    )
    return [console_sink, file_sink]


def teardown_logging(sink_ids: list[int]) -> None:
    for sink_id in sink_ids:
        logger.remove(sink_id)
```

```yaml
logging:
  enabled: true
  level: INFO
  log_dir: logs
  rotation_mb: 50
  retention_days: 14
  task_logs_enabled: true
  ai_creation_logs_enabled: true
  preview_chars: 120
```

- [ ] **Step 4: Re-run the logging utility tests**

Run: `uv run pytest tests/test_logging_util.py -v`

Expected: PASS with one redaction test and one JSONL bootstrap test.

- [ ] **Step 5: Commit and push the bootstrap change**

```bash
git add pixelle_video/utils/logging_util.py pixelle_video/config/schema.py config.yaml tests/test_logging_util.py
git commit -m "feat: add structured logging bootstrap"
git push origin dev
```

### Task 2: Bootstrap web and API logging, then propagate request context

**Files:**
- Modify: `api/app.py`
- Modify: `web/app.py`
- Modify: `api/routers/video.py`
- Modify: `api/tasks/manager.py`
- Modify: `web/components/output_preview.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_logging_util.py`

- [ ] **Step 1: Write the failing request-context propagation tests**

```python
def test_build_single_generation_request_passes_request_and_session_ids():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "request_id": "req_1234",
            "session_id": "sess_5678",
        },
        progress_callback=_progress,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )

    assert request["request_id"] == "req_1234"
    assert request["session_id"] == "sess_5678"
```

```python
def test_new_correlation_id_uses_prefix():
    request_id = new_correlation_id("req")
    session_id = new_correlation_id("sess")

    assert request_id.startswith("req_")
    assert session_id.startswith("sess_")
    assert request_id != session_id
```

- [ ] **Step 2: Run the web/request-context tests to verify they fail**

Run: `uv run pytest tests/test_output_preview.py tests/test_logging_util.py -k "request_and_session_ids or correlation_id" -v`

Expected: FAIL because the request builder and logging utility do not yet expose the new fields.

- [ ] **Step 3: Bootstrap logging in both app entrypoints and propagate request context**

```python
from pixelle_video.utils.logging_util import setup_logging


setup_logging("api")
```

```python
from pixelle_video.utils.logging_util import new_correlation_id


def _get_or_create_log_session_id(session_state) -> str:
    session_id = session_state.get("log_session_id")
    if not session_id:
        session_id = new_correlation_id("sess")
        session_state["log_session_id"] = session_id
    return session_id
```

```python
request_id = new_correlation_id("req")
session_id = _get_or_create_log_session_id(st.session_state)

generation_request = build_single_generation_request(
    {
        "text": text,
        "mode": mode,
        "title": title,
        "n_scenes": n_scenes,
        "split_mode": split_mode,
        "media_workflow": workflow_key,
        "frame_template": frame_template,
        "prompt_prefix": prompt_prefix,
        "bgm_path": bgm_path,
        "bgm_volume": bgm_volume,
        "tts_inference_mode": tts_mode,
        "tts_voice": selected_voice,
        "tts_speed": tts_speed,
        "tts_workflow": tts_workflow_key,
        "ref_audio": ref_audio_path,
        "template_params": custom_values_for_video,
        "request_id": request_id,
        "session_id": session_id,
    },
    progress_callback=update_progress,
    session_state=st.session_state,
)
```

```python
request_id = new_correlation_id("req")
video_params["request_id"] = request_id

if is_async:
    video_params["api_task_id"] = task.task_id
```

```python
logger.bind(api_task_id=task_id).info(f"Task {task_id} started")
```

- [ ] **Step 4: Re-run the focused propagation tests**

Run: `uv run pytest tests/test_output_preview.py tests/test_logging_util.py -k "request_and_session_ids or correlation_id" -v`

Expected: PASS and the request payload now includes correlation fields from the web UI path.

- [ ] **Step 5: Commit and push the request-context change**

```bash
git add api/app.py web/app.py api/routers/video.py api/tasks/manager.py web/components/output_preview.py tests/test_output_preview.py tests/test_logging_util.py
git commit -m "feat: bind request context to generation logs"
git push origin dev
```

### Task 3: Add task log paths, attach task sinks, and persist observability summaries

**Files:**
- Modify: `pixelle_video/utils/logging_util.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/services/history_manager.py`
- Create: `tests/test_task_log_persistence.py`
- Modify: `tests/test_storyboard_snapshot_persistence.py`

- [ ] **Step 1: Write the failing task-log persistence tests**

```python
from datetime import datetime

import pytest

from loguru import logger

from pixelle_video.services.history_manager import HistoryManager
from pixelle_video.services.persistence import PersistenceService
from pixelle_video.utils.logging_util import attach_task_log_sinks


def test_persistence_service_exposes_task_log_paths(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))

    assert persistence.get_task_logs_dir("task-1") == tmp_path / "task-1" / "logs"
    assert persistence.get_task_runtime_log_path("task-1") == tmp_path / "task-1" / "logs" / "runtime.jsonl"
    assert persistence.get_task_ai_creation_log_path("task-1") == tmp_path / "task-1" / "logs" / "ai_creation.jsonl"


def test_attach_task_log_sinks_stops_writing_after_close(tmp_path):
    task_dir = tmp_path / "task-1"
    task_dir.mkdir(parents=True, exist_ok=True)

    session = attach_task_log_sinks(task_id="task-1", task_dir=task_dir)
    try:
        logger.bind(task_id="task-1", channel="runtime").info("first task line")
    finally:
        session.close()

    logger.bind(task_id="task-2", channel="runtime").info("later task line")

    contents = (task_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    assert "first task line" in contents
    assert "later task line" not in contents


@pytest.mark.asyncio
async def test_history_manager_task_detail_includes_observability(tmp_path):
    persistence = PersistenceService(output_dir=str(tmp_path))
    history = HistoryManager(persistence)

    await persistence.save_task_metadata(
        "task-2",
        {
            "created_at": datetime.now(),
            "status": "completed",
            "input": {"text": "demo"},
            "result": {"video_path": "output/final.mp4"},
            "config": {},
            "observability": {
                "version": "v1",
                "ai_creation": {"slowest_stage": "storyboard_planning"},
            },
        },
    )

    detail = await history.get_task_detail("task-2")

    assert detail["observability"]["ai_creation"]["slowest_stage"] == "storyboard_planning"
```

- [ ] **Step 2: Run the persistence/history tests to verify they fail**

Run: `uv run pytest tests/test_task_log_persistence.py tests/test_storyboard_snapshot_persistence.py -v`

Expected: FAIL because log-path helpers and the top-level `observability` field are not implemented yet.

- [ ] **Step 3: Extend pipeline context, persistence helpers, and metadata persistence**

```python
@dataclass
class PipelineContext:
    input_text: str
    params: Dict[str, Any]
    progress_callback: Optional[Callable[[ProgressEvent], None]] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    api_task_id: Optional[str] = None
    task_log_session: Any = None
    observability: Dict[str, Any] = field(default_factory=dict)
```

```python
ctx = PipelineContext(
    input_text=text,
    params=kwargs,
    progress_callback=progress_callback,
    request_id=kwargs.get("request_id"),
    session_id=kwargs.get("session_id"),
    api_task_id=kwargs.get("api_task_id"),
)
```

```python
def get_task_logs_dir(self, task_id: str) -> Path:
    return self.get_task_dir(task_id) / "logs"


def get_task_runtime_log_path(self, task_id: str) -> Path:
    return self.get_task_logs_dir(task_id) / "runtime.jsonl"


def get_task_ai_creation_log_path(self, task_id: str) -> Path:
    return self.get_task_logs_dir(task_id) / "ai_creation.jsonl"
```

```python
ctx.observability.update(
    {
        "version": "v1",
        "request_id": ctx.request_id,
        "session_id": ctx.session_id,
        "api_task_id": ctx.api_task_id,
        "task_id": task_id,
        "runtime_log_path": str(self.core.persistence.get_task_runtime_log_path(task_id)),
        "ai_creation_log_path": str(self.core.persistence.get_task_ai_creation_log_path(task_id)),
    }
)
ctx.task_log_session = attach_task_log_sinks(task_id=task_id, task_dir=Path(task_dir))
```

```python
try:
    await self.setup_environment(ctx)
    await self.generate_content(ctx)
    await self.determine_title(ctx)
    await self.plan_visuals(ctx)
    await self.initialize_storyboard(ctx)
    await self.produce_assets(ctx)
    await self.post_production(ctx)
    return await self.finalize(ctx)
except Exception as error:
    await self._persist_failed_task_data(ctx, error)
    await self.handle_exception(ctx, error)
    raise
finally:
    if ctx.task_log_session is not None:
        ctx.task_log_session.close()
```

```python
metadata["observability"] = ctx.observability
```

```python
async def _persist_failed_task_data(self, ctx: PipelineContext, error: Exception) -> None:
    if not ctx.task_id:
        return

    metadata = {
        "task_id": ctx.task_id,
        "status": "failed",
        "error": str(error),
        "input": {"text": ctx.input_text, **ctx.params},
        "config": {},
        "observability": ctx.observability,
    }
    await self.core.persistence.save_task_metadata(ctx.task_id, metadata)
```

```python
return {
    "metadata": metadata,
    "storyboard": storyboard,
    "planning_snapshot": storyboard.planning_snapshot if storyboard else None,
    "observability": metadata.get("observability"),
}
```

- [ ] **Step 4: Re-run the persistence/history tests**

Run: `uv run pytest tests/test_task_log_persistence.py tests/test_storyboard_snapshot_persistence.py -v`

Expected: PASS with path helpers and `observability` visible in history detail payloads.

- [ ] **Step 5: Commit and push the task-log persistence change**

```bash
git add pixelle_video/utils/logging_util.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/services/persistence.py pixelle_video/services/history_manager.py tests/test_task_log_persistence.py tests/test_storyboard_snapshot_persistence.py
git commit -m "feat: persist task scoped observability metadata"
git push origin dev
```

### Task 4: Emit structured AI creation stage events and aggregate stage timings

**Files:**
- Modify: `pixelle_video/utils/logging_util.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_content_generators_structured_output.py`
- Modify: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Write the failing AI creation stage tests**

```python
@pytest.mark.asyncio
async def test_generate_title_reports_stage_callback():
    observed = []

    class FakeLLM:
        async def __call__(self, prompt, **kwargs):
            return "Demo Title"

    title = await content_generators.generate_title(
        FakeLLM(),
        "demo topic",
        strategy="llm",
        stage_callback=observed.append,
    )

    assert title == "Demo Title"
    assert [item["event"] for item in observed] == ["start", "end"]
    assert observed[0]["stage"] == "title_generation"
    assert observed[1]["latency_ms"] >= 0
```

```python
@pytest.mark.asyncio
async def test_generate_image_prompts_reports_actual_llm_call_count_for_batched_stage():
    observed = []

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def __call__(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return content_generators.ImagePromptBatchResponse(image_prompts=["prompt"] * 10)
            return content_generators.ImagePromptBatchResponse(image_prompts=["prompt"])

    prompts = await content_generators.generate_image_prompts(
        FakeLLM(),
        narrations=["scene"] * 11,
        batch_size=10,
        stage_callback=observed.append,
    )

    assert len(prompts) == 11
    end_event = next(item for item in observed if item["stage"] == "image_prompt_batch" and item["event"] == "end")
    assert end_event["llm_call_count"] == 2
    assert end_event["batch_total"] == 2
```

- [ ] **Step 2: Run the AI creation tests to verify they fail**

Run: `uv run pytest tests/test_content_generators_structured_output.py tests/test_standard_pipeline_staged_mode.py -k "stage_callback or observability" -v`

Expected: FAIL because the content generators do not yet accept a `stage_callback` and the standard pipeline does not yet aggregate AI creation timings.

- [ ] **Step 3: Add stage-event helpers and aggregate AI creation summaries**

```python
def emit_stage_event(
    *,
    channel: str,
    stage: str,
    event: str,
    message: str,
    callback: Callable[[dict[str, Any]], None] | None = None,
    **fields,
) -> None:
    payload = {"channel": channel, "stage": stage, "event": event, **fields}
    logger.bind(**payload).info(message)
    if callback is not None:
        callback(payload)
```

```python
stage_start = perf_counter()
emit_stage_event(
    channel="ai_creation",
    stage="title_generation",
    event="start",
    message="title generation started",
    callback=stage_callback,
)
response = await llm_service(prompt, temperature=0.7, max_tokens=50)
emit_stage_event(
    channel="ai_creation",
    stage="title_generation",
    event="end",
    message="title generation completed",
    callback=stage_callback,
    latency_ms=round((perf_counter() - stage_start) * 1000),
    llm_call_count=1,
    status="success",
)
```

```python
stage_llm_calls = 0
for batch_idx, batch_narrations in enumerate(batches, 1):
    for attempt in range(1, max_retries + 1):
        stage_llm_calls += 1
        prompt = build_image_prompt_prompt(
            narrations=batch_narrations,
            min_words=min_words,
            max_words=max_words,
            style_profile=style_profile,
        )
        response: ImagePromptBatchResponse = await llm_service(
            prompt=prompt,
            response_type=ImagePromptBatchResponse,
            temperature=0.7,
            max_tokens=8192,
        )
        batch_prompts = list(response.image_prompts)

emit_stage_event(
    channel="ai_creation",
    stage="image_prompt_batch",
    event="end",
    message="image prompt batch completed",
    callback=stage_callback,
    latency_ms=round((perf_counter() - stage_start) * 1000),
    llm_call_count=stage_llm_calls,
    retry_count=max(stage_llm_calls - len(batches), 0),
    batch_total=len(batches),
    status="success",
)
```

```python
def _record_ai_creation_stage(self, ctx: PipelineContext, event: dict[str, Any]) -> None:
    if event["channel"] != "ai_creation" or event["event"] != "end":
        return

    summary = ctx.observability.setdefault(
        "ai_creation",
        {"total_latency_ms": 0, "llm_call_count": 0, "slowest_stage": None, "stages": []},
    )
    stage_entry = {
        "stage": event["stage"],
        "status": event.get("status", "success"),
        "latency_ms": event.get("latency_ms", 0),
        "llm_call_count": event.get("llm_call_count", 0),
    }
    summary["stages"].append(stage_entry)
    summary["total_latency_ms"] = sum(item["latency_ms"] for item in summary["stages"])
    summary["slowest_stage"] = max(summary["stages"], key=lambda item: item["latency_ms"])["stage"]
    summary["llm_call_count"] += event.get("llm_call_count", 0)
```

```python
ctx.title = await generate_title(
    self.llm,
    text,
    strategy="auto",
    stage_callback=lambda payload: self._record_ai_creation_stage(ctx, payload),
)
```

- [ ] **Step 4: Run the focused AI creation regression suite**

Run: `uv run pytest tests/test_logging_util.py tests/test_task_log_persistence.py tests/test_storyboard_snapshot_persistence.py tests/test_output_preview.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py -q`

Expected: PASS and the pipeline now persists enough observability data to identify the slowest AI creation stage from `metadata.json` and the task log files.

- [ ] **Step 5: Commit and push the AI creation observability change**

```bash
git add pixelle_video/utils/logging_util.py pixelle_video/utils/content_generators.py pixelle_video/pipelines/standard.py tests/test_content_generators_structured_output.py tests/test_standard_pipeline_staged_mode.py
git commit -m "feat: log ai creation stage events"
git push origin dev
```

### Task 5: Final verification and diff audit

**Files:**
- Modify: `pixelle_video/utils/logging_util.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `config.yaml`
- Modify: `api/app.py`
- Modify: `web/app.py`
- Modify: `api/routers/video.py`
- Modify: `api/tasks/manager.py`
- Modify: `web/components/output_preview.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/services/history_manager.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Create: `tests/test_logging_util.py`
- Create: `tests/test_task_log_persistence.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_storyboard_snapshot_persistence.py`
- Modify: `tests/test_standard_pipeline_staged_mode.py`
- Modify: `tests/test_content_generators_structured_output.py`

- [ ] **Step 1: Run the full focused verification suite**

Run: `uv run pytest tests/test_logging_util.py tests/test_task_log_persistence.py tests/test_storyboard_snapshot_persistence.py tests/test_output_preview.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py -q`

Expected: PASS across the new logging tests, persistence/history tests, request-context tests, and standard pipeline AI creation tests.

- [ ] **Step 2: Audit the final diff before closing**

```bash
git diff --stat
git diff -- pixelle_video/utils/logging_util.py pixelle_video/config/schema.py config.yaml api/app.py web/app.py api/routers/video.py api/tasks/manager.py web/components/output_preview.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/services/persistence.py pixelle_video/services/history_manager.py pixelle_video/utils/content_generators.py tests/test_logging_util.py tests/test_task_log_persistence.py tests/test_output_preview.py tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py
```

Expected: only the observability feature files are present, with no unrelated workspace drift mixed into the branch.
