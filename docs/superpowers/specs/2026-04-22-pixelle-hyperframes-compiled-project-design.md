# Pixelle HyperFrames Compiled Project Design

## Goal

Make Pixelle generate a fully renderable HyperFrames project package so that HyperFrames can render final video without runtime guessing, manifest-driven DOM assembly, or Pixelle-specific render patches.

This design is a correction to the earlier HyperFrames V1 approach. The new target is:

`Pixelle assets + timing + template data -> compiled HyperFrames project -> HyperFrames render`

## Why This Change Is Needed

The current HyperFrames integration still leaves too much critical render logic to runtime JavaScript inside template files:

- media and audio sources are mounted at runtime from `render_manifest.json`
- composition duration is partially static in HTML and partially corrected in JS
- final canvas size and source media size are mixed together in one manifest contract
- render success is inferred from process completion instead of validated from output streams

This creates avoidable failure modes:

- local Windows paths can fail to load as browser media sources
- a template can render with the wrong duration if static and runtime timing disagree
- picture placement can break when media size is mistaken for final canvas size
- HyperFrames can return a file even when audio is missing or visual clips failed to mount

These are not isolated bugs. They are signs that the integration boundary is wrong.

## Review-Driven Root Causes

Two review rounds against the current codebase exposed four root-cause classes that this design must eliminate, not merely patch:

1. **Static duration wins over runtime correction**
   - if template HTML ships with `data-duration="8"`, HyperFrames may honor that static value before Pixelle runtime JS updates it
   - consequence: finished videos can be silently truncated even when manifest and audio duration are correct

2. **Canvas contract and media contract are mixed**
   - current manifest shape allows source media dimensions such as `768x768` to leak into final composition sizing
   - consequence: wrong aspect ratio, misplaced media slots, and shell layouts rendered on the wrong coordinate system

3. **Absolute local paths leak into browser media loading**
   - current runtime assembly can inject Windows file paths directly into `img.src` or `audio.src`
   - consequence: broken image placeholders, missing audio, and non-portable projects

4. **Render completion is not the same as render correctness**
   - current bridge can treat a produced file as success even when it has no audio stream or the wrong duration
   - consequence: silent failure slips through as a "successful" render

This compiled-project design is the source-level answer to those review findings.

## Best-Practice Direction

Pixelle should not teach HyperFrames how to assemble Pixelle data at runtime.

Instead, Pixelle should behave like a compiler that emits a normal HyperFrames project with:

- stable project-local assets
- static composition HTML with resolved timing attributes
- static composition HTML with resolved media sources
- static captions composition input
- explicit final canvas dimensions
- explicit final duration

HyperFrames should then do what it is best at:

- load a standard project directory
- compile the HTML compositions
- render the final MP4

The key principle is:

**HyperFrames is the render engine, not the Pixelle-specific data assembler.**

## Architecture Summary

### Before

`Pixelle -> render_manifest.json -> template JS fetches manifest -> runtime mounts images/audio -> HyperFrames render`

### After

`Pixelle -> compile project-local assets + static compositions -> HyperFrames render`

In the corrected design:

- Pixelle owns asset planning, timing, and project compilation
- HyperFrames owns composition parsing and media rendering
- template HTML becomes static, deterministic render input
- `render_manifest.json` becomes a debug and audit artifact, not the primary runtime contract

## Core Principles

### 1. Pixelle Compiles, HyperFrames Renders

Pixelle must resolve all task-specific render decisions before calling HyperFrames:

- which assets are used
- where those assets live
- which clip starts and ends when
- what the canvas size is
- what the final composition duration is

HyperFrames should receive a project that is already valid and renderable.

### 2. Runtime JavaScript Must Not Own Critical Render Contract

Template runtime JS may still animate or style content, but it must not be responsible for:

- discovering audio and visual clips from a Pixelle manifest
- deciding the composition's canonical duration
- fixing missing media paths
- correcting canvas size after the page loads

