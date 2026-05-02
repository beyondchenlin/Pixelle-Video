# Stage2 Projection Selection Flow Design

## Goal

Rebuild the Stage2 PromptPlan projection preview selection flow so the default user path prevents mismatched context, wrong asset selections, and stale preview assumptions before the request is sent.

## Background

The current Stage2 projection preview already enforces important boundaries:

- preview-only
- no PromptPlan persistence
- no stale marking
- no title / subtitle / text-style fields in the request
- no local path, provider URL, or workflow path leakage

Those boundaries are correct and must remain unchanged.

The current problem is not request safety. The current problem is that the frontend selection flow is fragmented across:

- context load
- AssetBible draft creation / staging
- SceneCast draft creation / staging
- AssetBible selection
- SceneCast selection
- storyboard / frame text inputs
- preview cache invalidation

Each individual rule is reasonable, but the whole flow still relies on the user to understand implicit dependencies. That creates a source-level UX defect:

- users can lose track of which context is loaded
- users can switch AssetBible and not immediately understand downstream invalidation
- users can see storyboard/frame IDs as plain text fields without knowing whether they were auto-derived or manually overridden
- users can reach preview with a technically complete form but a cognitively unclear selection state

This feature must solve the selection problem at the flow level rather than adding another local patch.

## Scope

This design covers only the Stage2 projection preview selection flow and its immediate draft-to-preview staging path.

Included:

- Stage2 projection preview page flow in `web/components/asset_prompt_plan_projection.py`
- draft setup to preview staging in `web/components/asset_bible_draft_setup.py`
- projection session-state helpers in `web/components/stage2_projection_state.py`
- UI tests covering selection flow, state invalidation, and preview-only boundaries

Explicitly excluded:

- backend API contract changes
- projection preview persistence
- stale write integration
- title, subtitle, caption-style, or text-rendering request fields
- image/video generation entrypoints
- new provider-facing fields

## Non-Negotiable Constraints

The optimized flow must preserve all existing Stage1 / Stage2 boundaries:

- The preview request remains limited to `workspace_id`, `storyboard_plan_id`, and `frame_id`.
- The frontend must not render default-flow inputs for `title_style`, `subtitle_style`, `caption_style`, `font`, `local_path`, provider URLs, or workflow paths.
- The preview result remains read-only and non-persistent.
- The preview flow must not call any stale-aware write service.
- The preview flow must not imply that projection has been saved or entered the main generation path.

## Root Cause

The source problem is that selection state exists, but the user-facing flow does not present that state as a single coherent process.

Today the page behaves like a set of cooperating controls. It needs to behave like a guided selection flow.

The root issues are:

1. The page exposes downstream fields before upstream context is clearly established.
2. AssetBible, SceneCast, storyboard, and frame state are coupled, but the UI communicates them as separate controls rather than as a dependency chain.
3. Draft staging from create flows is useful, but the page does not clearly distinguish staged values from manually entered fallback values.
4. Cache invalidation exists internally, but the user does not get a clear mental model of when previous preview results are no longer valid.

## Design Decision

Use a guided five-step selection flow inside the existing Stage2 projection preview page:

1. Context
2. AssetBible
3. SceneCast
4. Storyboard Frame
5. Preview

This is not a full wizard with page-to-page navigation. It is a single-page guided flow with strong dependency visibility and progressive enablement.

This approach fixes the source issue without overbuilding a new UI framework.

## UX Structure

### 1. Context Step

The page starts with a clear context block:

- API Base URL
- Project ID
- Workspace ID
- explicit "Load Context" action

Until context is valid and loaded, downstream selection areas stay in a locked state with explanatory copy instead of showing empty working controls.

The context block becomes the single source for:

- projection context load
- staged draft context compatibility
- invalidation of downstream selections

If the context changes, the page must clearly reset downstream state and explain that previous selections and previews are no longer valid.

### 2. AssetBible Step

After context is loaded:

- show available AssetBible drafts
- show a small summary for the selected draft
- keep draft-creation entrypoints nearby so creation and selection remain in the same mental zone

If a new AssetBible is created from the draft setup flow:

- it is staged into the current context automatically
- it becomes the selected AssetBible
- SceneCast selection and preview results are reset

The user should not need to infer whether a newly created draft has been wired into preview. That state must be obvious and immediate.

### 3. SceneCast Step

SceneCast becomes a strict child selection of AssetBible.

After AssetBible changes:

- reload SceneCast list for that AssetBible
- clear prior SceneCast, storyboard, frame, and preview result
- auto-select the existing valid SceneCast if still compatible, otherwise first valid option

If a SceneCast is created from draft setup:

