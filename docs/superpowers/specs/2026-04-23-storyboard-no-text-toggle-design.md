# Storyboard No-Text Toggle Design

## Goal

Expose the existing `forbid_embedded_text_in_image` behavior as a user-facing control inside the `Storyboard Planning` panel, while keeping the current Pixelle UI language and the default behavior unchanged.

This change should:

- add a visible toggle in the `Storyboard Planning` section
- default that toggle to `on`
- preserve the current backend default of forbidding embedded text in generated images
- thread the toggle through Web request building and API schemas
- keep the control visually consistent with the current storyboard controls

This change should not:

- redesign the storyboard panel
- move the control into an unrelated section
- change the current default behavior from `forbid` to `allow`
- implement OCR or post-generation validation

## Current State

The backend already supports a `forbid_embedded_text_in_image` parameter:

- `pixelle_video/utils/content_generators.py`
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/pipelines/custom.py`

The current runtime behavior is:

- default `True`
- all generated prompts get the no-text positive rule
- workflows that support `negative_prompt` also receive a merged no-text negative prompt

What is missing is the user-facing control surface:

- the `Storyboard Planning` panel has no toggle for this behavior
- Web request builders do not expose the field
- API schemas do not document or accept the field

So the feature exists operationally, but not as an intentional product control.

## Product Judgment

The toggle belongs in `Storyboard Planning`, not in the generic media/workflow section.

Reasoning:

- the user is currently using storyboard controls as the main quality-and-consistency surface
- embedded text suppression is part of image hygiene and continuity quality, not a low-level workflow detail from the user's perspective
- placing it near `world preset`, `shot preset`, and `consistency` keeps the interaction model coherent

This is slightly higher-level than the backend implementation, but it matches the way the feature is used in practice.

## Options Considered

### Option A: Add the toggle inside `Storyboard Planning`

Pros:

- matches the user's current working area
- keeps the control with related visual-quality settings
- smallest UX surprise
- easiest to keep stylistically consistent with the current panel

Cons:

- the setting is technically broader than storyboard alone

### Option B: Add the toggle in the media/workflow section

Pros:

- maps more directly to the backend execution layer

Cons:

- splits a quality-related control away from the storyboard planning flow
- weakens discoverability for the user who is already configuring visual behavior in storyboard

### Option C: Keep it backend-only

Pros:

- no UI work

Cons:

- does not satisfy the requirement for user control
- forces users into one fixed default even for poster/title-card use cases

## Approved Direction

Use **Option A**.

Add a `禁止图中文字` control inside the `Storyboard Planning` panel and keep it defaulted to `on`.

Implementation should preserve the current panel's visual language. The control should look like part of the existing storyboard configuration set rather than a new sub-panel or styled exception.

## UI Design

### Placement

Place the toggle inside the existing `Storyboard Planning` section in `web/components/style_config.py`.

It should appear in the same control group as the existing storyboard options, below the current preset/strategy controls and above the preview override area.

This keeps:

- preset choice
- strategy choice
- image hygiene choice
- preview override choice

in one continuous workflow.

### Control Type

Use a standard checkbox.

Approved label:

- `禁止图中文字`

Approved help text intent:

- generated images should avoid embedded Chinese text, English text, subtitles, captions, logos, and watermarks
- users can turn it off for posters, title cards, packaging, or other cases where text in the image is intentional

### Default Behavior

Default value is `True`.

The default resolution order should be:

1. current session value
2. explicit loaded task/request value when replaying or previewing
3. hard default `True`

This matches the existing backend default and avoids changing current output behavior for users who do nothing.

### Visual Rules

The implementation should reuse the existing storyboard panel styling.

Do:

- use the same checkbox/radio/select control family already present in the panel
- keep the explanatory copy concise
- extend the existing help/guide content rather than adding a visually separate advisory card

Do not:

- introduce a new custom color treatment
- add a standalone warning box unless there is a concrete validation error
- create a new collapsible subsection for one toggle

## Guide Copy Update

The existing `如何使用分镜规划` guide should be updated so the new toggle is explained alongside the other storyboard controls.

The new copy only needs to explain:

- what the toggle does
- why it is on by default
- when users may want to turn it off

This belongs in the same explanatory block that already documents `世界预设`, `镜头预设`, and the other planning parameters.

## Data Flow Contract

### Web/UI State

`render_style_config()` should include the selected boolean in its returned configuration payload.

Approved field name:

- `forbid_embedded_text_in_image`

### Request Builders

The field must be threaded through:

- single generation request builders
- batch shared config builders
- any storyboard preview/generate path that already serializes storyboard options

If the storyboard panel is disabled, the field may still be present and should default to `True`. There is no need to suppress it purely because storyboard planning is off.

### API Schemas

Add the optional field to:

- `api/schemas/content.py`
- `api/schemas/video.py`

Schema contract:

- type: `Optional[bool]`
- default behavior when omitted remains the current pipeline default (`True`)

This keeps API compatibility while making the behavior explicit for Web and future clients.

### Pipeline Behavior

No new pipeline logic is required beyond existing support.

The pipelines should continue to resolve:

- missing value -> default `True`
- explicit `False` -> disable no-text injection
- explicit `True` -> enable current no-text behavior

## Testing Contract

At minimum, implementation must add or update tests for:

### UI / Request Tests

- the storyboard panel shows the toggle
- the toggle defaults to `True`
- when unchecked, generated request payload includes `forbid_embedded_text_in_image=False`
- when left unchanged, payload either includes `True` or cleanly omits it while preserving backend default, depending on the chosen request-builder pattern

### API Schema Tests

- content-image prompt request accepts the field
- video generation request accepts the field

### Integration Coverage

- at least one Web or pipeline-facing test should verify that explicit `False` reaches `generate_styled_image_prompt_batch(...)`

The implementation does not need new image-generation end-to-end tests beyond this if existing prompt-composition tests already cover the downstream behavior.

## Non-Goals

This patch does not include:

- OCR-based post-checking
- automatic regeneration when text is detected
- model-specific workflow surgery for `z-image turbo`
- per-world-preset text policies
- a separate media-level duplicate control outside storyboard planning

## File Scope

Expected implementation touch points:

- `web/components/style_config.py`
- `web/components/output_preview.py` or related request builders if needed
- `api/schemas/content.py`
- `api/schemas/video.py`
- related UI / API tests

The existing backend prompt logic added in `7219e7b` remains the source of truth for actual no-text prompt injection.
