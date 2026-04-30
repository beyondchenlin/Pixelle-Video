# Stage 1A Text / Image Prompt / LLM Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 1A upstream creative contract: ScriptDraft-ready content flow, ImagePromptDraft, PromptPlan, and LLMInteractionTrace so Stage 1B can consume stable, traceable prompt plans.

**Architecture:** Keep the existing `StoryboardPlan`, `ImagePromptComposer`, and content APIs as the runtime base. Add focused domain models and local JSONL trace services behind interfaces, then thread trace context through `LLMService` and prompt generation without changing image generation or workbench behavior.

**Tech Stack:** Python dataclasses, Pydantic API schemas, FastAPI routers, local JSON/JSONL persistence, pytest, existing Pixelle `LLMService`, existing `ImagePromptComposer`.

---

## Planning Authority

This plan implements Stage 1A only. It is governed by:

- `docs/pixelle_video_full_planning_md/MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`
- `docs/pixelle_video_full_planning_md/12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/12B_LLM_INTERACTION_TRACE_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`
- `docs/superpowers/specs/2026-04-29-llm-interaction-trace-design.md`

Repository override:

```text
AGENTS.md forbids git worktree use in this repository.
Execute in the current workspace with narrow staging and atomic commits.
Use Chinese commit messages.
```

## Scope

This plan implements:

- `LLMInteractionTrace` and `LLMTraceContext`.
- Local trace store and recorder.
- `LLMService` trace capture.
- `ImagePromptDraft`, `PromptPlan`, and `PromptProjection`.
- PromptPlan builder from existing `StoryboardPlan` and generated prompts.
- Trace read API for Stage 1A calls.
- Compatibility tests proving Stage 1B can consume PromptPlan and link upstream trace.

This plan does not implement:

- Artifact / ArtifactVersion.
- Workbench image candidate selection.
- Image regeneration.
- Complete AssetBible / SceneCast.
- FlowGram.
- SaaS billing or public API hard rejection of raw fields.
- Video segment generation.

## File Structure

- Create `pixelle_video/models/llm_interaction_trace.py`: trace domain model.
- Create `pixelle_video/services/llm_trace.py`: local JSONL trace store and recorder.
- Modify `pixelle_video/services/llm_service.py`: optional trace context and recorder capture.
- Create `pixelle_video/models/prompt_plan.py`: ImagePromptDraft, PromptPlan, PromptProjection contracts.
- Create `pixelle_video/services/prompt_plan_service.py`: build PromptPlan objects from StoryboardPlan and prompt output.
- Modify `pixelle_video/services/image_prompt_composer.py`: accept optional trace context and return prompt-plan-ready snapshot.
- Create `api/schemas/llm_trace.py`: trace response schemas.
- Create `api/routers/llm_trace.py`: trace read endpoints.
- Modify `api/app.py`: include trace router.
- Add tests:
  - `tests/test_llm_interaction_trace_model.py`
  - `tests/test_llm_trace_store.py`
  - `tests/test_llm_service_trace.py`
  - `tests/test_prompt_plan_model.py`
  - `tests/test_prompt_plan_service.py`
  - `tests/test_llm_trace_api.py`

---

### Task 1: LLM Interaction Trace Domain Contract

**Files:**
- Create: `pixelle_video/models/llm_interaction_trace.py`
- Test: `tests/test_llm_interaction_trace_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_interaction_trace_model.py
from pixelle_video.models.llm_interaction_trace import (
    LLMInteractionStatus,
    LLMInteractionTrace,
    LLMTraceContext,
)


def test_trace_context_carries_stage1a_semantics():
    context = LLMTraceContext(
        task_id="task-1",
        request_id="request-1",
        project_id="project-1",
        stage="image_prompt.generate_batch",
        purpose="Generate image prompts for storyboard frames",
        source_entity_type="storyboard_plan",
        source_entity_id="plan-1",
        frame_id="frame_0001",
        visibility="creator",
    )

    payload = context.to_dict()

    assert payload["stage"] == "image_prompt.generate_batch"
    assert payload["frame_id"] == "frame_0001"
    assert payload["visibility"] == "creator"


def test_llm_interaction_trace_redacts_secrets_from_preview():
    context = LLMTraceContext(
        request_id="request-1",
        stage="script_draft.generate",
        purpose="Generate script draft",
        visibility="admin",
    )
    trace = LLMInteractionTrace.start(
        context=context,
        provider="openai",
        model="gpt-5.1",
        temperature=0.2,
        max_tokens=1000,
        response_type="ScriptDraftResponse",
        request_messages=[{"role": "user", "content": "api_key=secret-token\nwrite a story"}],
    ).complete(
        response="generated",
        parsed_output={"title": "Demo"},
        token_usage={"total_tokens": 42},
    )

    payload = trace.to_dict()
    restored = LLMInteractionTrace.from_dict(payload)

    assert restored.status == LLMInteractionStatus.SUCCEEDED
    assert "secret-token" not in restored.request_messages_preview
    assert restored.parsed_output_preview == {"title": "Demo"}
    assert restored.interaction_id.startswith("llm_")
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_llm_interaction_trace_model.py -v`