- it is staged into the same context automatically
- it becomes the selected SceneCast
- storyboard and frame are auto-populated from the staged SceneCast

This makes SceneCast the primary driver for frame-scoped preview context.

### 4. Storyboard Frame Step

Storyboard Plan ID and Frame ID remain part of the request contract, but the default flow changes:

- if the selected SceneCast includes `storyboard_plan_id` and `frame_id`, treat them as the default current selection
- show them as derived selection values first, not as unexplained freeform inputs
- only fall back to manual text entry when the SceneCast data is incomplete or when the user enters an explicit debug path

The default user path must answer:

- where did this storyboard/frame come from?
- is it tied to the currently selected SceneCast?
- has it been manually overridden?

That status needs to be visible in copy, not hidden in session-state.

### 5. Preview Step

The preview action should sit beside a compact "current request summary" block:

- context
- AssetBible
- SceneCast
- storyboard/frame source

Before the request is sent, the frontend should perform explicit flow validation:

- context is complete
- AssetBible is selected
- SceneCast is selected
- storyboard/frame are present
- if storyboard/frame are derived, they still match the currently selected SceneCast

If validation fails, block the request and explain the exact missing or invalid step.

## Progressive Enablement

The flow should be visibly progressive:

- Context incomplete: downstream steps show disabled-state guidance
- Context loaded but no AssetBible: SceneCast / Frame / Preview remain blocked
- AssetBible selected but no SceneCast: Frame / Preview remain blocked
- SceneCast selected with derived frame data: Preview becomes ready
- SceneCast selected without derived frame data: require explicit frame completion before Preview

This is the main anti-error mechanism. It is better to disable a downstream step with a clear explanation than to show a live control that the user can misuse.

## State Model

The flow should continue using Streamlit session state, but the UI should represent a smaller set of explicit states.

Required concepts:

- loaded projection context
- selected AssetBible
- selected SceneCast
- derived storyboard/frame selection
- manual debug override state
- cached preview result bound to a specific request source

Important rule:

- derived selection state and debug override state must not be visually mixed together in the default path

Advanced Debug remains available, but it must stay clearly secondary and opt-in.

## Draft Setup Integration

Draft setup integration is part of the source-level fix and is allowed in this feature.

Required behavior:

- creating an AssetBible stages it directly into the current projection context
- creating a SceneCast stages it directly into the current projection context
- staging updates the active selection, not just the hidden state cache
- staging must never bypass context compatibility checks

The integration point should make creation feel like part of the same selection flow rather than a separate subsystem.

## Result Presentation

The existing result area already has the right safety direction. It should be kept preview-only, but improved so it reflects the new guided flow.

The result section should emphasize:

- what was selected
- what was projected
- what remains read-only

Recommended result grouping:

- Request Summary
- Prompt Output
- Asset Locks
- Source Trace

The page should continue avoiding:

- raw JSON dumps in the default path
- save/generate verbs
- provider-facing technical labels

## Error Handling

Errors should be step-local when possible.

Examples:

- context load failure belongs in Context
- SceneCast list failure belongs in SceneCast
- derived storyboard/frame mismatch belongs in Storyboard Frame
- preview request failure belongs in Preview

Do not collapse all failures into a single generic "preview failed" message if the flow can identify the specific broken step earlier.

## Testing Strategy

This feature should be test-first and must extend the existing projection UI test suite.

Coverage must prove:

- downstream steps do not behave as active selections before upstream context is ready
- AssetBible changes invalidate SceneCast, frame, and preview state correctly
- staged draft creation updates visible active selection
- default flow keeps manual asset IDs hidden
- default flow keeps style/path inputs hidden
- preview request payload still contains only endpoint fields
- preview flow still renders preview-only language and never save/generate/stale language
- cached preview results are cleared whenever request source changes

No backend contract tests need to be expanded beyond what this UI change touches.

## Acceptance Criteria

This feature is complete only when all of the following are true:

- The default user path is a coherent guided selection flow rather than a loose collection of controls.
- Users can understand the dependency chain `Context -> AssetBible -> SceneCast -> Storyboard Frame -> Preview` from the page itself.
- Wrong or stale downstream selections are cleared before a request is sent.
- The page makes derived frame context visible and understandable.
- Preview-only boundaries remain intact.
- No new persistence path is introduced.
- No title/subtitle/text-style/path/provider leakage is introduced.
- Existing Stage2 projection preview registration and safety tests still pass.

## Out Of Scope Follow-Up

This feature intentionally does not solve the next two UI goals:

- richer projection result diff visualization
- stronger visual styling for preview-only boundary messaging

Those belong to later single-feature cycles after this selection-flow rewrite passes integration acceptance.
