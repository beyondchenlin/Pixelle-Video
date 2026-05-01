# Stage 1B Workbench Stale Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only stale dependency radar to the existing Storyboard Preview / Workbench frame UI.

**Architecture:** Keep stale API fetching in a focused Workbench stale component and keep the generic stale panel renderer unchanged. The Storyboard Preview passes per-frame `prompt_plan_id` and optional frontend context into the stale component, which fails closed when required context is missing.

**Tech Stack:** Python, Streamlit component helpers, existing `web.utils.stale_api`, pytest fake UI tests, ruff.

---

## Governing Spec

- `docs/superpowers/specs/2026-05-01-stage1b-workbench-stale-panel-design.md`

## File Structure

- Create `web/components/storyboard_workbench_stale.py`: context resolution, safe API call, and per-frame stale panel rendering.
- Modify `web/components/storyboard_preview.py`: accept stale context/renderer and call it inside each frame card.
- Modify `web/components/storyboard_planning_controls.py`: pass stale context from session state into preview renderer.
- Add `tests/test_storyboard_workbench_stale_ui.py`: component and integration tests.
- Optionally modify `web/i18n/locales/en_US.json` and `web/i18n/locales/zh_CN.json` only if existing translation fallback is insufficient for user-visible labels.

## Task 1: Stale Component Contract

**Files:**

- Create: `tests/test_storyboard_workbench_stale_ui.py`
- Create: `web/components/storyboard_workbench_stale.py`

- [ ] **Step 1: Write failing component tests**

Create tests that prove:

- `render_frame_stale_panel()` calls the stale API when `api_base_url`, `workspace_id`, `project_id`, and `prompt_plan_id` are present.
- It passes `target_type="prompt_plan"` and the current `prompt_plan_id`.
- It renders the existing stale panel output.
- It does not call the API when context is missing.
- It suppresses API exception details and shows only a safe caption.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py
```

Expected: fail because `web.components.storyboard_workbench_stale` does not exist.

- [ ] **Step 3: Implement component**

Implement:

- `build_stale_panel_context(session_state=None, api_base_url=None, workspace_id=None, project_id=None) -> dict[str, str]`
- `render_frame_stale_panel(prompt_plan_id, *, ui=st, translate=tr, stale_summary_loader=get_stale_target_summary, panel_renderer=render_stale_target_panel, api_base_url=None, workspace_id=None, project_id=None) -> None`

Rules:

- Default `api_base_url` to session state `api_base_url`, then `http://localhost:8000/api`.
- Read `workspace_id` and `project_id` from explicit args first, then session state.
- If `workspace_id`, `project_id`, or `prompt_plan_id` is missing, call `ui.caption(translate("stale.workbench.missing_context"))` and return without API call.
- On loader exception, call `ui.caption(translate("stale.workbench.unavailable"))` and do not include the exception string in UI.
- Pass `stale_summary=response["stale_summary"]` into `panel_renderer`.
- Do not add buttons or generation actions.

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py
```

Expected: all tests in the new file pass.

## Task 2: Storyboard Preview Integration

**Files:**

- Modify: `tests/test_storyboard_workbench_stale_ui.py`
- Modify: `web/components/storyboard_preview.py`
- Modify: `web/components/storyboard_planning_controls.py`

- [ ] **Step 1: Write failing integration tests**

Add tests that prove:

- `render_storyboard_preview(planning_snapshot, stale_context=..., stale_renderer=...)` invokes the stale renderer once per frame with the frame row `plan_id`.
- Existing frame override payload collection still returns the same valid override shape.
- `render_storyboard_advanced_controls()` can pass `stale_context` into its preview renderer without changing existing payload semantics.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py tests/test_stale_frontend_ui.py
```

Expected: fail because `render_storyboard_preview()` does not accept stale integration arguments yet.

- [ ] **Step 3: Implement integration**

Implement:

- Add optional `stale_context: Mapping[str, str] | None = None` to `render_storyboard_preview()`.
- Add optional `stale_renderer: Callable[..., None] | None = render_frame_stale_panel`.
- Inside each frame card, call stale renderer after editable fields:
  - `prompt_plan_id=row["plan_id"]`
  - `api_base_url=stale_context.get("api_base_url")`
  - `workspace_id=stale_context.get("workspace_id")`
  - `project_id=stale_context.get("project_id")`
  - `ui=st`
  - `translate=tr`
- In `render_storyboard_advanced_controls()`, build stale context from session state using `build_stale_panel_context()` and pass it to the preview renderer.
- Preserve the existing `preview_renderer(preview_snapshot)` callable compatibility by falling back if a custom renderer does not accept `stale_context`.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py tests/test_stale_frontend_ui.py
```

Expected: both files pass.

## Task 3: Regression Verification And Review

**Files:**

- Test only unless review finds a source-level defect.

- [ ] **Step 1: Run targeted frontend and stale tests**

Run:

```bash
python -m pytest -q tests/test_storyboard_workbench_stale_ui.py tests/test_stale_frontend_ui.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_service.py tests/test_storyboard_frame_regeneration.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run broader Stage1B/Stage2 stale boundary tests**

Run:

```bash
python -m pytest -q tests/test_stale_dependency_read_model.py tests/test_stale_dependency_api.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_propagation.py tests/test_stale_write_integration.py tests/test_artifact_dependency_integration.py tests/test_asset_bible_api.py tests/test_asset_prompt_plan_composer.py tests/test_prompt_composer_asset_projection.py tests/test_scene_casting_validation.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py
```

Expected: all selected tests pass.

- [ ] **Step 3: Run lint and whitespace checks**

Run:

```bash
python -m ruff check web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/components/storyboard_planning_controls.py tests/test_storyboard_workbench_stale_ui.py tests/test_stale_frontend_ui.py
git diff --check
```

Expected: ruff reports all checks passed and `git diff --check` exits 0.

- [ ] **Step 4: Review twice**

Review pass 1, requirement compliance:

- Stale panel is read-only.
- Missing context does not call stale API.
- API errors do not leak sensitive details.
- Stage 2 projection preview remains preview-only.
- Title/subtitle rendering remains separate.

Review pass 2, source quality:

- No duplicated HTTP endpoint logic.
- No hard-coded project/workspace values.
- No local path/provider/workflow leakage.
- Existing storyboard override behavior remains unchanged.
- New component has one clear responsibility.

- [ ] **Step 5: Commit and push**

Run:

```bash
git add web/components/storyboard_workbench_stale.py web/components/storyboard_preview.py web/components/storyboard_planning_controls.py tests/test_storyboard_workbench_stale_ui.py
git commit -m "feat: 接入 Workbench stale 只读面板"
git push origin dev
```

Expected: commit and push succeed.

## Self Review

- Spec coverage：计划覆盖组件、真实 preview 挂载点、session context、fail-closed 行为、安全边界、测试和双轮 review。
- Placeholder scan：无 TBD、TODO、implement later 或未定项。
- Type consistency：计划中的函数名和参数在 Task 1、Task 2 中保持一致。
- Scope check：计划不包含生成、重抽、保存、候选图 gallery、Stage 2 persistence 或标题/字幕改造。
