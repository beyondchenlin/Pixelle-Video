# Image Style Profile Backend Design

## Goal

Upgrade the current image style system from simple prefix concatenation to a backend flow based on style resolution, structured constraints, and strategy-based prompt generation.

This rollout must:

- keep the current frontend interaction unchanged
- support template-like visual styles similar to Fooocus
- support stronger `ip_world` behavior for world-building styles
- improve multi-frame consistency by sharing one resolved style contract across the whole task
- stay compatible with the existing `prompt_prefix_library`
- keep request-time temporary prefix overrides working
- keep preview output semantically aligned with real generation

## Non-Goals

This rollout does not include:

- new frontend fields or new frontend editing flows
- reference-image character consistency
- mandatory model replacement
- mandatory `negative_prompt` support for every workflow

## Current Problems

The current pipeline has four main problems:

1. The style prefix is applied only as late string concatenation.
2. `ip_world` styles such as Angry Birds or Plants vs. Zombies are treated like ordinary visual prefixes.
3. The same prefix may be interpreted differently across tasks, which weakens consistency.
4. `prompt_prefix_library` stores free text only and has no structured style meaning.

## Design Summary

The new design has two layers:

1. A surface prefix library layer that keeps the current product shape.
2. A backend `style_profile` layer that stores structured style meaning.

The generation flow changes from:

`prefix + base_prompt`

to:

`prefix item -> style resolution -> style_profile -> style-guided base prompt generation -> final prompt assembly`

Important distinction:

- `scene + character action + emotion + symbolic elements` stays as the writing skeleton for each single image prompt
- `style_profile` sits above that skeleton and constrains the whole batch

## Core Rules

### 1. `style_kind` must stay

`style_kind` is a required backend routing field with three values:

- `visual_only`
- `ip_world`
- `hybrid`

Meaning:

- `visual_only`: mainly changes material, palette, lighting, composition, and atmosphere
- `ip_world`: must affect subject redesign, world elements, and shared universe feel
- `hybrid`: combines visual language and narrative tone, but does not default to replacing the subject with an existing IP character

### 2. `ip_world` cannot rely on simple prefix concatenation

When `style_kind = ip_world`, the system must use:

- `subject_policy`
- `world_elements`
- `consistency_anchor`

and must apply them during `base prompt` generation, not only after it.

### 3. Style resolution results should be cached per prefix item

The same prefix should not be reinterpreted from scratch on every task.

In V1, resolved style metadata should be cached by prefix identity in runtime memory, not auto-written back into global config during generation.

This lets the system:

- improve consistency
- reduce LLM calls
- support future model upgrades without redesigning the style layer
- avoid mutating shared config during normal generation

## Data Model

### Existing Surface Fields

These fields stay and remain the frontend-facing shape:

- `id`
- `name`
- `content`
- `style_category_id`
- `scene_category_id`
- `source`
- `is_builtin`
- `note`
- `preview_asset_path`
- `workflow_preview_assets`
- `created_at`

### Runtime Resolved Object

V1 introduces a backend-only runtime object, referred to here as `ResolvedStyleSpec`.

Recommended fields:

- `style_kind`
- `prompt_template`
- `negative_prompt`
- `style_profile`
- `content_hash`
- `resolver_version`
- `source_identity`

Purpose:

- `prompt_template` borrows the Fooocus-style wrapper idea
- `negative_prompt` supports compatible workflows now and stronger models later
- `style_profile` stores structured style constraints
- `content_hash` detects whether source prefix content changed
- `resolver_version` invalidates old runtime cache after resolver upgrades
- `source_identity` distinguishes library items from request-scoped temporary prefixes

### Persisted Structured Fields

Persisting resolved style metadata back into `PromptPrefixItemConfig` is not part of V1 generation flow.

Reason:

- current config writes are whole-object updates
- concurrent tasks can overwrite each other
- normal generation should not silently mutate global user config

Future persistence can be added later behind an explicit save or migration flow.

## Minimal `style_profile`

V1 uses a small field set:

- `style_kind`
- `subject_policy`
- `shape_language`
- `material`
- `palette`
- `lighting`
- `world_elements`
- `consistency_anchor`
- `negative_rules`

Field intent:

- `subject_policy`: whether the subject stays semantically the same, is redesigned, or must not be replaced
- `shape_language`: rounded geometric, soft silhouettes, sharp graphic shapes, and similar guidance
- `material`: watercolor, clay, paper, clean cartoon surface, and similar guidance
- `palette`: color tendency
- `lighting`: light and atmosphere tendency
- `world_elements`: props, background elements, and universe cues
- `consistency_anchor`: shared series-level constraint across all frames
- `negative_rules`: what the prompt should avoid falling back into

## Style Resolution Pipeline

### Step 1: Resolve the prefix input source

The backend must support two input sources:

1. Request-scoped temporary prefix override
2. Active prefix item from the global library

Rules:

- if the request explicitly passes `prompt_prefix`, treat it as an ephemeral style source for this request only
- if no request override exists, use the active library item
- the ephemeral path must use the same style resolver as the library path
- ephemeral resolution must not write anything back to the library

### Step 2: Reuse or build structured style metadata

Use a runtime cache as the V1 source of truth.

Cache key recommendation:

- library item: `library:{item_id}:{content_hash}:{resolver_version}`
- request override: `request:{content_hash}:{resolver_version}`

Reuse a cached resolved result only if:

- a runtime cache entry exists
- `content_hash` matches current `content`
- `resolver_version` matches the current resolver version

Otherwise, call a new style-resolution prompt that returns:

