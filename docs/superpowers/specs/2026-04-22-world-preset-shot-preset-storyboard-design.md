# World Preset and Shot-Preset Storyboard Design

## Goal

Upgrade the current copy-to-prompt flow from style-aware prompt assembly into a storyboard-first generation system built on:

- `world preset`
- `cast bible`
- `shot preset`
- `storyboard planner`
- `consistency guard`

This rollout must:

- keep knowledge content as the first priority
- support strong IP-style world packaging such as "Angry Birds version of Romance of the Three Kingdoms"
- support both topic-rich content and concept-only content
- keep multi-frame style, role, and world elements more stable even when the model does not support character reference inputs
- allow users to manually choose a shot-rhythm template
- preserve graceful degradation across model capability levels

## Non-Goals

This rollout does not include:

- mandatory character-reference support for every model
- turning every workflow into an image-edit or reference-image workflow
- replacing the existing prompt-prefix library UI with a fully separate product surface
- full post-generation VLM scoring as a required V1 gate
- solving identity-perfect character continuity across unlimited episodes using prompt text alone

## Current Problems

The current styled prompt pipeline already improves visual style handling, but it still has four major gaps:

1. It is better at keeping visual style consistent than keeping roles and world entities consistent.
2. It does not yet distinguish clearly between content that already has canonical entities and content that needs a default explainer cast.
3. Shot distance and shot rhythm are not first-class planning inputs, so outputs can collapse into repetitive mid shots.
4. When a model lacks character-reference support, the system does not yet have a strong text-first continuity contract beyond style guidance.

## Content Modes

V1 should treat all copy input as one of two planning modes.

### 1. `theme_mapping`

Use this mode when the content already contains strong semantic anchors such as:

- named characters
- factions
- canonical props
- historical relationships
- narrative worlds

Example:

- "How to study Romance of the Three Kingdoms"

In this mode, the system should preserve the original educational meaning first, then remap the theme into the selected IP-like world.

### 2. `concept_explainer`

Use this mode when the content is mainly conceptual and does not contain a ready-made cast or world.

Example:

- "What is penicillin"

In this mode, the system should activate a preset-defined explainer world with a stable host cast, stable teaching props, and a stable educational scene language.

## Explored Approaches

### 1. Lightweight Prompt-Only Expansion

Keep the current flow mostly unchanged and rely on:

- free-text world prefix
- free-text shot hints
- LLM interpretation at generation time

Pros:

- lowest implementation cost
- smallest change to current flow

Cons:

- weak role continuity
- weak world continuity
- weak shot-distribution reliability

### 2. Balanced Structured Prompt System

Add:

- `world preset`
- `cast bible`
- `shot preset`

while keeping generation mostly prompt-centric.

Pros:

- much stronger continuity than free-text-only prompt generation
- moderate implementation cost

Cons:

- still less controllable than full storyboard planning
- harder to preview and override frame-level intent before generation

### 3. Storyboard-First Structured System

Generate a structured frame plan before prompt generation, based on:

- selected world preset
- selected shot preset
- content mode
- cast rules

Pros:

- strongest controllability
- strongest multi-frame consistency
- cleanest place to add future human review and model-specific fallbacks

Cons:

- highest implementation complexity
- requires new intermediate planning objects

## Approved Approach

Use the storyboard-first structured system.

This is the best match for the confirmed product direction:

- knowledge clarity must outrank style packaging
- users must be able to choose a shot-rhythm template
- the system must still work when character-reference support is missing
- long-term role and world continuity matter more than minimum implementation cost

## Design Summary

The new generation flow changes from:

`copy -> styled prompt batch -> generation`

to:

`copy -> content-mode routing -> world preset -> cast bible -> shot preset -> storyboard planner -> consistency guard -> prompt builder -> generation`

Core rule:

- the model should not be asked to directly improvise final frame prompts from copy alone
- the model should first help produce a structured explanation plan for what each frame is supposed to do

## Core Product Rules

### 1. Knowledge meaning comes first

The system must prioritize educational clarity before IP packaging.

This means:

- "Angry Birds version of Romance of the Three Kingdoms" is still fundamentally about learning Three Kingdoms
- the selected world preset may package the theme, but may not replace the educational subject

### 2. Style consistency is necessary but insufficient

