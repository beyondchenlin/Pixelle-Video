# Platform Foundation Zero Technical Debt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 0.5 repository, object-store, resource-resolver, and API-boundary contracts that Stage 1A, Stage 1B, and Stage 2 must consume.

**Architecture:** Define production-first interfaces before stage-specific services. Domain services depend on protocols and factory-injected adapters; local filesystem implementations are dev/test adapters only and must not leak local paths as domain contracts.

**Tech Stack:** Python protocols/dataclasses, Pydantic schemas, FastAPI config factories, pytest, existing `api.tasks` store/artifact abstractions, PostgreSQL/Object Storage contract docs.

---

## Planning Authority

This plan is governed by:

- `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/11_DATABASE_QUEUE_STORAGE_SCHEMA.md`
- `docs/pixelle_video_full_planning_md/18_PROVIDER_RESOURCE_RESOLVER_SUBPLAN.md`
- `docs/superpowers/specs/2026-04-25-distributed-generation-registry-design.md`

Repository override:

```text
AGENTS.md allows `worktree` / `git worktree` when isolation or parallel execution is needed, but change boundaries must remain explicit and unrelated diffs must not be mixed.
Execute in the current workspace or a dedicated worktree with narrow staging and atomic commits.
Use Chinese commit messages and push each commit unless the user explicitly asks for local-only work.
```

## Scope

This plan implements:

- Trace, raw payload, artifact, asset bible, prompt plan, and resource resolver interfaces.
- In-memory fakes for domain tests.
- Dev filesystem object-store adapters that return storage keys, not local absolute paths.
- Factory-level production fail-fast checks.
- API schema split rules for App/Public versus Internal/Debug raw inputs.

This plan does not implement:

- Stage 1A prompt generation.
- Stage 1B workbench behavior.
- Stage 2 IP generation.
- Full production PostgreSQL migrations for every future table.
- S3/MinIO client implementation beyond the object-store contract.

## File Structure

- Create `pixelle_video/repositories/trace.py`: `TraceRepository` and raw payload contract types.
- Create `pixelle_video/repositories/artifacts.py`: `ArtifactRepository` and `ArtifactObjectStore` protocols.
- Create `pixelle_video/repositories/assets.py`: `AssetBibleRepository` protocol.
- Create `pixelle_video/repositories/prompt_plans.py`: `PromptPlanRepository` protocol.
- Create `pixelle_video/repositories/fakes.py`: in-memory repositories for tests.
- Create `pixelle_video/storage/object_store.py`: `RawPayloadStore` and dev object-store adapters.
- Create `pixelle_video/services/resource_resolver.py`: resource ID resolver contract and static resolver.
- Modify `api/config.py`: runtime profile and production fail-fast settings.
- Add tests:
  - `tests/test_platform_repository_contracts.py`
  - `tests/test_platform_object_store_contract.py`
  - `tests/test_resource_resolver_contract.py`
  - `tests/test_runtime_profile_fail_fast.py`

## Task 1: Repository Protocol Contracts

**Files:**

- Create: `pixelle_video/repositories/trace.py`
- Create: `pixelle_video/repositories/artifacts.py`
- Create: `pixelle_video/repositories/assets.py`
- Create: `pixelle_video/repositories/prompt_plans.py`
- Test: `tests/test_platform_repository_contracts.py`

- [ ] **Step 1: Write protocol import tests**

Create `tests/test_platform_repository_contracts.py` with assertions that the contracts can be imported and expose the required method names:

```python
from pixelle_video.repositories.artifacts import ArtifactObjectStore, ArtifactRepository
from pixelle_video.repositories.assets import AssetBibleRepository
from pixelle_video.repositories.prompt_plans import PromptPlanRepository
from pixelle_video.repositories.trace import TraceRepository


def test_repository_protocols_expose_required_methods():
    assert hasattr(TraceRepository, "append_llm_interaction")
    assert hasattr(TraceRepository, "append_generation_event")
    assert hasattr(ArtifactRepository, "create_artifact_version")
    assert hasattr(ArtifactRepository, "select_artifact_version")
    assert hasattr(ArtifactObjectStore, "put_file")
    assert hasattr(AssetBibleRepository, "save_asset_bible")
    assert hasattr(PromptPlanRepository, "save_prompt_plan_bundle")
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_platform_repository_contracts.py -v`

