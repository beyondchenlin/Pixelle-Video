# Prompt Prefix Details Modal

## Goal

Replace the current bottom-mounted prompt-prefix details panel with a modal-based details experience so users can inspect one style without scrolling to the bottom of the page.

This change should:

- keep the existing gallery card layout and overall Pixelle UI language
- move `View Details` from the lower page section into a centered modal flow
- remove the default bottom empty `Style Panel` block from the page
- keep `Add Style`, `Edit`, and `AI Generate` in non-modal page-level flows
- avoid over-design, new visual language, or unrelated interaction changes

## Problem Summary

The current prompt-prefix gallery uses one lower page section for multiple workflows:

- viewing style details
- editing an existing style
- manual creation
- AI-generated candidate management

For details inspection, this is inefficient:

- the trigger is on the card, but the content appears far below the card grid
- users must scroll away from the gallery to inspect one style
- the interaction feels spatially disconnected from the user action
- the empty-state `Style Panel` occupies visible page height even when it provides no value

The details workflow should be immediate and local to the click target, while edit, creation, and AI-generation can remain page-level tools.

## Existing Context

The current prompt-prefix UI in `web/components/style_config.py` has these relevant traits:

- gallery cards already expose `View Details`, `Compare`, and `Select`
- a shared session-state mode (`prompt_prefix_panel_mode`) controls the lower page section
- the lower page section currently renders:
  - details
  - edit
  - manual create
  - AI generate
  - empty state
- the gallery toolbar already exposes entry points for create and AI flows
- the page already uses restrained white cards, rounded borders, and minimal framing

This is the visual system to preserve. The modal should feel like part of the same interface family, not a separate designed subsystem.

## Options Considered

### Option A: Centered Details Modal

Use a modal dialog for `View Details` only. Keep `Add Style`, `Edit`, and `AI Generate` in their existing inline areas. Remove the default empty panel state and stop using the lower section for details.

Pros:

- best matches the user goal of avoiding page-bottom scrolling
- smallest behavioral change
- easiest to keep visually aligned with the existing front end
- keeps gallery browsing context mentally intact

Cons:

- requires extracting the current details renderer into a reusable function
- modal content height needs careful structure so it remains readable

### Option B: Right-Side Drawer

Use a right-side drawer for details.

Pros:

- preserves more horizontal browsing context
- handles long content naturally

Cons:

- more custom layout work in Streamlit
- higher visual and implementation risk
- easier to drift away from the current UI language

### Option C: Keep Bottom Panel but Auto-Scroll

Preserve the current lower section and scroll the page to it when `View Details` is clicked.

Pros:

- smallest code change

Cons:

- does not solve the underlying spatial disconnect
- still leaves the bottom empty-state panel in the page
- weaker UX than a true modal

## Approved Direction

Use **Option A: Centered Details Modal**, implemented with Streamlit's dialog capability (`st.dialog`) unless a concrete technical limitation is found during implementation.

This is the most direct solution to the actual problem and stays within the user's constraint of keeping the design unified and restrained.

## Interaction Design

### 1. Card Trigger

`View Details` remains on each gallery card and on the active-style summary strip.

Click behavior:

- clicking `View Details` opens a centered modal for that item
- it does not scroll the page
- it does not change active selection by itself

### 2. Modal Scope

The modal is used for **details only**.

It does **not** absorb:

- `Add Style`
- `Edit`
- `AI Generate`
- compare preview generation

Those flows remain in their current page-level positions.

### 3. Removed Surface

The default bottom `Style Panel` block is removed from this section.

That means:

- no empty-state panel when no page-level tool is active
- no bottom details panel
- no bottom close button for details
- page-level create / edit / AI surfaces may still render below the gallery when explicitly opened

### 4. Close Behavior

The modal closes when:

- the user clicks the built-in close affordance
- the user completes an action that should naturally return them to the gallery context

If the user chooses `Edit` from inside the details modal, the modal should close and the existing page-level edit flow should open.

Default modal behavior is preferred. No custom transitions or decorative motion should be introduced.

## Modal Content Structure

The modal should reuse the current details information hierarchy with minimal visual change.

Top to bottom:

1. preview image
2. style / scene / source metadata
3. optional note
4. thumbnail workflow status metadata
   - workflow label
   - generated time
   - reference prompt
5. full prompt-prefix content
6. action buttons

Action buttons remain:

- `Set Active`
- `Add to Preview` / `Remove from Preview`
- `Duplicate`
- `Edit` for non-built-in styles
- `Delete` for non-built-in styles

Built-in styles continue to show the disabled built-in badge where applicable.

## Visual Design Rules

The modal should match the current front end, not redefine it.

Do:

- reuse the same white background and rounded-border card language
- keep spacing moderate and readable
- keep typography close to the current detail panel
- keep controls visually consistent with the current button system
- let the preview image remain the strongest visual anchor

Do not:

- introduce heavy shadows, glassmorphism, or vivid accent colors
- change the gallery card design
- turn the modal into a large custom-designed showcase
- introduce extra decorative sections or badges unrelated to current data

In practical terms, this should read as "current details panel, but in a modal."

## State Model

The current panel-mode state should be narrowed rather than rewritten.

Recommended state behavior:

- keep the existing detail-target item state so current interactions remain understandable
- stop rendering the lower-page details surface
- route the `details` branch into modal rendering instead
- leave `manual`, `edit`, and `ai` flows on their existing non-modal paths unless specifically changed later
- remove the default `panel_empty` rendering path from the page

This reduces change risk and avoids coupling the modal redesign to broader prompt-prefix management refactors.

## Error Handling

The modal change should not alter existing operational behavior.

Specific expectations:

- if a style item no longer exists, the details modal should not render stale content
- delete confirmation should remain explicit and localized
- compare-limit warnings should continue to use the current warning mechanism
- no new fallback panel should appear when there is no selected item

## Testing

Relevant automated coverage should verify:

- the source no longer renders the default bottom empty `panel_empty` area
- the `details` branch is no longer rendered in the lower page section
- `View Details` still exists on cards
- the details renderer remains available for one item
- locale keys remain valid if any new modal-related labels are added
- the filter panel remains collapsed by default
- `manual`, `edit`, and `ai` branches remain available as non-modal page flows

If implementation requires a new helper or state transition for modal rendering, add direct tests for that helper instead of relying only on source-shape assertions.

## Out of Scope

This design does not include:

- moving `Add Style` into a modal
- moving `Edit` into a modal
- moving `AI Generate` into a modal
- redesigning the gallery cards
- changing compare or selection semantics
- changing prompt-prefix data storage
- redesigning the preview section

## Implementation Consequence

Implementation should be treated as a focused UI refactor inside the prompt-prefix gallery:

- extract the current details block into a reusable render helper
- replace lower-section details rendering with modal rendering
- remove the default empty `Style Panel` block
- preserve existing create, edit, AI, compare, and selection flows
- keep implementation styling restrained and aligned with the existing Pixelle UI language

This should produce a faster inspection workflow without broadening the scope into a full prompt-prefix management redesign.
