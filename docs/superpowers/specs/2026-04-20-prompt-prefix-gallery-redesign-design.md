# Prompt Prefix Gallery Redesign

## Goal

Redesign the image prompt-prefix experience from a text-heavy configuration panel into a template-library-style gallery that feels native to the existing Pixelle UI.

The new experience should:

- visually align with the existing Template Gallery
- use real illustration preview images as the primary browsing surface
- preserve the product rule that real generation uses one active style only
- keep multi-style comparison available for preview
- avoid regressing into a dense admin/configuration interface

This redesign builds on the existing prompt-prefix-library feature and focuses on presentation, interaction model, and information hierarchy.

## Problem Summary

The current prompt-prefix UI is functionally richer than the original single text area, but it still reads like a management panel:

- the primary surface is text and form controls, not visual style exploration
- English prefix content occupies too much of the main view
- the section does not match the mental model established by the existing Template Gallery
- style selection feels like configuration work instead of choosing from a visual library

Because users are selecting illustration styles, the dominant interaction should be image-first, not text-first.

## Existing Visual Reference

The existing Template Gallery in `web/components/style_config.py` establishes a clear UI language:

- top-level container with minimal framing
- tabs for classification/grouping
- a grid of vertical cards
- large preview image as the focal point
- a single clear primary action under each card: `Select` or `Selected`
- restrained surrounding metadata

The redesigned prompt-prefix area should reuse this language instead of inventing a parallel subsystem.

## Approved Direction

### 1. Overall Layout Direction: `B`

Use a template-library-style gallery as the main body, while preserving a lightweight status strip above it.

This means:

- the main browsing surface becomes a grid of style cards
- the top of the section keeps a light `current active style` summary strip
- filters and tools stay above the card grid
- the section still supports library management, but management is not the visual center

This is intentionally more capable than the pure-template approach, but still clearly belongs to the same interface family.

### 2. Card Interaction Direction: `C`

Use a single primary action below each card and a small comparison affordance in the card corner.

Card actions:

- bottom primary button: `Select` / `Selected`
- top-right small badge or chip: `Add to Compare` / `In Compare`
- click on card body: open details drawer

This preserves the Template Gallery rhythm while still supporting multi-style preview comparison.

### 3. Tool Entry Direction

Place `Add Style` and `AI Generate` in a top toolbar above the gallery.

Do not hide them in a detached management page or in a fake “plus card” inside the main gallery grid.

Reason:

- keeps the gallery visually clean
- keeps management actions available but secondary
- matches the existing “browse first, manage second” flow

### 4. Workflow-Aware Preview Rule

The gallery must respect the fact that image workflows are user-switchable.

Therefore:

- gallery card images are treated as reference cover images for browsing, not as guaranteed exact outputs for every workflow
- the currently selected image workflow remains the source of truth for any newly generated comparison result
- switching workflows must not silently regenerate the entire gallery grid
- comparison output and any explicit preview-generation action should clearly be tied to the current workflow selection

This keeps the gallery fast and stable while avoiding the false promise that one fixed cover image exactly represents every workflow.

## Core Interaction Rules

### 1. One Active Style for Real Generation

Formal image generation continues to use exactly one active prompt prefix.

The gallery redesign must not change this rule.

### 2. Multi-Select Only for Comparison

Preview comparison may include multiple style cards.

The comparison set is separate from the active style:

- active style = single source of truth for formal generation
- comparison set = temporary preview-only selection

### 3. Card Click Semantics

Card interactions are split by intent:

- click card body: inspect the style
- click bottom primary button: make it the active style
- click top-right compare badge: add or remove from comparison set

This reduces accidental state changes and fits the existing gallery browsing behavior.

### 4. Interaction Priority and Mobile Rules

The redesign adds more hit targets than the current Template Gallery, so click behavior must be explicit.

Rules:

- the bottom primary button is the only control that changes the active style directly
- the compare badge only changes compare membership and must not open details
- the remaining card body opens the details view
- button clicks and badge clicks must stop propagation so they do not also trigger the card-body action
- mobile uses the same intent split with no hover-only affordances
- the compare badge needs a touch-safe hit area, even if the visible chip stays visually small

