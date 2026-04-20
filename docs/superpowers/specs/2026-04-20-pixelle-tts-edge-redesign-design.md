# Pixelle TTS Edge Redesign

## Context

`workflows/selfhost/tts_edge.json` currently depends on third-party ComfyUI custom nodes:

- `ComfyUI-EdgeTTS` for speech generation
- `ComfyUI-Easy-Use` for simple pass-through helper nodes

The observed failure mode is severe: the workflow can appear to succeed and produce an MP3 file, but the file is silent. Root-cause investigation showed that the third-party `EdgeTTS` node may swallow runtime failures during audio decode and return an all-zero waveform instead of failing loudly. This makes the workflow operationally unsafe because downstream nodes cannot distinguish success from silent failure.

Pixelle already contains a more robust local Edge TTS implementation in `pixelle_video/utils/tts_util.py` and `pixelle_video/services/tts_service.py`, including retry behavior and explicit failures. The current architecture duplicates responsibility across two unrelated implementations:

- Pixelle application runtime owns one TTS implementation
- ComfyUI workflow runtime depends on a different third-party implementation

This split is the source of drift, debugging cost, and inconsistent behavior.

## Goal

Make `workflows/selfhost/tts_edge.json` reliable and maintainable by replacing third-party ComfyUI TTS dependencies with a Pixelle-owned ComfyUI plugin, while keeping Pixelle's application-side TTS implementation as the authoritative behavior reference.

## Non-Goals

- Do not modify ComfyUI core.
- Do not introduce a worktree-based workflow.
- Do not redesign Index TTS in this change.
- Do not remove Pixelle's existing local TTS service in this change.

## Requirements

### Functional Requirements

1. `tts_edge.json` must produce audible audio or fail explicitly.
2. The workflow must not depend on `ComfyUI-EdgeTTS`.
3. The workflow must not depend on `ComfyUI-Easy-Use`.
4. Voice input must use real Edge voice IDs such as `zh-CN-YunjianNeural`, not display-label placeholders.
5. The ComfyUI-side implementation must support:
   - text
   - voice ID
   - speed
   - pitch
6. Failure to generate or decode audio must raise a visible node error instead of returning silent placeholder audio.

### Reliability Requirements

1. The node must not rely on `torchaudio.load` as the only decode path.
2. The node must use a controlled decode strategy that remains valid when `torchcodec` or FFmpeg shared DLL availability differs across Windows machines.
3. Network or upstream Edge service failures must be surfaced clearly.
4. The workflow must avoid extra helper nodes when direct primitive inputs are sufficient.

### Maintainability Requirements

1. Pixelle must own the ComfyUI TTS node implementation.
2. The node implementation should mirror Pixelle's local TTS behavior where practical.
3. The repository must include regression coverage for the workflow structure.
4. The repository documentation under `workflows/down/` must describe the new dependency model and validation steps in Chinese.

## Proposed Architecture

### 1. Pixelle-Owned ComfyUI Plugin

Create a new plugin under:

`E:\comfyui\comfyui\custom_nodes\ComfyUI-Pixelle-TTS`

This plugin will define a node such as `PixelleEdgeTTS`.

Responsibilities:

- Call Edge TTS directly
- Accept explicit voice IDs
- Convert returned audio bytes into ComfyUI `AUDIO`
- Fail loudly on generation or decode errors
- Keep implementation small and purpose-built for Pixelle's workflow needs

This is preferable to forking `ComfyUI-EdgeTTS` because:

- Pixelle owns behavior and upgrade cadence
- The implementation can align with the repository's existing Edge TTS utility
- Third-party plugin regressions no longer silently affect Pixelle's default workflow

### 2. Thin Workflow

Rewrite `workflows/selfhost/tts_edge.json` so it uses:

- `PrimitiveStringMultiline` for text
- `PrimitiveStringMultiline` for voice ID
- `PixelleEdgeTTS` for synthesis
- `SaveAudioMP3` for output

The workflow should no longer require `easy showAnything` or similar pass-through nodes. `speed` and `pitch` should be configured directly on the `PixelleEdgeTTS` node as native widget inputs unless a future workflow requirement explicitly needs them exposed as upstream parameters.

### 3. Shared Behavioral Contract

Pixelle application-side local TTS remains the behavioral reference:

- retry strategy
- parameter conventions
- voice ID format
- explicit failure semantics

The ComfyUI plugin does not need to import Pixelle package code directly if that would create fragile path coupling, but it should intentionally implement the same contract.

## Implementation Approach Options

### Option A: Keep patching `tts_edge.json` only

Pros:

- smallest change

Cons:

