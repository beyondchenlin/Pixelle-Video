# IPProfile Workbench Upsert Save Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent IP Design Workbench saves from dropping sibling `ip_profiles` and make editing resolve profiles by `ip_profile_id`.

**Architecture:** Add a reusable AssetBible draft projection helper in the web API utility layer, then make the IP Design Workbench upsert the currently edited profile into that projected draft payload. The UI may remain a single-profile editing surface, but persistence must preserve all unedited profiles and all non-IP asset collections.

**Tech Stack:** Python, Streamlit component helpers, pytest, existing AssetBible App API draft schema.

---

### Task 1: AssetBible Draft Projection Helper

**Files:**
- Modify: `web/utils/asset_bible_api.py`
- Test: `tests/test_asset_bible_payload_projection.py`

- [ ] **Step 1: Write failing projection tests**

Create `tests/test_asset_bible_payload_projection.py` with tests for:
- converting an AssetBible API response into a draft-save payload without response-only fields
- replacing an existing `ip_profile_id`
- appending a new `ip_profile_id`
- preserving sibling `ip_profiles` and asset collections

- [ ] **Step 2: Run RED**

Run:

```powershell
$env:PYTHONPATH='D:\demo1\Pixelle\Pixelle\.worktrees\ipprofile-save-upsert'; pytest tests/test_asset_bible_payload_projection.py -v
```

Expected: FAIL because the projection/upsert helpers do not exist.

- [ ] **Step 3: Implement projection helpers**

Add public helpers in `web/utils/asset_bible_api.py`:
- `build_asset_bible_draft_payload_from_response(asset_bible)`
- `upsert_ip_profile_draft(asset_bible_payload, ip_profile)`

The helper must whitelist draft fields and use existing `build_asset_bible_payload(..., require_ids=False)` validation.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
$env:PYTHONPATH='D:\demo1\Pixelle\Pixelle\.worktrees\ipprofile-save-upsert'; pytest tests/test_asset_bible_payload_projection.py -v
```

Expected: PASS.

### Task 2: Workbench Read/Save By IP Profile ID

**Files:**
- Modify: `web/components/ip_design_workbench.py`
- Test: `tests/test_ip_design_workbench_ui.py`

- [ ] **Step 1: Write failing UI tests**

Add tests proving:
- saving one profile keeps sibling `ip_profiles`
- the form reads the profile matching `ip_design_ip_profile_id` instead of always reading the first profile

- [ ] **Step 2: Run RED**

Run:

```powershell
$env:PYTHONPATH='D:\demo1\Pixelle\Pixelle\.worktrees\ipprofile-save-upsert'; pytest tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_preserves_sibling_ip_profiles_when_saving tests/test_ip_design_workbench_ui.py::test_ip_design_workbench_reads_profile_matching_session_ip_profile_id -v
```

Expected: FAIL under current `_first_dict(...)` and single-profile save behavior.

- [ ] **Step 3: Update Workbench**

Change `web/components/ip_design_workbench.py` so it:
- resolves the active profile by current/session `ip_profile_id`
- builds current profile draft from form fields
- projects the selected AssetBible to a draft payload
- upserts current profile by `ip_profile_id`

- [ ] **Step 4: Run GREEN**

Run:

```powershell
$env:PYTHONPATH='D:\demo1\Pixelle\Pixelle\.worktrees\ipprofile-save-upsert'; pytest tests/test_ip_design_workbench_ui.py -v
```

Expected: PASS.

### Task 3: Verification And Commit

**Files:**
- Modified files from Tasks 1-2

- [ ] **Step 1: Run focused verification**

Run:

```powershell
$env:PYTHONPATH='D:\demo1\Pixelle\Pixelle\.worktrees\ipprofile-save-upsert'; pytest tests/test_asset_bible_payload_projection.py tests/test_ip_design_workbench_ui.py tests/test_asset_prompt_plan_projection_ui.py tests/test_ip_design_client.py -v
```

Expected: PASS.

- [ ] **Step 2: Run git diff review**

Run:

```powershell
git diff -- web/utils/asset_bible_api.py web/components/ip_design_workbench.py tests/test_asset_bible_payload_projection.py tests/test_ip_design_workbench_ui.py
```

Expected: only projection/upsert and workbench read/save changes.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/superpowers/plans/2026-05-04-ipprofile-workbench-upsert-save-implementation.md web/utils/asset_bible_api.py web/components/ip_design_workbench.py tests/test_asset_bible_payload_projection.py tests/test_ip_design_workbench_ui.py
git commit -m "fix: 修复IP工作台保存覆盖其他形象"
```

Expected: one atomic commit.
