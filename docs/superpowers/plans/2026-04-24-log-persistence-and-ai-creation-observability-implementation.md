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
- Modify: `pixelle_video/pipelines/custom.py`
  Attach and detach task runtime sinks for the non-linear custom pipeline after its task directory is created.
- Modify: `pixelle_video/pipelines/asset_based.py`
  Attach and detach task runtime sinks for the asset-based pipeline, which overrides `LinearVideoPipeline.__call__`.
- Modify: `pixelle_video/services/persistence.py`
  Add task log path helpers under `output/<task_id>/logs/`.
- Modify: `pixelle_video/services/history_manager.py`
  Return `observability` in task detail payloads.
- Modify: `pixelle_video/utils/content_generators.py`
  Emit structured AI creation stage events and forward stage summaries back to the pipeline.
- Create: `tests/test_logging_util.py`
  Lock the logging bootstrap and redaction contract.
- Create: `tests/test_logging_redaction_policy.py`
  Lock message-level redaction and no-full-content global logging behavior.
- Create: `tests/test_task_log_persistence.py`
  Lock task log path helpers and persisted observability metadata.
- Create: `tests/test_task_log_context_isolation.py`
  Lock task sink filtering and concurrent task context isolation.
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
- Create: `tests/test_logging_redaction_policy.py`

- [ ] **Step 1: Write the failing logging utility tests**

```python
import json

from loguru import logger

from pixelle_video.utils.logging_util import (
    build_content_observability,
    redact_mapping,
    redact_text,
    setup_logging,
    teardown_logging,
)


def _logging_config(tmp_path):
    return {
        "enabled": True,
        "level": "INFO",
        "log_dir": str(tmp_path),
        "rotation_mb": 50,
        "retention_days": 14,
        "task_logs_enabled": True,
        "ai_creation_logs_enabled": True,
        "preview_chars": 12,
    }


def test_redact_mapping_masks_sensitive_keys_by_substring_and_suffix():
    payload = {
        "api_key": "sk-secret",
        "comfyui_api_key": "comfy-secret",
        "runninghub_api_key": "rh-secret",
        "nested": {"access_token": "abc123", "model": "qwen-max"},
    }

    redacted = redact_mapping(payload)

    assert redacted["api_key"] == "***"
    assert redacted["comfyui_api_key"] == "***"
    assert redacted["runninghub_api_key"] == "***"
    assert redacted["nested"]["access_token"] == "***"
    assert redacted["nested"]["model"] == "qwen-max"


def test_redact_text_masks_secret_bearing_message_fragments():
    message = "ComfyKit config: {'runninghub_api_key': 'rh-secret', 'model': 'x'}"

    redacted = redact_text(message)

    assert "rh-secret" not in redacted
    assert "***" in redacted
    assert "model" in redacted


def test_setup_logging_writes_complete_flat_jsonl_record(tmp_path):
    sink_ids = setup_logging(service_name="web", config=_logging_config(tmp_path))
    try:
        logger.bind(
            channel="ai_creation",
            service="pipeline",
            request_id="req_1",
            session_id="sess_1",
            api_task_id=None,
            task_id="task-1",
            pipeline="standard",
            stage="title_generation",
            event="end",
            status="success",
            provider="dashscope",
            model="qwen-max",
            latency_ms=12,
            llm_call_count=1,
            retry_count=0,
            attempt=1,
            batch_index=None,
            batch_total=None,
            narration_count=5,
            workflow="selfhost/image.json",
            template="1080x1920/default.html",
        ).info("title generation completed")
    finally:
        teardown_logging(sink_ids)

    payload = json.loads((tmp_path / "web.jsonl").read_text(encoding="utf-8").splitlines()[0])

    expected_keys = {
        "timestamp",
        "level",
        "service",
        "channel",
        "message",
        "request_id",
        "session_id",
        "api_task_id",
        "task_id",
        "pipeline",
        "stage",
        "event",
        "status",
        "provider",
        "model",
        "latency_ms",
        "llm_call_count",
        "retry_count",
        "attempt",
        "batch_index",
        "batch_total",
        "narration_count",
        "workflow",
        "template",
        "extra",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["service"] == "pipeline"
    assert payload["channel"] == "ai_creation"
    assert payload["llm_call_count"] == 1


def test_content_observability_uses_hash_length_and_bounded_preview():
    summary = build_content_observability("abcdefghijklmnopqrstuvwxyz", preview_chars=8)

    assert summary["input_length"] == 26
    assert summary["preview"] == "abcdefgh..."
    assert len(summary["content_hash"]) == 16
```