Expected: fail with missing repository modules.

- [ ] **Step 3: Create protocol modules**

Define protocol classes with async methods and typed `dict` payload boundaries. Do not add local JSON implementations in these files.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_platform_repository_contracts.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/repositories tests/test_platform_repository_contracts.py
git commit -m "feat: 建立平台仓储接口合同"
```

## Task 2: Object Store Contract

**Files:**

- Create: `pixelle_video/storage/object_store.py`
- Test: `tests/test_platform_object_store_contract.py`

- [ ] **Step 1: Write storage-key tests**

Test that the dev adapter returns normalized storage keys and never returns absolute local paths.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_platform_object_store_contract.py -v`

Expected: fail with missing object store module.

- [ ] **Step 3: Implement `RawPayloadStore` and `FilesystemDevRawPayloadStore`**

The dev adapter may write under a configured root, but public return values must look like `raw-payloads/{workspace_id}/{object_id}.json`.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_platform_object_store_contract.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/storage/object_store.py tests/test_platform_object_store_contract.py
git commit -m "feat: 建立原始载荷对象存储合同"
```

## Task 3: Resource Resolver Contract

**Files:**

- Create: `pixelle_video/services/resource_resolver.py`
- Test: `tests/test_resource_resolver_contract.py`

- [ ] **Step 1: Write resolver tests**

Test that formal inputs are resource IDs and that arbitrary local paths or workflow paths are rejected.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_resource_resolver_contract.py -v`

Expected: fail with missing resolver module.

- [ ] **Step 3: Implement resolver protocol and static resolver**

Implement a `ResourceResolver` protocol and `StaticResourceResolver` for dev/test. Reject values containing drive roots, absolute paths, `..`, or raw provider URLs.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_resource_resolver_contract.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/resource_resolver.py tests/test_resource_resolver_contract.py
git commit -m "feat: 建立资源解析器合同"
```

## Task 4: Runtime Profile Fail Fast

**Files:**

- Modify: `api/config.py`
- Test: `tests/test_runtime_profile_fail_fast.py`

- [ ] **Step 1: Write fail-fast tests**

Test that production profile requires PostgreSQL and object storage configuration, while dev profile may use in-memory repositories and filesystem dev stores.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_runtime_profile_fail_fast.py -v`

Expected: fail because runtime profile validation is missing.

- [ ] **Step 3: Add config validation**

Add `PIXELLE_RUNTIME_PROFILE=dev|production`. In production, fail at config build time if required database or object-store settings are absent.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_runtime_profile_fail_fast.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add api/config.py tests/test_runtime_profile_fail_fast.py
git commit -m "feat: 增加生产运行配置快速失败"
```

## Task 5: Active Plan Guard

**Files:**

- Test: `tests/test_active_plan_zero_debt_policy.py`

- [ ] **Step 1: Write documentation guard test**

Add a test that scans active Stage 1A, Stage 1B, and Stage 2 plans and fails if they contain `LocalJson`, `LocalLLMTraceStore`, `LocalAssetBibleService`, or `_runtime/trace`.

- [ ] **Step 2: Verify pass**

Run: `pytest tests/test_active_plan_zero_debt_policy.py -v`

Expected: all tests pass after the rewritten plans are active.

- [ ] **Step 3: Commit**

```bash
git add tests/test_active_plan_zero_debt_policy.py
git commit -m "test: 防止阶段计划重新引入本地临时合同"
```

## Verification Checklist

Run:

```bash
pytest \
  tests/test_platform_repository_contracts.py \
  tests/test_platform_object_store_contract.py \
  tests/test_resource_resolver_contract.py \
  tests/test_runtime_profile_fail_fast.py \
  tests/test_active_plan_zero_debt_policy.py \
  -v
```

Expected: all selected tests pass.

Run:

```bash
rg "LocalJson|LocalLLMTraceStore|LocalAssetBibleService|_runtime/trace" docs/superpowers/plans/2026-04-30-stage1a-text-image-prompt-trace-implementation.md docs/superpowers/plans/2026-04-29-storyboard-workbench-stage1-implementation.md docs/superpowers/plans/2026-04-30-stage2-assetbible-ip-scenecast-implementation.md
```

Expected: no matches.
