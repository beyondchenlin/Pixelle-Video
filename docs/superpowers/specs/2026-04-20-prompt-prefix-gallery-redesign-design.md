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

### Custom and AI-Generated Styles

For user-created styles, the system should support a preview image field in the creation flow.

V1 rule:

- built-in styles must always have real curated preview images
- custom and AI-generated styles may use a user-provided preview image when available
- if no preview image is available yet, the UI may fall back to a neutral placeholder card until a preview asset is generated or supplied

This keeps the built-in gallery visually strong without blocking custom-style creation.

## Drawer System

Use a unified right-side drawer system for secondary interactions.

Desktop:

- right-side drawers

Mobile:

- full-screen drawer or bottom-sheet equivalent

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

Actions:

- `Save to Library`
- optional `Save and Set Active`

### 3. AI Generate Drawer

Purpose:

- generate candidate styles from the configured LLM

Contents:

- one natural-language idea input
- one short note explaining that the current system LLM config will be reused
- candidate list rendered as mini visual cards

Each candidate should provide:

- preview area
- style name
- categories
- short description
- `Add to Library`
- `Set Active`
- `Add to Compare`

Generation failures should be contained inside the drawer and must not disturb the main gallery state.

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
- video prompt-prefix behavior remains out of scope

## Out of Scope

This redesign does not include:

- a separate video style gallery
- replacing the underlying prompt-prefix data model
- building a fully separate admin page for style management
- forcing all custom styles to generate preview assets automatically in V1

## Implementation Consequence

The current prompt-prefix library implementation should be treated as functional infrastructure.

The redesign should primarily refactor:

- information hierarchy
- card layout
- action placement
- preview asset presentation
- management affordances

without changing the already approved behavioral rules around active selection, preview comparison, and LLM-powered prefix generation.
