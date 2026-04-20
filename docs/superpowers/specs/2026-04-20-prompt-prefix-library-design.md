# Prompt Prefix Library Design

## Goal

Upgrade the current single `prompt_prefix` text input into a global prompt-prefix library that supports:

- storing multiple reusable prompt prefixes
- choosing exactly one active prefix for actual image generation
- previewing multiple prefixes side by side for comparison
- generating candidate prefixes from the already configured LLM
- organizing prefixes by both style type and usage scene
- preserving the existing Pixelle Web UI visual language instead of introducing a new, disconnected interface style

The design should improve prompt-style workflow efficiency without disrupting the current generation flow or the surrounding UI patterns in `web/components/style_config.py`.

## Problem Summary

The current implementation in `web/components/style_config.py` has one temporary `st.text_area` for `prompt_prefix`:

- users can only work with one prefix at a time
- prefixes are not managed as reusable assets
- the UI does not provide saving, tagging, or quick switching
- preview only reflects the current typed prefix, so style comparison is slow
- users who want new prefixes must write them manually, even though the product already has an LLM configuration surface

This makes style exploration cumbersome, especially for users who frequently switch illustration styles or want to keep multiple brand or scenario-specific presets.

## Explored Approaches

### 1. Inline Enhanced Prefix Section

Keep the prompt-prefix capability in its current location and expand that area into a richer management experience.

Pros:

- most consistent with the current page structure
- lowest learning cost for existing users
- easiest to keep visually aligned with existing Streamlit containers, expanders, and inputs
- preserves the current generation workflow

Cons:

- the section becomes taller and more feature-dense

### 2. Tabbed Prefix Workspace

Replace the single input area with tabs such as `Choose`, `AI Generate`, and `Manage`.

Pros:

- clearer functional separation
- easier to hide complexity

Cons:

- introduces a stronger application-management feel than the current UI
- more navigation overhead for quick operations
- less aligned with the current Pixelle page rhythm

### 3. Separate Prefix Manager

Move prefix management into another settings area or a dedicated page, leaving only a simple selector in the style section.

Pros:

- keeps the main style area compact

Cons:

- breaks the user's working context
- makes preview/selection slower
- conflicts with the requirement that the feature should feel more convenient, not more indirect

## Approved Approach

Use the inline enhanced prefix section.

This approach preserves the existing overall style and interaction flow while adding the needed capability where users already expect to configure visual style.

## Core Product Rules

### 1. Global Shared Library

The prompt-prefix library is global, not per workflow.

That means:

- all image workflows share one prefix library
- users can reuse the same prefixes across different image workflows
- workflow choice and prefix choice remain separate concerns

### 2. Single Active Prefix for Real Generation

Actual image generation must use exactly one active prompt prefix.

This avoids:

- accidental style mixing
- unclear generation behavior
- unstable output caused by concatenating unrelated style presets

### 3. Multi-Select Only for Preview

The preview area may allow multiple prefixes to be selected at once.

Purpose:

- compare several styles side by side using the same test prompt
- help the user decide which single prefix should become the active one

Preview multi-select must not automatically change the active prefix.

## Information Architecture

The prompt-prefix area should remain in the current style configuration section and expand into four sub-areas.

### 1. Active Prefix Summary

This block shows the currently active prefix used for actual image generation.

Display:

- prefix name
- style category
- scene category
- full English prefix content

Lightweight actions:

- set as default active prefix
- copy content
- clear active prefix

### 2. Prefix Library Browser

This is the main interaction area for selection.

Controls:

- style-category filter
- scene-category filter
- keyword search

Each prefix item should show:

- name
- style tag
- scene tag
- short description or truncated content
- source label such as built-in, manual, or AI-generated

Actions per item:

- `Set Active`: sets the single formal prefix for real generation
- `Add to Preview`: adds the item into the preview comparison set

### 3. Manual Create and AI Generate

These should live in collapsible sections under the library browser so the interface stays familiar and uncluttered.

#### Manual Create

Fields:

- name
- style category
- scene category
- English prefix content
- optional short note

Action:

- save to library

#### AI Generate

Fields:

- one natural-language idea input from the user

Behavior:

- reuse the already configured system LLM
- call an internal prefix-generation prompt
- return several structured candidate prefixes

Candidate actions:

- add to library
- add to preview
- set active immediately

### 4. Preview Comparison

This area stays where preview already lives conceptually, but supports multi-prefix comparison.

Behavior:

- the user enters one test prompt, for example `a dog`
- the user selects 2-4 prefixes from the preview set
- the system generates parallel previews with the same base prompt and different prefixes
- each preview card shows the result plus the associated prefix name
- each preview card can promote its prefix to active

Formal generation remains single-prefix even when preview is multi-prefix.

## Frontend Design Principle

This feature must follow a conservative enhancement strategy.

It should not introduce a visually disconnected subsystem. Instead, it should grow naturally from the existing Pixelle style configuration interface.

Implementation guidance:

- preserve the current white-background, rounded-corner, low-contrast input style
- continue using the same Streamlit primitives and spacing rhythm already present in the page
- avoid turning this section into a dense admin console
- use grouping, labels, expanders, and lightweight tags to improve clarity without changing the overall visual identity

In short: enhance capability, not visual direction.

## Data Model

The library should be stored as global configuration data rather than a database-backed feature.

Recommended structure:

```yaml
prompt_prefix_library:
  active_prefix_id: builtin_childrens_storybook_warm
  items:
    - id: builtin_childrens_storybook_warm
      name: Childrens Storybook Warm
      content: warm children's storybook illustration, soft lighting, gentle hand-painted texture, clean composition, expressive characters
      style_category: storybook
      scene_category: childrens_story
      source: builtin
      is_builtin: true
      note: Suitable for warm, healing, family-friendly content
      created_at: 2026-04-20T00:00:00Z
```

