# Pixelle HyperFrames Rendering Architecture Design

> **Status:** Partially superseded by
> [2026-04-22-pixelle-hyperframes-compiled-project-design.md](/d:/demo1/Pixelle/Pixelle/docs/superpowers/specs/2026-04-22-pixelle-hyperframes-compiled-project-design.md).
> This document still explains the HyperFrames-first direction, but its runtime-manifest assembly model is no longer the preferred implementation target.

## Goal

Make HyperFrames the single final rendering engine for Pixelle so that images, audio, subtitles, and template layout all run on one deterministic timeline.

This design should:

- stop treating final video assembly as a `segment.mp4 + concat` problem
- preserve Pixelle as the system of record for script, storyboard, TTS, and media generation
- migrate Pixelle HTML templates into HyperFrames-compatible compositions instead of replacing them with a different design system
- support subtitle changes inside a single storyboard frame and subtitle groups that can span multiple frames
- keep future access to HyperFrames `agent`, `capture`, `tts`, and `transcribe` capabilities without making them mandatory for the first rollout

## Non-Goals

This design does not include:

- replacing ComfyUI-based media generation
- replacing Pixelle's script generation or storyboard planning logic
- migrating every template in a single implementation pass
- making HyperFrames `transcribe` the primary caption source for normal Pixelle tasks
- introducing cloud-only dependencies or mandatory LLM APIs for rendering

## Current Problem

Pixelle currently produces final videos through a frame-local pipeline:

`tts -> media -> compose html frame -> segment.mp4 -> concat`

This creates three separate timing domains:

1. TTS audio timing
2. frame image / segment timing
3. subtitle display timing

The current subtitle implementation is especially limiting:

- subtitle text is rendered directly into `composed.png`
- one frame shows one static subtitle for the whole frame duration
- subtitles do not have an independent timeline
- a frame cannot naturally display multiple subtitle groups over time
- a subtitle cannot naturally span across frame boundaries

This is the root cause of the current quality ceiling:

- if image timing drifts, picture switches early or late
- if subtitle timing needs to change inside a frame, the current pipeline cannot express it
- even when segment durations are improved, subtitles remain structurally tied to the wrong abstraction

## Best-Practice Direction

The long-term correct architecture is:

`Pixelle produces assets and timing data -> HyperFrames renders the final video`

In this model:

- Pixelle is the asset and metadata producer
- HyperFrames is the only final composition and render runtime
- existing HTML templates become HyperFrames compositions
- subtitles become first-class timeline elements instead of burned-in frame text

This is preferable to extending Pixelle's current FFmpeg-only assembly path because HyperFrames already provides:

- one shared HTML-native timeline using `data-start`, `data-duration`, and `data-track-index`
- independent caption compositions
- deterministic local rendering
- preview and final render workflows
- future optional `transcribe`, `tts`, `capture`, and agent tooling

## Architecture Summary

Pixelle will continue to generate:

- title and content metadata
- storyboard frames
- per-frame narration text
- per-frame TTS audio
- per-frame image or video media

Pixelle will stop owning final visual assembly.

Instead, Pixelle will export a render package that HyperFrames consumes. HyperFrames will then render:

- template shell
- timed visual clips
- master narration audio
- timed subtitle composition
- final MP4 output

## Core Principles

### 1. Audio Is the Master Clock

Final visual timing must derive from narration audio timing.

Rules:

- every visual clip start/end is computed from cumulative narration timing
- subtitle timing is expressed on the same global clock
- the final render uses one global timeline, not per-frame segment concatenation

### 2. Script and Sentence Boundaries Must Be Preserved

Best practice is not `audio only`.

Pixelle must preserve and pass through:

- frame narration text
- sentence boundaries inside narration text
- frame order
- frame durations

This matters because:

- known text plus audio is more reliable than ASR-only reconstruction
- future forced alignment depends on having the original text
- subtitle styling, grouping, and override logic is easier when text remains structured

### 3. Audio-Only Subtitle Generation Is a Fallback, Not the Main Path

If a task truly has audio only, HyperFrames can still generate timestamps through `transcribe`.

But the normal architecture should prefer:

1. Pixelle-provided text + timing metadata
2. Pixelle-provided text + future forced alignment
3. HyperFrames `transcribe` only when text is absent

### 4. Block TTS Plus Forced Alignment Is the Default Timing Strategy

For Pixelle-generated content, the default timing strategy should be:

1. preserve the original sentence split
2. synthesize audio in block-sized TTS requests instead of sentence-by-sentence requests
3. align the resulting block audio back to the known text
4. aggregate aligned word or character timings into sentence-level subtitle cues

This gives better TTS throughput than sentence-by-sentence synthesis while still producing sentence-level timing that can drive:

