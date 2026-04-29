# LLM Interaction Trace Design

## Goal

Build a platform-level LLM interaction trace system for Pixelle Stage 1A so every model call used by script drafting, storyboard planning, image prompt generation, and PromptPlan building becomes inspectable, replayable, and safely auditable.

The visible left-side panel is only the product surface. The source fix is to make LLM input and output a first-class production record instead of relying on terminal logs or ad hoc debug prints.

## Reference: BettaFish

Reference project: https://github.com/666ghj/BettaFish

BettaFish uses a practical frontend console model:

- A main work area is paired with a black console panel.
- The console has tabs for different engines such as Insight, Media, Query, Forum, and Report.
- Each tab has a status dot.
- Backend log lines are written to files and pushed to the browser through Socket.IO.
- The frontend also polls historical output endpoints to recover missed lines when the page becomes visible again.
- Each console layer keeps its own scroll state and auto-scroll behavior.

Pixelle should borrow these product ideas:

- Persistent live visibility while generation is running.
- Stage or engine tabs with status indicators.
- A readable timeline that does not require opening terminal output.
- Auto-scroll that pauses when the user inspects older entries.
- History recovery when the browser reconnects or refreshes.

Pixelle should not copy BettaFish as an architecture:

- Do not treat stdout text lines as the system of record.
- Do not make the frontend parse raw log text to infer model calls.
- Do not expose raw prompts to every user.
- Do not mix process orchestration logs with domain generation traces.

Pixelle needs structured, typed LLM interaction records because future debugging must answer why a ScriptDraft, StoryboardPlan, ImagePromptDraft, or PromptPlan was produced.

## Current State

Pixelle already has useful observability foundations:

- `pixelle_video/utils/logging_util.py` persists structured process and task logs.
- Pipeline context includes `request_id`, `session_id`, `api_task_id`, `task_id`, and `observability`.
- Standard pipeline AI creation stages can emit `ai_creation` events.
- Task outputs can include runtime logs and observability summaries.

The missing source-level capability is that `LLMService` does not yet persist a complete, structured record for each outbound model interaction. Current observability can say that a stage happened, but not reliably show the exact request body, response body, parsing result, schema validation error, retry chain, or entity produced by that call.

## Design Principles

1. Every outbound LLM call must be traceable at the LLM gateway layer.
2. Business services must attach semantic context, but they must not hand-roll prompt logging.
3. Raw request and raw response payloads must be stored as protected debug artifacts.
4. The frontend panel reads structured trace records, not terminal logs.
5. Trace records must link to domain outputs such as ScriptDraft, StoryboardPlan, ImagePromptDraft, and PromptPlan.
6. Summary visibility and raw visibility must be permission-separated from the beginning.
7. The design must work locally first and migrate to database/object storage later without changing the domain contract.

## Architecture

```text
ScriptDraftService / StoryboardPlanner / ImagePromptComposer / PromptPlanBuilder
  -> LLMService
      -> LLMInteractionRecorder
          -> LocalLLMTraceStore
              -> output/{task_id}/trace/llm_interactions.jsonl
              -> output/{task_id}/trace/raw/{interaction_id}_request.json
              -> output/{task_id}/trace/raw/{interaction_id}_response.json
  -> GenerationTraceService
      -> event timeline
  -> Studio Trace Panel
      -> summary timeline
      -> structured input/output panes
      -> protected raw payload panes
```

`LLMService` remains the single gateway for model calls. It creates an interaction record before the provider call, completes it after the response, and records parsing or validation failures before raising.

## Core Model

```python
class LLMInteractionTrace(BaseModel):
    interaction_id: str
    task_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    source_entity_type: Literal[
        "user_input",
        "script_draft",
        "storyboard_plan",
        "storyboard_frame",
        "image_prompt_draft",
        "prompt_plan",
        "unknown",
    ]
    source_entity_id: str | None = None
    frame_id: str | None = None
    stage: str
    purpose: str
    provider: str | None = None
    model: str
    base_url_fingerprint: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    response_type: str | None = None
    response_format: dict | None = None
    request_messages_preview: list[dict]
    request_hash: str
    response_preview: str | None = None
    response_hash: str | None = None
    parsed_output_preview: dict | list | str | None = None
    raw_request_object_key: str | None = None
    raw_response_object_key: str | None = None
    status: Literal["started", "success", "failed", "retrying"]
    attempt: int = 1
    latency_ms: int | None = None
    token_usage: dict | None = None
    parse_error: str | None = None
    validation_error: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    visibility: Literal["summary", "debug_raw"] = "summary"
```

The trace record keeps safe previews inline and stores full raw payloads behind object keys. For local MVP those object keys are relative file paths. In SaaS they become object storage keys.

## Storage Layout

Local Stage 1A storage:

```text
output/{task_id}/trace/
  events.jsonl
  llm_interactions.jsonl
  raw/
    {interaction_id}_request.json
    {interaction_id}_response.json
    {interaction_id}_parsed.json
    {interaction_id}_error.json
```

