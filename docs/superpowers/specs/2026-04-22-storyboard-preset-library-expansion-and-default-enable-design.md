# Storyboard Preset Library Expansion and Default Enable Design

## Goal

Expand the storyboard preset library from a minimal architecture-proofing set into a user-facing selection set, and change the main video-generation experience so storyboard planning is enabled by default.

This design covers three outcomes:

- add more `world preset` choices that reflect the product direction discussed earlier
- add more `shot preset` choices so users can choose a meaningful camera-language template
- make storyboard planning default-on for the main video workflow while still allowing users to turn it off

It also includes a maintainability cleanup for the storyboard guide UI so explanatory content is driven more by structured data and less by large inline HTML blocks.

## Current State

The current implementation in `pixelle_video/config/storyboard_preset_library.py` only ships:

- 2 world presets
  - `neutral_knowledge_storyboard`
  - `dual_mode_storyboard`
- 2 shot presets
  - `balanced_explainer`
  - `detail_focus`

The current web UI in `web/components/style_config.py` also requires users to explicitly opt in through:

- `Enable storyboard planning`

This means the product currently behaves like:

- storyboard is available
- storyboard defaults exist internally
- but the main generation path still starts from the weaker non-storyboard route unless the user deliberately enables it

That behavior is acceptable for a rollout-safe V1, but it does not match the confirmed product direction for knowledge video generation.

## Product Judgment

### 1. Preset count is too small

The current preset library is enough to validate architecture, but not enough to feel like a real product surface.

Why:

- users cannot meaningfully choose among different world-packaging strategies
- users cannot meaningfully choose among different explanation rhythms
- the current world presets are structurally valid but too abstract compared with the earlier discussion

### 2. Main video generation should default to storyboard-on

For this product, the primary use case is not one-off prompt experimentation. It is:

- knowledge explanation
- content breakdown
- theme mapping
- multi-frame storytelling

For those tasks, continuity and shot rhythm are not optional polish. They are part of the default expected quality bar.

Therefore:

- default-off is too conservative for the main video path
- default-on is the better product default

### 3. Storyboard should still be easy to disable

Default-on should not become forced-on.

Users still need a quick escape hatch when they are:

- rapidly trying styles
- validating raw prompt direction
- working with unstable outlines
- intentionally generating independent single-image ideas

So the correct product rule is:

- default enabled
- easy to disable

## Approved Default Behavior

### Main video-generation experience

Storyboard planning should be enabled by default.

UI behavior:

- `storyboard_planning_enabled` defaults to `True` on first load of the main video-generation flow
- users may manually disable it for the current session or task
- once disabled by the user, session state should respect that choice until the page/session resets

### Preset selections when storyboard is enabled

When storyboard planning is enabled:

- `world preset` should always resolve to a selected preset
- `shot preset` should always resolve to a selected preset

There should be no empty or placeholder selection state in the main storyboard UI.

Resolution order:

1. user-selected session value
2. configured library default id
3. first valid item in the corresponding library

### Where default-on does and does not apply

Default-on applies to:

- the main multi-scene video-generation flow
- workflows where storyboard planning is the recommended path

Default-on does not need to apply automatically to:

- purely exploratory style-preview tools
- standalone prompt-generation helpers
- low-commitment experimentation surfaces where the user expectation is speed over continuity

### Default-on technical contract

The current shared UI implementation uses one shared storyboard toggle inside `web/components/style_config.py`. The default-on scope must therefore be expressed as one explicit caller-provided contract rather than ad hoc branching inside multiple pages.

Approved V1 contract:

- the shared style-config renderer should accept one explicit boolean input such as `storyboard_default_enabled`
- main multi-scene video-generation entry points pass `True`
- exploratory style-preview or prompt-helper entry points pass `False` unless they deliberately opt into storyboard-first behavior
- the shared component must not infer this from page title, route name, or heuristics

State precedence:

1. user-changed session state
2. existing storyboard preview session state
3. caller-provided `storyboard_default_enabled`

This keeps one source of truth for default behavior and avoids different entry points silently diverging.

## World Preset Expansion

