# Stage2 Projection Selection Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Stage2 projection preview default path into a guided Context -> AssetBible -> SceneCast -> Storyboard Frame -> Preview selection flow that prevents wrong or stale selections before preview.

**Architecture:** Keep the backend preview endpoint unchanged and refactor only the Streamlit selection flow plus its tests. Add focused helper functions in `web/components/asset_prompt_plan_projection.py` for flow state, derived frame display, request validation, and request summary; keep draft staging in `asset_bible_draft_setup.py` as the source of automatic active-selection updates.

**Tech Stack:** Python, Streamlit-compatible component functions, pytest fake UI tests, existing `web.utils.asset_bible_api` projection client.

---

## File Structure

- Modify: `web/components/asset_prompt_plan_projection.py`
  - Owns the guided selection flow UI, request validation, derived frame display, request summary, and preview result rendering.
- Modify: `tests/test_asset_prompt_plan_projection_ui.py`
  - Adds tests for locked downstream steps, guided step labels, derived frame status, mismatch blocking, and existing preview-only boundaries.
- Verify: `web/components/asset_bible_draft_setup.py`
  - Existing staging functions should remain the source of draft-to-preview selection updates. Only patch this file if tests prove a staging gap.

No backend API schemas, routers, projection service, generation pipeline, title/subtitle/text-rendering contract, or persistence layer should be changed by this plan.

## Task 1: Lock Down Guided Flow Tests

**Files:**

- Modify: `tests/test_asset_prompt_plan_projection_ui.py`
- Modify in Task 2: `web/components/asset_prompt_plan_projection.py`

- [ ] **Step 1: Add failing tests for step labels and locked downstream default state**

Append these tests near the existing projection preview UI tests:

```python
def test_render_projection_preview_guides_user_through_selection_steps():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "1. Context" in rendered
    assert "2. AssetBible" in rendered
    assert "3. SceneCast" in rendered
    assert "4. Storyboard Frame" in rendered
    assert "5. Preview" in rendered
    assert "Load context before selecting AssetBible" in rendered
    assert "Load context before selecting SceneCast" in rendered
    assert "Preview is locked until context, AssetBible, SceneCast, storyboard, and frame are ready" in rendered
```

```python
def test_render_projection_preview_does_not_show_frame_inputs_before_context_is_loaded():
    from web.components.asset_prompt_plan_projection import (
        render_asset_prompt_plan_projection_preview,
    )

    fake_ui = _ProjectionFakeUI()

    render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    projection_labels = {
        item["key"]: item["label"]
        for item in fake_ui.text_inputs
        if item.get("key", "").startswith("projection_")
    }
    assert "projection_project_id" in projection_labels
    assert "projection_workspace_id" in projection_labels
    assert "projection_storyboard_plan_id" not in projection_labels
    assert "projection_frame_id" not in projection_labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_guides_user_through_selection_steps tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_does_not_show_frame_inputs_before_context_is_loaded
```

Expected: FAIL because the current UI does not expose guided step labels and still renders storyboard/frame text inputs before context is loaded.

## Task 2: Implement Guided Step Shell And Progressive Locking

**Files:**

- Modify: `web/components/asset_prompt_plan_projection.py`
- Modify: `tests/test_asset_prompt_plan_projection_ui.py`

- [ ] **Step 1: Add small rendering helpers**

Add these helpers near the existing UI helpers:

```python
def _render_step_header(ui, number: int, title: str, status: str) -> None:
    ui.markdown(f"#### {number}. {title}")
    if status:
        ui.caption(status)


def _render_locked_step(ui, number: int, title: str, message: str) -> None:
    _render_step_header(ui, number, title, "Locked")
    ui.caption(message)


def _is_context_loaded(session_state: dict[str, Any], *, api_base_url: str, project_id: str, workspace_id: str) -> bool:
    loaded_source = session_state.get("projection_context_source")
    if not loaded_source:
        return False
    return loaded_source == build_projection_context_source(
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )
```

- [ ] **Step 2: Restructure top-level render flow**