Those values must be compiled into the project before render starts.

Corollary:

- runtime JS may animate already-mounted elements
- runtime JS may not be the first place that creates `<img>`, `<video>`, or `<audio>` elements that the render engine depends on
- runtime JS may not be the source of truth for root composition duration

### 3. All Rendered Assets Must Be Project-Local

Compiled HyperFrames projects must not depend on absolute Windows paths such as:

- `D:\...`
- `C:\...`

Instead, Pixelle should copy or materialize needed assets under the task-local HyperFrames project, then reference them through project-relative paths.

Examples:

- `assets/images/01_image.png`
- `assets/audio/master_audio.wav`
- `assets/video/03_video.mp4`

This avoids browser path ambiguity and makes the project portable, debuggable, and reproducible.

### 4. Canvas Size and Media Size Must Be Separate Concepts

The render contract must distinguish:

- `canvas_width` / `canvas_height`
  - final output resolution, for example `1080x1920`
- `media_width` / `media_height`
  - source image or generated media resolution, for example `768x768`

HyperFrames compositions should always be driven by canvas size. Media size affects generation quality, not composition layout coordinates.

### 5. Render Success Requires Output Validation

A finished process is not enough to declare success.

After HyperFrames render completes, Pixelle must validate the final artifact:

- output file exists
- output contains a video stream
- output contains an audio stream when master audio exists
- output duration is within tolerance of the compiled master audio duration
- output resolution matches the compiled canvas size

This is part of the render contract, not optional diagnostics.

### 6. Static Composition Markup Must Be Internally Consistent

Compiled HTML must already agree with itself before HyperFrames starts:

- root `data-duration`
- child composition `data-duration`
- audio `data-duration`
- clip `data-start` / `data-duration`
- canvas `data-width` / `data-height`

The compiler must not rely on "we will fix it in JS after page load."

### 7. Canonical Timeline Must Be Explicit

Compiled projects must define one canonical render timeline.

Rules:

- if silence trimming or any other remap step is applied, compiled HTML and captions must use remapped timing
- if no remap step is applied, compiled HTML and captions must use source timing
- shell visuals, captions, and master audio must all be compiled against the same chosen timeline
- no compiled artifact may mix `source_*` times for one layer and `remapped_*` times for another

Operationally:

- `source_start` / `source_end` remain the pre-remap audit record
- `remapped_start` / `remapped_end` become the render-time values when present
- compiled HTML should never force HyperFrames to infer which timeline is authoritative

## Compiled Project Contract

Each task should compile to a project-local HyperFrames directory:

`output/<task_id>/hyperframes/`

Recommended structure:

```text
output/<task_id>/hyperframes/
  index.html
  compositions/
    captions.html
  assets/
    audio/
      master_audio.wav
    images/
      01_image.png
      02_image.png
    video/
  data/
    render_manifest.json
    captions.json
```

### Template Render Context

Pixelle should compile each task against a normalized template input contract rather than passing ad-hoc fields per template.

Recommended structure:

```text
TemplateRenderContext
  template_id
  canvas_width
  canvas_height
  duration
  fps
  title
  author
  theme
  template_params
  visuals[]
  captions[]
  audio
```

Minimum rules:

- `TemplateRenderContext` is the only source of task-specific shell data used to compile `index.html`
- migrated templates must consume this normalized contract instead of introducing template-specific runtime fetches
- `template_params` may extend styling or decoration, but must not redefine timing, canvas size, or asset path ownership
- all template migrations should map their shell needs into this contract before adding new one-off fields

### What Is Runtime-Critical

These must be final before render starts:

- `index.html`
- `compositions/captions.html`
- project-local assets in `assets/`

Additionally:

- root composition duration must already be final in static HTML
- shell composition dimensions must already be final in static HTML
- audio and visual sources must already point to project-local paths in static HTML
- runtime-critical compositions must not depend on `render_manifest.json` fetch to become renderable
- runtime-critical compositions must not depend on public network fonts, public CDN scripts, or any other remote runtime asset