Expected: fail with `ModuleNotFoundError: No module named 'pixelle_video.models.llm_interaction_trace'`.

- [ ] **Step 3: Create the trace domain model**

```python
# pixelle_video/models/llm_interaction_trace.py
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class LLMInteractionStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_copy(item) for item in value]
    return value


SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|secret)\s*[:=]\s*([^\s,;]+)"
)


def redact_text(value: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", value)


def preview(value: Any, *, max_length: int = 2000) -> Any:
    copied = json_copy(value)
    if isinstance(copied, str):
        redacted = redact_text(copied)
        return redacted[:max_length]
    if isinstance(copied, list):
        return [preview(item, max_length=max_length) for item in copied]
    if isinstance(copied, dict):
        return {key: preview(item, max_length=max_length) for key, item in copied.items()}
    return copied


@dataclass(frozen=True)
class LLMTraceContext:
    request_id: str
    stage: str
    purpose: str
    task_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    source_entity_type: str | None = None
    source_entity_id: str | None = None
    frame_id: str | None = None
    visibility: str = "creator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "stage": self.stage,
            "purpose": self.purpose,
            "source_entity_type": self.source_entity_type,
            "source_entity_id": self.source_entity_id,
            "frame_id": self.frame_id,
            "visibility": self.visibility,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LLMTraceContext":
        return cls(
            task_id=payload.get("task_id"),
            request_id=str(payload["request_id"]),
            session_id=payload.get("session_id"),
            project_id=payload.get("project_id"),
            stage=str(payload["stage"]),
            purpose=str(payload["purpose"]),
            source_entity_type=payload.get("source_entity_type"),
            source_entity_id=payload.get("source_entity_id"),
            frame_id=payload.get("frame_id"),
            visibility=str(payload.get("visibility") or "creator"),
        )


@dataclass(frozen=True)
class LLMInteractionTrace:
    interaction_id: str
    context: LLMTraceContext
    provider: str | None
    model: str
    temperature: float
    max_tokens: int
    response_type: str | None
    request_messages_preview: Any
    request_hash: str
    status: LLMInteractionStatus
    attempt: int = 1
    response_preview: Any = None
    response_hash: str | None = None
    parsed_output_preview: Any = None
    raw_request_object_key: str | None = None
    raw_response_object_key: str | None = None
    latency_ms: int | None = None
    token_usage: dict[str, Any] | None = None
    parse_error: str | None = None
    validation_error: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_iso_now)
    completed_at: str | None = None

    @classmethod
    def start(
        cls,
        *,
        context: LLMTraceContext,
        provider: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        response_type: str | None,
        request_messages: Sequence[Mapping[str, Any]],
        attempt: int = 1,
    ) -> "LLMInteractionTrace":
        request_payload = json_copy(list(request_messages))
        request_hash = stable_id("hash", request_payload)
        interaction_id = stable_id("llm", context.request_id, context.stage, context.frame_id or "", attempt)
        return cls(
            interaction_id=interaction_id,
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_type=response_type,
            request_messages_preview=preview(request_payload),
            request_hash=request_hash,
            status=LLMInteractionStatus.STARTED,
            attempt=attempt,
        )

    def complete(
        self,
        *,
        response: Any,
        parsed_output: Any = None,
        token_usage: Mapping[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> "LLMInteractionTrace":
        return replace(
            self,
            status=LLMInteractionStatus.SUCCEEDED,
            response_preview=preview(response),
            response_hash=stable_id("hash", response),
            parsed_output_preview=preview(parsed_output),
            token_usage=json_copy(token_usage or {}),
            latency_ms=latency_ms,
            completed_at=utc_iso_now(),
        )

    def fail(self, *, error_message: str, parse_error: str | None = None, validation_error: str | None = None) -> "LLMInteractionTrace":
        return replace(
            self,
            status=LLMInteractionStatus.FAILED,
            error_message=redact_text(error_message),
            parse_error=redact_text(parse_error) if parse_error else None,
            validation_error=redact_text(validation_error) if validation_error else None,
            completed_at=utc_iso_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "interaction_id": self.interaction_id,
            "context": self.context.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_type": self.response_type,
            "request_messages_preview": json_copy(self.request_messages_preview),
            "request_hash": self.request_hash,
            "status": self.status.value,
            "attempt": self.attempt,
            "response_preview": json_copy(self.response_preview),
            "response_hash": self.response_hash,
            "parsed_output_preview": json_copy(self.parsed_output_preview),
            "raw_request_object_key": self.raw_request_object_key,
            "raw_response_object_key": self.raw_response_object_key,
            "latency_ms": self.latency_ms,
            "token_usage": json_copy(self.token_usage or {}),
            "parse_error": self.parse_error,
            "validation_error": self.validation_error,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LLMInteractionTrace":
        return cls(
            interaction_id=str(payload["interaction_id"]),
            context=LLMTraceContext.from_dict(payload["context"]),
            provider=payload.get("provider"),
            model=str(payload["model"]),
            temperature=float(payload["temperature"]),
            max_tokens=int(payload["max_tokens"]),
            response_type=payload.get("response_type"),
            request_messages_preview=json_copy(payload.get("request_messages_preview")),
            request_hash=str(payload["request_hash"]),
            status=LLMInteractionStatus(payload["status"]),
            attempt=int(payload.get("attempt") or 1),
            response_preview=json_copy(payload.get("response_preview")),
            response_hash=payload.get("response_hash"),
            parsed_output_preview=json_copy(payload.get("parsed_output_preview")),
            raw_request_object_key=payload.get("raw_request_object_key"),
            raw_response_object_key=payload.get("raw_response_object_key"),
            latency_ms=payload.get("latency_ms"),
            token_usage=json_copy(payload.get("token_usage") or {}),
            parse_error=payload.get("parse_error"),
            validation_error=payload.get("validation_error"),
            error_message=payload.get("error_message"),
            created_at=str(payload["created_at"]),
            completed_at=payload.get("completed_at"),
        )


__all__ = ["LLMInteractionStatus", "LLMInteractionTrace", "LLMTraceContext"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_llm_interaction_trace_model.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_interaction_trace_model.py pixelle_video/models/llm_interaction_trace.py
git commit -m "feat: 新增大模型交互追踪合同"
```

