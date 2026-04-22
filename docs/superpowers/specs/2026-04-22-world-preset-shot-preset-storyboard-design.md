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

`copy -> content-mode routing -> world preset -> style-source normalization -> cast bible -> shot preset -> storyboard planner -> consistency guard -> prompt builder -> generation`

Core rule:

- the model should not be asked to directly improvise final frame prompts from copy alone
- the model should first help produce a structured explanation plan for what each frame is supposed to do

## Source Precedence and Compatibility

The new system must define a strict precedence order between:

- selected `world preset`
- request-scoped `prompt_prefix`
- active `prompt_prefix_library` item
- existing style-resolution output

Rules:

1. `world preset` is the top-level universe contract.
2. Existing `prompt_prefix` sources are subordinate style modifiers, not equal competitors to the selected world preset.
3. If a selected or resolved prefix attempts to introduce a different `ip_world` or incompatible narrative universe, that prefix must not override the selected world preset.
4. If no world preset is selected, behavior depends on the entry path:
   - storyboard-first entry points must resolve an explicit safe default preset before planning
   - legacy styled-prompt entry points may continue on the existing styled-prefix fallback path

### Compatibility normalization

Before prompt building, the system should normalize style inputs into one of three outcomes:

- `compatible_refinement`
- `visual_only_refinement`
- `conflicting_world_override`

Behavior:

- `compatible_refinement`: preserve useful style cues from the prefix
- `visual_only_refinement`: keep only material, palette, composition, or lighting cues
- `conflicting_world_override`: drop or downgrade the conflicting world-level prefix signal

This prevents double-universe prompt assembly such as:

- one selected world preset for "Angry Birds Three Kingdoms"
- another runtime prefix that tries to inject a different `ip_world`

The `prompt builder` should consume normalized style output, not blindly merge all upstream style text.

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

### 5. Content routing must be explicit and recoverable

The system must not silently route content into `theme_mapping` or `concept_explainer` without a recoverable contract.

Rules:

- the user may explicitly override the mode
- if the user does not override, the backend may classify automatically
- the classifier must emit machine-readable confidence and rationale
- low-confidence routing must not silently behave like a high-confidence decision

This rule exists because mode routing determines:

- cast strategy
- world interpretation
- storyboard behavior
- prompt composition

## World Preset

`world preset` is the main product-facing universe selector. It is not just a free-text prompt prefix.

Each preset should define:

- `preset_id`
- `display_name`
- `supported_modes`: one or both of `theme_mapping` and `concept_explainer`
- `forced_mode`: optional; when present, the preset is treated as single-mode
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

World presets should also declare:

- whether they are single-mode or dual-mode through `supported_modes`
- whether they define different cast policies for different supported modes
- what the conservative fallback mode is when auto-routing confidence is low

V1 schema rule:

- `supported_modes` is the source of truth for mode compatibility
- `forced_mode` may only be set to one value already listed inside `supported_modes`
- single-mode presets should use `supported_modes` with one entry plus matching `forced_mode`
- dual-mode presets should omit `forced_mode`

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

## Content Mode Routing Contract

### Compatibility gate

Mode routing must first validate whether the selected world preset supports the requested mode.

Rules:

- if the user sets a mode override that is not listed in `supported_modes`, pre-planning validation must return a configuration conflict
- if the preset declares `forced_mode` and the user override does not match it, the system must block generation and ask the user to either change the preset or clear the override
- the system must not silently rewrite a conflicting user override into another mode

### Resolution order

After compatibility is validated, automatic mode selection should follow this strict order:

1. `forced_mode`, if the preset is single-mode
2. compatible user-specified mode override
3. automatic classifier result
4. preset conservative fallback mode

The automatic classifier should return:

- `mode`
- `confidence`
- `mixed_content_flag`
- `dominant_anchor_type`
- `reason_summary`

### Confidence behavior

The automatic classifier should emit numeric confidence in the range `[0, 1]`.

V1 default threshold:

- `0.70`

Recommended V1 behavior:

- high confidence: use classifier result directly
- low confidence: fall back to the preset's conservative mode and surface a warning in the storyboard preview

Threshold contract:

- preview and final generation must use the same resolved threshold for one task
- V1 should read the threshold from one backend configuration source
- a world preset may optionally override the default threshold, but only through explicit preset metadata rather than ad hoc prompt logic

### Mixed-content rule

Mixed-content input should still resolve to one primary mode.

Decision rule:

- use `theme_mapping` when canonical entities are themselves the teaching subject
- use `concept_explainer` when canonical entities are only examples inside a broader conceptual explanation

This avoids introducing a third planning mode while still handling borderline copy.

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

### Repair policy

