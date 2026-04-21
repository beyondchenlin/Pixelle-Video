# Prompt Prefix Thumbnail Gallery Refinement

## Goal

Refine the prompt-prefix gallery so it feels visually as polished as the existing Template Gallery, while upgrading cards from static placeholder-like covers into workflow-aware thumbnail cards backed by real generated previews.

This refinement keeps the approved gallery architecture intact and focuses on:

- stronger template-gallery-style visual hierarchy
- real thumbnail replacement for style cards
- robust adaptive card layout for mixed Chinese/English labels
- workflow-aware thumbnail caching and refresh behavior

## Relationship to the Existing Gallery Spec

This spec extends `docs/superpowers/specs/2026-04-20-prompt-prefix-gallery-redesign-design.md`.

That earlier spec defines:

- the gallery-first interaction model
- single active style for generation
- multi-select comparison for preview
- toolbar and drawer structure

This refinement adds the thumbnail system and the detailed adaptive layout rules required to make the gallery feel complete in production.

## Problem Summary

The current gallery structure is directionally correct, but it still has two experience gaps:

1. Card layout still feels slightly too configuration-oriented.
   - text density is still higher than the existing Template Gallery
   - image is present, but not yet the uncontested primary surface
   - mixed label lengths can easily make cards feel noisy or awkward

2. The cover image experience still reads as provisional.
   - users want cards to look like real selectable style samples, not placeholders
   - static reference covers help avoid blank states, but they are not enough on their own
   - once users explicitly generate thumbnails for the current workflow, the card should feel upgraded with a real thumbnail

The intended experience is:

- every card always has a usable cover
- default cover is visually curated
- real thumbnail replaces the curated cover when the user explicitly generates thumbnails
- switching workflows does not destroy the grid, but makes thumbnail staleness visible

## Approved Direction

### 1. Card Default Strategy: Hybrid

Each style card uses a hybrid image strategy:

- default state: show the built-in or uploaded reference cover
- upgraded state: show the real generated thumbnail for the current workflow when available

This avoids both empty cards and forced up-front generation.

### 2. Thumbnail Prompt Strategy: Dedicated Gallery Prompt

Thumbnail generation uses its own dedicated gallery reference prompt.

It must not reuse the comparison preview test prompt.

Reason:

- the gallery needs visual consistency across cards
- comparison preview and gallery thumbnailing serve different purposes
- users need a stable thumbnail reference prompt without disturbing comparison workflows

### 3. Generation Trigger Strategy: Explicit Batch Action

Real thumbnails are generated only when the user explicitly clicks `Generate Thumbnails`.

They are not generated automatically on page load and are not generated implicitly by merely opening the gallery.

### 4. Batch Scope Strategy: Current Filter Result

`Generate Thumbnails` acts only on the current filtered result set.

This matches how users narrow the gallery before taking an action, and it keeps generation cost predictable.

### 5. Workflow Strategy: Cache Per Workflow

Each style stores real thumbnail results separately per image workflow.

The same style must not reuse one shared real thumbnail across all workflows.

## Visual System

### 1. Card Layout Rhythm

The card should feel closer to the Template Gallery than to a management panel.

Each card consists of:

- image block
- title
- one compact classification line
- one primary action button

The card should not permanently display long notes or full prompt content.

Those belong in the details drawer only.

### 2. Thumbnail as Primary Surface

The image block must dominate the card visually.

Rules:

- fixed image ratio: `4:5`
- image always appears before any text
- image height is fixed per card size
- text never changes image height

### 3. Overlay Badge Placement

Badges sit on top of the image, not in the main text body.

Overlay badges:

- top-left: source badge (`builtin`, `manual`, `AI`)
- top-right: compare badge and, when needed, thumbnail freshness badge

This keeps the lower text area visually quiet.

### 4. Strong Adaptive Typography Rules

To avoid ugly overflow and inconsistent card heights, the gallery must enforce strict truncation rules.

Rules:

- title: maximum 2 lines, then ellipsis
- classification row: maximum 1 line, then ellipsis
- note text: not shown in card body by default
- badges: use short labels only, never long sentences
- bottom button text remains short: `Select / Selected`

### 5. Equal-Height Cards

All cards in a row must maintain equal height.

Longer Chinese or mixed-language titles must truncate instead of expanding the card.

### 6. Responsive Grid Rules

Desktop and smaller breakpoints should reduce column count before shrinking image quality.

Grid rules:

- desktop: `4` columns
- medium screens: `2` columns
- small screens: `1` column

The design should prefer fewer, larger cards over cramped cards.

## Toolbar Design

The toolbar is split into two visual layers.

### 1. Top Toolbar Row

Contains high-frequency controls:

- style category filter
- scene category filter
- keyword search
- `Generate Thumbnails`
- `Add Style`
- `AI Generate`

### 2. Thumbnail Status Row

Contains thumbnail-specific status and configuration:

- dedicated thumbnail reference prompt input
- filtered result count
- generation progress or summary text

This keeps the primary interaction row clean while still exposing generation state.

## Real Thumbnail Lifecycle