Create `tests/test_logging_redaction_policy.py`:

```python
import json

from loguru import logger

from pixelle_video.utils.logging_util import setup_logging, teardown_logging


def test_global_log_does_not_persist_secret_values_or_full_prompt_text(tmp_path):
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
            "preview_chars": 10,
        },
    )
    try:
        logger.bind(
            config={
                "comfyui_api_key": "comfy-secret",
                "runninghub_api_key": "rh-secret",
            },
            content={
                "input_length": 43,
                "content_hash": "abc123",
                "preview": "Long topic...",
            },
        ).info("Submitting generation request: Long topic...")
    finally:
        teardown_logging(sink_ids)

    raw_line = (tmp_path / "api.jsonl").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(raw_line)

    assert "comfy-secret" not in raw_line
    assert "rh-secret" not in raw_line
    assert "abcdefghijklmnopqrstuvwxyz" not in raw_line
    assert payload["extra"]["config"]["comfyui_api_key"] == "***"
    assert payload["extra"]["content"]["input_length"] == 43
```

- [ ] **Step 2: Run the logging utility tests to verify they fail**

Run: `uv run pytest tests/test_logging_util.py tests/test_logging_redaction_policy.py -v`

Expected: FAIL because `pixelle_video.utils.logging_util`, the complete JSONL contract, and the new `logging` config do not exist yet.

- [ ] **Step 3: Add the logging config model and utility implementation**

Add `LoggingConfig` to `pixelle_video/config/schema.py` and add `logging: LoggingConfig = Field(default_factory=LoggingConfig)` to `PixelleVideoConfig`:

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

Create `pixelle_video/utils/logging_util.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from loguru import logger


_SENSITIVE_TOKENS = ("api_key", "authorization", "bearer", "token", "secret", "password")
_REQUIRED_FIELDS = (
    "timestamp",
    "level",
    "service",
    "channel",
    "message",
    "request_id",
    "session_id",
    "api_task_id",
    "task_id",
    "pipeline",
    "stage",
    "event",
    "status",
    "provider",
    "model",
    "latency_ms",
    "llm_call_count",
    "retry_count",
    "attempt",
    "batch_index",
    "batch_total",
    "narration_count",
    "workflow",
    "template",
)


def is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in _SENSITIVE_TOKENS)


def redact_mapping(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("***" if is_sensitive_key(key) else redact_mapping(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_mapping(item) for item in payload]
    return payload


def redact_text(message: str) -> str:
    redacted = str(message)
    for token in _SENSITIVE_TOKENS:
        pattern = re.compile(
            rf"({token}|[A-Za-z0-9_]*{token}[A-Za-z0-9_]*)"
            rf"(\s*[:=]\s*)"
            rf"(['\"]?)[^,'\"\s}}]+(\3)",
            re.IGNORECASE,
        )
        redacted = pattern.sub(r"\1\2\3***\4", redacted)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", redacted, flags=re.IGNORECASE)
    return redacted


def build_content_observability(content: str | None, *, preview_chars: int = 120) -> dict[str, Any]:
    value = content or ""
    preview = value[:preview_chars]
    if len(value) > preview_chars:
        preview = f"{preview}..."
    return {
        "input_length": len(value),
        "content_hash": hashlib.sha256(value.encode("utf-8")).hexdigest()[:16],
        "preview": preview,
    }


def new_correlation_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_log_payload(record: dict[str, Any], *, service_name: str) -> dict[str, Any]:
    extra = redact_mapping(dict(record["extra"]))
    payload = {field: None for field in _REQUIRED_FIELDS}
    payload.update(
        {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "service": extra.get("service") or service_name,
            "channel": extra.get("channel", "runtime"),
            "message": redact_text(record["message"]),
            "extra": extra,
        }
    )
    for field in _REQUIRED_FIELDS:
        if field not in {"timestamp", "level", "service", "channel", "message"}:
            payload[field] = extra.get(field)
    return payload


def _jsonl_formatter(service_name: str) -> Callable[[dict[str, Any]], str]:
    def _format(record: dict[str, Any]) -> str:
        return json.dumps(build_log_payload(record, service_name=service_name), ensure_ascii=False) + "\n"

    return _format


def _resolve_logging_config(config: dict[str, Any] | None) -> dict[str, Any]:
    defaults = {
        "enabled": True,
        "level": "INFO",
        "log_dir": "logs",
        "rotation_mb": 50,
        "retention_days": 14,
        "task_logs_enabled": True,
        "ai_creation_logs_enabled": True,
        "preview_chars": 120,
    }
    return {**defaults, **(config or {})}


def setup_logging(service_name: str, config: dict[str, Any] | None = None) -> list[int]:
    resolved = _resolve_logging_config(config)
    if not resolved["enabled"]:
        return []

    log_dir = Path(resolved["log_dir"])
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(extra={"service": service_name})
    console_sink = logger.add(sys.stderr, level=resolved["level"])
    file_sink = logger.add(
        log_dir / f"{service_name}.jsonl",
        level=resolved["level"],
        format=_jsonl_formatter(service_name),
        rotation=f"{resolved['rotation_mb']} MB",
        retention=f"{resolved['retention_days']} days",
    )
    return [console_sink, file_sink]


def teardown_logging(sink_ids: list[int]) -> None:
    for sink_id in sink_ids:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass


@contextmanager
def bind_log_context(**context: Any) -> Iterator[None]:
    clean_context = {key: value for key, value in context.items() if value is not None}
    with logger.contextualize(**clean_context):
        yield
```