- image clip boundaries
- subtitle cue boundaries
- future word-level emphasis

### 5. Silence Trimming Is Optional and Must Preserve Time Remapping Metadata

When long synthetic pauses harm pacing, Pixelle may run an optional silence-trimming stage after block TTS.

This stage must:

- preserve the original untrimmed master narration audio
- write a machine-readable edit timeline
- remap sentence and subtitle timings onto the trimmed timeline before export

Silence trimming is a pacing optimization, not a substitute for alignment.

## Caption Source Policy

Caption timing must follow this priority order:

### Primary Source: Pixelle Narration + Forced Alignment

When Pixelle has known narration text and generated audio, it should use forced alignment to recover timing.

Recommended default engine:

- `Qwen3-ForcedAligner-0.6B`

This gives word-level or character-level timings without guessing text from audio, and those fine-grained timings can then be aggregated into sentence-level subtitle cues.

### Bootstrap Fallback: Pixelle Narration + Direct Duration Metadata

If forced alignment is temporarily unavailable, Pixelle may still build coarse phrase-level cues from its own narration and duration metadata.

This path is acceptable as a bootstrap or compatibility mode, but it is not the preferred best-practice timing source for normal Pixelle-generated tasks.

### Fallback Source: FunASR / FunClip Transcribe

When only audio exists, Pixelle should use a dedicated transcription fallback instead of reusing the normal forced-alignment path.

Recommended fallback stack:

- `FunASR` for speech recognition and timestamp recovery
- `FunClip` when a ready-made `SRT` export path is useful

Fallback responsibilities:

- recover text when Pixelle narration text is missing
- recover phrase-level or sentence-level timing when only audio or video is available
- optionally export `SRT` as an interoperability artifact

Important limitation:

- this fallback is not the preferred path for Pixelle-generated tasks with known narration text
- `ASS` remains a Pixelle-side export responsibility if required later

Important design rule:

- this is a compatibility path
- it must not become the main path for normal Pixelle-generated tasks
- it must not replace `Qwen3-ForcedAligner-0.6B` as the default timing engine for `text + audio`

## Render Package Contract

Pixelle should export a normalized render package per task.

Recommended shape:

### `render_manifest.json`

Contains task-level render metadata:

- `task_id`
- `title`
- `width`
- `height`
- `fps`
- `template_id`
- `template_variant`
- `master_audio_path`
- `duration`

### `frames[]`

Each frame entry contains:

- `index`
- `narration`
- `audio_path`
- `duration`
- `media_type`
- `media_path`
- `template_params`

### `visual_clips[]`

Global-timeline clip records:

- `id`
- `frame_index`
- `start`
- `end`
- `duration`
- `track_index`
- `media_path`
- `media_type`

### `caption_cues[]`

Independent subtitle time records:

- `id`
- `text`
- `start`
- `end`
- `frame_indices`
- `style_profile`
- optional `word_timings`

This model is intentionally independent of `segment.mp4`.

## HyperFrames Integration Topology

For a Python-first repository, best practice is not to shell out to `npx hyperframes render` as the core integration contract.

Instead, Pixelle should introduce a small Node bridge that wraps `@hyperframes/producer`.

Rationale:

- `@hyperframes/producer` exposes a stable programmatic render API
- it can later run as a render server
- preview, lint, and render can share one Node-side integration layer
- Pixelle keeps a clean Python/Node boundary instead of scattering CLI shell calls through the pipeline

Recommended topology:

1. Python generates the render package and composition assets
2. Python calls an internal Node bridge
3. The Node bridge uses `@hyperframes/producer` to render the final MP4

The Node bridge may support two modes:

- one-shot local render invoked by Python
- optional long-lived render server for future preview and throughput improvements

## Template Migration Strategy

Pixelle templates should be migrated, not discarded.

Each existing HTML template should be split into two conceptual layers:

### Template Shell

The shell preserves:

- page size
- background design
- image/video frame placement
- title block
- author / branding area
- decorative CSS

The shell must stop rendering the main body subtitle text directly.

### Caption Composition

The caption composition owns:

- timed subtitle groups
- within-frame subtitle changes
- cross-frame subtitle spans
- word-level or phrase-level emphasis

This composition uses the same visual language as the shell's original subtitle region:

- same font family
- same font size scale
- same safe area
- same alignment and spacing principles

The key difference is that it is timeline-driven instead of frame-static.

## Template Compatibility Assessment

Image-based Pixelle templates are a good fit for HyperFrames because they are already HTML/CSS based.

The first migration target should be:

- `templates/1080x1920/image_life_insights_light.html`

Why this template:

- high production relevance
- clear title / media / bottom text layout
- simple enough to become the migration reference implementation

Migration rule:

- `{{text}}` is removed from the shell composition
- the bottom text visual zone becomes the reference style profile for the caption composition

After the reference template is proven:

- other `image_*` templates can migrate through the same shell + caption split
- `video_*` templates can migrate in a later phase

## Target Render Flow

The target final render flow becomes:

1. Pixelle generates storyboard, media, and preserved sentence boundaries
2. Pixelle synthesizes narration audio in block-sized TTS requests
3. Pixelle aligns block audio back to text and optionally trims long silence with remapping metadata
4. Pixelle computes the global narration timeline
5. Pixelle exports a HyperFrames render package
6. Pixelle writes or updates HyperFrames composition files for the selected template
7. HyperFrames renders the final MP4 from the render package

This replaces:

- frame-local composed subtitle images
- per-frame subtitle burn-in
- segment-first final assembly as the dominant render strategy

## Subtitle Behavior Requirements

The new system must support all of the following:

1. Multiple subtitle groups inside one storyboard frame
2. One subtitle group spanning multiple storyboard frames
3. Phrase-level cue timing in the first release
4. Future word-level timing without redesigning the architecture
5. Template-specific subtitle styling

These requirements are exactly why subtitles must become independent timeline entities.

## Migration Phases

### Phase 1: Foundation

Build the integration base:

- render package schema
- Python export step
- Node bridge using `@hyperframes/producer`
- one migrated HyperFrames template shell
- one caption composition

Deliverable:

- one production-capable reference template rendered fully through HyperFrames

### Phase 2: Template Family Expansion

Generalize the migration pattern:

- shared template adapter abstractions
- style profiles for caption regions
- support for multiple `image_*` templates

Deliverable:

- a reusable adapter pattern for portrait image templates

### Phase 3: Better Subtitle Timing

Upgrade caption timing quality:

- default forced alignment when narration text is present
- optional silence trimming with timing remap metadata
- optional `FunASR` / `FunClip` transcription fallback when narration text is missing
- richer grouping and emphasis logic

Deliverable:

- phrase-level timing by default
- word-level timing where available

### Phase 4: Optional Capability Reuse

Add optional HyperFrames ecosystem features without changing the core render contract:

- `capture`
- `agent`-assisted composition generation
- `tts`
- `transcribe`

Deliverable:

- additional inputs and authoring paths, still feeding the same render package model

## Why Not Keep the Old Final Assembly Path

Keeping Pixelle's current final assembly path as the main render strategy would preserve the wrong boundary:

- visuals remain frame-bound
- subtitles remain second-class
- timing corrections stay patch-based

That may solve tactical issues but not the architecture problem.

Best practice requires changing the final rendering model, not only refining segment timing.

## Risks

Main risks:

1. Template migration will expose differences between browser CSS rendering in Pixelle templates and HyperFrames composition structure
2. Introducing a Python-to-Node bridge adds deployment and environment coordination work
3. The first template migration may reveal assumptions in Pixelle templates that are too tightly coupled to burned-in frame text
4. Audio-only fallback transcription may be less accurate than preserved-script timing, so the system must not silently downgrade normal tasks to audio-only behavior
5. `FunASR` / `FunClip` fallback introduces a second subtitle source, so the system must keep a strict policy boundary between `primary = forced alignment` and `fallback = transcription`

## Testing Strategy

Testing should cover four layers:

### 1. Manifest Export Tests

Validate that Pixelle correctly exports:

- frame durations
- cumulative visual clip timings
- caption cue timings
- master audio references

### 2. Template Adapter Tests

Validate that migrated template shells:

- preserve expected width and height
- position the media slot correctly
- expose the correct caption safe zone

### 3. Render Integration Tests

Validate that the Node bridge can:

- lint compositions
- preview compositions
- render MP4 output from a Pixelle-generated package

### 4. Output Acceptance Tests

For the reference template, verify:

- picture changes happen on the expected timeline
- subtitle groups can switch inside a frame
- one subtitle group can span multiple frames
- subtitle style visually matches the original template closely enough for approval

## Recommendation

Adopt a HyperFrames-first target architecture:

- Pixelle remains the script, asset, and timing-data producer
- HyperFrames becomes the only final rendering engine
- subtitles become independent timeline compositions
- existing Pixelle HTML templates are migrated into HyperFrames shell + caption compositions

Primary rule for subtitle data:

- preserve Pixelle narration text and durations as first-class render inputs
- use `Qwen3-ForcedAligner-0.6B` as the default timing engine for `text + audio`
- use `FunASR` / `FunClip` audio-only transcription only as a fallback, not as the normal contract

This is the strongest long-term architecture for solving Pixelle's current synchronization problems while keeping room for future reuse of HyperFrames `agent`, `capture`, `tts`, and `transcribe` features.