- cannot fix silent fallback inside third-party node
- continues reliance on fragile external dependencies
- not a source-level fix

Rejected.

### Option B: Fork and maintain `ComfyUI-EdgeTTS`

Pros:

- faster than writing a new node from scratch

Cons:

- long-term ownership remains muddy
- upstream merge burden
- keeps unrelated features and legacy behavior we do not need

Not recommended.

### Option C: Build `ComfyUI-Pixelle-TTS` and switch workflow to it

Pros:

- clear ownership
- explicit failure semantics
- minimal dependency surface
- consistent with Pixelle's local TTS design

Cons:

- requires new plugin maintenance

Recommended.

## Detailed Design

### ComfyUI Node Interface

Node name:

- internal class: `PixelleEdgeTTS`
- display name: `Pixelle Edge TTS`

Inputs:

- `text: STRING`
- `voice: STRING`
- `speed: FLOAT`
- `pitch: INT`

Output:

- `AUDIO`

Behavior:

1. Validate text is non-empty.
2. Validate voice is non-empty and resembles a real Edge voice ID.
3. Convert speed multiplier to Edge rate string.
4. Request audio from Edge TTS.
5. Decode returned bytes into mono waveform and sample rate.
6. Normalize waveform to expected ComfyUI `AUDIO` shape.
7. Return waveform.
8. If any stage fails, raise an exception. Do not fabricate a silent waveform.

### Audio Decode Strategy

Best-practice source fix:

- Treat remote TTS response bytes as the source of truth.
- Avoid the current design where a third-party node writes a temp file and then depends on `torchaudio.load` with environment-sensitive codec behavior.
- Prefer a decode path we explicitly control. Practical choices:
  - FFmpeg subprocess decode from temp file or stdin
  - a stable Python decoder dependency with predictable Windows packaging

Recommendation:

- Use FFmpeg subprocess decode in the ComfyUI plugin.

Reasoning:

- predictable behavior across ComfyUI Python environments
- easy to diagnose
- avoids silent `torchcodec` coupling
- FFmpeg is already an accepted repository-level system tool

Failure mode:

- if FFmpeg decode fails, the node raises an explicit error describing the command failure

### Voice Representation

The workflow should store real voice IDs, for example:

- `zh-CN-YunjianNeural`

This avoids ambiguity between UI labels and actual runtime IDs.

### Dependency Model

After redesign, `tts_edge.json` depends on:

- Pixelle-owned ComfyUI plugin
- ComfyUI built-in save node
- Edge TTS Python package
- FFmpeg available to the ComfyUI runtime

After redesign, it no longer depends on:

- `ComfyUI-EdgeTTS`
- `ComfyUI-Easy-Use`

## Testing Strategy

### Repository Tests

Add or update tests to verify:

1. `tts_edge.json` is parseable.
2. `tts_edge.json` no longer references `EdgeTTS`.
3. `tts_edge.json` no longer references `easy showAnything`.
4. `tts_edge.json` stores a real Edge voice ID.
5. The workflow text input is intact and UTF-8 safe.

### ComfyUI Runtime Validation

Manual validation steps:

1. Restart ComfyUI.
2. Confirm `PixelleEdgeTTS` appears in `/object_info`.
3. Run `tts_edge.json` with Chinese text and `zh-CN-YunjianNeural`.
4. Confirm resulting MP3 contains non-silent audio.
5. Temporarily break FFmpeg path and confirm node fails loudly instead of outputting a silent file.

## Documentation Changes

Update `workflows/down/tts_edge_依赖与下载说明.md` to:

- describe `ComfyUI-Pixelle-TTS`
- remove `ComfyUI-EdgeTTS` and `ComfyUI-Easy-Use` as required dependencies for this workflow
- document FFmpeg requirement for the new node
- document verification and failure expectations

## Risks and Mitigations

### Risk: plugin drift from Pixelle local TTS

Mitigation:

- keep node scope minimal
- align parameter naming and failure behavior with `tts_util.py`
- document the shared contract

### Risk: FFmpeg not available in ComfyUI environment

Mitigation:

- explicit startup/runtime error message
- document installation and verification clearly

### Risk: network instability from Edge service

Mitigation:

- implement retry behavior in plugin
- keep errors visible when retries are exhausted

## Success Criteria

This redesign is complete when:

1. `tts_edge.json` uses Pixelle-owned nodes only for TTS generation.
2. The workflow no longer needs `ComfyUI-EdgeTTS` or `ComfyUI-Easy-Use`.
3. ComfyUI runs produce real audio or explicit errors, never silent fake success.
4. Repository tests cover the new workflow structure.
5. Chinese documentation reflects the new dependency and validation model.