Shot presets must define what happens when the first planner output violates shot rules.

Recommended repair order:

1. break illegal consecutive shot runs
2. inject missing shot-distance diversity into the lowest-priority unlocked frames
3. repair opening and closing rule violations
4. re-balance extreme close-up usage
5. if still invalid, fall back to a conservative default shot preset and surface that downgrade to the user

The system must not stop at validation failure without a defined repair path.

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
- `locked_fields`
- `frame_source`
- `replan_scope`
- `planner_version`

### Why this layer matters

Without a frame plan, the model tends to optimize for local prompt quality. With a frame plan, the system can optimize for whole-batch explanation quality.

This is the main mechanism that prevents:

- topic drift
- character drift
- repeated framing
- missing educational structure

### Preview-edit and replan contract

The storyboard preview is not read-only. V1 should define how user edits survive replanning.

Rules:

- user-edited fields become locked fields for that frame
- locked fields must not be silently overwritten by later local replanning
- local replanning is the default after a single-frame edit
- global replanning should happen only after explicit user action or after top-level inputs change

Recommended `replan_scope` values:

- `local`
- `adjacent`
- `global`

Recommended behavior:

- editing one frame defaults to `local`
- shot-balance repair may adjust adjacent unlocked frames if necessary
- world preset or shot preset changes trigger `global` replan

This avoids a common failure mode where the user fixes one frame and the system silently rewrites it on the next pass.

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

The `prompt builder` must also respect normalized style precedence:

- world preset identity first
- cast continuity second
- shot-purpose and knowledge intent third
- compatible style refinements last

## Consistency Guard

`consistency guard` should operate at three stages.

### 1. Pre-Planning Validation

Validate whether:

- the chosen world preset fits the content type
- the requested mode override is allowed by the selected world preset
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

### Capability source of truth

Capability must not be guessed from model nicknames, workflow names, or prompt text.

V1 source of truth should be:

- parsed selfhost workflow metadata
- explicit runninghub wrapper capability metadata
- explicit backend capability registry when the workflow layer exposes structured flags

If capability metadata is missing, the system must degrade to the safest lower tier rather than guessing.

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

This keeps capability routing aligned with the earlier workflow-capability design direction and prevents brittle name-based behavior.

## User Experience Design

### Default controls

The default user flow should expose:

- `world preset`
- `shot preset`
- `consistency strength`
- `scene count`

### Consistency Strength Contract

`consistency strength` must be a real backend contract, not just a UI label.

V1 should expose:

- `standard`
- `strong`

Recommended behavior:

- `standard`: balanced planner freedom, normal cast reuse, conservative repair on unlocked frames, compact prompt anchors
- `strong`: tighter cast reuse, stronger world-element carry-over, lower planner freedom on weaker models, denser continuity anchors, more aggressive repair before falling back

This setting should influence at least:

- cast reuse and locking policy
- planner freedom
- shot-repair aggressiveness
- continuity-anchor density in prompt construction
- downgrade behavior on weaker capability tiers

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

Per-frame overrides should initially allow:

- shot type
- primary subject
- focus detail
- key world elements

The system should not claim editable preview support without preserving these edits through the replan contract.

## Persistence Scope

The system must separate:

- reusable preset assets
- runtime plan state
- immutable task snapshots

### 1. Reusable assets

These should be treated as project-level editable assets in V1:

- custom world presets
- custom shot presets
- custom cast-bible definitions

Built-in presets remain read-only defaults.

Global cross-project preset libraries are out of scope for V1.

### 2. Runtime state

These should remain task-local or session-local:

- preview selections
- current storyboard draft
- unlocked/locked frame editing state before final generation

### 3. Immutable task snapshot

When a task is submitted, the system should persist a snapshot of:

- selected world preset
- resolved cast bible
- selected shot preset
- final storyboard plan
- normalized style inputs

History replay and task inspection must use this task snapshot, not the latest mutable preset definitions.

This prevents old tasks from changing behavior after users later edit a shared preset.

## Backward Compatibility

This rollout should remain compatible with the current styled prompt pipeline.

Rules:

1. Existing prefix-library and style-resolution behavior stays usable.
2. If no world preset is selected, storyboard-first entry points must resolve an explicit safe default preset, while legacy styled-prompt entry points may continue on the existing styled-prefix fallback path.
3. If the model does not support character references, the flow must continue through text-only cast anchors.
4. If shot planning fails, the system may fall back to a conservative default shot preset instead of failing the whole task.
5. Existing simple prompt-generation endpoints may coexist during migration, but the new storyboard-first path should become the preferred route.
6. Historical tasks should remain reproducible through stored task snapshots even if shared presets are later edited.

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
