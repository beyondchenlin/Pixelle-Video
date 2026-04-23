# TTS Audio Strategy And ComfyUI Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple TTS audio organization from `render_backend`, make legacy ComfyUI default to master-track generation, and migrate ComfyUI Desktop runtime to `E:\comfyui-venv`.

**Architecture:** Add a dedicated `tts_audio_strategy` config field and resolve it inside `StandardPipeline`. In legacy master-track mode, synthesize master audio first, derive frame clips from that track, then reuse the existing legacy media/compose/segment flow unchanged. Runtime migration is handled by a PowerShell helper plus docs, and only after validation do we remove the old ComfyUI venv.

**Tech Stack:** Python dataclasses, Pydantic config schema, Streamlit UI, pytest, PowerShell, ComfyUI Desktop config.

---

### Task 1: Persist The New Audio Strategy Field

**Files:**
- Create: `pixelle_video/tts_audio_strategy.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/pipelines/storyboard_config.py`
- Modify: `pixelle_video/services/persistence.py`
- Modify: `config.yaml` (local runtime config, ignored by Git)
- Test: `tests/test_render_package_models.py`

- [ ] **Step 1: Write the failing tests**

Add tests that expect:

- `StoryboardConfig(...).tts_audio_strategy == "auto"`
- persistence round-trip preserves `tts_audio_strategy`
- YAML round-trip preserves `render.timing.tts_audio_strategy`
- `resolve_storyboard_render_kwargs()` resolves the new field

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_render_package_models.py -q`

Expected: failure mentioning missing `tts_audio_strategy` behavior or missing resolved field.

- [ ] **Step 3: Write the minimal implementation**

Add shared constants/validation for:

```python
TTSAudioStrategy = Literal["auto", "per_frame", "master_track"]
```

Wire that field through runtime config, storyboard config, request resolution, persistence, and local `config.yaml` (while keeping the change out of Git-tracked files).

- [ ] **Step 4: Re-run the focused tests**

Run: `pytest tests/test_render_package_models.py -q`

Expected: pass.

### Task 2: Add Legacy Master-Track Resolution And Preparation

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_staged_mode.py`

- [ ] **Step 1: Write the failing tests**

Add tests that expect:

- `legacy + comfyui + auto` calls a master-track preparation helper instead of per-frame audio generation
- `legacy + comfyui + per_frame` still uses the existing per-frame audio loop
- resolution helper maps `auto` to the expected effective strategy

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -q`

Expected: failure because legacy comfyui still calls `_step_generate_audio` per frame.

- [ ] **Step 3: Write the minimal implementation**

Inside `StandardPipeline`:

- resolve effective `tts_audio_strategy`
- for legacy `master_track`, synthesize master audio first
- align sentence timings
- extract per-frame clips from the master audio
- let existing legacy flows skip audio because `frame.audio_path` is already present

- [ ] **Step 4: Re-run the focused tests**

Run: `pytest tests/test_standard_pipeline_staged_mode.py -q`

Expected: pass.

### Task 3: Expose The Field Through The Web UI

**Files:**
- Create: `web/utils/tts_audio_strategy_ui.py`
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Test: `tests/test_render_backend_ui.py`

- [ ] **Step 1: Write the failing tests**

Add tests that expect:

- selector default comes from runtime config
- request builders forward `tts_audio_strategy`

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_render_backend_ui.py tests/test_output_preview.py -q`

Expected: failure because the field is not forwarded/rendered yet.

- [ ] **Step 3: Write the minimal implementation**

Add a selector near render backend controls and copy the selected value into single-run and batch requests.

- [ ] **Step 4: Re-run the focused tests**

Run: `pytest tests/test_render_backend_ui.py tests/test_output_preview.py -q`

Expected: pass.

### Task 4: Add ComfyUI Runtime Migration Docs And Helper Script

**Files:**
- Modify: `workflows/down/索引语音二代_依赖与下载说明.md`
- Create: `scripts/migrate_comfyui_runtime_to_e_drive.ps1`

- [ ] **Step 1: Write the migration helper**

The script should:

- target `E:\comfyui-venv`
- inspect current ComfyUI Desktop config
- update `basePath`
- create required runtime directories
- print validation guidance

- [ ] **Step 2: Document the runtime layout and DeepSpeed prerequisites**

Update the Chinese workflow dependency doc with:

- current path split
- new runtime target
- standalone Python requirement
- DeepSpeed prerequisites and verification commands

- [ ] **Step 3: Validate the script syntax**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_comfyui_runtime_to_e_drive.ps1 -WhatIf`

Expected: no PowerShell parse errors.

### Task 5: Full Verification And Cleanup

**Files:**
- Modify only if fixes are needed after verification.

- [ ] **Step 1: Run focused regression coverage**

Run:

```bash
pytest tests/test_render_package_models.py tests/test_standard_pipeline_staged_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_render_backend_ui.py tests/test_output_preview.py -q
```

Expected: all pass.

- [ ] **Step 2: Validate ComfyUI Desktop runtime config**

Check:

- `C:\Users\ai\AppData\Roaming\ComfyUI\config.json`
- target directory `E:\comfyui-venv`

- [ ] **Step 3: Remove the old ComfyUI venv only after validation**

Run:

```powershell
Remove-Item -LiteralPath 'C:\Users\ai\Documents\ComfyUI\.venv' -Recurse -Force
```

Expected: old runtime venv removed only after the new runtime path is confirmed.

- [ ] **Step 4: Commit and push atomic changes**

Commit only the files for this feature/runtime migration unit with a concrete message, then push unless an external blocker prevents it.