The built-in world preset library should move from 2 presets to a broader initial set.

### Keep existing built-ins

- `neutral_knowledge_storyboard`
- `dual_mode_storyboard`

These remain useful as:

- safe default
- neutral fallback
- compatibility/testing anchors

### Required schema contract for added world presets

The new built-in presets must not be added as prose-only concepts. Each one must be specified as a concrete `WorldPresetDefinition` payload compatible with the parent storyboard spec.

At minimum, every new built-in world preset added in this patch must declare:

- `preset_id`
- `display_name`
- `supported_modes`
- `forced_mode` when single-mode
- `style_core`
- `world_elements`
- `knowledge_scene_rules`
- `negative_rules`
- `default_shot_preset_ids`
- `conservative_fallback_mode`
- `cast_slots` or `cast_slots_by_mode`

For built-in user-facing presets, V1 should also add:

- `display_name_key`
- optional `description_key`

so the UI can localize preset names and short explanations without relying on raw English strings.

### Add new built-in world presets

#### 1. `angry_birds_three_kingdoms`

Display name:

- `Angry Birds Three Kingdoms`

Purpose:

- theme-mapping-first preset for historical or canonical-entity content

Core traits:

- Angry Birds-like silhouette and playful material language
- Three Kingdoms teaching props such as scrolls, war maps, faction banners, camp structures, and strategy boards
- stable role slots for leader, strategist, warrior, and learner perspectives
- educational subject remains historical understanding first, not pure game parody

Preferred use:

- `How to study Romance of the Three Kingdoms`
- character/faction explanations
- history-theme branded knowledge content

Required V1 contract:

- `supported_modes = ("theme_mapping",)`
- `forced_mode = "theme_mapping"`
- `conservative_fallback_mode = "theme_mapping"`
- `default_shot_preset_ids = ("character_relationship", "opening_world_building", "balanced_explainer")`
- use `cast_slots` with stable slots such as:
  - `shu_leader`
  - `wei_leader`
  - `strategist`
  - `warrior_support`
  - `learner_observer`

The implementation must not ship this preset without explicit role anchors for faction and role mapping.

#### 2. `angry_birds_knowledge_classroom`

Display name:

- `Angry Birds Knowledge Classroom`

Purpose:

- concept-explainer-first preset for general knowledge topics without natural canonical casts

Core traits:

- stable explainer cast
- classroom or lab-like recurring scene motifs
- repeatable props such as whiteboard, pointer, sample objects, labels, charts, and experiment tables
- IP packaging remains secondary to explanation clarity

Preferred use:

- `What is penicillin`
- science explainers
- general educational videos needing one repeatable host world

Required V1 contract:

- `supported_modes = ("concept_explainer",)`
- `forced_mode = "concept_explainer"`
- `conservative_fallback_mode = "concept_explainer"`
- `default_shot_preset_ids = ("classroom_demo", "balanced_explainer", "detail_focus")`
- use `cast_slots` with stable slots such as:
  - `host_explainer`
  - `learner_support`
  - `demo_assistant`

The implementation must treat this preset as a stable explainer-world preset, not a generic dual-mode placeholder.

#### 3. `angry_birds_history_classroom`

Display name:

- `Angry Birds History Classroom`

Purpose:

- a bridge preset between strict theme mapping and generic concept explanation

Core traits:

- recurring lecture-hall / archive-room / timeline-wall motifs
- stronger history-teaching atmosphere than neutral classroom presets
- good for dynasty,人物,事件,关系梳理类内容

Preferred use:

- history teaching content that is not as character-centric as Three Kingdoms
- culture/history breakdowns that still benefit from a branded world wrapper

Required V1 contract:

- `supported_modes = ("theme_mapping", "concept_explainer")`
- omit `forced_mode`
- `conservative_fallback_mode = "concept_explainer"`
- `default_shot_preset_ids = ("opening_world_building", "balanced_explainer", "character_relationship")`
- use `cast_slots_by_mode`
  - `theme_mapping` should define stable history-role slots such as `history_figure_lead`, `era_context_support`, `narrator_moderator`
  - `concept_explainer` should define stable explainer slots such as `history_host`, `timeline_support`

