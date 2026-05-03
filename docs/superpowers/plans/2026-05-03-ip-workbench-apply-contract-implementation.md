# IP Workbench Apply Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing AssetBible / SceneCast / preview-only projection work into a formal IP Workbench apply flow that saves applied PromptPlans through the existing repository and stale dependency contracts.

**Architecture:** Keep `PromptPlanProjectionPreview` read-only. Add a separate backend apply service and endpoint that loads the current PromptPlan bundle, applies one validated SceneCast to one frame, and saves the updated bundle through `StaleAwarePromptPlanWriteService`. Add a Workbench client boundary for IP operations, then render IP controls inside the Storyboard Workbench without direct HTTP helper imports.

**Tech Stack:** Python dataclasses, FastAPI, Pydantic, Streamlit, existing repository protocols, pytest, ruff.

---

## Current State Guard

Do not execute `docs/superpowers/plans/2026-04-30-stage2-assetbible-ip-scenecast-implementation.md` as a new work plan. It is now a historical plan; the model/API/preview foundation it describes is already present.

This plan starts from the current `dev` state where the focused Stage2/IP suite passes:

```powershell
python -m pytest -q tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py tests/test_stale_write_integration.py
```

Expected current result: pass.

## File Structure

- Create `pixelle_video/services/asset_prompt_plan_apply.py`
  - Backend service for persisted apply. It orchestrates repositories and stale-aware write service, not HTTP or UI.
- Modify `api/schemas/asset_bible.py`
  - Adds apply request/response schemas.
- Modify `api/routers/asset_bible.py`
  - Adds `prompt-plan-apply` endpoint. Keeps existing `prompt-plan-projection` endpoint preview-only.
- Create `web/ip_workbench/client.py`
  - Defines `StoryboardIPWorkbenchClient` protocol and error type.
- Create `web/ip_workbench/http_client.py`
  - Wraps `web.utils.asset_bible_api` and apply endpoint.
- Create `web/ip_workbench/inprocess_client.py`
  - Calls local repositories/services directly.
- Create `web/state/ip_workbench_client.py`
  - Resolves and caches HTTP/in-process IP clients using the same mode as Storyboard Workbench.
- Modify `web/utils/asset_bible_api.py`
  - Adds apply endpoint builder/caller for HTTP adapter use only.
- Create `web/components/ip_workbench_panel.py`
  - Formal Workbench panel for AssetBible/SceneCast selection and apply.
- Modify `web/components/storyboard_preview.py`
  - Passes IP client and frame context to the IP panel.
- Modify `web/pages/3_🧭_Storyboard_Workbench.py`
  - Resolves `StoryboardIPWorkbenchClient` next to the existing Storyboard Workbench client.
- Tests:
  - Create `tests/test_asset_prompt_plan_apply.py`
  - Update `tests/test_asset_bible_api.py`
  - Create `tests/test_ip_workbench_client.py`
  - Create `tests/test_ip_workbench_panel_ui.py`
  - Update `tests/test_storyboard_workbench_page.py`
  - Add source-boundary assertions to prevent direct HTTP imports in formal IP UI.

## Task 1: Backend Apply Service

**Files:**
- Create: `pixelle_video/services/asset_prompt_plan_apply.py`
- Test: `tests/test_asset_prompt_plan_apply.py`

- [ ] **Step 1: Write failing tests for persisted apply**

Create `tests/test_asset_prompt_plan_apply.py` with focused fake repositories. Cover:

```python
@pytest.mark.asyncio
async def test_apply_scene_cast_replaces_only_target_prompt_plan_and_saves_bundle():
    # arrange two prompt plans in the same bundle
    # apply SceneCast to frame_0001
    # assert frame_0001 has character_ids/scene_id/prop_ids/style_id
    # assert frame_0002 is unchanged
    # assert fake stale-aware writer was called exactly once with full bundle
```

Also cover:

```python
@pytest.mark.asyncio
async def test_apply_scene_cast_rejects_missing_prompt_plan_frame():
    # expect PromptPlanApplyNotFoundError

@pytest.mark.asyncio
async def test_apply_scene_cast_rejects_invalid_scene_cast_reference():
    # expect PromptPlanApplyValidationError

@pytest.mark.asyncio
async def test_apply_scene_cast_requires_stale_aware_writer():
    # expect PromptPlanApplyDependencyError
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_apply.py
```

Expected: fail because `pixelle_video.services.asset_prompt_plan_apply` does not exist.

