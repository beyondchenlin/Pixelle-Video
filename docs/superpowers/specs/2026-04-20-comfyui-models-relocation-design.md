# ComfyUI Models Relocation Design

## Goal

Move the full ComfyUI `models` directory from `C:\Users\ai\Documents\ComfyUI\models` to `E:\comfyui\confyui\models` to free space on `C:`, while keeping the existing ComfyUI desktop setup working without changing its runtime behavior.

## Approved Approach

Use filesystem redirection instead of changing ComfyUI's effective model path logic:

1. Stop ComfyUI for a safe migration window.
2. Move the full `models` directory to `E:\comfyui\confyui\models`.
3. Create an NTFS directory junction at `C:\Users\ai\Documents\ComfyUI\models` that points to `E:\comfyui\confyui\models`.
4. Leave `C:\Users\ai\AppData\Roaming\ComfyUI\extra_models_config.yaml` unchanged.

## Why This Approach

- Lowest-risk option for the existing desktop ComfyUI setup.
- Existing workflows, loaders, and download behavior continue to use the original path.
- Future writes to the original `models` path will land on `E:` through the junction.
- Easier rollback than changing multiple ComfyUI configuration paths.

## Current Environment

- ComfyUI desktop app executable: `E:\comfyui\ComfyUI.exe`
- Current ComfyUI base path: `C:\Users\ai\Documents\ComfyUI`
- Current extra models config: `C:\Users\ai\AppData\Roaming\ComfyUI\extra_models_config.yaml`
- Target relocated path: `E:\comfyui\confyui\models`

## Verification Requirements

- Confirm `E:\comfyui\confyui\models` exists after migration.
- Confirm `C:\Users\ai\Documents\ComfyUI\models` is a junction.
- Confirm required FLUX model files are reachable through the original `C:` path.
- Confirm ComfyUI can be restarted with the migrated model path layout.

## Rollback

1. Stop ComfyUI.
2. Remove the junction at `C:\Users\ai\Documents\ComfyUI\models`.
3. Move `E:\comfyui\confyui\models` back to `C:\Users\ai\Documents\ComfyUI\models`.