---

### Task 2: Local LLM Trace Store And Recorder

**Files:**
- Create: `pixelle_video/services/llm_trace.py`
- Test: `tests/test_llm_trace_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_trace_store.py
import json

import pytest

from pixelle_video.models.llm_interaction_trace import LLMInteractionTrace, LLMTraceContext
from pixelle_video.services.llm_trace import LocalLLMTraceStore, LLMInteractionRecorder


@pytest.mark.asyncio
async def test_local_trace_store_appends_and_loads_interactions(tmp_path):
    store = LocalLLMTraceStore(output_dir=tmp_path)
    context = LLMTraceContext(request_id="request-1", stage="prompt_plan.build", purpose="Build PromptPlan")
    trace = LLMInteractionTrace.start(
        context=context,
        provider="openai",
        model="gpt-5.1",
        temperature=0.2,
        max_tokens=100,
        response_type=None,
        request_messages=[{"role": "user", "content": "hello"}],
    ).complete(response="world")

    await store.append_interaction(trace)
    loaded = await store.load_interactions(request_id="request-1")

    assert loaded == [trace]
    assert (tmp_path / "_runtime" / "trace" / "request-1" / "llm_interactions.jsonl").exists()


@pytest.mark.asyncio
async def test_recorder_writes_raw_payloads(tmp_path):
    store = LocalLLMTraceStore(output_dir=tmp_path)
    recorder = LLMInteractionRecorder(store=store)
    context = LLMTraceContext(request_id="request-1", stage="script_draft.generate", purpose="Generate script")

    trace = await recorder.record_success(
        context=context,
        provider="openai",
        model="gpt-5.1",
        temperature=0.1,
        max_tokens=200,
        response_type="ScriptDraftResponse",
        request_messages=[{"role": "user", "content": "write"}],
        raw_response={"choices": [{"message": {"content": "{}"}}]},
        parsed_output={"title": "Demo"},
        latency_ms=10,
    )

    raw_request = tmp_path / "_runtime" / "trace" / "request-1" / "raw" / f"{trace.interaction_id}_request.json"
    raw_response = tmp_path / "_runtime" / "trace" / "request-1" / "raw" / f"{trace.interaction_id}_response.json"

    assert json.loads(raw_request.read_text(encoding="utf-8"))[0]["content"] == "write"
    assert json.loads(raw_response.read_text(encoding="utf-8"))["choices"]
    assert trace.raw_request_object_key.endswith("_request.json")
    assert trace.raw_response_object_key.endswith("_response.json")
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_llm_trace_store.py -v`

Expected: fail with `ModuleNotFoundError: No module named 'pixelle_video.services.llm_trace'`.

- [ ] **Step 3: Create local store and recorder**

