# Stage 1A Text / Image Prompt / LLM Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 1A upstream creative contract: ScriptDraft-ready content flow, ImagePromptDraft, PromptPlan, PromptProjection, and LLMInteractionTrace through platform repository contracts.

**Architecture:** Stage 1A owns the canonical `PromptPlan` shape and LLM trace semantics, but it does not own storage implementation. All trace persistence goes through `TraceRepository` and `RawPayloadStore`; local filesystem adapters are only injected by the Stage 0.5 foundation layer for dev/test.

**Tech Stack:** Python dataclasses, Pydantic API schemas, FastAPI routers, repository protocols from Stage 0.5, pytest, existing Pixelle `LLMService`, existing `ImagePromptComposer`.

---

## Planning Authority

This plan implements Stage 1A only. It is governed by:

- `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/12B_LLM_INTERACTION_TRACE_STAGE1A_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`
- `docs/superpowers/plans/2026-04-30-platform-foundation-zero-technical-debt-implementation.md`

Repository override:

```text
AGENTS.md allows `worktree` / `git worktree` when isolation or parallel execution is needed, but change boundaries must remain explicit and unrelated diffs must not be mixed.
Execute in the current workspace or a dedicated worktree with narrow staging and atomic commits.
Use Chinese commit messages and push each commit unless the user explicitly asks for local-only work.
```

## Hard Prerequisite

Do not execute Stage 1A service integration until Gate 0.5 passes:

```text
TraceRepository exists.
RawPayloadStore exists.
PromptPlanRepository exists or is explicitly stubbed by an in-memory fake.
No active Stage 1A code depends on JSONL paths, _runtime paths, or a local trace service.
```

If these contracts are missing, execute `2026-04-30-platform-foundation-zero-technical-debt-implementation.md` first.

## Scope

This plan implements:

- `LLMInteractionTrace` and `LLMTraceContext`.
- `LLMInteractionRecorder` that writes through `TraceRepository` and `RawPayloadStore`.
- `LLMService` trace capture at gateway level.
- `ImagePromptDraft`, `PromptPlan`, and `PromptProjection`.
- `PromptPlanBundle` builder from existing `StoryboardPlan` and generated prompts.
- Trace read API for Stage 1A calls.
- Compatibility tests proving Stage 1B can consume Stage 1A `PromptPlan`.

This plan does not implement:

- Local JSONL trace store.
- `_runtime` trace fallback.
- Artifact / ArtifactVersion.
- Workbench image candidate selection.
- Image regeneration.
- Complete AssetBible / SceneCast.
- Natural-language IP hints as long-term facts.
- FlowGram, SaaS billing, or video segment generation.

## File Structure

- Create `pixelle_video/models/llm_interaction_trace.py`: trace domain model.
- Create `pixelle_video/models/prompt_plan.py`: `ImagePromptDraft`, `PromptPlan`, `PromptProjection` contracts.
- Create `pixelle_video/services/llm_interaction_recorder.py`: recorder using injected repository/store interfaces.
- Modify `pixelle_video/services/llm_service.py`: optional trace context and recorder capture.
- Create `pixelle_video/services/prompt_plan_service.py`: build `PromptPlanBundle` from `StoryboardPlan` and prompt output.
- Modify `pixelle_video/services/image_prompt_composer.py`: return prompt-plan-ready snapshot and trace linkage.
- Create `api/schemas/llm_trace.py`: trace response schemas.
- Create `api/routers/llm_trace.py`: trace read endpoints backed by repository injection.
- Modify `api/app.py`: include trace router.
- Add tests:
  - `tests/test_llm_interaction_trace_model.py`
  - `tests/test_llm_interaction_recorder.py`
  - `tests/test_llm_service_trace_capture.py`
  - `tests/test_prompt_plan_model.py`
  - `tests/test_prompt_plan_service.py`
  - `tests/test_llm_trace_api.py`

## Task 1: LLM Trace Domain Contract

**Files:**

- Create: `pixelle_video/models/llm_interaction_trace.py`
- Test: `tests/test_llm_interaction_trace_model.py`

- [ ] **Step 1: Write model tests**

Test that a trace contains semantic context, safe previews, hashes, status, parse/validation errors, and object-store keys for raw payloads.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_llm_interaction_trace_model.py -v`

Expected: fail with missing trace model.

- [ ] **Step 3: Implement model**

Implement immutable dataclasses. Do not store raw request/response inline except bounded previews and hashes.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_llm_interaction_trace_model.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/llm_interaction_trace.py tests/test_llm_interaction_trace_model.py
git commit -m "feat: 建立大模型交互追踪领域模型"
```

## Task 2: Repository-Backed Recorder

**Files:**

- Create: `pixelle_video/services/llm_interaction_recorder.py`
- Test: `tests/test_llm_interaction_recorder.py`