- [ ] **Step 3: Implement apply service**

Create `pixelle_video/services/asset_prompt_plan_apply.py`:

- Define errors:
  - `PromptPlanApplyError`
  - `PromptPlanApplyDependencyError`
  - `PromptPlanApplyNotFoundError`
  - `PromptPlanApplyValidationError`
  - `PromptPlanApplyRepositoryIdentityError`
- Define result dataclasses:
  - `PromptPlanApplySource`
  - `PromptPlanApplyWriteSummary`
  - `PromptPlanApplyResult`
- Implement `AssetPromptPlanApplyService.apply_scene_cast_to_prompt_plan_bundle(...)`.

Implementation rules:

- Load AssetBible through `AssetBibleRepository.load_asset_bible(workspace_id, asset_bible_id)`.
- Load SceneCast through `AssetBibleRepository.load_scene_cast(workspace_id, scene_cast_id)`.
- Validate with `validate_scene_cast(scene_cast, asset_bible)`.
- Load full PromptPlans with `PromptPlanRepository.load_prompt_plans_by_storyboard(workspace_id, storyboard_plan_id)`.
- Reconstruct a `PromptPlanBundle`. Reuse loaded prompt plan `image_prompt_draft_id` values by creating matching `ImagePromptDraft` objects from the existing prompt text if the repository does not return drafts.
- Replace only the target frame PromptPlan with `apply_scene_cast_to_prompt_plan(prompt_plan, scene_cast)`.
- Save through `StaleAwarePromptPlanWriteService.save_prompt_plan_bundle(workspace_id, project_id, bundle)`.
- Return applied PromptPlan and write summary.

- [ ] **Step 4: Run service tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_apply.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add -- pixelle_video/services/asset_prompt_plan_apply.py tests/test_asset_prompt_plan_apply.py
git commit -m "feat: 增加IP分镜应用服务"
git push origin $(git branch --show-current)
```

## Task 2: Apply API Contract

**Files:**
- Modify: `api/schemas/asset_bible.py`
- Modify: `api/routers/asset_bible.py`
- Test: `tests/test_asset_bible_api.py`

- [ ] **Step 1: Write failing API tests**

Extend `tests/test_asset_bible_api.py`:

```python
def test_apply_scene_cast_to_prompt_plan_saves_projected_bundle():
    # POST /api/projects/project_1/asset-bible/bible_demo/scene-casts/cast_frame_1/prompt-plan-apply
    # assert response contains application.prompt_plan.character_ids
    # assert fake prompt writer saved updated bundle
```

Add boundary tests:

```python
def test_projection_preview_does_not_save_prompt_plan_bundle():
    # call existing prompt-plan-projection
    # assert fake writer/repository save count remains zero

def test_apply_rejects_path_like_ids_before_repository_calls():
    # use asset_bible_id="D:\\bad"
    # assert 422 and repository not called
```

- [ ] **Step 2: Run API tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py
```

Expected: fail because apply schemas/route do not exist.

- [ ] **Step 3: Add schemas**

In `api/schemas/asset_bible.py`, add:

- `PromptPlanApplyRequest`
- `PromptPlanApplySourceResponse`
- `PromptPlanApplyWriteResponse`
- `PromptPlanApplyPayload`
- `PromptPlanApplyResponse`

Reuse the same public ID and metadata validation style as projection schemas.

- [ ] **Step 4: Add route**

In `api/routers/asset_bible.py`, add:

```text
POST /{project_id}/asset-bible/{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-apply
```

Route rules:

- Validate route IDs with `_validate_public_id`.
- Build `AssetPromptPlanApplyService`.
- Map missing resources to `404`.
- Map validation to `422`.
- Map repository identity corruption to `502`.
- Map missing stale-write infrastructure to `503`.
- Do not modify the existing preview route.

- [ ] **Step 5: Run API tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py tests/test_asset_prompt_plan_apply.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add -- api/schemas/asset_bible.py api/routers/asset_bible.py tests/test_asset_bible_api.py
git commit -m "feat: 提供IP分镜应用接口"
git push origin $(git branch --show-current)
```

## Task 3: IP Workbench Client Boundary

**Files:**
- Create: `web/ip_workbench/client.py`
- Create: `web/ip_workbench/http_client.py`
- Create: `web/ip_workbench/inprocess_client.py`
- Create: `web/ip_workbench/__init__.py`
- Create: `web/state/ip_workbench_client.py`
- Modify: `web/utils/asset_bible_api.py`
- Test: `tests/test_ip_workbench_client.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_ip_workbench_client.py`:

```python
def test_http_ip_workbench_client_wraps_asset_bible_helpers():
    # inject fake helper functions
    # assert list_asset_bibles/list_scene_casts/apply call helpers with api_base_url

