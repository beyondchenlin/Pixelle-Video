# Log Persistence and AI Creation Observability Design

## Goal

Add a stable, project-owned logging system that persists runtime logs to disk and makes the `Quick Create -> AI Creation` path explainable after the fact.

This design must let an engineer answer, for any completed run:

- how long the full request took
- how many Qwen calls happened before media generation
- which AI creation stage was slowest
- whether the run was truly slow or only appeared slow because logs were coarse

## Current State

The current repository emits many `loguru` messages, but it does not define a project-level file sink.

Observed behavior in the current codebase:

- `api/app.py` and `web/app.py` start the app processes without configuring file-backed logging
- the codebase imports `loguru.logger` broadly, but does not call `logger.add(...)` to persist logs into project-managed files
- `start_web.bat` and `start_web.sh` launch Streamlit directly and do not redirect stdout or stderr into files
- `pixelle_video/services/persistence.py` persists `metadata.json` and `storyboard.json`, but not runtime logs
- Docker retains container stdout via `json-file`, but that is infrastructure logging, not application-owned task logging

The quick-create path is also inherently multi-stage. In the default configuration it can execute several sequential LLM calls before frame rendering begins:

1. narration generation
2. title generation
3. style resolution
4. storyboard planning
5. image-prompt batch generation

Recent observability work already added better timing logs and progress subtasks in `pixelle_video/utils/content_generators.py`, `pixelle_video/pipelines/standard.py`, and `web/components/output_preview.py`. What is still missing is durable log storage, request correlation, and task-level archival.

## Non-Goals

This design does not include:

- introducing ELK, Loki, OpenTelemetry, or any external logging backend
- building a full in-app raw-log viewer
- replacing the existing `ProgressEvent` UI progress model
- redesigning asynchronous task persistence in `api/tasks/manager.py`
- storing full user prompts, full scripts, or secrets in log files

## Requirements

### Functional Requirements

1. The application must persist runtime logs to local files in both direct local runs and Docker runs.
2. Every generated task under `output/<task_id>/` must keep its own task-scoped runtime logs.
3. The `Quick Create -> AI Creation` chain must emit structured stage logs for start, end, skip, retry, and failure.
4. Web, API, and pipeline logs must share correlation identifiers so one request can be traced across layers.
5. History-facing task detail data must expose a compact observability summary without reading the entire raw log stream.

### Safety Requirements

1. API keys, bearer tokens, and secret config values must never be written to persisted logs.
2. Full prompt bodies and full user scripts must not be written to global logs.
3. Task logs should prefer counts, hashes, lengths, and bounded previews over raw content bodies.

### Operational Requirements

1. Console logging must remain available for local development.
2. File logging must work without changing the startup scripts.
3. Log files must rotate and retain bounded history.
4. Deleting a task through existing task-history flows must also remove that task's log files because they live under the task directory.

## Approved Direction

Use a hybrid logging architecture:

1. human-readable console logging for local development
2. structured JSONL global log files under `logs/`
3. structured JSONL task log files under `output/<task_id>/logs/`
4. a compact observability summary persisted alongside task metadata

The project should keep using `loguru`, but logging must be bootstrapped centrally instead of relying on the default sink.

## Storage Layout

### Global Logs

Create project-owned files under `logs/`:

- `logs/web.jsonl`
- `logs/api.jsonl`

Each process writes its own JSONL file. The `service` field inside each record distinguishes `web`, `api`, and `pipeline` activity inside the same process.

### Task Logs

For every completed or in-flight generated task, create:

- `output/<task_id>/logs/runtime.jsonl`
- `output/<task_id>/logs/ai_creation.jsonl`

`runtime.jsonl` keeps task-scoped logs for the whole generation lifecycle.

`ai_creation.jsonl` keeps only the `Quick Create -> AI Creation` stage events so slow prompt-generation runs can be inspected without scanning frame-rendering noise.

### Metadata Summary

Extend `metadata.json` with an `observability` object. This is the summary surface consumed by history/detail views and quick troubleshooting.

Approved shape:

```json
{
  "observability": {
    "version": "v1",
    "request_id": "req_01...",
    "session_id": "sess_01...",
    "api_task_id": "9f2d...",
    "task_id": "20260424_102233_ab12",
    "runtime_log_path": "output/20260424_102233_ab12/logs/runtime.jsonl",
    "ai_creation_log_path": "output/20260424_102233_ab12/logs/ai_creation.jsonl",
    "ai_creation": {
      "total_latency_ms": 8123,
      "llm_call_count": 5,
      "slowest_stage": "storyboard_planning",
      "stages": [
        {
          "stage": "narration_generation",
          "status": "success",
          "latency_ms": 1432
        }
      ]
    }
  }
}
```

The summary belongs in `metadata.json` rather than a separate third file so existing history/detail loaders can extend naturally from current persistence code.

## Record Format

Persisted file logs use one JSON object per line.

Required fields:

- `timestamp`
- `level`
- `service`
- `channel`
- `message`
- `request_id`
- `session_id`
- `api_task_id`
- `task_id`
- `pipeline`
- `stage`
- `event`
- `status`
- `provider`
- `model`
- `latency_ms`
- `attempt`
- `batch_index`
- `batch_total`
- `narration_count`
- `workflow`
- `template`

Optional fields may live under an `extra` object when they do not deserve top-level status.

Example task-stage record:

```json
{
  "timestamp": "2026-04-24T10:22:45.815+08:00",
  "level": "INFO",
  "service": "pipeline",
  "channel": "ai_creation",
  "message": "storyboard planning completed",
  "request_id": "req_4f62e4a7",
  "session_id": "sess_4d2c60b9",
  "api_task_id": null,
  "task_id": "20260424_102241_aa12",
  "pipeline": "standard",
  "stage": "storyboard_planning",
  "event": "end",
  "status": "success",
  "provider": "dashscope",
  "model": "qwen-max",
  "latency_ms": 2217,
  "attempt": 1,
  "batch_index": null,
  "batch_total": null,
  "narration_count": 5,
  "workflow": "selfhost/image_z_image_turbo.json",
  "template": "1080x1920/default.html"
}
```

## Correlation Model

### Identifiers

- `request_id`: created at the web or API entry point for every generation request
- `session_id`: created or recovered from the Streamlit session for web requests; null for API requests that do not expose a session
- `api_task_id`: the task ID from `api/tasks/manager.py` for async API requests
- `task_id`: the output task directory ID created in `StandardPipeline.setup_environment`

### Binding Rules

1. Web and API entrypoints create `request_id` before calling into `pixelle_video.generate_video(...)`.
2. API async generation also binds `api_task_id` when `task_manager.create_task(...)` succeeds.
3. `StandardPipeline.setup_environment(...)` creates `task_id` and then attaches task-scoped log sinks.
4. Once `task_id` exists, all nested logs inherit it automatically through bound context rather than passing IDs manually to every function.
5. The pipeline emits one binding event when `request_id`, `api_task_id`, and `task_id` become known together.

This design keeps correlation stable without changing the public pipeline call signatures everywhere.

## AI Creation Stage Contract

The `ai_creation` channel must emit structured records for these stages:

- `request_received`
- `script_split` or `narration_generation`
- `title_generation`
- `style_resolution`
- `storyboard_planning`
- `image_prompt_batch`
- `prompt_assembly`
- `ai_creation_total`

Each stage supports these events:

- `start`
- `end`
- `skip`
- `retry`
- `fail`

Batch-aware stages must also populate:

- `batch_index`
- `batch_total`
- `narration_count`

The approved intent is that a single quick-create run can be reconstructed from `ai_creation.jsonl` alone without reading `runtime.jsonl`.

## Redaction and Content Policy

### Must Redact

- `api_key`
- `authorization`
- `bearer`
- `token`
- `secret`
- `password`

The redaction layer must inspect both structured `extra` fields and any config payloads deliberately logged by code. This is necessary because the current codebase contains at least one risky debug log of ComfyUI config in `pixelle_video/service.py`.

### Prompt and Script Logging Policy

Global file logs must not persist full user text, full narration arrays, or full prompt arrays.

Approved replacements:

- `input_length`
- `narration_count`
- `prompt_count`
- `content_hash`
- bounded `preview` fields with a short length cap

Task logs may include short previews when needed for debugging, but the default phase should still prefer counts and hashes over raw content bodies.

## Configuration

Add a new `logging` section to the application configuration schema.

Approved initial fields:

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

This configuration is intentionally small. The system should not start with a wide matrix of knobs before the storage and correlation model are proven.

## Code Ownership and Impact

The implementation should stay close to the existing code boundaries.

Expected new utility module:

- `pixelle_video/utils/logging_util.py`

Expected integration points:

- `api/app.py`
- `web/app.py`
- `api/routers/video.py`
- `api/tasks/manager.py`
- `pixelle_video/service.py`
- `pixelle_video/pipelines/linear.py`
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/utils/content_generators.py`
- `pixelle_video/services/persistence.py`
- `pixelle_video/services/history_manager.py`
- `pixelle_video/config/schema.py`
- `config.yaml`

Expected new tests:

- `tests/test_logging_util.py`
- `tests/test_task_log_persistence.py`

Expected existing tests to extend:

- `tests/test_storyboard_snapshot_persistence.py`
- `tests/test_output_preview.py`
- `tests/test_standard_pipeline_staged_mode.py`
- `tests/test_content_generators_structured_output.py`

## Rollout

### Phase 1: Logging Bootstrap

- centralize loguru sink setup
- keep console output
- add JSONL global file sinks
- add redaction helpers

### Phase 2: Correlation and Task Logs

- create request and session correlation helpers
- attach task log sinks after task directory creation
- persist observability summary into `metadata.json`

### Phase 3: AI Creation Structured Events

- convert the quick-create path to explicit stage events
- record stage durations, retries, skips, and failure reasons
- keep progress UI behavior unchanged

### Phase 4: History Detail Consumption

- expose observability summary through history/detail service methods
- keep raw log reading optional and out of the first UI pass

## Risks and Guardrails

### Risk: Duplicated or inconsistent IDs

Guardrail:

- use one shared context-binding helper instead of manually passing IDs through ad hoc kwargs

### Risk: Log noise grows too quickly

Guardrail:

- keep global logs compact
- send detailed stage traces into task logs
- rotate global files by size and retain bounded history

### Risk: Secret leakage

Guardrail:

- central redaction helper
- explicit tests for redaction behavior
- remove or rewrite risky config debug logs

### Risk: Task logs are missing for failed runs

Guardrail:

- create task `logs/` as soon as `task_id` exists
- emit failure records in `finally` or exception paths before re-raising

## Acceptance Criteria

This design is satisfied when:

1. starting the web app locally creates `logs/web.jsonl`
2. starting the API locally creates `logs/api.jsonl`
3. running one quick-create generation creates `output/<task_id>/logs/runtime.jsonl`
4. that same run creates `output/<task_id>/logs/ai_creation.jsonl`
5. `metadata.json` contains an `observability` summary with total AI creation latency and per-stage timings
6. persisted logs contain `request_id` and `task_id` correlation fields where applicable
7. no API keys or bearer tokens appear in persisted logs
8. an engineer can identify the slowest AI creation stage from the task files alone