When a task ID is not available, local development traces may fall back to:

```text
_runtime/trace/{request_id}/
```

The fallback is only for development entrypoints that call content APIs without creating a full generation task.

## Stage 1A Integration

Stage 1A must trace these LLM purposes:

```text
script_draft.generate
script_draft.repair
storyboard_plan.generate
storyboard_plan.validate_or_repair
image_prompt.generate_batch
image_prompt.repair
prompt_plan.build
prompt_plan.validate_or_repair
```

Each call must pass semantic context:

```text
stage
purpose
source_entity_type
source_entity_id
frame_id when available
response_type when structured output is requested
```

The business service may describe intent, but the recorder owns how request and response bodies are captured, redacted, and stored.

## API Surface

Recommended App API:

```http
GET /api/content/tasks/{task_id}/llm-interactions
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}/raw-request
GET /api/content/tasks/{task_id}/llm-interactions/{interaction_id}/raw-response
GET /api/content/tasks/{task_id}/llm-interactions/stream
```

The stream endpoint may be SSE in the API-first app. Streamlit can start with polling because current Pixelle Studio is Streamlit-based.

Response shape should separate summary and debug payloads:

```json
{
  "interaction_id": "llmi_...",
  "stage": "image_prompt.generate_batch",
  "purpose": "generate image prompts for storyboard frames",
  "status": "success",
  "model": "qwen-max",
  "latency_ms": 2140,
  "source_entity_type": "storyboard_plan",
  "frame_id": "frame_003",
  "request_preview": [],
  "response_preview": "...",
  "parsed_output_preview": {},
  "raw_available": true,
  "raw_visible": false
}
```

## Studio Trace Panel

The first UI surface should be a left-side or side-panel trace explorer with:

- Stage tabs: Script, Storyboard, Image Prompts, PromptPlan, Provider, Errors.
- Status dots: idle, running, success, warning, failed.
- Timeline rows with time, model, stage, purpose, status, latency, and entity link.
- Expandable panes for submitted messages, returned response, parsed object, validation errors, and retries.
- Raw payload controls hidden behind Admin or local debug mode.
- Auto-scroll by default, with auto-scroll paused when the user scrolls up.
- History recovery on refresh or reconnect.

This borrows BettaFish's usability pattern but keeps Pixelle's trace content structured and domain-aware.

## Visibility And Security

Default visibility:

```text
Free/User: progress and final user-safe output summaries
Creator/Pro: StoryboardPlan, final image prompts, PromptPlan summaries
Admin/Local Debug: raw request, raw response, stacktrace, provider payload
```

Redaction must cover:

- API keys, tokens, passwords, bearer headers.
- Provider base URLs when they reveal private infrastructure.
- System/developer prompts unless in Admin/Local Debug.
- Internal workflow payloads unless in Admin/Local Debug.

Raw payloads are stored because developers need them, but raw payload display is not the default product behavior.

## Error Handling

The recorder must persist failures before raising:

```text
provider request failure
empty response
JSON parse failure
Pydantic schema validation failure
model refusal
timeout
retry exhausted
```

For structured output failures, the trace must show:

- raw response preview
- parse error
- schema validation error
- repair prompt interaction when repair is attempted
- final failed status if repair does not recover

## Testing Requirements

Minimum tests:

- `LLMService` records one interaction for a plain text call.
- `LLMService` records request, response, parsed preview, and `response_type` for structured output.
- Parse failure records raw response and parse error before raising.
- Secret fields are redacted from previews and JSONL records.
- Raw request and raw response files are written under the task trace directory.
- Content API calls can load interaction summaries by task or request.
- UI formatter renders stage tabs, status dots, expandable input/output blocks, and failed rows from structured records.

## Rollout

### Stage 1A-Trace-1: Domain Contract

Define `LLMInteractionTrace`, `LLMTraceContext`, and local trace store interfaces.

### Stage 1A-Trace-2: Gateway Capture

Instrument `LLMService` so every call can be traced without duplicating logic in business services.

### Stage 1A-Trace-3: Stage 1A Services

Attach semantic context in ScriptDraft, StoryboardPlan, ImagePromptDraft, and PromptPlan generation services.

### Stage 1A-Trace-4: API And Studio Panel

Expose summaries and protected raw details. Build the initial Trace Panel from structured trace records.

### Stage 1A-Trace-5: Compatibility Cleanup

Demote terminal logs to operational diagnostics. Stop relying on terminal output for model debugging.

## Acceptance Criteria

This design is complete when:

1. Every Stage 1A LLM call produces an `LLMInteractionTrace`.
2. A developer can inspect the exact request and response for a failed script, storyboard, image prompt, or PromptPlan generation.
3. The UI can show the model interaction timeline without reading terminal logs.
4. Raw prompt and raw response access is permission-gated.
5. BettaFish-like live visibility is achieved without making raw stdout the source of truth.
6. Stage 1B can link image generation, candidate selection, and regeneration events back to the upstream LLM interactions that created the PromptPlan.