### What Is Diagnostic

These remain useful, but are not the main runtime contract:

- `data/render_manifest.json`
- `data/captions.json`

They exist for inspection, debugging, acceptance tests, and reproducibility.

## Template Strategy

Pixelle should continue to preserve its existing template system, but migrate templates into HyperFrames-compatible structure.

### Existing Template Source

Current source templates remain under:

- `templates/`

These are the visual source of truth for layout language and styling.

### HyperFrames Template Target

Migrated HyperFrames templates live under:

- `resources/hyperframes/templates/<template_id>/`

Each migrated template should be split into:

- `index.html`
  - shell layout
  - title
  - decorative background
  - media slot
  - footer
- `compositions/captions.html`
  - independent caption layer
  - timeline-aware cue rendering

### Important Rule

The old `{{text}}` style of static subtitle rendering must not remain embedded as the main subtitle strategy in the shell template.

Subtitle timing must be expressed through the captions composition, not by baking narration text into the shell.

## Directory Ownership

To support long-term upgrades without mixing concerns, the repository should separate four responsibilities.

### 1. Upstream HyperFrames Source Snapshot

Recommended directory:

- `vendor/hyperframes/` or `third_party/hyperframes/`

Purpose:

- keep a reference snapshot of upstream HyperFrames source
- support upgrade comparisons
- avoid mixing Pixelle business logic into upstream files

Rule:

- treat this directory as vendor code
- do not place Pixelle template or bridge logic here
- this snapshot is a reference for upgrade review, not the runtime authority

### 2. Pixelle Node Integration Layer

Directory:

- `tools/hyperframes_bridge/`

Purpose:

- wrap `@hyperframes/producer`
- provide Pixelle-specific render invocation
- host Node-side validation or orchestration glue

This is Pixelle-owned integration code.

Runtime authority:

- `@hyperframes/producer` is the runtime source of truth
- if `vendor/hyperframes/` or `third_party/hyperframes/` is present, it exists for source comparison and upgrade analysis only
- Pixelle must not silently mix behavior from a vendor snapshot into bridge runtime without an explicit dependency/version change

### 3. Pixelle HyperFrames Template Resources

Directory:

- `resources/hyperframes/templates/`

Purpose:

- store migrated template shells and caption compositions
- preserve Pixelle design language in HyperFrames form

This is template asset code, not upstream HyperFrames code.

### 4. Pixelle Project Compiler and Services

Directories:

- `pixelle_video/services/hyperframes_*`
- `pixelle_video/models/render_package.py`

Purpose:

- plan timing
- materialize assets
- compile project structure
- validate render output

This is the Pixelle compiler side of the boundary.

## Recommended Compilation Flow

### Step 1: Produce Source Assets

Pixelle continues to generate:

- script and storyboard
- image or video media
- master audio
- sentence timing

Caption timing policy:

- primary = `qwen_forced_aligner` for known text plus generated audio
- fallback = `funasr_transcribe` only for audio-only or missing-text inputs
- compiled projects must never silently downgrade a normal `text + audio` task from forced alignment to transcription

### Step 2: Materialize Project-Local Assets

Pixelle materializes the exact render inputs into:

- `hyperframes/assets/audio/`
- `hyperframes/assets/images/`
- `hyperframes/assets/video/`

Compiled compositions should only reference these local assets.

Default policy:

- default strategy is copy
- link or symlink optimization is optional and must be explicitly enabled
- copy-first avoids cross-volume, permission, and Windows path edge cases leaking back into render behavior

### Step 3: Compile Static `index.html`

Pixelle writes a task-specific `index.html` with:

- final `data-width`
- final `data-height`
- final root `data-duration`
- final media elements and their `data-start` / `data-duration`
- final audio element and its `data-duration`

This HTML should not need runtime manifest fetch to become renderable.