If the card becomes too dense on smaller breakpoints, the compare action may collapse into a compact icon button, but the interaction priority must stay the same.

## Information Architecture

The redesigned section should be structured as follows.

### 1. Section Header

Keep the existing `插图生成 / Image Generation` container and workflow selector unchanged.

Do not move the feature to another page.

### 2. Active Style Strip

Directly under the size info block, add a compact status strip summarizing the currently active style.

Display:

- active style name
- style category
- scene category
- short one-line description

Actions in the strip:

- `View Details`
- `Manage Library` or `Open Library`

This strip should feel lighter than a form block and should not show the full English prefix by default.

### 3. Top Toolbar

Above the gallery grid, add a lightweight toolbar containing:

- style category filter
- scene category filter
- keyword search
- `Add Style`
- `AI Generate`

Optional:

- compare count indicator such as `Comparing 2 styles`

### 4. Gallery Grid

The main body becomes a grid of style cards, visually similar to template cards:

- large vertical preview image
- style name
- small tags or minimal metadata
- single bottom primary button
- small corner compare badge

The full English prefix content must not dominate this surface.

## Style Card Specification

Each style card should contain:

- preview image
- style name
- small source badge if useful: built-in / AI / custom
- minimal tags for style and scene classification
- bottom primary action button: `Select` or `Selected`
- top-right compare badge: `Add to Compare` or `In Compare`

The card should not show the full English prefix content by default.

If a short Chinese note exists, it may appear as a one-line caption, but only if it does not make the card feel text-heavy.

## Preview Asset Strategy

### Built-In Styles

Built-in styles should ship with fixed, curated real preview images.

These assets are part of the library package and ensure:

- fast gallery loading
- consistent layout
- consistent visual comparison quality
- a browsing experience that feels close to the Template Gallery

These built-in assets are reference covers.

They are intentionally stable across workflow switches so the gallery remains fast, recognizable, and visually curated.

The UI must not imply that these cover images are guaranteed exact outputs for every workflow/model combination.

When the user runs preview comparison, those newly generated results become the authoritative representation for the current workflow session.

### Custom and AI-Generated Styles

For user-created styles, the system should support a preview image field in the creation flow.

V1 rule:

- built-in styles must always have real curated preview images
- custom and AI-generated styles may use a user-provided preview image when available
- if no preview image is available yet, the UI may fall back to a neutral placeholder card until a preview asset is generated or supplied

This keeps the built-in gallery visually strong without blocking custom-style creation.

### Preview Asset Persistence Model

Preview images must be persisted as asset references, not embedded inside YAML.

V1 persistence rule:

- extend the prompt-prefix item metadata with an optional preview asset field such as `preview_asset_path`
- store a repo-relative or app-relative asset path, not raw image bytes
- built-in assets may live in a shipped static folder such as `resources/prompt_prefix_previews/`
- user-uploaded preview images should be copied into the same managed asset area on save
- deleting a custom style should only delete its preview asset if that asset is owned exclusively by that item

This gives custom styles durable cover images across restart/export/import without turning the config file into a media blob store.

### AI Candidate Preview Policy

AI-generated candidates should use a two-stage preview model.

Stage 1:

- LLM generation returns structured text candidates only
- candidate cards render immediately with metadata and a neutral preview frame or placeholder state
- no hidden image-generation request is triggered automatically as part of text generation

Stage 2:

- the user may explicitly request candidate previews using the current workflow and a test prompt
- candidate preview generation should run sequentially or in another already-approved low-risk batching mode, not as an implicit fan-out burst
- generated candidate previews are session-scoped until the user saves a style or explicitly promotes a preview asset

This preserves the visual gallery direction without making `AI Generate` unexpectedly slow or expensive.

## Drawer System

Use a unified right-side drawer system for secondary interactions.

Desktop:

- right-side drawers

Mobile:

- full-screen drawer or bottom-sheet equivalent

Implementation note:

- a true right-side drawer is the preferred desktop presentation
- if Streamlit limitations make a real drawer brittle, the allowed fallback is a right-anchored secondary panel or modal-like side sheet that preserves the same information architecture
- the fallback must still keep the main gallery visible or mentally present, rather than navigating users to a separate management page
- only one secondary panel should be open at a time

### 1. Style Details Drawer

Purpose:

- inspect one style without leaving the gallery

Contents:

- large preview image
- style name
- source badge
- style category
- scene category
- short Chinese description
- English prompt-prefix content

Actions:

- `Set Active`
- `Add to Compare` / `Remove from Compare`
- `Copy Prefix`
- `Duplicate as New Style`

For custom styles only:

- `Edit`
- `Delete`

### 2. Manual Create Drawer

Purpose:

- add a new custom style without turning the main page into a form

Fields:

- style name
- style category
- scene category
- English prefix content
- short Chinese note
- preview image input or upload

Preview asset behavior:

- uploaded preview images become the style's persisted cover image after save
- if the user does not provide one, the style may save with a placeholder and receive a real cover image later

Actions:

- `Save to Library`
- optional `Save and Set Active`

### 3. AI Generate Drawer

Purpose:

- generate candidate styles from the configured LLM

Contents:

- one natural-language idea input
- one short note explaining that the current system LLM config will be reused
- candidate list rendered as mini cards with explicit preview states

Each candidate should provide:

- preview area that can show either a placeholder or an explicitly generated candidate preview
- style name
- categories
- short description
- optional `Generate Preview` or batch `Generate Candidate Previews` action tied to the current workflow and test prompt
- `Add to Library`
- `Set Active`
- `Add to Compare`

Generation failures should be contained inside the drawer and must not disturb the main gallery state.

The AI drawer must not imply that preview images exist immediately after text generation if the user has not yet requested them.

### 4. Delete Confirmation

Use a small confirmation modal for deletion only.

Deletion does not need its own drawer.

## Detail Density Rules

To preserve the Template Gallery feel:

- the gallery surface is image-first
- full English prefix text belongs in the details drawer, not the main card grid
- creation and AI generation forms belong in drawers, not inline in the main gallery
- the main gallery should remain scannable in a few seconds

In short:

- main surface = browse and choose
- drawer = inspect and manage

## Visual Design Principles

This redesign must preserve the current project’s visual language.

Do:

- keep the existing white background and rounded card language
- keep selection state visually close to the Template Gallery
- keep the gallery airy and image-led
- use restrained metadata
- preserve the current spacing rhythm and low-contrast framing

Do not:

- turn the gallery into a settings dashboard
- show long prompt bodies on every card
- introduce a totally new color system or component language
- overload cards with multiple equal-weight actions

## Recommended User Flow

1. User opens the image generation section.
2. User sees the active style strip.
3. User filters or scrolls the visual style gallery.
4. User clicks a card body to inspect details if needed.
5. User clicks the bottom primary button to set one style active.
6. User optionally marks several styles for comparison via the corner badge.
7. User runs preview comparison.
8. User promotes one compared style to active.

This flow should feel closer to selecting a template than editing prompt strings.

## Compatibility Notes

This redesign changes presentation, not the core product rules:

- global shared image prompt-prefix library remains
- single active prefix for real generation remains
- preview comparison multi-select remains
- gallery cover images remain browsing references, while workflow-driven preview output remains the authoritative current-workflow result
- video prompt-prefix behavior remains out of scope

## Out of Scope

This redesign does not include:

- a separate video style gallery
- replacing the underlying prompt-prefix data model
- building a fully separate admin page for style management
- forcing all custom styles to generate preview assets automatically in V1
- regenerating the full gallery whenever the selected workflow changes

## Implementation Consequence

The current prompt-prefix library implementation should be treated as functional infrastructure.

The redesign should primarily refactor:

- information hierarchy
- card layout
- action placement
- preview asset presentation
- management affordances

without changing the already approved behavioral rules around active selection, preview comparison, and LLM-powered prefix generation.