This preset must be implemented as a real dual-mode preset, not a single-mode preset with vague history wording.

### Future additions

These do not need to ship in the same patch, but should be treated as explicit follow-up candidates:

- `angry_birds_strategy_room`
- `angry_birds_science_lab`
- `brand_mascot_explainer_world`
- `neutral_history_storyboard`

## Shot Preset Expansion

The built-in shot preset library should move from 2 presets to at least 5 presets, matching the earlier storyboard design.

### Keep existing built-ins

- `balanced_explainer`
- `detail_focus`

### Add new built-in shot presets

### Required schema contract for added shot presets

The new built-in shot presets must also be expressed as concrete `ShotPresetDefinition` payloads rather than only descriptive labels.

At minimum, every new built-in shot preset added in this patch must declare:

- `preset_id`
- `display_name`
- `supported_scene_count`
- `max_consecutive_same`
- `shot_distribution_rules`
- `opening_rules`
- `closing_rules`
- `transition_rules`
- `purpose_bias`
- `override_policy`

For built-in user-facing shot presets, V1 should also add:

- `display_name_key`
- optional `description_key`

so the UI can localize the preset catalog consistently.

#### 1. `opening_world_building`

Purpose:

- prioritize strong openers and world-establishing frames

Bias:

- more long/full shots early
- clearer location and cast staging
- useful for branded worlds and theme-heavy storytelling

Required V1 contract:

- `supported_scene_count = (4, 5, 6, 7)`
- `max_consecutive_same = 2`
- `shot_distribution_rules` must require at least one long/full establishing frame in the opening portion
- `opening_rules` must explicitly prioritize world/context establishment
- `closing_rules` should return to a readable knowledge takeaway after the wider setup
- `transition_rules` should tighten gradually from wide to medium/detail emphasis
- `override_policy = "adaptive"`

#### 2. `character_relationship`

Purpose:

- emphasize subject-to-subject relationships rather than object detail

Bias:

- more full/medium shots
- more paired or grouped compositions
- especially good for faction,人物关系,角色对照内容

Required V1 contract:

- `supported_scene_count = (3, 4, 5, 6, 7)`
- `max_consecutive_same = 2`
- `shot_distribution_rules` must preserve relational readability rather than object-detail bias
- `opening_rules` should establish the key pair/group before detail inserts
- `closing_rules` should end on a relationship summary or comparison beat
- `transition_rules` should prefer full/medium alternation over frequent extreme close-ups
- `override_policy = "adaptive"`

#### 3. `classroom_demo`

Purpose:

- emphasize explainer-led educational demonstration

Bias:

- stable medium-shot teaching rhythm
- close-ups reserved for key props or experiment details
- useful for concept explanation and classroom-style knowledge content

Required V1 contract:

- `supported_scene_count = (3, 4, 5, 6)`
- `max_consecutive_same = 2`
- `shot_distribution_rules` must keep a stable teaching rhythm with medium shots as the backbone
- `opening_rules` should establish the explainer or teaching setup quickly
- `closing_rules` should end on the final demonstrated takeaway or key teaching prop
- `transition_rules` should move from explainer framing to prop/detail framing in a controlled way
- `override_policy = "adaptive"`

## Recommended Initial Built-in Preset Inventory

### World presets

- `neutral_knowledge_storyboard`
- `dual_mode_storyboard`
- `angry_birds_three_kingdoms`
- `angry_birds_knowledge_classroom`
- `angry_birds_history_classroom`

### Shot presets

- `balanced_explainer`
- `opening_world_building`
- `detail_focus`
- `character_relationship`
- `classroom_demo`

This gives users:

- one safe neutral world
- one generic dual-mode world
- three stronger branded educational worlds
- five distinct rhythm templates

That is enough to feel intentionally designed without overwhelming users.

## Default Pairing Rules

Each world preset should define its preferred default shot presets.

Recommended V1 pairings:

- `neutral_knowledge_storyboard`
  - `balanced_explainer`
  - `detail_focus`
  - `classroom_demo`
