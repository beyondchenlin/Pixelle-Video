# ComfyUI Models Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the full ComfyUI `models` directory to `E:\comfyui\comfyui\models` and preserve the original path via an NTFS junction.

**Architecture:** Keep ComfyUI's configured base path unchanged and redirect only the `models` directory at the filesystem layer. This minimizes application-level changes while shifting model storage to `E:`.

**Tech Stack:** Windows PowerShell, NTFS junctions, local ComfyUI desktop app

---

### Task 1: Record Current State

**Files:**
- Modify: `docs/superpowers/specs/2026-04-20-comfyui-models-relocation-design.md`
- Modify: `docs/superpowers/plans/2026-04-20-comfyui-models-relocation.md`

- [ ] **Step 1: Confirm current model directory and target path**

Run: `Test-Path 'C:\Users\ai\Documents\ComfyUI\models'; Test-Path 'E:\comfyui\comfyui'`
Expected: both paths exist before migration starts.

- [ ] **Step 2: Confirm ComfyUI desktop is using the expected base path**

Run: `Get-Content 'C:\Users\ai\AppData\Roaming\ComfyUI\extra_models_config.yaml'`
Expected: `base_path: C:\Users\ai\Documents\ComfyUI`

### Task 2: Safe Migration Window

**Files:**
- Modify: `C:\Users\ai\Documents\ComfyUI\models` (filesystem move)
- Create: `E:\comfyui\comfyui\models`

- [ ] **Step 1: Stop ComfyUI**

Run: `Get-Process ComfyUI,python -ErrorAction SilentlyContinue`
Expected: identify desktop and backend processes, then stop the ComfyUI-related ones.

- [ ] **Step 2: Move the full models directory**

Run: `Move-Item -LiteralPath 'C:\Users\ai\Documents\ComfyUI\models' -Destination 'E:\comfyui\comfyui\models'`
Expected: `models` now exists at `E:\comfyui\comfyui\models`

### Task 3: Preserve Original Path

**Files:**
- Create: `C:\Users\ai\Documents\ComfyUI\models` (junction)

- [ ] **Step 1: Create the junction**

Run: `cmd /c mklink /J "C:\Users\ai\Documents\ComfyUI\models" "E:\comfyui\comfyui\models"`
Expected: Windows reports `Junction created`

- [ ] **Step 2: Verify the junction**

Run: `Get-Item 'C:\Users\ai\Documents\ComfyUI\models' | Format-List FullName,LinkType,Target,Attributes`
Expected: `LinkType` shows `Junction` and target points to `E:\comfyui\comfyui\models`

### Task 4: Post-Migration Verification

**Files:**
- Verify: `C:\Users\ai\Documents\ComfyUI\models\diffusion_models\flux1-dev.safetensors`
- Verify: `C:\Users\ai\Documents\ComfyUI\models\text_encoders\clip_l.safetensors`
- Verify: `C:\Users\ai\Documents\ComfyUI\models\text_encoders\t5xxl_fp8_e4m3fn.safetensors`
- Verify: `C:\Users\ai\Documents\ComfyUI\models\vae\ae.safetensors`

- [ ] **Step 1: Verify key model files through the original path**

Run: a PowerShell check over the known FLUX files.
Expected: all files still resolve through the original `C:` path.

- [ ] **Step 2: Restart ComfyUI if needed**

Run: launch `E:\comfyui\ComfyUI.exe`
Expected: ComfyUI starts successfully and continues to use the original model path transparently.