The system must maintain three layers of consistency:

- semantic consistency
- world consistency
- visual consistency

V1 may not solve all identity drift, but it must explicitly model all three layers.

### 3. Shot variation is a hard requirement

A valid image batch must not collapse into one repeated shot distance.

The planner must produce a reasonable distribution across:

- long shot
- full shot
- medium shot
- close-up
- extreme close-up

### 4. User-facing control stays simple

The frontend should expose only a small number of high-value controls by default:

- world preset
- shot preset
- consistency strength
- scene count

Advanced controls may be expandable, but the default UX should remain understandable.

## World Preset

`world preset` is the main product-facing universe selector. It is not just a free-text prompt prefix.

Each preset should define:

- `preset_id`
- `display_name`
- `mode`: `theme_mapping` or `concept_explainer`
- `style_core`
- `world_elements`
- `knowledge_scene_rules`
- `negative_rules`
- `default_shot_preset_ids`
- `cast_slots`

### Example responsibilities

For "Angry Birds version of Three Kingdoms", the preset defines:

- the cartoon-material and silhouette language
- recurring scene props such as slingshot structures, wooden towers, scrolls, camp flags, and battlefield maps
- educational staging rules such as "history is taught through camp strategy boards, scrolls, and role comparison scenes"

For "Angry Birds knowledge classroom", the preset defines:

- a fixed explainer world
- classroom or lab-like repeated scene motifs
- a stable teaching grammar for concept-only topics

## Cast Bible

`cast bible` is the text-first continuity contract for recurring roles.

This layer is required even when the model does not support character references.

Each cast slot should define:

- `slot_id`
- `semantic_role`
- `visual_anchor`
- `prop_anchor`
- `personality_anchor`
- `theme_mapping_rule`
- `reuse_priority`

### `theme_mapping` behavior

When content contains canonical entities, the system should map them into preset slots.

Example:

- Liu Bei maps to the Shu leader slot
- Cao Cao maps to the Wei leader slot
- Guan Yu and Zhang Fei map to fixed warrior slots

### `concept_explainer` behavior

When content lacks natural characters, the system should activate stable explainer roles, such as:

- host explainer
- learner
- assistant or demonstrator

These roles should recur across concept-only topics instead of being reinvented per task.

## Shot Preset

`shot preset` is the user-selectable rhythm template for scene planning.

It should not be modeled as a rigid frame-by-frame hardcoded sequence. Instead, it should be modeled as a distribution and transition rule set.

Each shot preset should define:

- `preset_id`
- `display_name`
- `supported_scene_count`
- `shot_distribution_rules`
- `opening_rules`
- `closing_rules`
- `transition_rules`
- `purpose_bias`
- `override_policy`

### Recommended initial shot presets

- `balanced_explainer`
- `opening_world_building`
- `detail_focus`
- `character_relationship`
- `classroom_demo`

### Hard shot rules

At minimum, V1 should enforce:

- at least three distinct shot distances in one batch when scene count allows it
- no more than two consecutive frames of the same shot type
- close-up and extreme close-up must serve a knowledge point, not random magnification
- opening frames should usually establish world, subject, or context

## Storyboard Planner

`storyboard planner` is the new center of the system.

Its job is to turn:

- copy
- content mode
- world preset
- cast bible
- shot preset

into a structured frame plan before final prompt construction.

Each frame plan should define:

- `scene_id`
- `narration_fragment`
- `knowledge_goal`
- `shot_type`
- `shot_purpose`
- `primary_subject`
- `secondary_subjects`
- `world_elements`
- `continuity_anchors`
- `focus_detail`
- `prompt_intent`

### Why this layer matters

Without a frame plan, the model tends to optimize for local prompt quality. With a frame plan, the system can optimize for whole-batch explanation quality.

This is the main mechanism that prevents:

- topic drift
- character drift
- repeated framing
- missing educational structure

## Prompt Builder

`prompt builder` converts the structured frame plan into generation-ready prompt inputs.

It should combine:

- frame intent
- resolved world preset
- selected cast anchors
- selected shot intent
- style-resolution output

The final prompt assembly should include:

- frame-level knowledge purpose
- shot-distance wording
- stable role anchors
- recurring world elements
- selected preset style language

If the workflow supports optional fields, it may also include:

- `negative_prompt`
- role/reference attachments