Each prefix item should include:

- `id`: stable unique identifier
- `name`: user-facing display name, mainly Chinese
- `content`: actual English prefix text used in prompt assembly
- `style_category`: style dimension
- `scene_category`: scene dimension
- `source`: `builtin`, `manual`, or `llm`
- `is_builtin`: whether the item is protected as a system preset
- `note`: optional short explanation
- `created_at`: audit-friendly creation time

Library state should also track:

- `active_prefix_id`: the single effective prefix for real generation

## Configuration and Persistence

Recommended persistence strategy:

- keep using the existing config management system
- store the prefix library in `config.yaml` through the same config manager path
- avoid introducing a new persistence technology

Important rules:

- missing library config should gracefully fall back to built-in presets
- reading config should not silently rewrite user files
- built-in presets should be available by default, but custom changes should only persist when the user explicitly saves configuration

## Built-In Preset Strategy

The system should ship with a starter library so users do not face an empty state.

Recommended initial coverage by style:

- childrens storybook
- flat illustration
- minimal line art
- watercolor hand-painted
- 3D cartoon
- cinematic realism
- anime-inspired
- traditional Chinese illustration

Recommended initial coverage by scene:

- childrens story
- educational illustration
- emotional copywriting
- knowledge sharing
- commercial cover
- short video illustration

Built-in presets should:

- be immediately usable
- be visible in the same library as custom items
- support copy/clone into custom items
- not be casually overwritten in place

## LLM Prefix Generator Design

The prefix generator should reuse the system-wide LLM configuration that users already manage in the settings panel.

### Inputs

- a single freeform idea input in Chinese or English

Example:

- "I want a warm children's storybook style with healing emotion, simple composition, and hand-painted texture"

### Internal Prompt Contract

The system should provide an internal prompt that instructs the LLM to:

- produce image-generation-ready English prompt prefixes
- keep each result concrete and style-operational
- avoid vague or overly long wording
- provide a Chinese display name
- assign both style and scene categories
- provide a short Chinese note
- output several candidates in a structured shape

### Output Shape

Recommended default: 4 candidates per generation request.

Each candidate returns:

- `name`
- `content`
- `style_category`
- `scene_category`
- `note`

### Post-Generation Actions

Generated candidates should not automatically override the active prefix.

Each result should support:

- add to library
- add to preview
- set as active

### Language Rule

Use:

- Chinese for names, categories, and notes
- English for `content`

This keeps the UI friendly while preserving better compatibility with image-generation models.

### Failure Behavior

If LLM configuration is incomplete or the generation call fails:

- show a clear message
- keep manual creation and manual selection fully available
- do not block the rest of the style workflow

## Generation Behavior

Actual generation behavior should stay simple and deterministic.

Rules:

1. If an active prefix exists, use that single prefix for actual generation.
2. If no active prefix exists, fall back to empty prefix behavior.
3. Preview comparison may use multiple selected prefixes, but each preview image is still generated with exactly one prefix at a time.

The existing prompt assembly helper can remain conceptually unchanged:

- each final prompt is still `build_image_prompt(base_prompt, selected_prefix_content)`

What changes is selection and management, not the final prompt-building rule.

## Validation Rules

Before saving a prefix item:

- `name` must be non-empty
- `content` must be non-empty
- category fields must be present
- duplicate handling should be defined, ideally warning on same-name or same-content collisions

Before preview:

- allow only a bounded number of selected prefixes at once, recommended 2-4

Before setting active:

- ensure the target item still exists in the library

## Error Handling

Expected resilience behavior:

- If the library config is absent, load built-in presets.
- If the active prefix is deleted or missing, clear active state or fall back to a safe built-in default.
- If the LLM is not configured, disable only the AI generator.
- If AI generation fails, keep all saved prefixes and current active selection unchanged.
- If a preview selection is too large, show a validation message instead of launching too many generations.
- If a prefix item is malformed, reject it before saving.

## Compatibility and Migration

The new feature should remain compatible with existing configurations that only contain a single `comfyui.image.prompt_prefix`.

Recommended compatibility behavior:

- preserve current generation behavior for users who never use the new library UI
- optionally seed the library from existing configured `prompt_prefix` when practical
- avoid destructive migration
- prefer additive configuration evolution

If a compatibility bootstrap is implemented, it should be explicit and safe:

- create one imported custom library item from the old single prefix
- do not discard the previous value silently

## Testing Strategy

Prefer testing pure helpers and config transformations instead of only relying on full Streamlit rendering.

Minimum coverage:

- default built-in library loads when new config fields are absent
- active prefix resolution returns exactly one effective prefix
- preview selection supports multiple items without affecting active selection
- category filtering works across style and scene dimensions
- manual prefix creation validates required fields
- LLM result parsing produces valid prefix items
- incomplete LLM config disables AI generation safely
- deleting or editing items updates active state correctly
- compatibility behavior with existing single-prefix config is deterministic

## Out of Scope

This design does not include:

- redesigning the full page layout outside the prompt-prefix area
- introducing workflow-specific prefix libraries
- changing the underlying image generation workflow files
- turning real generation into multi-prefix composition
- adding a database or remote storage layer
- replacing the existing prompt helper contract

## Rollout Notes

The value of this feature comes from turning prompt prefixes into reusable product assets instead of transient text.

After implementation, users should be able to:

- browse ready-made style presets
- save their own preferred prefixes
- ask the configured LLM to generate new candidates from natural language
- compare several styles visually before committing
- keep actual generation behavior stable with one explicit active prefix