- `dual_mode_storyboard`
  - `balanced_explainer`
  - `detail_focus`
  - `character_relationship`
- `angry_birds_three_kingdoms`
  - `character_relationship`
  - `opening_world_building`
  - `balanced_explainer`
- `angry_birds_knowledge_classroom`
  - `classroom_demo`
  - `balanced_explainer`
  - `detail_focus`
- `angry_birds_history_classroom`
  - `opening_world_building`
  - `balanced_explainer`
  - `character_relationship`

This keeps the default automatic pairing feeling intentional rather than arbitrary.

## Guide Copy and Product Framing

The storyboard guide copy should be updated to match the new default-on behavior.

### Old framing

The current guide language assumes storyboard is something users may manually enable when they want more control.

### New framing

The guide should instead communicate:

- storyboard planning is the recommended default path for multi-scene knowledge videos
- users can turn it off when exploring fast
- presets are not advanced-only extras; they are the normal route for continuity

### Preset localization contract

The current UI renders preset option labels directly from preset metadata. If built-in presets are expanded without a localization contract, the Chinese UI will degrade into a mixed-language catalog.

Approved V1 contract:

- built-in world presets should expose `display_name_key` and may expose `description_key`
- built-in shot presets should expose `display_name_key` and may expose `description_key`
- `zh_CN` and `en_US` locale files must provide translations for every built-in preset key shipped in this patch
- UI label resolution order should be:
  1. translated `display_name_key`
  2. raw `display_name`

History and task snapshots should continue to store stable `preset_id` values as the source of truth rather than localized labels.

### Recommended guide structure

The guide should answer four things, in this order:

1. what storyboard planning helps with
2. when to keep it on
3. when to turn it off temporarily
4. what each control changes

The previously approved guidance remains correct, but should be reframed for default-on behavior:

- keep on for explainers, content breakdowns, theme mapping, branded multi-frame sequences
- consider turning off for fast style exploration or unstable early ideation

## UI Maintainability Cleanup

The large inline HTML blocks in `render_storyboard_planning_guide()` are not the core business logic. They are presentation code for explanatory cards.

That code currently mixes:

- copy content
- information hierarchy
- styling
- HTML markup

in one place.

### Problem

This makes the guide:

- harder to edit
- harder to localize cleanly
- harder to review for content changes
- more fragile when the copy strategy changes

### Approved direction

Refactor the guide rendering so that:

- guide sections are defined by structured content data
- reusable rendering helpers consume those data records
- large inline HTML strings are reduced

This is not a full UI redesign. It is a maintainability refactor that should happen together with the copy update.

## Expected Files in Scope

- `pixelle_video/models/storyboard_planning.py`
- `pixelle_video/config/storyboard_preset_library.py`
- `pixelle_video/config/schema.py`
- `web/components/style_config.py`
- `web/pipelines/standard.py`
- `web/i18n/locales/zh_CN.json`
- `web/i18n/locales/en_US.json`
- tests covering:
  - preset library contents
  - preset cross-reference validity
  - storyboard UI default enabled behavior
  - default preset selection behavior
  - default-on scope behavior for main vs exploratory entry points
  - preset localization fallback behavior
  - guide copy or rendering expectations where appropriate

## Risks

### 1. Too many presets too quickly

Mitigation:

- keep the initial expansion to a curated set
- avoid flooding users with near-duplicate presets

### 2. Default-on may feel heavier for pure explorers

Mitigation:

- keep the toggle visible and easy to disable
- keep defaults gentle: `balanced_explainer`, `standard`, `auto`, `adaptive`

### 3. Preset names without enough world-definition detail

Mitigation:

- every new preset must define cast and world anchors clearly
- avoid adding brand-like names without enough continuity rules

## Success Criteria

This design is successful if:

1. users see a materially richer preset library instead of only 2 + 2 options
2. main video generation starts with storyboard planning already enabled
3. world and shot preset selectors always show a concrete selected default when storyboard is on
4. users can still disable storyboard quickly when they want fast exploration
5. the guide copy matches the actual default product behavior
6. storyboard guide code becomes easier to maintain than the current large inline HTML approach
