# Storyboard Workbench Stage 1B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 1B storyboard image workbench by consuming Stage 1A `PromptPlan` outputs and using platform repositories for artifacts, versions, trace events, selection, regeneration, lock, and stale state.

**Architecture:** Stage 1B does not define prompt planning or storage implementation. It owns workbench state and user actions, while persistence goes through `ArtifactRepository`, `ArtifactObjectStore`, `TraceRepository`, and `PromptPlanRepository`; raw generation parameters move behind Internal/Debug API boundaries instead of remaining deprecated App/Public fields.

**Tech Stack:** Python dataclasses, Pydantic schemas, FastAPI routers, platform repository protocols from Stage 0.5, pytest, existing `TaskManager`, existing ComfyUI/media services through Pixelle core.

---

## Planning Authority

This plan implements Stage 1B only. It is governed by:

- `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/13_STORYBOARD_WORKBENCH_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/18_PROVIDER_RESOURCE_RESOLVER_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`
- `docs/superpowers/plans/2026-04-30-stage1a-text-image-prompt-trace-implementation.md`

Repository override:

```text
AGENTS.md forbids git worktree use in this repository.
Execute in the current workspace with narrow staging and atomic commits.
Use Chinese commit messages.
```

## Hard Prerequisites

Do not execute Stage 1B production integration until these gates pass:

```text
Gate 0.5: ArtifactRepository, ArtifactObjectStore, TraceRepository, PromptPlanRepository, and ResourceResolver exist.
Gate A: Stage 1A PromptPlan and PromptPlanBundle exist with the canonical frame_id-based shape.
```

If Stage 1A is not complete, Stage 1B may only implement pure `Artifact`, `ArtifactVersion`, `GenerationEvent`, and workbench-state model tests.

## Scope

This plan implements:

- `Artifact` and `ArtifactVersion` domain contracts.
- `GenerationEvent` domain contract.
- `StoryboardFrameWorkbenchState`, lock policy, and stale flags.
- Candidate image listing and selected image version update.
- Frame image regeneration orchestration through existing task infrastructure.
- Trace linkage from selected/candidate image events back to Stage 1A `PromptPlan`.
- App/Public API schemas based on resource IDs and Internal/Debug schemas for raw controls.

This plan does not implement:

- `PromptPlan` or `PromptPlanBuilder`.
- Local JSON artifact service.
- Local JSONL generation trace service.
- Deprecated-only raw field cleanup.
- FlowGram, full Workflow Engine, SaaS billing, ProviderCapability matrix, quality scoring, or video segment regeneration.

## File Structure

- Create `pixelle_video/models/artifact.py`: durable artifact and artifact-version contracts.
- Create `pixelle_video/models/generation_event.py`: generation trace event contract.
- Create `pixelle_video/models/storyboard_workbench.py`: lock policy, stale flags, and stale propagation helpers.
- Modify `pixelle_video/models/storyboard.py`: add optional workbench fields to `StoryboardFrame`.
- Modify `pixelle_video/services/persistence.py`: persist and restore workbench fields without becoming the artifact fact source.
- Create `pixelle_video/services/storyboard_workbench.py`: selection and frame-regeneration orchestration using injected repositories.
- Modify `api/tasks/models.py`: add `FRAME_IMAGE_REGENERATION`.
- Create `api/schemas/storyboard_workbench.py`: App/Public request/response schemas.
- Create `api/schemas/video_internal.py`: Internal/Debug raw-generation schemas.
- Create `api/routers/storyboard_workbench.py`: artifact listing, image selection, and regeneration endpoints.
- Modify `api/routers/video.py`: route App/Public requests through resource IDs and `ResourceResolver`.
- Modify `api/app.py`: include the new router.
- Add tests:
  - `tests/test_artifact_models.py`
  - `tests/test_generation_event_model.py`
  - `tests/test_storyboard_workbench_metadata.py`
  - `tests/test_storyboard_workbench_service.py`
  - `tests/test_storyboard_workbench_api.py`
  - `tests/test_storyboard_frame_regeneration.py`
  - `tests/test_video_api_raw_boundary.py`

## Task 1: Artifact And ArtifactVersion Contracts

**Files:**

- Create: `pixelle_video/models/artifact.py`
- Test: `tests/test_artifact_models.py`

- [ ] **Step 1: Write model tests**

Test that `Artifact` is the stable logical item and `ArtifactVersion` is the generated output version. Regeneration must create a new version and never overwrite an old selected version.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_artifact_models.py -v`

Expected: fail with missing artifact model.

- [ ] **Step 3: Implement model**

Use stable IDs, version IDs, object-store keys, provider metadata, source `prompt_plan_id`, status, and timestamps. Do not include local file paths as facts.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_artifact_models.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/artifact.py tests/test_artifact_models.py
git commit -m "feat: 建立分镜产物版本合同"
```

## Task 2: GenerationEvent Contract

**Files:**

- Create: `pixelle_video/models/generation_event.py`
- Test: `tests/test_generation_event_model.py`

- [ ] **Step 1: Write event tests**

Test events for generate, fail, select, regenerate, and stale-mark actions. Events must reference domain IDs and object keys, not raw local paths.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_generation_event_model.py -v`

Expected: fail with missing generation event model.

- [ ] **Step 3: Implement model**

Implement immutable event records suitable for `TraceRepository.append_generation_event()`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_generation_event_model.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/generation_event.py tests/test_generation_event_model.py
git commit -m "feat: 建立生成事件领域模型"
```

