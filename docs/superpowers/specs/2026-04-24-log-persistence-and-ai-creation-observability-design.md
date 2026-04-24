# Log Persistence and AI Creation Observability Design

## Goal

Add a stable, project-owned logging system that persists runtime logs to disk and makes the `Quick Create -> AI Creation` path explainable after the fact.

This design must let an engineer answer, for any completed run, and for any failed run that already created a task directory:

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
2. Every generated task that reaches `task_id` creation under `output/<task_id>/` must keep its own task-scoped runtime logs.
3. The `Quick Create -> AI Creation` chain must emit structured stage logs for start, end, skip, retry, and failure.
4. Web, API, and pipeline logs must share correlation identifiers so one request can be traced across layers.
5. History-facing task detail data must expose a compact observability summary without reading the entire raw log stream.
6. Failed runs must persist the latest available observability summary once `task_id` exists.
7. Task log sinks must be filtered by contextual `task_id` and channel so concurrent tasks cannot write into each other's task log files.

### Safety Requirements

1. API keys, bearer tokens, and secret config values must never be written to persisted logs.
2. Full prompt bodies and full user scripts must not be written to global logs.
3. Task logs should prefer counts, hashes, lengths, and bounded previews over raw content bodies.
4. Redaction must apply to both structured log fields and rendered message strings before any record is written to disk.
5. Existing direct logs that include full topic text, prompt prefixes, or ComfyUI config snapshots must be rewritten to log bounded structured metadata instead.

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

Global logs rotate and retain bounded history. Task logs do not need cross-task rotation because each task owns its own files under its own directory.

### Task Logs

For every completed or in-flight generated task, create:

- `output/<task_id>/logs/runtime.jsonl`
- `output/<task_id>/logs/ai_creation.jsonl`

`runtime.jsonl` keeps task-scoped logs for the whole generation lifecycle.

`ai_creation.jsonl` keeps only the `Quick Create -> AI Creation` stage events so slow prompt-generation runs can be inspected without scanning frame-rendering noise.