- [ ] **Step 1: Write recorder tests with fakes**

Use in-memory fake `TraceRepository` and fake `RawPayloadStore`. Assert the recorder writes raw payloads through the store and persists only object keys on trace records.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_llm_interaction_recorder.py -v`

Expected: fail with missing recorder.

- [ ] **Step 3: Implement recorder**

Inject `TraceRepository` and `RawPayloadStore` through the constructor. Do not instantiate filesystem or JSONL classes inside the recorder.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_llm_interaction_recorder.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/llm_interaction_recorder.py tests/test_llm_interaction_recorder.py
git commit -m "feat: 通过仓储接口记录大模型交互"
```

## Task 3: PromptPlan And ImagePromptDraft Contracts

**Files:**

- Create: `pixelle_video/models/prompt_plan.py`
- Test: `tests/test_prompt_plan_model.py`

- [ ] **Step 1: Write contract tests**

Test required fields for `ImagePromptDraft`, `PromptPlan`, and `PromptProjection`. The canonical `PromptPlan` shape must use `frame_id`, `storyboard_plan_id`, `image_prompt_draft_id`, `prompt_sections`, and `final_prompt`.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: fail with missing prompt plan model.

- [ ] **Step 3: Implement contracts**

Use the canonical shape above. Do not add historical panel/base prompt fields.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_prompt_plan_model.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/prompt_plan.py tests/test_prompt_plan_model.py
git commit -m "feat: 建立提示词计划正式合同"
```

## Task 4: PromptPlan Builder

**Files:**

- Create: `pixelle_video/services/prompt_plan_service.py`
- Test: `tests/test_prompt_plan_service.py`

- [ ] **Step 1: Write builder tests**

Test that `build_prompt_plan_bundle()` preserves `StoryboardPlan.frame_id`, links generated prompts to `ImagePromptDraft`, and rejects prompt/frame count mismatch.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: fail with missing builder.

- [ ] **Step 3: Implement builder**

Return a `PromptPlanBundle` with image prompt drafts and prompt plans. Do not persist inside the builder; persistence belongs to `PromptPlanRepository`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_prompt_plan_service.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/prompt_plan_service.py tests/test_prompt_plan_service.py
git commit -m "feat: 构建分镜提示词计划"
```

## Task 5: LLMService Gateway Trace Capture

**Files:**

- Modify: `pixelle_video/services/llm_service.py`
- Modify: `pixelle_video/services/image_prompt_composer.py`
- Test: `tests/test_llm_service_trace_capture.py`

- [ ] **Step 1: Write gateway tests**

Test successful LLM calls and parse failures. Assert trace capture happens at the gateway, not by each business service hand-rolling logging.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_llm_service_trace_capture.py -v`

Expected: fail because trace capture is not wired.

- [ ] **Step 3: Implement gateway capture**

Thread `LLMTraceContext` and optional recorder through the gateway. Business services may provide semantic context but must not write raw payloads directly.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_llm_service_trace_capture.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/llm_service.py pixelle_video/services/image_prompt_composer.py tests/test_llm_service_trace_capture.py
git commit -m "feat: 在大模型网关接入交互追踪"
```

## Task 6: Trace Read API

**Files:**

- Create: `api/schemas/llm_trace.py`
- Create: `api/routers/llm_trace.py`
- Modify: `api/app.py`
- Test: `tests/test_llm_trace_api.py`

- [ ] **Step 1: Write API tests**

Test summary reads and raw payload authorization boundaries using fake repositories. Public summary response must not include raw payload content.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_llm_trace_api.py -v`

Expected: fail with missing API.

- [ ] **Step 3: Implement API**

Expose structured trace records through repository reads. Raw payload endpoints must require Admin/Local Debug capability and read by object key through `RawPayloadStore`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_llm_trace_api.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/llm_trace.py api/routers/llm_trace.py api/app.py tests/test_llm_trace_api.py
git commit -m "feat: 提供大模型追踪读取接口"
```

## Verification Checklist

Run:

```bash
pytest \
  tests/test_llm_interaction_trace_model.py \
  tests/test_llm_interaction_recorder.py \
  tests/test_llm_service_trace_capture.py \
  tests/test_prompt_plan_model.py \
  tests/test_prompt_plan_service.py \
  tests/test_llm_trace_api.py \
  -v
```

Expected: all selected tests pass.

Run the active-plan guard from the Stage 0.5 foundation plan.

## Implementation Notes

- `PromptPlan` defined here is the canonical Stage 1A contract.
- Stage 1B must consume this contract and must not redefine it.
- Stage 2 may fill reserved asset fields after Gate A, but must not modify the core PromptPlan shape without a separate migration plan.
- IP/AssetBible facts belong to Stage 2; Stage 1A may carry asset IDs but must not invent a parallel prompt-only IP fact source.