```python
# pixelle_video/services/llm_trace.py
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from pixelle_video.models.llm_interaction_trace import LLMInteractionTrace, LLMTraceContext


class LocalLLMTraceStore:
    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir)

    def _trace_dir(self, *, request_id: str, task_id: str | None = None) -> Path:
        if task_id:
            return self.output_dir / task_id / "trace"
        return self.output_dir / "_runtime" / "trace" / request_id

    async def append_interaction(self, trace: LLMInteractionTrace) -> None:
        trace_dir = self._trace_dir(request_id=trace.context.request_id, task_id=trace.context.task_id)
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / "llm_interactions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")

    async def save_raw_payload(self, *, trace: LLMInteractionTrace, suffix: str, payload: Any) -> str:
        trace_dir = self._trace_dir(request_id=trace.context.request_id, task_id=trace.context.task_id)
        raw_dir = trace_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{trace.interaction_id}_{suffix}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path.relative_to(self.output_dir)).replace("\\", "/")

    async def load_interactions(self, *, request_id: str, task_id: str | None = None) -> list[LLMInteractionTrace]:
        path = self._trace_dir(request_id=request_id, task_id=task_id) / "llm_interactions.jsonl"
        if not path.exists():
            return []
        traces: list[LLMInteractionTrace] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                traces.append(LLMInteractionTrace.from_dict(json.loads(line)))
        return traces


class LLMInteractionRecorder:
    def __init__(self, store: LocalLLMTraceStore | None = None) -> None:
        self.store = store or LocalLLMTraceStore()

    async def record_success(
        self,
        *,
        context: LLMTraceContext,
        provider: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        response_type: str | None,
        request_messages: Sequence[Mapping[str, Any]],
        raw_response: Any,
        parsed_output: Any = None,
        latency_ms: int | None = None,
        token_usage: Mapping[str, Any] | None = None,
    ) -> LLMInteractionTrace:
        trace = LLMInteractionTrace.start(
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_type=response_type,
            request_messages=request_messages,
        ).complete(
            response=raw_response,
            parsed_output=parsed_output,
            latency_ms=latency_ms,
            token_usage=token_usage,
        )
        request_key = await self.store.save_raw_payload(trace=trace, suffix="request", payload=list(request_messages))
        response_key = await self.store.save_raw_payload(trace=trace, suffix="response", payload=raw_response)
        trace = replace(trace, raw_request_object_key=request_key, raw_response_object_key=response_key)
        await self.store.append_interaction(trace)
        return trace

    async def record_failure(
        self,
        *,
        context: LLMTraceContext,
        provider: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
        response_type: str | None,
        request_messages: Sequence[Mapping[str, Any]],
        error: Exception,
    ) -> LLMInteractionTrace:
        trace = LLMInteractionTrace.start(
            context=context,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_type=response_type,
            request_messages=request_messages,
        ).fail(error_message=str(error))
        request_key = await self.store.save_raw_payload(trace=trace, suffix="request", payload=list(request_messages))
        error_key = await self.store.save_raw_payload(trace=trace, suffix="error", payload={"error": str(error)})
        trace = replace(trace, raw_request_object_key=request_key, raw_response_object_key=error_key)
        await self.store.append_interaction(trace)
        return trace


__all__ = ["LLMInteractionRecorder", "LocalLLMTraceStore"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_llm_trace_store.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_trace_store.py pixelle_video/services/llm_trace.py
git commit -m "feat: 新增本地大模型追踪存储"
```

---

### Task 3: PromptPlan And ImagePromptDraft Contracts

**Files:**
- Create: `pixelle_video/models/prompt_plan.py`
- Test: `tests/test_prompt_plan_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_plan_model.py
from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan, PromptProjection


def test_image_prompt_draft_links_to_storyboard_frame():
    draft = ImagePromptDraft.create(
        frame_id="frame_0001",
        storyboard_plan_id="plan-1",
        visual_goal="detective in neon alley",
        image_prompt="cinematic comic detective in a neon alley",
        negative_prompt="blur, watermark",
        style_hint="noir comic",
        llm_interaction_id="llm_abc",
    )

    restored = ImagePromptDraft.from_dict(draft.to_dict())

    assert restored.frame_id == "frame_0001"
    assert restored.llm_interaction_id == "llm_abc"
    assert restored.image_prompt_draft_id.startswith("image_prompt_draft_")


def test_prompt_plan_preserves_reserved_asset_fields():
    plan = PromptPlan.create(
        frame_id="frame_0001",
        storyboard_plan_id="plan-1",
        image_prompt_draft_id="image_prompt_draft_1",
        prompt_sections={"subject": "detective", "style": "noir comic"},
        final_prompt="noir comic detective",
        negative_prompt="blur",
        style_id="style_noir",
        character_ids=["char_detective"],
        scene_id="scene_alley",
        prop_ids=["prop_umbrella"],
        llm_interaction_id="llm_abc",
    )

    restored = PromptPlan.from_dict(plan.to_dict())

    assert restored.prompt_plan_id.startswith("prompt_plan_")
    assert restored.character_ids == ("char_detective",)
    assert restored.scene_id == "scene_alley"
    assert restored.llm_interaction_id == "llm_abc"


def test_prompt_projection_is_provider_specific_not_fact_source():
    plan = PromptPlan.create(
        frame_id="frame_0001",
        storyboard_plan_id="plan-1",
        image_prompt_draft_id="draft-1",
        prompt_sections={"subject": "base"},
        final_prompt="final",
        negative_prompt="negative",
    )

    projection = PromptProjection.from_prompt_plan(plan, provider_id="comfyui", model_id="z-image")

    assert projection.prompt == "final"
    assert projection.negative_prompt == "negative"
    assert projection.prompt_plan_id == plan.prompt_plan_id
    assert projection.provider_id == "comfyui"
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: fail with missing `prompt_plan` module.

- [ ] **Step 3: Create PromptPlan contracts**

```python
# pixelle_video/models/prompt_plan.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_copy(item) for item in value]
    return value