- `style_kind`
- `prompt_template`
- `negative_prompt`
- `style_profile`

V1 rule:

- generation may populate the runtime cache
- generation must not auto-persist resolver output into `config.yaml`

### Step 3: Generate image prompts with style guidance

Extend `image_generation.py` so the LLM receives:

- `style_profile_json`
- `narrations_json`

The prompt must explicitly require:

- one shared `style_profile` for the whole narration batch
- one image prompt per narration
- continued use of `scene + character action + emotion + symbolic elements`
- subject design, material, palette, and world elements to obey `style_profile` first

### Step 4: Assemble the final prompt by strategy

#### `visual_only`

Preferred behavior:

- wrap `base prompt` using `prompt_template` if available
- otherwise fall back to simple positive prefixing
- raw `content` may still be used as fallback positive text when needed

#### `ip_world`

Preferred behavior:

- do not depend on simple prefix concatenation
- force world-constrained subject redesign inside `base prompt` generation
- allow `prompt_template` only as a secondary helper
- raw `content` is not blindly prepended at the end
- any lexical carryover that must survive into final prompt must be emitted by the resolver through `prompt_template` and `style_profile`

#### `hybrid`

Preferred behavior:

- use `style_profile` to shape both visual language and narrative tone
- optionally use `prompt_template` if it is helpful and not redundant
- raw `content` may be retained only when it adds non-duplicated signal

## Prompt Assembly Rules

New assembly rules:

1. `base prompt` is generated from `narration + style_profile`
2. `prompt_template` is an optional outer wrapper, not the only style mechanism
3. `negative_prompt` is passed only when the workflow supports it

Recommended final order:

- `base prompt`
- optional `prompt_template`
- optional fallback raw prefix text

The system must stop treating raw `content` as the only source of style meaning.

Additional assembly rules:

- `visual_only`: fallback raw prefix text is allowed
- `ip_world`: fallback raw prefix text is disallowed by default
- `hybrid`: fallback raw prefix text is allowed only if it adds signal not already captured by resolver output

This removes ambiguity around when raw prefix text may appear in final prompt.

## Workflow Compatibility

### Positive prompt

Already supported by the current image workflows because they expose `prompt`.

### Negative prompt

`negative_prompt` should be part of the backend design even if the current default workflow does not expose it yet.

Compatibility rules:

- if the workflow exposes `negative_prompt`, pass it through
- if the workflow does not expose it, keep the field but do not force usage
- if the team later switches to a stronger model or a different workflow, reuse the same style-resolution layer

### Capability detection source of truth

Workflow capability must not be guessed from prompt text or workflow name.

V1 source of truth:

- for selfhost workflows, use parsed workflow parameter metadata
- if `WorkflowParser` reports `negative_prompt` as an exposed parameter, pass it through
- if the parsed workflow metadata does not expose it, do not pass it
- for runninghub wrappers, use explicit wrapper metadata if present
- if a runninghub wrapper does not declare capability metadata, default to not passing optional fields such as `negative_prompt`

### Why this matters

This keeps the style system independent from the currently selected image workflow:

- current `z-image` can keep using positive prompt only
- future workflows can adopt `negative_prompt`, edit inputs, or reference-image inputs without redesigning style resolution

## Preview Parity

Frontend layout does not need to change, but preview semantics must match real generation semantics.

Rule:

- all preview entry points must call the same backend prompt-assembly pipeline used by formal generation
- preview code must stop directly calling old string-only prefix concatenation helpers

This matters because otherwise users will see preview results that do not match the new style-aware generation path.

## Backward Compatibility

The rollout must remain compatible with existing config and library items.

Rules:

1. existing `content` remains valid input
2. old prefix items without structured fields are resolved lazily on first use
3. if resolution fails, the system falls back to current simple prefix concatenation
4. the current frontend input shape stays unchanged
5. request-scoped temporary prefixes remain supported without requiring library save

## Files in Scope

Expected backend work touches:

- `pixelle_video/config/schema.py`
- `pixelle_video/config/prompt_prefix_library.py`
- a new runtime style-resolution helper
- a new workflow capability helper
- a new style-resolution prompt file
- `pixelle_video/prompts/image_generation.py`
- `pixelle_video/utils/content_generators.py`
- `pixelle_video/pipelines/standard.py`
- `pixelle_video/utils/prompt_helper.py`
- preview-generation call sites that currently assemble prompts directly
- related tests

## Risks

### 1. Over-flexible style resolution

If the resolver prompt is too loose, `style_profile` may still drift.

Mitigation:

- keep the field set small
- enforce a strict output schema
- use versioned cache invalidation

### 2. `ip_world` degrades into a style adjective

Mitigation:

- require `subject_policy` and `world_elements` to appear in the prompt-generation instructions
- add tests specifically for `ip_world`

### 3. Workflow capabilities differ

Mitigation:

- keep style resolution separate from workflow inputs
- treat `negative_prompt`, reference-image support, and edit-model inputs as capability-gated features

### 4. Preview and generation diverge

Mitigation:

- route preview through the same backend assembly helper used by final generation
- add tests for preview/build parity

## Success Criteria

This design is successful if:

1. the current prefix library still works without frontend changes
2. the backend can resolve and cache structured style metadata per prefix item
3. `visual_only`, `ip_world`, and `hybrid` use different generation strategies
4. all frames in one task share the same `style_profile`
5. `ip_world` improves subject and world consistency in a visible way
6. request-scoped temporary prefixes still work without touching library state
7. preview and real generation use the same prompt-assembly semantics
8. unsupported workflow capabilities do not block the long-term style architecture
