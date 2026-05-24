# Prompt Prefix Library Design

## Goal

Upgrade the current single image `prompt_prefix` text input into a global prompt-prefix library that supports:

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

### 4. Scope Boundary

This feature applies to image prompt prefixes only.

Important scope rules:

- the new library governs image-generation prefix selection
- existing `comfyui.video.prompt_prefix` behavior remains unchanged
- video-template preview can keep the current single-prefix behavior
- if a future video-prefix library is needed, it should be designed separately instead of being coupled into this rollout

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
- localized style tag
- localized scene tag
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
- style category selector
- scene category selector
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
- the system generates a bounded preview batch with the same base prompt and different prefixes
- each preview card shows the result plus the associated prefix name
- each preview card can promote its prefix to active

Formal generation remains single-prefix even when preview is multi-prefix.

Execution rule:

- preview comparison should run sequentially by default, not as unrestricted concurrent generation
- the UI may present results side by side after generation completes
- future concurrency optimization is optional and must respect self-hosted resource limits and RunningHub quota limits

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
comfyui:
  image:
    default_workflow: selfhost/image_z_image_turbo.json
    prompt_prefix: "legacy fallback only"
    prompt_prefix_library:
      active_prefix_id: builtin_childrens_storybook_warm
      items:
        - id: builtin_childrens_storybook_warm
          name: Childrens Storybook Warm
          content: warm children's storybook illustration, soft lighting, gentle hand-painted texture, clean composition, expressive characters
          style_category_id: storybook
          scene_category_id: childrens_story
          source: builtin
          is_builtin: true
          note: Suitable for warm, healing, family-friendly content
          created_at: 2026-04-20T00:00:00Z
```

Each prefix item should include:

- `id`: stable unique identifier
- `name`: user-facing display name, free text in the current UI language
- `content`: actual English prefix text used in prompt assembly
- `style_category_id`: stable ASCII style category id
- `scene_category_id`: stable ASCII scene category id
- `source`: `builtin`, `manual`, or `llm`
- `is_builtin`: whether the item is protected as a system preset
- `note`: optional short explanation
- `created_at`: audit-friendly creation time

Library state should also track:

- `active_prefix_id`: the single effective prefix for real generation

Category display labels should not be stored as the source of truth.

Instead:

- persist stable category ids in config
- render localized labels from a fixed mapping in the UI and generator helpers
- keep item `name` and `note` as user-facing free text

## Configuration and Persistence

Recommended persistence strategy:

- keep using the existing config management system
- store the prefix library under `comfyui.image.prompt_prefix_library` in `config.yaml`
- avoid introducing a new persistence technology

Important rules:

- missing library config should gracefully fall back to built-in presets
- reading config should not silently rewrite user files
- create, edit, delete, duplicate, and set-active actions are explicit user mutations and should persist immediately through the config manager
- preview selections, filters, and search state are session-level UI state and should not persist to config
- built-in presets should be available by default without requiring a save on first read

### Schema Alignment Requirements

This design requires schema and round-trip support, not only UI state.

Minimum implementation requirements:

- add a `PromptPrefixItemConfig` model
- add a `PromptPrefixLibraryConfig` model
- extend `ImageSubConfig` with `prompt_prefix_library`
- add config-manager helpers for reading and mutating the image prefix library
- ensure `model_dump()` and `save()` preserve the new structure without dropping fields

## Built-In Preset Strategy

The system should ship with a starter library so users do not face an empty state.

Recommended initial coverage by style:

- storybook
- flat_illustration
- minimal_line_art
- watercolor
- cartoon_3d
- cinematic_realism
- anime
- chinese_traditional

Recommended initial coverage by scene:

- childrens_story
- educational_illustration
- emotional_copywriting
- knowledge_sharing
- commercial_cover
- short_video_illustration

Built-in presets should:

- be immediately usable
- be visible in the same library as custom items
- support copy/clone into custom items
- not be casually overwritten in place
- render localized human-readable labels from these stable ids

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
- provide a user-facing display name in the current UI language
- assign both style and scene category ids from a predefined allowed list
- provide a short user-facing note in the current UI language
- output several candidates in a structured shape

### Output Shape

Recommended default: 4 candidates per generation request.

Each candidate returns:

- `name`
- `content`
- `style_category_id`
- `scene_category_id`
- `note`

### Post-Generation Actions

Generated candidates should not automatically override the active prefix.

Each result should support:

- add to library
- add to preview
- set as active

Persistence rule:

- `add to library` persists immediately
- `set as active` persists immediately
- `add to preview` affects only the current session preview batch

### Language Rule

Use:

- English for `content`
- current-UI-language free text for `name` and `note`
- stable ASCII ids for categories

This keeps the UI friendly while preserving better compatibility with image-generation models.

### Failure Behavior

If LLM configuration is incomplete or the generation call fails:

- show a clear message
- keep manual creation and manual selection fully available
- do not block the rest of the style workflow

## Generation Behavior

Actual generation behavior should stay simple and deterministic.

Rules:

1. For image generation, if an active library prefix exists, use that single prefix as a style source.
2. If the image prefix library is absent or has no valid active item, use structured scene prompting without silently activating `comfyui.image.prompt_prefix`.
3. Preview comparison may use multiple selected prefixes, but each preview image is still generated with exactly one explicit prefix source at a time.
4. Video generation must follow the same explicit-source rule; saved config text is not an implicit source.

Prompt assembly must produce one coherent final prompt:

- each selected style source is resolved into structured style semantics first
- final prompt assembly fuses scene, style, IP, text policy, and workflow constraints semantically
- no raw prefix concatenation is allowed in production generation

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
- If the active prefix is deleted or missing, clear active state or fall back to a safe built-in default, then to legacy `comfyui.image.prompt_prefix` if needed.
- If the LLM is not configured, disable only the AI generator.
- If AI generation fails, keep all saved prefixes and current active selection unchanged.
- If a preview selection is too large, show a validation message instead of launching too many generations.
- If a prefix item is malformed, reject it before saving.

## Compatibility and Migration

The new feature should remain compatible with existing configurations that only contain a single `comfyui.image.prompt_prefix`.

Recommended compatibility behavior:

- preserve current generation behavior for users who never use the new library UI
- optionally seed the library from existing configured `comfyui.image.prompt_prefix` when practical
- avoid destructive migration
- prefer additive configuration evolution
- leave `comfyui.video.prompt_prefix` untouched in this rollout

If a compatibility bootstrap is implemented, it should be explicit and safe:

- create one imported custom library item from the old single prefix
- do not discard the previous value silently
- do not require users to migrate video prefix settings

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
- redesigning video prompt-prefix management
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