If the workflow does not support such fields, the system must degrade to text-only continuity without breaking the pipeline.

## Consistency Guard

`consistency guard` should operate at three stages.

### 1. Pre-Planning Validation

Validate whether:

- the chosen world preset fits the content type
- the chosen shot preset fits the requested scene count
- the requested combination is internally coherent

### 2. Post-Planning Validation

Validate whether the storyboard plan satisfies:

- knowledge-theme continuity
- role continuity
- world-element continuity
- shot-distribution rules

### 3. Pre-Prompt Validation

Validate whether the final prompt inputs still contain required anchors:

- educational subject
- role identity
- world motifs
- shot wording
- key negative rules

### Optional future stage

V2 may add post-generation validation through VLM or image-understanding checks, but this is not required for V1 rollout.

## Model Capability Tiers

The system must adapt to model capability instead of assuming all workflows support the same control surface.

### Tier A

Supports:

- character references
- stronger structured control

Use:

- world preset
- cast bible
- shot preset
- storyboard planner
- optional character-reference attachments

### Tier B

Does not support character references, but follows structured text prompts well.

Use:

- world preset
- cast bible
- shot preset
- storyboard planner
- stronger text anchors

### Tier C

Has weak reference support and weaker planning fidelity.

Use:

- world preset
- stricter cast wording
- stricter shot-distribution enforcement
- lower planner freedom

The user-facing product should stay stable while the backend adapts to model capability automatically.

## User Experience Design

### Default controls

The default user flow should expose:

- `world preset`
- `shot preset`
- `consistency strength`
- `scene count`

### Advanced controls

Expandable advanced settings may expose:

- role strategy: auto / stable explainer cast / theme mapping
- role locking strength
- shot strategy: adaptive / strict preset
- per-frame overrides

### Pre-Generation Storyboard Preview

The system should present a storyboard preview before final generation.

Each frame card should show:

- shot type
- frame purpose
- primary subject
- key world elements
- intended knowledge point

This preview is a major product benefit of the storyboard-first system because it allows correction before image generation spend.

## Backward Compatibility

This rollout should remain compatible with the current styled prompt pipeline.

Rules:

1. Existing prefix-library and style-resolution behavior stays usable.
2. If no world preset is selected, a safe default preset may be applied.
3. If the model does not support character references, the flow must continue through text-only cast anchors.
4. If shot planning fails, the system may fall back to a conservative default shot preset instead of failing the whole task.
5. Existing simple prompt-generation endpoints may coexist during migration, but the new storyboard-first path should become the preferred route.

## Files and Systems in Scope

Expected implementation work will likely touch:

- new world-preset configuration and schema files
- new cast-bible models
- new shot-preset configuration and schema files
- new storyboard planning models
- prompt-building helpers
- style-resolution integration points
- standard and preview generation entry points
- frontend controls for world preset and shot preset
- tests for content routing, shot distribution, and continuity validation

## Risks

### 1. Over-engineering the first rollout

The storyboard-first system is heavier than the current flow.

Mitigation:

- keep V1 fields focused
- expose only a small default control set
- defer advanced visual post-checking

### 2. Prompt overload

Too many anchors can make prompts bloated or conflicting.

Mitigation:

- keep the structured planner as the source of truth
- avoid blindly concatenating every possible field
- prefer compact, role-aware final prompts

### 3. Weak continuity on low-capability models

Text-only continuity will still have limits.

Mitigation:

- encode continuity in cast bible and world anchors
- reduce planner freedom on weaker models
- surface "consistency strength" controls and capability-aware fallbacks

### 4. Mechanical shot planning

If shot presets are too rigid, outputs may feel formulaic.

Mitigation:

- use rule-based distributions instead of fixed rigid sequences
- let the planner adapt inside preset boundaries

## Success Criteria

This design is successful if:

1. the system clearly distinguishes `theme_mapping` and `concept_explainer` content
2. users can select a `world preset` and a `shot preset`
3. the planner produces a structured frame plan before prompt generation
4. role and world continuity are visibly stronger even without character-reference support
5. one batch no longer collapses into one repeated shot distance
6. knowledge meaning remains clear while IP-style packaging is applied
7. users can review storyboard intent before spending on final generation
8. backend behavior degrades safely across model capability tiers