Add this default section to `config.yaml`:

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

Run: `uv run pytest tests/test_logging_util.py tests/test_logging_redaction_policy.py -v`

Expected: PASS with complete JSONL top-level fields, broad key redaction, message redaction, and bounded content summaries.

- [ ] **Step 5: Commit and push the bootstrap change**

```bash
git add pixelle_video/utils/logging_util.py pixelle_video/config/schema.py config.yaml tests/test_logging_util.py tests/test_logging_redaction_policy.py
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
- Modify: `web/utils/batch_manager.py`
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
def test_build_batch_shared_config_passes_session_id():
    shared = output_preview.build_batch_shared_config(
        {
            "frame_template": "1080x1920/default.html",
            "tts_inference_mode": "local",
            "session_id": "sess_5678",
        }
    )

    assert shared["session_id"] == "sess_5678"
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

Run: `uv run pytest tests/test_output_preview.py tests/test_logging_util.py -k "request_and_session_ids or batch_shared_config_passes_session_id or correlation_id" -v`

Expected: FAIL because the request builder and logging utility do not yet expose the new fields.

- [ ] **Step 3: Bootstrap logging in both app entrypoints and propagate request context**

```python
from pixelle_video.config import config_manager
from pixelle_video.utils.logging_util import setup_logging


setup_logging("api", config_manager.config.logging.model_dump())
```

```python
from pixelle_video.config import config_manager
from pixelle_video.utils.logging_util import new_correlation_id, setup_logging


setup_logging("web", config_manager.config.logging.model_dump())
```

```python
from pixelle_video.utils.logging_util import build_content_observability, new_correlation_id


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
request["request_id"] = video_params.get("request_id")
request["session_id"] = video_params.get("session_id")
```

```python
session_id = video_params.get("session_id")
if session_id:
    shared_config["session_id"] = session_id
```

```python
from pixelle_video.utils.logging_util import new_correlation_id


task_params = {
    "text": topic,
    "mode": "generate",
    "request_id": new_correlation_id("req"),
    "session_id": shared_config.get("session_id"),
}
```

```python
from pixelle_video.utils.logging_util import build_content_observability, new_correlation_id


request_id = new_correlation_id("req")
logger.bind(
    request_id=request_id,
    channel="runtime",
    content=build_content_observability(request_body.text),
).info("sync video generation request received")
video_params["request_id"] = request_id
```

For async API generation, create `request_id` before `task_manager.create_task(...)`, store it in `request_params`, and pass both IDs to the pipeline:

```python
request_id = new_correlation_id("req")
task = task_manager.create_task(
    task_type=TaskType.VIDEO_GENERATION,
    request_params={**request_body.model_dump(), "request_id": request_id},
)
video_params["request_id"] = request_id
video_params["api_task_id"] = task.task_id
```

In `api/tasks/manager.py`, bind task lifecycle logs with context rather than only rendering the ID into the message:

```python
from pixelle_video.utils.logging_util import bind_log_context


