# AGENTS.md

## Model Download Preference

- For AI model files, ComfyUI model assets, and other large downloadable artifacts, prefer `ModelScope` as the default source.
- If the same artifact exists on both `ModelScope` and another source such as Hugging Face, use `ModelScope` first.
- Only fall back to other sources when the required file is missing from `ModelScope` or `ModelScope` is unavailable.

## Download Behavior

- When downloading models for ComfyUI, place files into the correct target subdirectory based on the workflow and loader type.
- If multiple required files are independent, parallel download is allowed and preferred when bandwidth and disk space permit.
- Before starting large downloads, check available disk space and confirm the target directory.
- After each download, verify that the file exists and has a reasonable size before reporting success.

## Current Repo Context

- This repository uses local ComfyUI workflows and may require downloading model files such as `diffusion_models`, `text_encoders`, and `vae` assets.
- In this repo, future model download tasks should default to `ModelScope` first.