### 1. Default Card Image Resolution

Each card resolves its image in this order:

1. current workflow real thumbnail
2. most recent real thumbnail from another workflow, marked as stale
3. default reference cover (`preview_asset_path`)

This guarantees that cards always have a meaningful image.

### 2. What Counts as the Default Reference Cover

`preview_asset_path` remains the default cover field.

It is used for:

- built-in curated style covers
- uploaded custom style covers
- any non-workflow-specific reference image

Real workflow thumbnails must not overwrite this field.

### 3. Real Thumbnail Generation Behavior

When the user clicks `Generate Thumbnails`:

- validate that the filtered set is not empty
- validate that the current workflow is known
- validate that the dedicated thumbnail reference prompt is not empty
- generate thumbnails sequentially for each filtered style
- persist each successful thumbnail immediately after generation
- continue the batch even if one item fails

### 4. Progress Feedback

Generation must never feel silent.

Show visible progress text such as:

- `Generating thumbnails...`
- `Completed 3 / 8`
- `Generated 6, failed 2`

### 5. Failure Handling

Single-item failure does not cancel the batch.

If a style fails:

- keep showing the default reference cover
- show a light `failed` or `needs retry` indicator
- allow the user to rerun thumbnail generation later

### 6. Refresh Behavior

If a thumbnail already exists for the current workflow and the user regenerates thumbnails, the current-workflow thumbnail is replaced.

Historical versions are out of scope.

## Workflow Switching Rules

Switching workflows must not blank out the gallery.

Rules:

- if a current-workflow thumbnail exists, show it
- if no current-workflow thumbnail exists but another workflow thumbnail exists, show that older real thumbnail and mark it stale
- if no real thumbnail exists at all, show the default reference cover

Recommended stale label:

- short, visually light, image-overlay badge
- semantic meaning: `stale`

It should be informative without turning the card into a warning state.

## Data Model Refinement

### 1. Keep the Existing Default Cover Field

Retain:

- `preview_asset_path`

This remains the workflow-independent reference cover field.

### 2. Add Workflow-Scoped Real Thumbnail Storage

Each prompt-prefix item should gain a workflow-scoped thumbnail cache structure:

- `workflow_preview_assets`

Each workflow entry stores:

- `asset_path`
- `reference_prompt`
- `generated_at`
- `status`

These field names are part of the intended contract for this refinement and should be implemented directly unless a compatibility constraint requires an explicit documented exception.

### 3. Why Workflow Cache Metadata Matters

Storing `reference_prompt` and `generated_at` is necessary so the UI can explain:

- which workflow produced the thumbnail
- what gallery prompt was used
- whether the image may now be outdated

### 4. Configuration vs UI Responsibility

Configuration should store only durable data:

- file paths
- workflow association
- reference prompt used
- generation timestamp
- status

UI-only layout rules must not be stored in config.

Do not persist visual values like:

- column count
- image ratio
- truncation lengths
- badge layout

Those remain purely in the frontend component.

## Drawer and Card Responsibility Split

To preserve the template-gallery feel:

- card body: recognition and quick selection
- details drawer: explanation and management

Card body shows only:

- image
- source badge
- compare/freshness badge
- title
- one compact classification line
- select button

Details drawer continues to own:

- longer note
- full prefix content
- copy actions
- edit/delete actions
- precise thumbnail provenance if exposed

## Error Handling and Safeguards

### 1. Empty Filter Result

If the filtered result set is empty, `Generate Thumbnails` must not run.

Show a concise warning only.

### 2. Empty Thumbnail Prompt

If the dedicated thumbnail prompt is empty, `Generate Thumbnails` must not run.

### 3. Missing Workflow Thumbnail Cache

Missing cache is not an error state by itself.

It simply means the card continues to use fallback cover logic.

### 4. Thumbnail Asset Missing on Disk

If a cached real thumbnail path no longer exists on disk:

- treat it as unavailable
- fall back using the standard image resolution order
- do not crash the gallery

## Testing Focus

Implementation must explicitly verify:

- current-workflow thumbnail wins over default cover
- other-workflow thumbnail falls back correctly and is marked stale
- default reference cover still renders when no workflow thumbnail exists
- explicit thumbnail batch generation only targets filtered items
- generation progress and result summaries update correctly
- failed items keep fallback covers without breaking the batch
- long titles and mixed-language labels do not break equal-height cards
- desktop `4`-column layout degrades cleanly to `2` and `1` columns
- workflow-specific thumbnail caches do not overwrite each other

## Out of Scope

This refinement does not include:

- automatic thumbnail generation on page load
- thumbnail version history
- global background regeneration jobs
- per-card freeform layout customization
- rewriting the approved drawer architecture

## Recommended Implementation Intent

The final result should feel like this:

- first open: a polished visual style library with curated covers
- after explicit thumbnail generation: a richer, more truthful style library with real workflow-aware thumbnails
- after workflow switching: a stable gallery that still looks good, while truthfully signaling when thumbnails may be outdated

The gallery should never regress into a text-heavy settings surface, and it should never feel visually unfinished.
