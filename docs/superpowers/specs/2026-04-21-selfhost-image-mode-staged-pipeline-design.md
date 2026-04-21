# Selfhost Image Mode Staged Pipeline Design

## Goal

Reduce repeated GPU model switching in image-generation mode when both TTS and image generation use selfhost ComfyUI workflows on the same local backend.

The new behavior should:

- keep the current `standard` pipeline as the single entry point
- switch automatically without adding a user-facing toggle
- apply only to image-generation mode, not video-generation mode
- preserve the existing storyboard/frame data model
- abort immediately on the first failed staged asset generation

## Non-Goals

This rollout does not include:

- changes to video workflow generation order
- a new standalone pipeline
- special handling for RunningHub workflows
- partial-success output when some frames fail
- resumable generation in the same task

## Current Problem

In the current `standard` pipeline, non-RunningHub tasks are processed frame by frame:

`frame 1: tts -> media -> compose -> segment`

`frame 2: tts -> media -> compose -> segment`

When both TTS and image generation run through selfhost ComfyUI, this causes repeated switching between TTS models and image models across frames.

The practical risks are:

- repeated model load/unload overhead
- more GPU memory fragmentation
- higher chance of OOM during longer tasks
- slower end-to-end runtime despite serial execution

## Trigger Conditions

The staged mode activates only when all of the following are true:

1. The selected template type is `image`
2. TTS inference mode is `comfyui`
3. The resolved TTS workflow key starts with `selfhost/`
4. The resolved media workflow key starts with `selfhost/`

If any condition is not met, the pipeline keeps the existing frame-by-frame behavior.

Resolution rule:

- trigger detection must resolve the effective workflow key, not rely only on raw `config.tts_workflow` / `config.media_workflow`
- this ensures configured default selfhost workflows still activate staged mode even when the request did not explicitly pass workflow keys

Important exclusions:

- `video` templates keep the current dependency order because video duration may depend on TTS duration
- `static` templates do not need media generation and should keep current lightweight behavior
- RunningHub workflows keep the current logic and concurrency behavior

## Design Summary

Within `StandardPipeline.produce_assets()`, add an automatic staged branch for the trigger conditions above.

The staged execution order becomes:

1. Generate audio for all frames
2. Generate images for all frames
3. Compose frames and create video segments for all frames
4. Concatenate all segments into the final video

The data model remains frame-based:

- each `StoryboardFrame` still stores its own `audio_path`
- each `StoryboardFrame` still stores its own `image_path`
- each `StoryboardFrame` still stores its own `video_segment_path`

What changes is execution order, not result shape.

## Execution Flow

### Phase 1: Audio Stage

Iterate over all storyboard frames in order and call the current audio-generation logic for each frame.

Rules:

- reuse the existing `_step_generate_audio()` logic
- write audio output into the same per-frame task paths as today
- update `frame.audio_path` and `frame.duration`
- stop the whole task immediately if any frame fails

### Phase 2: Image Stage

After all audio generation succeeds, iterate over all storyboard frames again and call the current media-generation logic for each frame.

Rules:

- only enter this stage for image templates
- reuse the existing `_step_generate_media()` logic
- keep output paths unchanged
- stop the whole task immediately if any frame fails

### Phase 3: Composition Stage

After all images succeed, iterate over all storyboard frames and run:

1. `_step_compose_frame()`
2. `_step_create_video_segment()`

Rules:

- preserve current HTML template rendering behavior
- preserve current FFmpeg segment creation behavior
- update `storyboard.total_duration` from frame durations as today
- stop the whole task immediately if any frame fails

### Phase 4: Final Concatenation

No change to post-production logic is required.

The final output still comes from the existing `concat_videos()` flow and optional BGM handling.

## Progress Model

The current UI assumes frame-local progress such as:

`frame X/Y - step 1/4`

That model does not accurately describe staged execution, so the progress callback needs a small translation layer.

Recommended staged progress events:

- audio stage: `frame_step`, `step=1`, `action="audio"`
- image stage: `frame_step`, `step=2`, `action="media"`
- compose stage: `frame_step`, `step=3`, `action="compose"`
- segment stage: `frame_step`, `step=4`, `action="video"`

Meaning:

- the UI text format can stay unchanged
- but the backend will emit these events while iterating across all frames in the current stage
- users will see the current stage advancing across frame numbers instead of one frame completing all four steps before the next begins

This keeps the frontend change minimal while making the displayed progress match the new execution model.

## Failure Handling

Failure policy is strict fail-fast.

Rules:

- any failure in audio stage aborts the whole task immediately
- any failure in image stage aborts the whole task immediately
- any failure in composition or segment creation aborts the whole task immediately
- no partial video should be returned

Rationale:

- keeps output semantics clear
- avoids silently skipping storyboard frames
- simplifies debugging of ComfyUI workflow and GPU-memory issues

## Implementation Boundaries

Primary change area:

- `pixelle_video/pipelines/standard.py`

Reuse without behavior changes where possible:

- `pixelle_video/services/frame_processor.py`
- `pixelle_video/services/video.py`
- existing storyboard models
- existing persistence and post-production flow

Expected implementation shape:

- extract a small helper to determine whether staged mode should activate
- add a staged branch inside `produce_assets()`
- keep the existing serial and RunningHub branches intact for non-trigger cases
- use the same workflow-resolution rules as the service layer when determining selfhost vs runninghub

## Testing Strategy

Add focused tests for:

1. Trigger detection
2. Staged execution order for image-mode selfhost ComfyUI tasks
3. Fallback to existing frame-by-frame logic for non-trigger cases
4. Immediate abort on staged audio failure
5. Immediate abort on staged image failure
6. Correct final frame state population after staged success

Important regression checks:

- video template tasks still use current flow
- local Edge-TTS plus selfhost image does not activate staged mode
- RunningHub tasks still use current behavior

## Risks

Main risks:

1. Progress percentages may look uneven if stage weights are not mapped carefully
2. Future changes to `FrameProcessor` step semantics may drift from staged progress mapping
3. Trigger detection must use resolved workflow keys, not only raw user params, to avoid misclassification

## Recommendation

Implement the staged branch only for the narrow selfhost image-mode case above.

This delivers the intended GPU-memory stability improvement with the smallest possible surface-area change, while preserving the current architecture and keeping future rollback simple.