Required constraint:

- the compiler must not emit placeholder durations such as `8` with the expectation that runtime JS will replace them later

### Step 4: Compile Static `captions.html`

Pixelle writes a task-specific captions composition with:

- cue data embedded or loaded from a project-local static data file
- final `data-duration`
- no dependency on Pixelle-specific runtime patching
- render-time cue boundaries resolved against the canonical timeline rule above

If a project-local static data file is used:

- it must live inside the compiled project directory
- it must be optional from HyperFrames' point of view, not a substitute for unresolved timing
- the captions composition must remain renderable without remote data access

### Step 5: Keep Manifest for Audit

Pixelle still writes `render_manifest.json`, but only as:

- debug metadata
- inspection artifact
- acceptance-test input

### Step 6: Render and Validate

HyperFrames renders the compiled project.

Pixelle then validates the final output with `ffprobe` or equivalent checks.

Minimum acceptance gates:

- final file contains at least one video stream
- final file contains an audio stream when `master_audio.wav` exists
- final duration is within tolerance of compiled master audio duration
- final width and height match compiled canvas size
- sample frames do not show missing-media placeholders

## Why This Is Better Than the Current V1 Approach

This architecture removes the three main classes of fragility we observed:

### Asset Path Fragility

Current V1 can fail if browser-side media loading receives Windows file paths.

Compiled project-local relative assets eliminate this ambiguity.

### Duration Drift

Current V1 can disagree between:

- static HTML duration
- runtime JS duration
- manifest duration

Compiled compositions reduce duration to one source of truth.

### Layout Coordinate Drift

Current V1 can confuse source media dimensions with final canvas size.

Compiled compositions make canvas geometry explicit and stable.

## Non-Goals

This design does not require:

- changing HyperFrames core engine behavior
- forking `@hyperframes/producer`
- replacing Pixelle script/storyboard/TTS/media generation
- migrating every template in one pass

It is specifically designed to avoid unnecessary changes to upstream HyperFrames.

## Risks

Main risks:

1. Compiled HTML generation is more opinionated than runtime mounting, so template migration needs stronger tests.
2. Asset materialization may increase disk usage because inputs are copied into project-local `assets/`.
3. Some existing templates may rely on assumptions that only worked when text was burned into precomposed frames.
4. A partial migration period will require clear compatibility rules between legacy runtime-driven templates and compiled-project templates.

## Testing Strategy

### 1. Compiler Tests

Validate that Pixelle compilation produces:

- project-local assets
- static `index.html`
- static `captions.html`
- correct relative asset paths
- correct root duration

### 2. Template Contract Tests

Validate that compiled templates have:

- one root composition
- explicit `data-width`, `data-height`, `data-duration`
- no runtime requirement to discover critical assets
- no placeholder duration values that differ from compiled duration
- only project-local asset references in critical media elements
- no public network dependencies in runtime-critical shell or captions paths
- template fields are sourced from `TemplateRenderContext` rather than ad-hoc runtime globals

### 3. Render Validation Tests

After render:

- assert output has audio when expected
- assert output duration matches master audio within tolerance
- assert output resolution matches canvas size
- assert output is not truncated to a template placeholder duration
- assert rendered sample frames do not show broken-image fallback states

### 4. Acceptance Tests

For each migrated template:

- first frame shows expected shell and media
- middle frame shows expected media progression
- subtitles switch on schedule
- no missing-media placeholders appear

## Recommendation

Adopt the corrected architecture:

- Pixelle becomes a HyperFrames project compiler
- HyperFrames remains the render engine
- existing Pixelle templates are migrated into HyperFrames shell + captions compositions
- upstream HyperFrames remains minimally touched
- the repository keeps a clean separation between vendor code, bridge code, template resources, and compiler logic

This is the strongest source-level solution because it fixes the boundary that caused missing audio, wrong aspect behavior, and broken media mounting instead of patching each symptom individually.
