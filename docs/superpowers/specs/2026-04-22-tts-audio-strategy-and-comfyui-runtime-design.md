# TTS Audio Strategy And ComfyUI Runtime Design

## Goal

Make TTS audio organization configurable independently from `render_backend`, while preserving the user's expected defaults:

- `legacy + local` stays per-frame.
- `legacy + comfyui` switches to master-track generation.
- `hyperframes_compiled` keeps using master-track generation.

In parallel, move the ComfyUI Desktop runtime base from `C:\Users\ai\Documents\ComfyUI` to `E:\comfyui-venv` so the runtime files, Python environment, and future DeepSpeed experiments are isolated from the Pixelle project venv.

## Current Context

- `StoryboardConfig.render_backend` and `render.timing.*` are already propagated from config/UI into the standard pipeline.
- `StandardPipeline` always builds `ctx.timing_plan` before asset production.
- Legacy asset production assumes each frame has its own `audio_path` and `duration`.
- HyperFrames already synthesizes block audio plus `master_audio.wav` and aligns sentence timings against those blocks.
- ComfyUI Desktop currently launches from `E:\comfyui\resources\ComfyUI\main.py`, but its runtime base and `.venv` still live under `C:\Users\ai\Documents\ComfyUI`.

## Requirements

### Functional

1. Add a new render-timing field, `tts_audio_strategy`, with supported values:
   - `auto`
   - `per_frame`
   - `master_track`
2. Keep the default at `auto`.
3. Resolve `auto` as:
   - `legacy + local` => `per_frame`
   - `legacy + comfyui` => `master_track`
   - `hyperframes_compiled` => `master_track`
4. When legacy resolves to `master_track`, synthesize narration as a master track first, then derive frame-level audio clips so the existing legacy segment compositor can continue working unchanged.
5. Expose the new option through persisted config, `StoryboardConfig`, and the Web UI request path.

### Operational

1. Add a repeatable migration script and documentation for moving ComfyUI Desktop's runtime base to `E:\comfyui-venv`.
2. Prefer a standalone runtime layout that does not reuse the Pixelle project venv.
3. Keep the current `E:\comfyui\comfyui\models` model location intact.
4. Only remove the old `C:\Users\ai\Documents\ComfyUI\.venv` after the new runtime path has been validated successfully.

## Design

### Audio Strategy Model

Add a dedicated audio-strategy enum-like helper module instead of overloading `render_backend` semantics further. The new helper will validate values and provide shared constants for config, pipeline logic, and UI helpers.

The request/config field name will be `tts_audio_strategy`, stored alongside the other render timing options.

### Legacy Master-Track Flow

Legacy rendering still needs per-frame audio clips because:

- image segments derive duration from audio,
- video segments merge narration audio during per-frame composition,
- post-production concatenates frame-level segments.

To preserve that contract, master-track mode in legacy will:

1. reuse the existing `ctx.timing_plan`,
2. synthesize block audio and `master_audio.wav`,
3. align sentence timings back onto the master timeline,
4. group sentence windows by frame,
5. extract one frame audio clip per frame from the master audio,
6. set `frame.audio_path` and `frame.duration`,
7. let the existing staged/serial/parallel legacy flow continue and naturally skip per-frame TTS.

This keeps media generation, composition, and concatenation behavior stable while reducing TTS call count for ComfyUI-backed legacy tasks.

### Alignment Strategy For Legacy Master Track

Legacy master-track mode should prefer the configured alignment engine, but it must not become more fragile than current legacy rendering. Therefore:

- `direct_duration` will use proportional duration alignment immediately.
- `qwen_forced_aligner` will be attempted first.
- If forced alignment fails at runtime, legacy master-track mode will log a warning and fall back to duration alignment instead of aborting the whole job.

HyperFrames behavior remains unchanged.

### UI And Metadata

The Web UI gets a dedicated selector for `tts_audio_strategy`, defaulting from runtime config. Requests built from the UI will forward that field just like `render_backend`.

Storyboard persistence will round-trip the new field so saved tasks remain inspectable and reproducible.

### ComfyUI Runtime Migration

Use `E:\comfyui-venv` as the new ComfyUI Desktop `basePath`.

Runtime responsibilities after migration:

- `E:\comfyui` stays the application/resources/models host.
- `E:\comfyui-venv` becomes the runtime base for:
  - `.venv`
  - `input`
  - `output`
  - `user`
  - logs/cache created by Desktop runtime

The migration script will:

1. create the target directory structure,
2. update ComfyUI Desktop `config.json` `basePath`,
3. validate the configured paths,
4. leave model paths untouched,
5. avoid deleting the old runtime automatically until validation passes.

If no standalone Python 3.11 is installed, the script/doc will call that out explicitly instead of pretending the DeepSpeed-ready runtime is complete.

## Risks And Mitigations

- Existing dirty changes in `standard.py` and tests:
  mitigate by reading diffs first and editing only the required lines.
- Master-track audio extraction accuracy:
  mitigate by preferring real alignment and falling back only when necessary.
- Deleting the old ComfyUI venv too early:
  mitigate by making deletion the final verified step only after the new base path is in place and tests pass.

## Validation

1. Add failing tests for config/UI propagation and legacy master-track selection.
2. Verify the new tests fail for the expected missing-behavior reason.
3. Implement the feature minimally.
4. Re-run focused tests plus broader regression tests around render config and standard pipeline behavior.
5. Validate the new ComfyUI runtime directory and Desktop config.
6. Remove `C:\Users\ai\Documents\ComfyUI\.venv` only after successful verification.