Task log sinks are not process-global forever. They are attached when `task_id` becomes known and must be removed in a `finally` block or equivalent task-session teardown path once the pipeline finishes or fails. A task log file must never receive records from a later unrelated task.

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
      "llm_call_count": 7,
      "slowest_stage": "storyboard_planning",
      "stages": [
        {
          "stage": "narration_generation",
          "status": "success",
          "latency_ms": 1432,
          "llm_call_count": 1
        },
        {
          "stage": "image_prompt_batch",
          "status": "success",
          "latency_ms": 3148,
          "llm_call_count": 3,
          "retry_count": 1
        }
      ]
    }
  }
}
```

The summary belongs in `metadata.json` rather than a separate third file so existing history/detail loaders can extend naturally from current persistence code.

## Record Format

Persisted file logs use one project-owned flat JSON object per line.

The approved contract is a flat JSONL schema defined by this document. Do not rely on raw Loguru `serialize=True` output for persisted application logs, because that shape does not match this contract and makes downstream readers depend on Loguru internals.

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
- `llm_call_count`
- `retry_count`
- `attempt`
- `batch_index`
- `batch_total`
- `narration_count`
- `workflow`
- `template`

Every persisted JSONL record must include the required top-level keys. Unknown values may be written as `null`. Optional fields may live under an `extra` object when they do not deserve top-level status.

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
6. Task log sinks are detached when the pipeline exits, regardless of success or failure.
7. Bound logging context must be request/task-local, preferably through `loguru.logger.contextualize(...)` or an equivalent `contextvars`-backed helper, so concurrent asynchronous runs do not share identifiers.
8. Task-scoped sinks must write only records whose contextual `task_id` equals the sink's task ID. The `ai_creation.jsonl` sink must additionally require `channel == "ai_creation"`.

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

Every stage must emit a `start` event and exactly one terminal event: `end`, `skip`, or `fail`. Retries are additional non-terminal events between `start` and the terminal event.

Batch-aware stages must also populate:

- `batch_index`
- `batch_total`
- `narration_count`

Stage end and stage fail events that wrap one or more outbound LLM calls must also populate:

- `llm_call_count`
- `retry_count`

`llm_call_count` means actual outbound LLM request attempts made during that stage, including batch splits and retries. It is not a count of logical stages.

The approved intent is that a single quick-create run can be reconstructed from `ai_creation.jsonl` alone without reading `runtime.jsonl`.

The standard quick-create path must emit all applicable stages. When a stage is not applicable, for example `storyboard_planning` without storyboard controls or `image_prompt_batch` for a static template, it must emit a `skip` terminal event with a bounded reason.

## Redaction and Content Policy

### Must Redact

- `api_key`
- `authorization`
- `bearer`
- `token`
- `secret`
- `password`

The redaction layer must inspect both structured `extra` fields and any config payloads deliberately logged by code before records are serialized to disk. This is necessary because the current codebase contains at least one risky debug log of ComfyUI config in `pixelle_video/service.py`.

Sensitive key matching is case-insensitive and must cover exact names, suffixes, and embedded names such as `comfyui_api_key`, `runninghub_api_key`, `access_token`, and `refresh_token`. Redaction must also scan rendered messages for obvious secret-bearing fragments. However, message redaction is a safety net, not the primary control: logs that currently render config dictionaries or full prompts into message strings must be rewritten to structured, redacted metadata.

### Prompt and Script Logging Policy

Global file logs must not persist full user text, full narration arrays, or full prompt arrays.

Approved replacements:

- `input_length`
- `narration_count`
- `prompt_count`
- `content_hash`
- bounded `preview` fields with a short length cap

Task logs may include short previews when needed for debugging, but the default phase should still prefer counts and hashes over raw content bodies.

The default preview cap is `logging.preview_chars`. Previews must be generated by a shared helper that returns `input_length`, `content_hash`, and a truncated `preview` so callers do not repeatedly hand-roll string slicing.

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

## Initial Scope

The first implementation pass should separate two concerns:

1. global and task-scoped runtime log persistence for all video-generation entrypoints
2. structured AI creation stage summaries for the `standard` pipeline, which powers the current quick-create path

`custom` and `asset_based` should still benefit from global/task log persistence in this phase, but they do not need the full `ai_creation` stage summary contract until a later pass.

Because `custom` does not inherit `LinearVideoPipeline` and `asset_based` overrides `__call__`, the first implementation pass must explicitly attach and detach task runtime sinks in those pipelines or route their task setup through a shared helper.

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
- `tests/test_logging_redaction_policy.py`
- `tests/test_task_log_context_isolation.py`

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
- detach task log sinks when the task exits
- persist observability summary into `metadata.json`
- persist failure metadata with observability when `task_id` already exists

### Phase 3: AI Creation Structured Events

- convert the quick-create path to explicit stage events
- record stage durations, retries, skips, failure reasons, and actual outbound LLM call counts
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
- serializer-level redaction before disk writes
- explicit tests for redaction behavior
- remove or rewrite risky config debug logs

### Risk: Task logs are missing for failed runs

Guardrail:

- create task `logs/` as soon as `task_id` exists
- detach task sinks in `finally`
- emit failure records and persist failure metadata before re-raising

## Acceptance Criteria

This design is satisfied when:

1. starting the web app locally creates `logs/web.jsonl`
2. starting the API locally creates `logs/api.jsonl`
3. running one quick-create generation creates `output/<task_id>/logs/runtime.jsonl`
4. that same run creates `output/<task_id>/logs/ai_creation.jsonl`
5. `metadata.json` contains an `observability` summary with total AI creation latency and per-stage timings
6. the `observability.ai_creation.llm_call_count` field reflects actual outbound LLM request attempts, including batch splits and retries
7. persisted logs contain `request_id` and `task_id` correlation fields where applicable
8. no API keys or bearer tokens appear in persisted logs
9. a failed `standard` pipeline run that already created `task_id` still persists task logs and a failure-shaped `observability` summary
10. an engineer can identify the slowest AI creation stage from the task files alone
11. concurrent task log sessions do not cross-write records between task directories
12. global file logs do not persist full topic text, full scripts, prompt prefixes, prompt arrays, or config dictionaries
13. `custom` and `asset_based` runs that create `task_id` also create task-scoped `runtime.jsonl`
