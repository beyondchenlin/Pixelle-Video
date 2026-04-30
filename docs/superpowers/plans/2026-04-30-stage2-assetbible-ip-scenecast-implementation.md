# Stage 2 AssetBible / IP / SceneCast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 2 IP and visual-consistency contract layer: AssetBible, IPProfile, CharacterProfile, SceneCast, and PromptComposer asset-reference projection.

**Architecture:** Stage 2 owns IP and visual consistency facts, but it does not own storage implementation or mutate Stage 1A's core prompt model. Asset facts persist through `AssetBibleRepository`; PromptComposer returns validated references or a new PromptPlan projection using Stage 1A's reserved fields after Gate A.

**Tech Stack:** Python dataclasses, Pydantic schemas, FastAPI routers, platform repository protocols from Stage 0.5, pytest, existing Pixelle `StoryboardPlan`, Stage 1A `PromptPlan`.

---

## Planning Authority

This plan implements Stage 2 contract work only. It is governed by:

- `docs/pixelle_video_full_planning_md/24_PLATFORM_FOUNDATION_ZERO_TECH_DEBT_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md`
- `docs/pixelle_video_full_planning_md/04_PROMPT_COMPOSER_AND_SCENE_CASTING.md`
- `docs/pixelle_video_full_planning_md/15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`
- `docs/pixelle_video_full_planning_md/23_STAGE1_STAGE2_PARALLEL_DEVELOPMENT_STRATEGY.md`

Repository override:

```text
AGENTS.md forbids git worktree use in this repository.
Execute in the current workspace with narrow staging and atomic commits.
Use Chinese commit messages.
```

## Hard Prerequisites

Stage 2 can run in parallel with Stage 1A only inside these boundaries:

```text
Gate 0.5 must pass before any AssetBible persistence or API work.
Before Gate A, Stage 2 may implement pure models, validators, repository fakes, and API draft contracts.
After Gate A, Stage 2 may consume Stage 1A PromptPlan reserved fields.
```

Do not connect AssetBible or SceneCast to the main generation path before Stage 1A `PromptPlan` is stable.

## Scope

This plan implements:

- `AssetBible`.
- `IPProfile`.
- `CharacterProfile`.
- `SceneAsset`.
- `PropAsset`.
- `StyleProfile`.
- `SceneCast`.
- `AssetBibleRepository` consumption through injected interfaces.
- SceneCast validation.
- PromptComposer asset-reference projection into Stage 1A reserved fields.
- Draft App API for asset bible and scene cast management.

This plan does not implement:

- Local JSON asset bible service.
- Reference image management.
- LoRA management.
- Image-to-image consistency.
- Provider routing.
- Billing or permissions.
- Main generation-path integration before Stage 1A PromptPlan is stable.

## File Structure

- Create `pixelle_video/models/asset_bible.py`: asset and IP contracts.
- Create `pixelle_video/models/scene_cast.py`: frame-level cast contracts.
- Create `pixelle_video/services/scene_casting.py`: validation and cast creation helpers.
- Create `pixelle_video/services/prompt_composer.py`: reserved-field projection into Stage 1A `PromptPlan`.
- Create `api/schemas/asset_bible.py`: draft asset request/response schemas.
- Create `api/routers/asset_bible.py`: asset bible and scene cast endpoints using injected repository.
- Modify `api/app.py`: include router after local tests pass.
- Add tests:
  - `tests/test_asset_bible_models.py`
  - `tests/test_scene_cast_model.py`
  - `tests/test_scene_casting_validation.py`
  - `tests/test_prompt_composer_asset_projection.py`
  - `tests/test_asset_bible_api.py`

## Task 1: AssetBible And IP Domain Models

**Files:**

- Create: `pixelle_video/models/asset_bible.py`
- Test: `tests/test_asset_bible_models.py`

- [ ] **Step 1: Write model tests**

Test `IPProfile`, `CharacterProfile`, `SceneAsset`, `PropAsset`, `StyleProfile`, and `AssetBible` serialization. `forbidden_elements` must be part of the IP profile contract.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_asset_bible_models.py -v`

Expected: fail with missing asset bible model.

- [ ] **Step 3: Implement models**

Use stable IDs and project/workspace ownership fields. Do not persist or read local files in model code.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_asset_bible_models.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/asset_bible.py tests/test_asset_bible_models.py
git commit -m "feat: 建立资产圣经领域模型"
```