In `render_asset_prompt_plan_projection_preview`, change the order after context inputs:

```python
    context_loaded = _is_context_loaded(
        ui.session_state,
        api_base_url=api_base_url,
        project_id=project_id,
        workspace_id=workspace_id,
    )

    if not context_loaded:
        _render_locked_step(ui, 2, "AssetBible", "Load context before selecting AssetBible.")
        _render_locked_step(ui, 3, "SceneCast", "Load context before selecting SceneCast.")
        _render_locked_step(ui, 4, "Storyboard Frame", "Load context before choosing a storyboard frame.")
        _render_locked_step(
            ui,
            5,
            "Preview",
            "Preview is locked until context, AssetBible, SceneCast, storyboard, and frame are ready.",
        )
        return None
```

Move `render_asset_bible_draft_setup(...)`, AssetBible selector, SceneCast selector, Storyboard Frame, and Preview blocks after this context-loaded gate.

- [ ] **Step 3: Add visible Context header**

Render `1. Context` before the context controls:

```python
    _render_step_header(ui, 1, "Context", "Load project/workspace context before selecting Stage2 assets.")
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_guides_user_through_selection_steps tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_does_not_show_frame_inputs_before_context_is_loaded tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_does_not_render_style_or_path_inputs
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

Run:

```powershell
git add web/components/asset_prompt_plan_projection.py tests/test_asset_prompt_plan_projection_ui.py
git commit -m "feat: 引导阶段二投影预览选择流程" -m "- 增加 Context 到 Preview 的步骤提示" -m "- 在上下文加载前锁定下游选择" -m "- 保持默认流程不暴露样式或路径字段"
git push origin dev
```

## Task 3: Add Derived Frame Status And Request Validation

**Files:**

- Modify: `web/components/asset_prompt_plan_projection.py`
- Modify: `tests/test_asset_prompt_plan_projection_ui.py`

- [ ] **Step 1: Add failing test for derived frame status**

Append:

```python
def test_render_projection_preview_shows_derived_frame_status_from_scene_cast():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_1",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_1",
                    "frame_id": "frame_001",
                }
            ],
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
        }
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "Storyboard/frame derived from selected SceneCast" in rendered
    assert "storyboard_1 / frame_001" in rendered
```

- [ ] **Step 2: Add failing test for mismatched derived frame blocking**

Append:

```python
def test_render_projection_preview_blocks_mismatched_scene_cast_frame_before_http(monkeypatch):
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_1",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_1",
                    "frame_id": "frame_001",
                }
            ],
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_other",
            "projection_frame_id": "frame_999",
            "projection_preview_submit": True,
        }
    )

    def fail_preview(**_kwargs):
        raise AssertionError("preview API must not be called for mismatched derived frame")

    monkeypatch.setattr(
        asset_prompt_plan_projection,
        "preview_prompt_plan_projection",
        fail_preview,
    )

    result = asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert result is None
    assert any("Storyboard/frame no longer matches selected SceneCast" in item for item in fake_ui.errors)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_shows_derived_frame_status_from_scene_cast tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_blocks_mismatched_scene_cast_frame_before_http
```

Expected: FAIL because derived frame status and pre-request mismatch validation are not implemented.

- [ ] **Step 4: Add helper functions**

Add:

```python
def _frame_status_for_scene_cast(
    scene_cast: dict[str, Any],
    *,
    storyboard_plan_id: str,
    frame_id: str,
) -> tuple[str, bool]:
    expected_storyboard = _safe_text(scene_cast.get("storyboard_plan_id"))
    expected_frame = _safe_text(scene_cast.get("frame_id"))
    current_storyboard = storyboard_plan_id.strip()
    current_frame = frame_id.strip()
    if expected_storyboard and expected_frame:
        if current_storyboard == expected_storyboard and current_frame == expected_frame:
            return (
                f"Storyboard/frame derived from selected SceneCast: {current_storyboard} / {current_frame}",
                True,
            )
        return ("Storyboard/frame no longer matches selected SceneCast.", False)
    if current_storyboard and current_frame:
        return ("Storyboard/frame manually completed because SceneCast did not provide both values.", True)
    return ("Storyboard/frame is required before preview.", False)