## Task 3: Workbench State Model

**Files:**

- Create: `pixelle_video/models/storyboard_workbench.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_storyboard_workbench_metadata.py`

- [ ] **Step 1: Write metadata tests**

Test selected/candidate image version IDs, lock policy, stale flags, and stable `frame_id` identity.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_storyboard_workbench_metadata.py -v`

Expected: fail because workbench metadata does not exist.

- [ ] **Step 3: Implement model and persistence bridge**

Persist only lightweight workbench references on storyboard snapshots. The artifact repository remains the fact source for artifact versions.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_storyboard_workbench_metadata.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/storyboard_workbench.py pixelle_video/models/storyboard.py pixelle_video/services/persistence.py tests/test_storyboard_workbench_metadata.py
git commit -m "feat: 增加分镜工作台状态模型"
```

## Task 4: Workbench Service Through Repositories

**Files:**

- Create: `pixelle_video/services/storyboard_workbench.py`
- Test: `tests/test_storyboard_workbench_service.py`

- [ ] **Step 1: Write service tests with fakes**

Use fake `ArtifactRepository`, `ArtifactObjectStore`, `TraceRepository`, and `PromptPlanRepository`. Test image selection, candidate listing, locked-frame behavior, and stale propagation.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_storyboard_workbench_service.py -v`

Expected: fail with missing workbench service.

- [ ] **Step 3: Implement service**

Inject repositories through the constructor. Do not create local JSON services inside the service.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_storyboard_workbench_service.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/storyboard_workbench.py tests/test_storyboard_workbench_service.py
git commit -m "feat: 通过仓储接口管理分镜工作台"
```

## Task 5: Regeneration Task Integration

**Files:**

- Modify: `api/tasks/models.py`
- Modify: `api/tasks/__init__.py`
- Test: `tests/test_storyboard_frame_regeneration.py`

- [ ] **Step 1: Write regeneration tests**

Test that a frame regeneration request creates a task tied to `frame_id`, `prompt_plan_id`, and target artifact ID, then writes a new `ArtifactVersion`.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_storyboard_frame_regeneration.py -v`

Expected: fail because the task type and workbench orchestration are missing.

- [ ] **Step 3: Implement task integration**

Use existing task infrastructure. Store generated outputs through `ArtifactObjectStore` and record lifecycle events through `TraceRepository`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_storyboard_frame_regeneration.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/tasks/models.py api/tasks/__init__.py tests/test_storyboard_frame_regeneration.py
git commit -m "feat: 接入单格图片重抽任务"
```

## Task 6: Workbench API

**Files:**

- Create: `api/schemas/storyboard_workbench.py`
- Create: `api/routers/storyboard_workbench.py`
- Modify: `api/app.py`
- Test: `tests/test_storyboard_workbench_api.py`

- [ ] **Step 1: Write API tests**

Test candidate listing, selecting an image version, and requesting regeneration. Responses must expose domain IDs and URLs/object keys, not local filesystem paths.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_storyboard_workbench_api.py -v`

Expected: fail with missing router.

- [ ] **Step 3: Implement API**

Wire API handlers to `StoryboardWorkbenchService` with repository injection/fakes in tests.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_storyboard_workbench_api.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/storyboard_workbench.py api/routers/storyboard_workbench.py api/app.py tests/test_storyboard_workbench_api.py
git commit -m "feat: 提供分镜工作台接口"
```

## Task 7: Raw Parameter Boundary Fix

**Files:**

- Create: `api/schemas/video_internal.py`
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Test: `tests/test_video_api_raw_boundary.py`

- [ ] **Step 1: Write boundary tests**

Test that App/Public schema accepts resource IDs such as `style_id`, `template_id`, `voice_id`, `bgm_id`, and `workflow_preset_id`. Test that raw local paths, workflow paths, provider URLs, and arbitrary prompt prefixes are rejected from App/Public routes.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_video_api_raw_boundary.py -v`

Expected: fail because raw fields are still mixed into public request schema.

- [ ] **Step 3: Split schemas**

Move raw generation controls to `api/schemas/video_internal.py` and restrict them to Internal/Debug routes. App/Public schemas must resolve through `ResourceResolver`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_video_api_raw_boundary.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/video.py api/schemas/video_internal.py api/routers/video.py tests/test_video_api_raw_boundary.py
git commit -m "feat: 拆分公开视频接口原始参数边界"
```

## Verification Checklist

Run:

```bash
pytest \
  tests/test_artifact_models.py \
  tests/test_generation_event_model.py \
  tests/test_storyboard_workbench_metadata.py \
  tests/test_storyboard_workbench_service.py \
  tests/test_storyboard_workbench_api.py \
  tests/test_storyboard_frame_regeneration.py \
  tests/test_video_api_raw_boundary.py \
  -v
```

Expected: all selected Stage 1B tests pass.

Run the active-plan guard from the Stage 0.5 foundation plan.

## Implementation Notes

- Stage 1B consumes Stage 1A `PromptPlan`; it never redefines prompt planning.
- Raw field cleanup is a boundary split, not a deprecated-only marker task.
- Local filesystem can appear only as a dev/test adapter injected by Stage 0.5 infrastructure.