@dataclass(frozen=True)
class ImagePromptDraft:
    image_prompt_draft_id: str
    frame_id: str
    storyboard_plan_id: str
    visual_goal: str
    image_prompt: str
    negative_prompt: str | None = None
    style_hint: str | None = None
    llm_interaction_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        frame_id: str,
        storyboard_plan_id: str,
        visual_goal: str,
        image_prompt: str,
        negative_prompt: str | None = None,
        style_hint: str | None = None,
        llm_interaction_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ImagePromptDraft":
        draft_id = stable_id("image_prompt_draft", storyboard_plan_id, frame_id, image_prompt)
        return cls(
            image_prompt_draft_id=draft_id,
            frame_id=frame_id,
            storyboard_plan_id=storyboard_plan_id,
            visual_goal=visual_goal,
            image_prompt=image_prompt,
            negative_prompt=negative_prompt,
            style_hint=style_hint,
            llm_interaction_id=llm_interaction_id,
            metadata=json_copy(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "frame_id": self.frame_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "visual_goal": self.visual_goal,
            "image_prompt": self.image_prompt,
            "negative_prompt": self.negative_prompt,
            "style_hint": self.style_hint,
            "llm_interaction_id": self.llm_interaction_id,
            "metadata": json_copy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ImagePromptDraft":
        return cls(
            image_prompt_draft_id=str(payload["image_prompt_draft_id"]),
            frame_id=str(payload["frame_id"]),
            storyboard_plan_id=str(payload["storyboard_plan_id"]),
            visual_goal=str(payload["visual_goal"]),
            image_prompt=str(payload["image_prompt"]),
            negative_prompt=payload.get("negative_prompt"),
            style_hint=payload.get("style_hint"),
            llm_interaction_id=payload.get("llm_interaction_id"),
            metadata=json_copy(payload.get("metadata") or {}),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class PromptPlan:
    prompt_plan_id: str
    frame_id: str
    storyboard_plan_id: str
    image_prompt_draft_id: str
    prompt_sections: dict[str, Any]
    final_prompt: str
    negative_prompt: str | None = None
    character_ids: tuple[str, ...] = field(default_factory=tuple)
    scene_id: str | None = None
    prop_ids: tuple[str, ...] = field(default_factory=tuple)
    style_id: str | None = None
    llm_interaction_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_iso_now)

    @classmethod
    def create(
        cls,
        *,
        frame_id: str,
        storyboard_plan_id: str,
        image_prompt_draft_id: str,
        prompt_sections: Mapping[str, Any],
        final_prompt: str,
        negative_prompt: str | None = None,
        character_ids: list[str] | tuple[str, ...] | None = None,
        scene_id: str | None = None,
        prop_ids: list[str] | tuple[str, ...] | None = None,
        style_id: str | None = None,
        llm_interaction_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PromptPlan":
        plan_id = stable_id("prompt_plan", storyboard_plan_id, frame_id, image_prompt_draft_id, final_prompt)
        return cls(
            prompt_plan_id=plan_id,
            frame_id=frame_id,
            storyboard_plan_id=storyboard_plan_id,
            image_prompt_draft_id=image_prompt_draft_id,
            prompt_sections=json_copy(prompt_sections),
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            character_ids=tuple(character_ids or ()),
            scene_id=scene_id,
            prop_ids=tuple(prop_ids or ()),
            style_id=style_id,
            llm_interaction_id=llm_interaction_id,
            metadata=json_copy(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_plan_id": self.prompt_plan_id,
            "frame_id": self.frame_id,
            "storyboard_plan_id": self.storyboard_plan_id,
            "image_prompt_draft_id": self.image_prompt_draft_id,
            "prompt_sections": json_copy(self.prompt_sections),
            "final_prompt": self.final_prompt,
            "negative_prompt": self.negative_prompt,
            "character_ids": list(self.character_ids),
            "scene_id": self.scene_id,
            "prop_ids": list(self.prop_ids),
            "style_id": self.style_id,
            "llm_interaction_id": self.llm_interaction_id,
            "metadata": json_copy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PromptPlan":
        return cls(
            prompt_plan_id=str(payload["prompt_plan_id"]),
            frame_id=str(payload["frame_id"]),
            storyboard_plan_id=str(payload["storyboard_plan_id"]),
            image_prompt_draft_id=str(payload["image_prompt_draft_id"]),
            prompt_sections=json_copy(payload.get("prompt_sections") or {}),
            final_prompt=str(payload["final_prompt"]),
            negative_prompt=payload.get("negative_prompt"),
            character_ids=tuple(payload.get("character_ids") or ()),
            scene_id=payload.get("scene_id"),
            prop_ids=tuple(payload.get("prop_ids") or ()),
            style_id=payload.get("style_id"),
            llm_interaction_id=payload.get("llm_interaction_id"),
            metadata=json_copy(payload.get("metadata") or {}),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class PromptProjection:
    prompt_plan_id: str
    provider_id: str
    model_id: str | None
    prompt: str
    negative_prompt: str | None

    @classmethod
    def from_prompt_plan(
        cls,
        prompt_plan: PromptPlan,
        *,
        provider_id: str,
        model_id: str | None = None,
    ) -> "PromptProjection":
        return cls(
            prompt_plan_id=prompt_plan.prompt_plan_id,
            provider_id=provider_id,
            model_id=model_id,
            prompt=prompt_plan.final_prompt,
            negative_prompt=prompt_plan.negative_prompt,
        )


__all__ = ["ImagePromptDraft", "PromptPlan", "PromptProjection"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: all three tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_plan_model.py pixelle_video/models/prompt_plan.py
git commit -m "feat: 新增提示词计划合同"
```

---

### Task 4: PromptPlan Builder From Existing StoryboardPlan

**Files:**
- Create: `pixelle_video/services/prompt_plan_service.py`
- Test: `tests/test_prompt_plan_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompt_plan_service.py
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle


def _storyboard_plan():
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(index=1, source_text="第一句。", visual_goal="show first", prompt_intent="first intent"),
            StoryboardPlanFrame(index=2, source_text="第二句。", visual_goal="show second", prompt_intent="second intent"),
        ],
    )


def test_build_prompt_plan_bundle_preserves_frame_ids_and_reserved_fields():
    plan = _storyboard_plan()

    bundle = build_prompt_plan_bundle(
        storyboard_plan=plan,
        image_prompts=["final prompt 1", "final prompt 2"],
        negative_prompt="blur",
        style_id="style_comic",
        llm_interaction_ids={plan.frames[0].frame_id: "llm_1"},
    )

    assert len(bundle.prompt_plans) == 2
    assert bundle.image_prompt_drafts[0].frame_id == plan.frames[0].frame_id
    assert bundle.prompt_plans[0].style_id == "style_comic"
    assert bundle.prompt_plans[0].llm_interaction_id == "llm_1"
    assert bundle.prompt_plans[1].character_ids == ()


def test_build_prompt_plan_bundle_rejects_prompt_count_mismatch():
    plan = _storyboard_plan()

    try:
        build_prompt_plan_bundle(storyboard_plan=plan, image_prompts=["only one"])
    except ValueError as exc:
        assert "image prompt count must match storyboard frame count" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: fail with missing `prompt_plan_service`.

- [ ] **Step 3: Create the builder service**

```python
# pixelle_video/services/prompt_plan_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from pixelle_video.models.prompt_plan import ImagePromptDraft, PromptPlan
from pixelle_video.models.storyboard_plan import StoryboardPlan


@dataclass(frozen=True)
class PromptPlanBundle:
    storyboard_plan_id: str
    image_prompt_drafts: tuple[ImagePromptDraft, ...]
    prompt_plans: tuple[PromptPlan, ...]


def build_prompt_plan_bundle(
    *,
    storyboard_plan: StoryboardPlan,
    image_prompts: Sequence[str],
    negative_prompt: str | None = None,
    style_id: str | None = None,
    llm_interaction_ids: Mapping[str, str] | None = None,
) -> PromptPlanBundle:
    if len(image_prompts) != storyboard_plan.resolved_scene_count:
        raise ValueError("image prompt count must match storyboard frame count")

    interaction_ids = dict(llm_interaction_ids or {})
    drafts: list[ImagePromptDraft] = []
    plans: list[PromptPlan] = []
    for frame, image_prompt in zip(storyboard_plan.frames, image_prompts):
        draft = ImagePromptDraft.create(
            frame_id=frame.frame_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            visual_goal=frame.visual_goal,
            image_prompt=image_prompt,
            negative_prompt=negative_prompt,
            style_hint=style_id,
            llm_interaction_id=interaction_ids.get(frame.frame_id),
            metadata={
                "prompt_intent": frame.prompt_intent,
                "source_start": frame.source_start,
                "source_end": frame.source_end,
            },
        )
        prompt_plan = PromptPlan.create(
            frame_id=frame.frame_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            image_prompt_draft_id=draft.image_prompt_draft_id,
            prompt_sections={
                "visual_goal": frame.visual_goal,
                "prompt_intent": frame.prompt_intent,
                "image_prompt": image_prompt,
            },
            final_prompt=image_prompt,
            negative_prompt=negative_prompt,
            style_id=style_id,
            llm_interaction_id=interaction_ids.get(frame.frame_id),
            metadata={"storyboard_frame_index": frame.index},
        )
        drafts.append(draft)
        plans.append(prompt_plan)

    return PromptPlanBundle(
        storyboard_plan_id=storyboard_plan.plan_id,
        image_prompt_drafts=tuple(drafts),
        prompt_plans=tuple(plans),
    )


__all__ = ["PromptPlanBundle", "build_prompt_plan_bundle"]
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_plan_service.py pixelle_video/services/prompt_plan_service.py
git commit -m "feat: 新增提示词计划构建服务"
```

---

### Task 5: Trace Capture In LLMService

**Files:**
- Modify: `pixelle_video/services/llm_service.py`
- Test: `tests/test_llm_service_trace.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_service_trace.py
from types import SimpleNamespace

import pytest

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.services.llm_service import LLMService


class _FakeRecorder:
    def __init__(self):
        self.successes = []
        self.failures = []

    async def record_success(self, **kwargs):
        self.successes.append(kwargs)
        return SimpleNamespace(interaction_id="llm_success")

    async def record_failure(self, **kwargs):
        self.failures.append(kwargs)
        return SimpleNamespace(interaction_id="llm_failed")


@pytest.mark.asyncio
async def test_llm_service_records_success(monkeypatch):
    service = LLMService(config={})
    recorder = _FakeRecorder()
    context = LLMTraceContext(request_id="request-1", stage="title.generate", purpose="Generate title")

    async def fake_create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
            usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 4}),
        )

    fake_client = SimpleNamespace(
        base_url="https://api.openai.com/v1",
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)),
    )
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    monkeypatch.setattr(service, "_get_config_value", lambda key, default=None: {"model": "gpt-5.1"}.get(key, default))

    result = await service(
        "Say hello",
        trace_context=context,
        trace_recorder=recorder,
        temperature=0.1,
        max_tokens=20,
    )

    assert result == "hello"
    assert recorder.successes[0]["context"] == context
    assert recorder.successes[0]["request_messages"][0]["content"] == "Say hello"
    assert recorder.successes[0]["raw_response"] == "hello"


@pytest.mark.asyncio
async def test_llm_service_records_failure(monkeypatch):
    service = LLMService(config={})
    recorder = _FakeRecorder()
    context = LLMTraceContext(request_id="request-1", stage="title.generate", purpose="Generate title")

    async def fake_create(**kwargs):
        raise RuntimeError("provider down")

    fake_client = SimpleNamespace(
        base_url="https://api.openai.com/v1",
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)),
    )
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)
    monkeypatch.setattr(service, "_get_config_value", lambda key, default=None: {"model": "gpt-5.1"}.get(key, default))

    with pytest.raises(RuntimeError):
        await service("Say hello", trace_context=context, trace_recorder=recorder)

    assert recorder.failures[0]["context"] == context
    assert "provider down" in str(recorder.failures[0]["error"])
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_llm_service_trace.py -v`

Expected: fail because `LLMService.__call__` ignores `trace_context` and `trace_recorder`.

- [ ] **Step 3: Extend `LLMService.__call__` signature**

Modify `pixelle_video/services/llm_service.py`:

```python
from time import perf_counter
from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.services.llm_trace import LLMInteractionRecorder
```

Add keyword parameters:

```python
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
```

Before the SDK call, define:

```python
        request_messages = [{"role": "user", "content": prompt}]
        started_at = perf_counter()
        response_type_name = response_type.__name__ if response_type is not None else None
```

Use `request_messages` in the non-structured SDK call instead of rebuilding messages inline.

- [ ] **Step 4: Record success and failure**

After the non-structured call succeeds:

```python
                if trace_context is not None:
                    recorder = trace_recorder or LLMInteractionRecorder()
                    usage = getattr(response, "usage", None)
                    token_usage = usage.model_dump() if hasattr(usage, "model_dump") else None
                    await recorder.record_success(
                        context=trace_context,
                        provider=str(client.base_url or ""),
                        model=final_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_type=response_type_name,
                        request_messages=request_messages,
                        raw_response=result,
                        parsed_output=result,
                        latency_ms=int((perf_counter() - started_at) * 1000),
                        token_usage=token_usage,
                    )
```

In the exception handler before `raise`:

```python
            if trace_context is not None:
                recorder = trace_recorder or LLMInteractionRecorder()
                await recorder.record_failure(
                    context=trace_context,
                    provider=str(client.base_url or ""),
                    model=final_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_type=response_type_name,
                    request_messages=request_messages,
                    error=e,
                )
```

For structured output, record `parsed_output=result.model_dump()` when the returned object has `model_dump`.

- [ ] **Step 5: Run the tests to verify pass**

Run: `pytest tests/test_llm_service_trace.py -v`

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_llm_service_trace.py pixelle_video/services/llm_service.py
git commit -m "feat: 接入大模型服务追踪"
```

---

### Task 6: Stage 1A Trace Read API

**Files:**
- Create: `api/schemas/llm_trace.py`
- Create: `api/routers/llm_trace.py`
- Modify: `api/app.py`
- Test: `tests/test_llm_trace_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_trace_api.py
import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app
from pixelle_video.models.llm_interaction_trace import LLMInteractionTrace, LLMTraceContext
from pixelle_video.services.llm_trace import LocalLLMTraceStore


@pytest.mark.asyncio
async def test_llm_trace_api_lists_interactions(tmp_path, monkeypatch):
    store = LocalLLMTraceStore(output_dir=tmp_path)
    trace = LLMInteractionTrace.start(
        context=LLMTraceContext(request_id="request-1", stage="prompt_plan.build", purpose="Build PromptPlan"),
        provider="openai",
        model="gpt-5.1",
        temperature=0.2,
        max_tokens=100,
        response_type=None,
        request_messages=[{"role": "user", "content": "hello"}],
    ).complete(response="world")
    await store.append_interaction(trace)

    monkeypatch.setattr("api.routers.llm_trace.LocalLLMTraceStore", lambda: store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/content/requests/request-1/llm-interactions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "request-1"
    assert payload["interactions"][0]["interaction_id"] == trace.interaction_id
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_llm_trace_api.py -v`

Expected: fail because the trace API route does not exist.

- [ ] **Step 3: Add response schemas**

```python
# api/schemas/llm_trace.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LLMInteractionTraceResponse(BaseModel):
    interaction_id: str
    stage: str
    purpose: str
    status: str
    model: str
    provider: str | None = None
    frame_id: str | None = None
    latency_ms: int | None = None
    request_messages_preview: Any = None
    response_preview: Any = None
    parsed_output_preview: Any = None
    error_message: str | None = None


class LLMInteractionTraceListResponse(BaseModel):
    request_id: str
    interactions: list[LLMInteractionTraceResponse]
```

- [ ] **Step 4: Add router**

```python
# api/routers/llm_trace.py
from __future__ import annotations

from fastapi import APIRouter

from api.schemas.llm_trace import LLMInteractionTraceListResponse, LLMInteractionTraceResponse
from pixelle_video.services.llm_trace import LocalLLMTraceStore

router = APIRouter(prefix="/content", tags=["LLM Trace"])


@router.get("/requests/{request_id}/llm-interactions", response_model=LLMInteractionTraceListResponse)
async def list_llm_interactions(request_id: str) -> LLMInteractionTraceListResponse:
    traces = await LocalLLMTraceStore().load_interactions(request_id=request_id)
    return LLMInteractionTraceListResponse(
        request_id=request_id,
        interactions=[
            LLMInteractionTraceResponse(
                interaction_id=trace.interaction_id,
                stage=trace.context.stage,
                purpose=trace.context.purpose,
                status=trace.status.value,
                model=trace.model,
                provider=trace.provider,
                frame_id=trace.context.frame_id,
                latency_ms=trace.latency_ms,
                request_messages_preview=trace.request_messages_preview,
                response_preview=trace.response_preview,
                parsed_output_preview=trace.parsed_output_preview,
                error_message=trace.error_message,
            )
            for trace in traces
        ],
    )
```

- [ ] **Step 5: Register router**

Modify `api/app.py`:

```python
from api.routers.llm_trace import router as llm_trace_router
```

Register near other routers:

```python
app.include_router(llm_trace_router, prefix=api_config.api_prefix)
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `pytest tests/test_llm_trace_api.py -v`

Expected: one test passes.

- [ ] **Step 7: Commit**

```bash
git add tests/test_llm_trace_api.py api/schemas/llm_trace.py api/routers/llm_trace.py api/app.py
git commit -m "feat: 新增大模型追踪查询接口"
```

---

## Stage 1A Verification Checklist

Run:

```bash
pytest \
  tests/test_llm_interaction_trace_model.py \
  tests/test_llm_trace_store.py \
  tests/test_llm_service_trace.py \
  tests/test_prompt_plan_model.py \
  tests/test_prompt_plan_service.py \
  tests/test_llm_trace_api.py \
  tests/test_image_prompt_composer.py \
  tests/test_content_image_prompt_api.py \
  -v
```

Expected: all selected tests pass.

## Implementation Notes

- Do not implement image generation, candidate selection, or regeneration in this plan.
- Do not create Artifact or ArtifactVersion here; those belong to Stage 1B.
- `PromptPlan` defined here is the canonical Stage 1A contract.
- Stage 1B must remove or skip its historical PromptPlan creation tasks and consume this contract.
- Stage 2 can fill reserved asset fields after this plan lands, but must not modify the core PromptPlan shape without a separate migration plan.

## Spec Coverage Self-Review

- `12A` coverage: ScriptDraft-ready content flow is supported by existing content/storyboard services; this plan adds ImagePromptDraft and PromptPlan contracts.
- `12B` coverage: LLMInteractionTrace, trace context, local store, recorder, LLMService capture, and trace API are covered.
- Placeholder scan: no placeholder tasks remain; each task has file paths, test commands, expected failures, and commit commands.
- Type consistency: `LLMTraceContext`, `LLMInteractionTrace`, `ImagePromptDraft`, `PromptPlan`, and `PromptProjection` names are consistent across tasks.