```

```python
def _validate_projection_flow(
    *,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
    scene_cast: dict[str, Any],
) -> str | None:
    missing = [
        label
        for label, value in (
            ("project_id", project_id),
            ("workspace_id", workspace_id),
            ("asset_bible_id", asset_bible_id),
            ("scene_cast_id", scene_cast_id),
            ("storyboard_plan_id", storyboard_plan_id),
            ("frame_id", frame_id),
        )
        if not value.strip()
    ]
    if missing:
        return f"缺少必填字段: {', '.join(missing)}"
    _message, is_valid = _frame_status_for_scene_cast(
        scene_cast,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    if not is_valid:
        return "Storyboard/frame no longer matches selected SceneCast."
    return None
```

- [ ] **Step 5: Render Storyboard Frame status and use validation before preview**

In the Storyboard Frame step:

```python
    selected_scene_cast = _find_item(scene_casts, "scene_cast_id", scene_cast_id)
    frame_status, frame_ready = _frame_status_for_scene_cast(
        selected_scene_cast,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
    _render_step_header(
        ui,
        4,
        "Storyboard Frame",
        frame_status,
    )
```

Before calling `preview_prompt_plan_projection`, replace the inline missing-field check with:

```python
    validation_error = _validate_projection_flow(
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
        scene_cast=selected_scene_cast,
    )
    if validation_error:
        ui.error(validation_error)
        return None
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_shows_derived_frame_status_from_scene_cast tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_blocks_mismatched_scene_cast_frame_before_http tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_loads_asset_and_scene_cast_choices
```

Expected: PASS.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add web/components/asset_prompt_plan_projection.py tests/test_asset_prompt_plan_projection_ui.py
git commit -m "feat: 校验阶段二投影预览帧选择" -m "- 显示 SceneCast 派生的 storyboard/frame 状态" -m "- 在请求前阻断错配的帧选择" -m "- 保持预览请求契约不变"
git push origin dev
```

## Task 4: Add Request Summary And Preserve Preview-Only Boundaries

**Files:**

- Modify: `web/components/asset_prompt_plan_projection.py`
- Modify: `tests/test_asset_prompt_plan_projection_ui.py`

- [ ] **Step 1: Add failing request summary test**

Append:

```python
def test_render_projection_preview_shows_current_request_summary_before_submit():
    from web.components import asset_prompt_plan_projection

    fake_ui = _ProjectionFakeUI()
    fake_ui.session_state.update(
        {
            "api_base_url": "http://localhost:8000/api",
            "projection_project_id": "project_1",
            "projection_workspace_id": "ws_1",
            "projection_context_source": {
                "api_base_url": "http://localhost:8000/api",
                "project_id": "project_1",
                "workspace_id": "ws_1",
            },
            "projection_asset_bibles": [{"asset_bible_id": "bible_1"}],
            "projection_asset_bible_id": "bible_1",
            "projection_scene_cast_asset_bible_id": "bible_1",
            "projection_scene_casts": [
                {
                    "scene_cast_id": "cast_1",
                    "asset_bible_id": "bible_1",
                    "storyboard_plan_id": "storyboard_1",
                    "frame_id": "frame_001",
                }
            ],
            "projection_scene_cast_id": "cast_1",
            "projection_storyboard_plan_id": "storyboard_1",
            "projection_frame_id": "frame_001",
        }
    )

    asset_prompt_plan_projection.render_asset_prompt_plan_projection_preview(
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    rendered = "\n".join(
        [item["message"] for item in fake_ui.markdowns]
        + fake_ui.captions
    )
    assert "Current request summary" in rendered
    assert "project_1 / ws_1" in rendered
    assert "bible_1" in rendered
    assert "cast_1" in rendered
    assert "storyboard_1 / frame_001" in rendered
```

- [ ] **Step 2: Add summary renderer**

Add:

```python
def _render_request_summary(
    ui,
    *,
    project_id: str,
    workspace_id: str,
    asset_bible_id: str,
    scene_cast_id: str,
    storyboard_plan_id: str,
    frame_id: str,
) -> None:
    ui.markdown("##### Current request summary")
    ui.markdown(f"- Context: {project_id.strip()} / {workspace_id.strip()}")
    ui.markdown(f"- AssetBible: {asset_bible_id.strip()}")
    ui.markdown(f"- SceneCast: {scene_cast_id.strip()}")
    ui.markdown(f"- Storyboard Frame: {storyboard_plan_id.strip()} / {frame_id.strip()}")
    ui.caption("Preview-only: no PromptPlan save, no stale marking, no image/video generation.")
```

- [ ] **Step 3: Render summary in Preview step**

Before the preview button:

```python
    _render_step_header(ui, 5, "Preview", "Review the request before sending preview.")
    _render_request_summary(
        ui,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_bible_id=asset_bible_id,
        scene_cast_id=scene_cast_id,
        storyboard_plan_id=storyboard_plan_id,
        frame_id=frame_id,
    )
```

- [ ] **Step 4: Run focused safety tests**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_shows_current_request_summary_before_submit tests/test_asset_prompt_plan_projection_ui.py::test_build_projection_request_payload_only_includes_endpoint_fields tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_result_uses_projection_lab_sections tests/test_asset_prompt_plan_projection_ui.py::test_render_projection_preview_does_not_render_style_or_path_inputs
```

Expected: PASS.

- [ ] **Step 5: Commit and push**

Run:

```powershell
git add web/components/asset_prompt_plan_projection.py tests/test_asset_prompt_plan_projection_ui.py
git commit -m "feat: 展示阶段二投影预览请求摘要" -m "- 在提交预览前展示当前选择摘要" -m "- 强化 preview-only 文案但不新增持久化行为"
git push origin dev
```

## Task 5: Final Verification And Integration Acceptance

**Files:**

- Verify: `web/components/asset_prompt_plan_projection.py`
- Verify: `web/components/asset_bible_draft_setup.py`
- Verify: `tests/test_asset_prompt_plan_projection_ui.py`
- Verify: `tests/test_stage2_projection_pipeline_ui.py`

- [ ] **Step 1: Run focused UI tests**

Run:

```powershell
python -m pytest -q tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py
```

Expected: all pass.

- [ ] **Step 2: Run cross-stage projection and boundary tests**

Run:

```powershell
python -m pytest -q tests/test_asset_bible_api.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py tests/test_prompt_composer_asset_projection.py tests/test_stale_write_integration.py
```

Expected: all pass.

- [ ] **Step 3: Run lint and diff checks**

Run:

```powershell
python -m ruff check web/components/asset_prompt_plan_projection.py web/components/asset_bible_draft_setup.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Run delivery loop integration acceptance**

Run:

```powershell
$runOutput = powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -RunIntegrationAcceptance
$runOutput
```

Expected: output contains `status: needs_review` and a report under `_runtime/integration_acceptance/`.

- [ ] **Step 5: Perform two review gates**

Review the report and this feature against:

- Stage2 projection preview remains preview-only.
- No title/subtitle/text-style/path/provider fields entered the projection request.
- No stale write or generation path was introduced.
- The default UI path now follows Context -> AssetBible -> SceneCast -> Storyboard Frame -> Preview.
- Failures are traceable to focused commands or UI tests.

If both gates pass:

```powershell
$report = (
    $runOutput |
    Select-String '^report: ' |
    Select-Object -Last 1
).Line -replace '^report:\s*', ''
if (-not $report) {
    throw "Delivery loop runner did not print a report path."
}
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -ReportPath $report -MarkReviewGate 1 -ReviewResult passed
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -ReportPath $report -MarkReviewGate 2 -ReviewResult passed
```

- [ ] **Step 6: Confirm next cycle gate**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -StartFeatureDelivery
```

Expected: `status: feature_delivery_ready`.

Do not start the next feature until this integration acceptance loop passes.
