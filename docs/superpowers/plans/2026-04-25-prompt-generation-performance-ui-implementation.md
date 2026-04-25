# Prompt Generation Performance UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository instructions forbid `git worktree`; execute in the current workspace and stage only the files owned by each task.

**Goal:** Add request-scoped prompt generation performance controls to the quick-create UI and propagate them consistently through Web, API, standard/custom pipelines, and prompt generation.

**Architecture:** Keep global LLM settings as defaults. Add a small Web helper that owns UI rendering and shared parameter names, and only emits override fields when the user enables custom performance. API schemas expose the same optional fields, and pipeline calls forward them to the existing prompt batch runner without changing runner semantics.

**Tech Stack:** Streamlit Web UI, Pydantic API schemas, pytest, existing Pixelle pipeline utilities.

---

### Task 1: Web UI Contract

**Files:**
- Create: `web/components/prompt_generation_performance.py`
- Modify: `web/components/content_input.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: `tests/test_prompt_generation_performance_ui.py`
- Test: `tests/test_output_preview.py`

- [ ] **Step 1: Write failing tests**

Add tests that prove:

```python
from web.components.prompt_generation_performance import (
    LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM,
    LLM_PROMPT_BATCH_SIZE_PARAM,
    copy_prompt_generation_performance_params,
)


def test_copy_prompt_generation_performance_params_omits_absent_values():
    target = {"mode": "generate"}
    copy_prompt_generation_performance_params({}, target)
    assert LLM_PROMPT_BATCH_SIZE_PARAM not in target
    assert LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM not in target


def test_copy_prompt_generation_performance_params_copies_enabled_values():
    target = {}
    copy_prompt_generation_performance_params(
        {
            LLM_PROMPT_BATCH_SIZE_PARAM: 8,
            LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM: 3,
        },
        target,
    )
    assert target[LLM_PROMPT_BATCH_SIZE_PARAM] == 8
    assert target[LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM] == 3
```

Also add request/shared-config tests in `tests/test_output_preview.py` proving enabled values are included and absent values are omitted.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
pytest tests/test_prompt_generation_performance_ui.py tests/test_output_preview.py -q
```

Expected: fail because the new helper and mapping behavior do not exist yet.

- [ ] **Step 3: Implement UI helper and request mapping**

Create `web/components/prompt_generation_performance.py` with constants, `copy_prompt_generation_performance_params()`, and `render_prompt_generation_performance_controls()`.

Render `提示词生成性能` from `render_content_input()` after the scene-count control in both single and batch modes. Do not use a gear icon. Add the returned override fields to `video_params` only when enabled.

Call `copy_prompt_generation_performance_params()` from `build_single_generation_request()` and `build_batch_shared_config()`.

- [ ] **Step 4: Verify Web tests pass**

Run:

```bash
pytest tests/test_prompt_generation_performance_ui.py tests/test_output_preview.py -q
```

Expected: pass.

### Task 2: Pipeline and API Propagation

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `api/schemas/content.py`
- Modify: `api/routers/content.py`
- Test: `tests/test_standard_pipeline_prompt_prefix.py`
- Test: `tests/test_custom_pipeline_styled_batch.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_content_image_prompt_api.py`

- [ ] **Step 1: Write failing propagation tests**

Add tests proving:

```python
assert captured["batch_size"] == 8
assert captured["max_concurrency"] == 3
```

for both `StandardPipeline.plan_visuals()` and the custom pipeline styled prompt path.

Add API tests proving `VideoGenerateRequest` and `ImagePromptGenerateRequest` accept `llm_prompt_batch_size` and `llm_prompt_batch_concurrent_limit`, and routers forward them only when present.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py tests/test_content_image_prompt_api.py -q
```

Expected: fail because pipeline/API forwarding is missing.

- [ ] **Step 3: Implement propagation**

Forward `ctx.params.get("llm_prompt_batch_size")` as `batch_size` and `ctx.params.get("llm_prompt_batch_concurrent_limit")` as `max_concurrency` in `StandardPipeline`.

Forward matching kwargs in `CustomPipeline`.

Add optional Pydantic schema fields with ranges `1-50` and `1-10`. Copy them into API generation params only when not `None`.

- [ ] **Step 4: Verify propagation tests pass**

Run:

```bash
pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py tests/test_content_image_prompt_api.py -q
```

Expected: pass.

### Task 3: Final Verification

**Files:**
- All files from Tasks 1-2.

- [ ] **Step 1: Run focused lint**

```bash
python -m ruff check web/components/prompt_generation_performance.py web/components/content_input.py web/components/output_preview.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py api/schemas/video.py api/routers/video.py api/schemas/content.py api/routers/content.py tests/test_prompt_generation_performance_ui.py tests/test_output_preview.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py tests/test_content_image_prompt_api.py
```

Expected: no lint errors.

- [ ] **Step 2: Run focused tests**

```bash
pytest tests/test_prompt_generation_performance_ui.py tests/test_output_preview.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py tests/test_content_image_prompt_api.py -q
```

Expected: pass.

- [ ] **Step 3: Run full test suite**

```bash
pytest -q
```

Expected: pass.

- [ ] **Step 4: Commit and push**

Stage only files changed for this feature. Commit with:

```bash
git commit -m "feat: add prompt performance controls"
git push
```