def test_inprocess_ip_workbench_client_uses_local_services_without_http():
    # inject fake core with repositories
    # assert client returns application payload

def test_ip_workbench_client_factory_does_not_cache_unconfigured_inprocess_client():
    # pixelle_video=None should return unavailable/no cached broken client

def test_formal_ip_workbench_ui_sources_do_not_import_http_helpers():
    # inspect web/components/ip_workbench_panel.py after Task 4
```

- [ ] **Step 2: Run client tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_ip_workbench_client.py
```

Expected: fail because client modules do not exist.

- [ ] **Step 3: Add HTTP apply helper**

In `web/utils/asset_bible_api.py`, add:

```python
def build_prompt_plan_apply_endpoint(
    *,
    api_base_url: str,
    project_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
) -> str:
    return (
        f"{api_base_url.rstrip('/')}/projects/{project_id}/asset-bible/"
        f"{asset_bible_id}/scene-casts/{scene_cast_id}/prompt-plan-apply"
    )
```

Add `apply_scene_cast_to_prompt_plan(...)` that posts `workspace_id`, `storyboard_plan_id`, `frame_id`, and optional `actor_id`.

- [ ] **Step 4: Implement client modules**

Implement:

- `StoryboardIPWorkbenchClient` protocol.
- `HttpStoryboardIPWorkbenchClient`.
- `InProcessStoryboardIPWorkbenchClient`.
- `resolve_storyboard_ip_workbench_client(...)`.

Factory rules:

- HTTP mode caches by `api_base_url`.
- In-process mode caches by `id(pixelle_video)`.
- No `pixelle_video` means no cached in-process client.
- UI must receive `None` or unavailable client rather than falling back to HTTP.

- [ ] **Step 5: Run client tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_ip_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add -- web/ip_workbench web/state/ip_workbench_client.py web/utils/asset_bible_api.py tests/test_ip_workbench_client.py
git commit -m "feat: 增加IP工作台客户端边界"
git push origin $(git branch --show-current)
```

## Task 4: Formal IP Workbench UI

**Files:**
- Create: `web/components/ip_workbench_panel.py`
- Modify: `web/components/storyboard_preview.py`
- Modify: `web/pages/3_🧭_Storyboard_Workbench.py`
- Test: `tests/test_ip_workbench_panel_ui.py`
- Test: `tests/test_storyboard_workbench_page.py`

- [ ] **Step 1: Write failing UI tests**

Create `tests/test_ip_workbench_panel_ui.py`:

```python
def test_ip_workbench_panel_lists_asset_bibles_and_scene_casts_from_client():
    # fake client returns one bible and one cast
    # assert rendered labels include bible/cast IDs and asset summary

def test_ip_workbench_panel_disables_apply_when_scene_cast_frame_mismatch():
    # fake cast has frame_id different from current frame
    # assert apply button disabled

def test_ip_workbench_panel_applies_scene_cast_through_client():
    # simulate apply button
    # assert fake client call includes project/workspace/storyboard/frame

def test_ip_workbench_panel_fails_closed_without_client():
    # assert unavailable message and no HTTP helper usage
```

Update `tests/test_storyboard_workbench_page.py`:

```python
def test_storyboard_workbench_page_passes_ip_client_to_preview(monkeypatch):
    # resolve fake IP client
    # assert preview renderer receives ip_workbench_client
```

- [ ] **Step 2: Run UI tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_page.py
```

Expected: fail because panel/page wiring does not exist.

- [ ] **Step 3: Implement panel**

`web/components/ip_workbench_panel.py` must:

- Accept `ip_workbench_client`.
- Accept `workspace_id`, `project_id`, `storyboard_plan_id`, `frame_id`.
- Fail closed if context or client is missing.
- List AssetBible via client.
- List SceneCast via client.
- Prefer SceneCast matching current storyboard/frame.
- Show character/scene/prop/style summary.
- Call `client.apply_scene_cast_to_prompt_plan(...)` only when selected SceneCast matches current frame.
- Never import `httpx`, `DEFAULT_API_BASE_URL`, or `web.utils.asset_bible_api`.

- [ ] **Step 4: Wire page and preview**

Modify:

- `web/pages/3_🧭_Storyboard_Workbench.py`
  - Resolve IP client beside Storyboard Workbench client.
  - Pass it into preview renderer.
- `web/components/storyboard_preview.py`
  - Accept `ip_workbench_client`.
  - Render `ip_workbench_panel` when project/workspace/storyboard/frame context exists.

- [ ] **Step 5: Run UI tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_page.py tests/test_ip_workbench_client.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit and push**

```powershell
git add -- web/components/ip_workbench_panel.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_page.py
git commit -m "feat: 接入正式IP分镜工作台"
git push origin $(git branch --show-current)
```

## Task 5: Boundary Regression And Preview Guard

**Files:**
- Modify tests only unless regressions fail.

- [ ] **Step 1: Add source-boundary regression tests**

Add or extend source inspection tests:

```python
def test_formal_ip_workbench_ui_does_not_import_transport_helpers():
    forbidden = (
        "web.utils.asset_bible_api",
        "httpx",
        "DEFAULT_API_BASE_URL",
        "localhost:8001",
    )
    for path in [
        Path("web/components/ip_workbench_panel.py"),
        Path("web/components/storyboard_preview.py"),
        Path("web/pages/3_🧭_Storyboard_Workbench.py"),
    ]:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source
```

Add preview guard assertion:

```python
def test_projection_preview_route_does_not_import_apply_service_or_writer():
    source = Path("api/routers/asset_bible.py").read_text(encoding="utf-8")
    preview_block = source.split("async def preview_prompt_plan_projection", 1)[1].split("def _get_asset_bible_repository", 1)[0]
    assert "AssetPromptPlanApplyService" not in preview_block
    assert "StaleAwarePromptPlanWriteService" not in preview_block
    assert "save_prompt_plan_bundle" not in preview_block
```

- [ ] **Step 2: Run full focused regression**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_apply.py tests/test_asset_bible_api.py tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py tests/test_stale_write_integration.py tests/test_ip_workbench_client.py tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
```

Expected: all tests pass.

- [ ] **Step 3: Run lint and diff checks**

Run:

```powershell
ruff check pixelle_video/services/asset_prompt_plan_apply.py api/schemas/asset_bible.py api/routers/asset_bible.py web/ip_workbench web/state/ip_workbench_client.py web/utils/asset_bible_api.py web/components/ip_workbench_panel.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_asset_prompt_plan_apply.py tests/test_asset_bible_api.py tests/test_ip_workbench_client.py tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_page.py
git diff --check
```

Expected: pass.

- [ ] **Step 4: Commit and push regression-only fixes**

If Step 2 or Step 3 required fixes:

```powershell
git add -- <fixed-files>
git commit -m "test: 固化IP工作台应用边界"
git push origin $(git branch --show-current)
```

If no fixes were needed, do not create an empty commit.

## Final Verification

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_apply.py tests/test_asset_bible_api.py tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py tests/test_stale_write_integration.py tests/test_ip_workbench_client.py tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_client.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_workbench_page.py
```

Run:

```powershell
ruff check pixelle_video/services/asset_prompt_plan_apply.py api/schemas/asset_bible.py api/routers/asset_bible.py web/ip_workbench web/state/ip_workbench_client.py web/utils/asset_bible_api.py web/components/ip_workbench_panel.py web/components/storyboard_preview.py web/pages/3_🧭_Storyboard_Workbench.py tests/test_asset_prompt_plan_apply.py tests/test_asset_bible_api.py tests/test_ip_workbench_client.py tests/test_ip_workbench_panel_ui.py tests/test_storyboard_workbench_page.py
git diff --check
git status --short --branch
```

Expected: focused tests pass, lint passes, diff check passes, and branch has no uncommitted changes from this plan.

## Self-Review

- Spec coverage: covers preview guard, apply service, apply API, client boundary, formal UI, stale-aware PromptPlan saving, and source-boundary regression.
- Placeholder scan: no unresolved placeholders or unspecified task bodies.
- Type consistency: stable names are `AssetPromptPlanApplyService`, `PromptPlanApplyResult`, `PromptPlanApplyResponse`, `StoryboardIPWorkbenchClient`, `HttpStoryboardIPWorkbenchClient`, `InProcessStoryboardIPWorkbenchClient`, and `render_ip_workbench_panel`.
- Scope check: no reference image, LoRA, provider routing, workflow path, or generation trigger is introduced.
- Debt check: new product path is Workbench client + apply contract; existing projection preview remains debug-only.
