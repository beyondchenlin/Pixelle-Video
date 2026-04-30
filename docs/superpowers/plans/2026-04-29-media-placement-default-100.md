# Media Placement Default 100 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the platform-wide default media placement scale from `80` to `100` so every request path that omits an explicit scale uses full contain-fit canvas coverage by default.

**Architecture:** Treat the default scale as a shared contract owned by `MediaPlacement`, then propagate that contract through API schemas, Streamlit session defaults, request builders, and user-facing copy. Preserve explicit user-provided scales such as `80`; only the implicit default changes.

**Tech Stack:** Python, Pydantic, Streamlit, pytest, i18n JSON locale files

---

### Task 1: Lock the new contract in regression tests

**Files:**
- Modify: `tests/test_media_placement.py`
- Modify: `tests/test_video_api.py`
- Modify: `tests/test_storyboard_size_contract.py`
- Modify: `tests/test_template_render_context.py`
- Modify: `tests/test_style_config_template_gallery.py`
- Modify: `tests/test_output_preview.py`

- [ ] **Step 1: Write the failing tests**

Update the existing default-value assertions from `80` to `100` in each test file so they describe the intended contract before any production code changes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_template_render_context.py tests/test_style_config_template_gallery.py tests/test_output_preview.py -q`

Expected: FAIL on assertions that still observe the old default `80`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_template_render_context.py tests/test_style_config_template_gallery.py tests/test_output_preview.py
git commit -m "test: lock media placement default at 100"
```

### Task 2: Update the shared contract and downstream defaults

**Files:**
- Modify: `pixelle_video/models/media_placement.py`
- Modify: `api/schemas/video.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`

- [ ] **Step 1: Write the minimal implementation**

Change the shared `MediaPlacement.scale_percent` default to `100`, align `MediaPlacementRequest.scale_percent` with the same default, and rewrite the help copy so it explains the meaning of `100%` and lower values without treating `80%` as the recommended baseline.

- [ ] **Step 2: Run the focused tests to verify they pass**

Run: `pytest tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_template_render_context.py -q`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add pixelle_video/models/media_placement.py api/schemas/video.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "fix: update shared media placement default to 100"
```

### Task 3: Verify UI and request-building propagation

**Files:**
- Modify: `web/components/style_config.py` if tests show session fallback still hard-codes `80`
- Modify: `web/components/output_preview.py` if tests show request fallback still bypasses the shared model default
- Test: `tests/test_style_config_template_gallery.py`
- Test: `tests/test_output_preview.py`

- [ ] **Step 1: Run the UI/request tests after the shared contract change**

Run: `pytest tests/test_style_config_template_gallery.py tests/test_output_preview.py -q`

Expected: PASS if those code paths already derive defaults from `MediaPlacement()`. FAIL only if there is a residual hard-coded `80`.

- [ ] **Step 2: If needed, write the minimal code fix**

Remove any remaining hard-coded `80` fallback and replace it with `MediaPlacement().scale_percent` or `MediaPlacement().to_dict()` so the default remains centralized.

- [ ] **Step 3: Re-run the UI/request tests**

Run: `pytest tests/test_style_config_template_gallery.py tests/test_output_preview.py -q`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add web/components/style_config.py web/components/output_preview.py tests/test_style_config_template_gallery.py tests/test_output_preview.py
git commit -m "fix: propagate media placement default through UI fallbacks"
```

### Task 4: Final verification

**Files:**
- Review: `git diff -- pixelle_video/models/media_placement.py api/schemas/video.py web/components/style_config.py web/components/output_preview.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_template_render_context.py tests/test_style_config_template_gallery.py tests/test_output_preview.py`

- [ ] **Step 1: Run the complete targeted regression suite**

Run: `pytest tests/test_media_placement.py tests/test_video_api.py tests/test_storyboard_size_contract.py tests/test_template_render_context.py tests/test_style_config_template_gallery.py tests/test_output_preview.py -q`

Expected: PASS

- [ ] **Step 2: Review the diff for accidental scope creep**

Confirm only the default contract, user-facing copy, and related tests changed.

- [ ] **Step 3: Report the behavior change**

Document that implicit defaults now resolve to `100`, while explicit values like `80` remain supported and unchanged.