async def _execute():
    with bind_log_context(api_task_id=task_id, channel="runtime"):
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            logger.info("task started")
            result = await coro_func(*args, **kwargs)
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now()
            logger.info("task completed")
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            logger.error(f"task failed: {e}")
```

- [ ] **Step 4: Re-run the focused propagation tests**

Run: `uv run pytest tests/test_output_preview.py tests/test_logging_util.py -k "request_and_session_ids or batch_shared_config_passes_session_id or correlation_id" -v`

Expected: PASS and the request payload now includes correlation fields from the single and batch web UI paths.

- [ ] **Step 5: Commit and push the request-context change**

```bash
git add api/app.py web/app.py api/routers/video.py api/tasks/manager.py web/components/output_preview.py web/utils/batch_manager.py tests/test_output_preview.py tests/test_logging_util.py
git commit -m "feat: bind request context to generation logs"
git push origin dev
```

### Task 3: Add task log paths, attach task sinks, and persist observability summaries

**Files:**
- Modify: `pixelle_video/utils/logging_util.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/services/history_manager.py`
- Create: `tests/test_task_log_persistence.py`
- Create: `tests/test_task_log_context_isolation.py`
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

Create `tests/test_task_log_context_isolation.py`:

```python
import asyncio

from loguru import logger

from pixelle_video.utils.logging_util import attach_task_log_sinks


async def _write_task_line(task_dir, task_id, message):
    session = attach_task_log_sinks(task_id=task_id, task_dir=task_dir)
    try:
        logger.bind(channel="runtime").info(message)
        await asyncio.sleep(0)
        logger.bind(channel="ai_creation", stage="title_generation", event="end").info(f"{message} ai")
    finally:
        session.close()


async def _run_parallel_writes(task_a_dir, task_b_dir):
    await asyncio.gather(
        _write_task_line(task_a_dir, "task-a", "only task a"),
        _write_task_line(task_b_dir, "task-b", "only task b"),
    )