## Task 2: SceneCast Model

**Files:**

- Create: `pixelle_video/models/scene_cast.py`
- Test: `tests/test_scene_cast_model.py`

- [ ] **Step 1: Write model tests**

Test frame-level references for `frame_id`, `character_ids`, `scene_id`, `prop_ids`, `style_id`, and continuity notes.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_scene_cast_model.py -v`

Expected: fail with missing scene cast model.

- [ ] **Step 3: Implement model**

`SceneCast` references IDs only; it must not embed full character or scene objects.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_scene_cast_model.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/scene_cast.py tests/test_scene_cast_model.py
git commit -m "feat: 建立场景出场合同"
```

## Task 3: SceneCast Validation

**Files:**

- Create: `pixelle_video/services/scene_casting.py`
- Test: `tests/test_scene_casting_validation.py`

- [ ] **Step 1: Write validation tests**

Test that SceneCast rejects unknown character, scene, prop, and style IDs. Test that all IDs belong to the current project AssetBible.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_scene_casting_validation.py -v`

Expected: fail with missing validation service.

- [ ] **Step 3: Implement validator**

Accept an `AssetBible` object or repository-loaded bible. Return deterministic validation errors with the invalid field and ID.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_scene_casting_validation.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/scene_casting.py tests/test_scene_casting_validation.py
git commit -m "feat: 校验场景出场资产引用"
```

## Task 4: PromptComposer Asset Projection

**Files:**

- Create: `pixelle_video/services/prompt_composer.py`
- Test: `tests/test_prompt_composer_asset_projection.py`

- [ ] **Step 1: Write projection tests**

Use Stage 1A `PromptPlan` fixtures. Test that `apply_scene_cast_to_prompt_plan()` returns a new PromptPlan or patch object with `character_ids`, `scene_id`, `prop_ids`, and `style_id` filled from a validated SceneCast.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prompt_composer_asset_projection.py -v`

Expected: fail with missing prompt composer.

- [ ] **Step 3: Implement projection**

Do not mutate the input object in place. Do not change the core PromptPlan shape. Do not connect to the main generation path in this task.

- [ ] **Step 4: Verify pass**

Run: `pytest tests/test_prompt_composer_asset_projection.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/prompt_composer.py tests/test_prompt_composer_asset_projection.py
git commit -m "feat: 投影场景资产到提示词计划"
```

## Task 5: AssetBible Draft API

**Files:**

- Create: `api/schemas/asset_bible.py`
- Create: `api/routers/asset_bible.py`
- Modify: `api/app.py`
- Test: `tests/test_asset_bible_api.py`

- [ ] **Step 1: Write API tests with repository fakes**

Test creating, loading, and updating AssetBible drafts through `AssetBibleRepository`. API responses must expose IDs and structured asset facts, not local storage paths.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_asset_bible_api.py -v`

Expected: fail because asset bible API does not exist.

- [ ] **Step 3: Add schemas and router**

Use request fields such as `ip_name`, `style_hint`, `world_hint`, `forbidden_elements`, and explicit asset lists. Persist through injected `AssetBibleRepository`.

- [ ] **Step 4: Register router**

Modify `api/app.py` to include the router under the configured API prefix.

- [ ] **Step 5: Verify pass**

Run: `pytest tests/test_asset_bible_api.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add api/schemas/asset_bible.py api/routers/asset_bible.py api/app.py tests/test_asset_bible_api.py
git commit -m "feat: 提供资产圣经草稿接口"
```

## Verification Checklist

Run:

```bash
pytest \
  tests/test_asset_bible_models.py \
  tests/test_scene_cast_model.py \
  tests/test_scene_casting_validation.py \
  tests/test_prompt_composer_asset_projection.py \
  tests/test_asset_bible_api.py \
  -v
```

Expected: all selected Stage 2 tests pass.

Run the active-plan guard from the Stage 0.5 foundation plan.

## Implementation Notes

- IP 形象设计从 Stage 2A 开始，并行内容是 `IPProfile`、`CharacterProfile`、`StyleProfile`、`AssetBible` 和 `SceneCast` 合同。
- Stage 2 does not modify Stage 1A PromptPlan's core shape.
- Reference images, LoRA, image-to-image, and Provider-specific consistency workflows are later stages.
- Local filesystem can appear only as a dev/test adapter injected by Stage 0.5 infrastructure.