def test_parallel_task_log_sessions_do_not_cross_write(tmp_path):
    task_a_dir = tmp_path / "task-a"
    task_b_dir = tmp_path / "task-b"

    asyncio.run(_run_parallel_writes(task_a_dir, task_b_dir))

    task_a_runtime = (task_a_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    task_b_runtime = (task_b_dir / "logs" / "runtime.jsonl").read_text(encoding="utf-8")
    task_a_ai = (task_a_dir / "logs" / "ai_creation.jsonl").read_text(encoding="utf-8")

    assert "only task a" in task_a_runtime
    assert "only task b" not in task_a_runtime
    assert "only task b" in task_b_runtime
    assert "only task a" not in task_b_runtime
    assert "only task a ai" in task_a_ai
```

- [ ] **Step 2: Run the persistence/history tests to verify they fail**

Run: `uv run pytest tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_storyboard_snapshot_persistence.py -v`

Expected: FAIL because log-path helpers, task-sink context isolation, and the top-level `observability` field are not implemented yet.

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
@dataclass
class TaskLogSession:
    sink_ids: list[int]
    context_manager: Any

    def close(self) -> None:
        for sink_id in self.sink_ids:
            try:
                logger.remove(sink_id)
            except ValueError:
                pass
        self.context_manager.__exit__(None, None, None)


def attach_task_log_sinks(
    *,
    task_id: str,
    task_dir: Path,
    service_name: str = "pipeline",
    ai_creation_enabled: bool = True,
) -> TaskLogSession:
    logs_dir = Path(task_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    def _task_filter(record: dict[str, Any]) -> bool:
        return record["extra"].get("task_id") == task_id

    def _ai_creation_filter(record: dict[str, Any]) -> bool:
        return _task_filter(record) and record["extra"].get("channel") == "ai_creation"

    context_manager = logger.contextualize(task_id=task_id, service=service_name)
    context_manager.__enter__()
    runtime_sink = logger.add(
        logs_dir / "runtime.jsonl",
        format=_jsonl_formatter(service_name),
        filter=_task_filter,
    )
    sink_ids = [runtime_sink]
    if ai_creation_enabled:
        sink_ids.append(
            logger.add(
                logs_dir / "ai_creation.jsonl",
                format=_jsonl_formatter(service_name),
                filter=_ai_creation_filter,
            )
        )
    return TaskLogSession(sink_ids=sink_ids, context_manager=context_manager)
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
logger.bind(
    channel="runtime",
    event="bind_task_context",
    request_id=ctx.request_id,
    session_id=ctx.session_id,
    api_task_id=ctx.api_task_id,
    task_id=task_id,
    pipeline="standard",
).info("task log context bound")
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

For `pixelle_video/pipelines/custom.py`, attach sinks immediately after `create_task_output_dir()` and close them in the method's existing `finally` path:

```python
task_dir, task_id = create_task_output_dir()
task_log_session = attach_task_log_sinks(
    task_id=task_id,
    task_dir=Path(task_dir),
    service_name="pipeline",
    ai_creation_enabled=False,
)
try:
    logger.bind(channel="runtime", pipeline="custom").info("custom task log context bound")
finally:
    task_log_session.close()
```

Move the existing custom pipeline statements that currently follow `create_task_output_dir()` inside the `try` block above, preserving their order.

For `pixelle_video/pipelines/asset_based.py`, add `task_log_session` to its `PipelineContext`, attach sinks in `setup_environment(...)`, and close the session in the `finally` block of its overridden `__call__(...)`:

```python
context.task_log_session = attach_task_log_sinks(
    task_id=task_id,
    task_dir=Path(task_dir),
    service_name="pipeline",
    ai_creation_enabled=False,
)
logger.bind(channel="runtime", pipeline="asset_based").info("asset task log context bound")
```

```python
finally:
    if getattr(ctx, "task_log_session", None) is not None:
        ctx.task_log_session.close()
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

Run: `uv run pytest tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_storyboard_snapshot_persistence.py -v`

Expected: PASS with path helpers, task-sink filtering, and `observability` visible in history detail payloads.

- [ ] **Step 5: Commit and push the task-log persistence change**

```bash
git add pixelle_video/utils/logging_util.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py pixelle_video/pipelines/asset_based.py pixelle_video/services/persistence.py pixelle_video/services/history_manager.py tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_storyboard_snapshot_persistence.py
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
    assert end_event["retry_count"] == 0
    assert end_event["narration_count"] == 11
```

```python
def test_standard_ai_creation_summary_records_terminal_skip_and_fail_events():
    from types import SimpleNamespace

    core = SimpleNamespace(llm=None, tts=None, media=None, video=None)
    pipeline = StandardPipeline(core)
    ctx = PipelineContext(input_text="demo", params={})

    pipeline._record_ai_creation_stage(
        ctx,
        {
            "channel": "ai_creation",
            "stage": "storyboard_planning",
            "event": "skip",
            "status": "skipped",
            "latency_ms": 0,
            "llm_call_count": 0,
            "retry_count": 0,
        },
    )
    pipeline._record_ai_creation_stage(
        ctx,
        {
            "channel": "ai_creation",
            "stage": "image_prompt_batch",
            "event": "fail",
            "status": "failed",
            "latency_ms": 42,
            "llm_call_count": 2,
            "retry_count": 1,
        },
    )

    summary = ctx.observability["ai_creation"]
    assert summary["llm_call_count"] == 2
    assert summary["slowest_stage"] == "image_prompt_batch"
    assert [item["status"] for item in summary["stages"]] == ["skipped", "failed"]
```

- [ ] **Step 2: Run the AI creation tests to verify they fail**

Run: `uv run pytest tests/test_content_generators_structured_output.py tests/test_standard_pipeline_staged_mode.py -k "stage_callback or observability" -v`

Expected: FAIL because the content generators do not yet accept a `stage_callback`, skip/fail terminal events are not aggregated, and the standard pipeline does not yet persist complete AI creation timings.

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

Emit `start` and a terminal `end`, `skip`, or `fail` for every AI creation stage. Use `try/except` wrappers around LLM-backed stages so failures are recorded before re-raising:

```python
stage_start = perf_counter()
emit_stage_event(
    channel="ai_creation",
    stage="narration_generation",
    event="start",
    message="narration generation started",
    callback=stage_callback,
    narration_count=n_scenes,
)
try:
    response: NarrationBatchResponse = await llm_service(
        prompt=prompt,
        response_type=NarrationBatchResponse,
        temperature=0.8,
        max_tokens=2000,
    )
except Exception:
    emit_stage_event(
        channel="ai_creation",
        stage="narration_generation",
        event="fail",
        message="narration generation failed",
        callback=stage_callback,
        status="failed",
        latency_ms=round((perf_counter() - stage_start) * 1000),
        llm_call_count=1,
        retry_count=0,
        narration_count=n_scenes,
    )
    raise
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
    retry_count=0,
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
    narration_count=len(narrations),
    status="success",
)
```

When a stage is not applicable, emit a bounded skip event instead of staying silent:

```python
emit_stage_event(
    channel="ai_creation",
    stage="storyboard_planning",
    event="skip",
    message="storyboard planning skipped",
    callback=stage_callback,
    status="skipped",
    latency_ms=0,
    llm_call_count=0,
    retry_count=0,
    extra={"reason": "storyboard controls disabled"},
)
```

```python
def _record_ai_creation_stage(self, ctx: PipelineContext, event: dict[str, Any]) -> None:
    if event["channel"] != "ai_creation" or event["event"] not in {"end", "skip", "fail"}:
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
        "retry_count": event.get("retry_count", 0),
    }
    if event.get("batch_total") is not None:
        stage_entry["batch_total"] = event["batch_total"]
    if event.get("narration_count") is not None:
        stage_entry["narration_count"] = event["narration_count"]
    summary["stages"].append(stage_entry)
    summary["total_latency_ms"] = sum(item["latency_ms"] for item in summary["stages"])
    summary["slowest_stage"] = max(summary["stages"], key=lambda item: item["latency_ms"])["stage"]
    summary["llm_call_count"] += event.get("llm_call_count", 0)
```

```python
def _ai_stage_callback(self, ctx: PipelineContext):
    return lambda payload: self._record_ai_creation_stage(ctx, payload)
```

Pass the callback through all standard quick-create AI creation calls: `generate_narrations_from_topic`, `split_narration_script`, `generate_title`, `generate_styled_image_prompt_batch`, `resolve_style_spec`, `plan_storyboard_batch`, `generate_image_prompts`, `generate_video_prompts`, and prompt assembly. Also emit `request_received` before the first stage and `ai_creation_total` after prompt assembly or on failure:

```python
stage_callback = self._ai_stage_callback(ctx)
emit_stage_event(
    channel="ai_creation",
    stage="request_received",
    event="end",
    message="ai creation request received",
    callback=stage_callback,
    status="success",
    latency_ms=0,
    llm_call_count=0,
    retry_count=0,
    narration_count=ctx.params.get("n_scenes"),
    pipeline="standard",
    workflow=ctx.params.get("media_workflow"),
    template=ctx.params.get("frame_template"),
)
ctx.title = await generate_title(self.llm, text, strategy="auto", stage_callback=stage_callback)
```

Rewrite risky full-content logs while adding stage events:

```python
logger.bind(
    channel="runtime",
    content=build_content_observability(topic),
    narration_count=n_scenes,
).info("generating narrations from topic")
```

```python
logger.bind(
    channel="runtime",
    prompt_prefix=build_content_observability(prompt_prefix),
).info("custom prompt prefix received")
```

- [ ] **Step 4: Run the focused AI creation regression suite**

Run: `uv run pytest tests/test_logging_util.py tests/test_logging_redaction_policy.py tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_storyboard_snapshot_persistence.py tests/test_output_preview.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py -q`

Expected: PASS and the pipeline now persists enough observability data to reconstruct the AI creation chain, identify skipped/failed stages, and identify the slowest stage from `metadata.json` and the task log files.

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
- Modify: `web/utils/batch_manager.py`
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `pixelle_video/services/history_manager.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Create: `tests/test_logging_util.py`
- Create: `tests/test_logging_redaction_policy.py`
- Create: `tests/test_task_log_persistence.py`
- Create: `tests/test_task_log_context_isolation.py`
- Modify: `tests/test_output_preview.py`
- Modify: `tests/test_storyboard_snapshot_persistence.py`
- Modify: `tests/test_standard_pipeline_staged_mode.py`
- Modify: `tests/test_content_generators_structured_output.py`

- [ ] **Step 1: Run the full focused verification suite**

Run: `uv run pytest tests/test_logging_util.py tests/test_logging_redaction_policy.py tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_storyboard_snapshot_persistence.py tests/test_output_preview.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py -q`

Expected: PASS across the new logging tests, redaction tests, task context isolation tests, persistence/history tests, request-context tests, and standard pipeline AI creation tests.

- [ ] **Step 2: Audit the final diff before closing**

```bash
git diff --stat
git diff -- pixelle_video/utils/logging_util.py pixelle_video/config/schema.py config.yaml api/app.py web/app.py api/routers/video.py api/tasks/manager.py web/components/output_preview.py web/utils/batch_manager.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py pixelle_video/pipelines/asset_based.py pixelle_video/services/persistence.py pixelle_video/services/history_manager.py pixelle_video/utils/content_generators.py tests/test_logging_util.py tests/test_logging_redaction_policy.py tests/test_task_log_persistence.py tests/test_task_log_context_isolation.py tests/test_output_preview.py tests/test_storyboard_snapshot_persistence.py tests/test_standard_pipeline_staged_mode.py tests/test_content_generators_structured_output.py
```

Expected: only the observability feature files are present, with no unrelated workspace drift mixed into the branch.
