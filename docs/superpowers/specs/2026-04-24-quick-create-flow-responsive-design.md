# Quick Create Flow Responsive Design

## Goal

Keep the current `快速创作流程 / Quick Create Flow` diagram in the middle column, but make it adapt cleanly across desktop, tablet, and phone widths without losing the existing left-to-right guidance.

This change should:

- preserve the current quick-create flow card metaphor and sequencing
- keep the diagram readable when the middle column becomes narrower
- ensure arrows stay visually centered relative to the cards they connect
- let card titles and descriptions wrap without breaking the layout
- avoid introducing JavaScript or a new rendering dependency

This change should not:

- move the flow to another page
- replace the diagram with a completely different component style
- introduce SVG/canvas rendering
- redesign unrelated middle-column sections

## Current State

The current implementation lives in `web/components/quick_create_flow.py` and emits one fixed HTML/CSS block.

The root issue is structural rather than cosmetic:

- each main row uses a fixed seven-track grid with hard-coded `24px` arrow columns
- the bottom row uses filler tracks to fake horizontal alignment with the rows above
- vertical arrows are pinned to absolute grid column numbers instead of card relationships
- only one small-screen breakpoint exists, so tablet and half-width desktop states fall into an awkward in-between layout
- cards use a mostly fixed height model, so text wrapping increases visual imbalance

Because of that, the diagram looks acceptable only near one reference width. As the column narrows or expands, arrow centers drift and card content stops feeling intentional.

## Options Considered

### Option A: Keep the current flow concept and rebuild it as a responsive three-mode layout

Pros:

- preserves the current product language and user familiarity
- fixes the actual layout model instead of patching offsets
- scales well across desktop, tablet, and phone widths
- keeps implementation inside the current HTML/CSS-only Streamlit component

Cons:

- requires replacing most of the current CSS block
- tests must be updated because the current layout contract changes

### Option B: Replace the flow with a vertical timeline

Pros:

- easiest layout to keep stable on narrow screens
- simplest arrows

Cons:

- loses the current serpentine reading path
- weakens the spatial correspondence with left, middle, and right page regions

### Option C: Render the flow as SVG

Pros:

- arrows can be mathematically precise
- visual composition can be more controlled

Cons:

- text wrapping and localization become harder to maintain
- more brittle inside Streamlit HTML injection
- unnecessary complexity for a small UI explainer

## Approved Direction

Use **Option A**.

Keep the current flow-diagram identity, but rebuild it as a three-tier responsive component:

1. desktop keeps the serpentine workflow
2. tablet switches to a two-column guided grid
3. phone collapses into a one-column stepper

This preserves the mental model while removing the fixed-grid assumptions that currently break alignment.

## Layout Design

### Desktop

Desktop should continue to feel like a guided board rather than a generic checklist.

Approved behavior:

- top row: `脚本输入 -> 创作模式 -> 分镜数 -> 背景音乐`
- second row reads back from right to left: `分镜模板 <- 分镜规划 <- 渲染后端 <- 配音合成`
- bottom row remains `插图生成 -> 生成视频`
- vertical connectors continue to indicate the drop from top row to middle row and from middle row to bottom row

Implementation rule:

- do not rely on filler tracks or hard-coded grid-column anchors for card centering
- each step block must own its own alignment and spacing
- arrows should be centered by local layout context, not by page-wide magic numbers

### Tablet

Tablet widths should stop pretending they are wide desktop.

Approved behavior:

- switch to a two-column card matrix
- keep the same logical step order
- render arrows as compact horizontal or vertical connectors between adjacent items rather than preserving the full desktop serpentine geometry
- preserve the visual distinction between input, config, and output cards

This is the range where the current component breaks most obviously, so the layout should optimize for legibility first and exact desktop mimicry second.

### Phone

Phone widths should become a clean single-column guided stack.

Approved behavior:

- one card per row
- a centered vertical connector between steps
- consistent spacing and readable wrapped copy
- no hidden or overlapping arrows

The phone view should read like a concise creation checklist rather than a compressed desktop diagram.

## Visual Rules

Follow the current middle-column visual language, but tighten it so the component feels designed rather than stretched.

Do:

- keep the light editorial card treatment
- continue using the three card tones for input, config, and output
- use CSS variables to centralize spacing, radius, arrow size, and color accents
- use `clamp()` where it improves card padding, font sizing, and minimum heights
- let descriptions wrap naturally

Do not:

- introduce a dark theme just for this block
- add decorative effects that compete with the controls around it
- depend on fixed card heights for alignment
- keep empty grid tracks only for positioning hacks

## Markup Contract

The rendered HTML should become more semantic so responsive styling can be reasoned about directly.

Approved markup direction:

- each step card should carry a stable node identifier such as `data-node="script_input"`
- rows or groups may carry descriptive classes such as desktop, tablet, or mobile-specific containers
- arrows should be generated as dedicated connector elements instead of relying on layout side effects

The implementation may keep a helper-driven HTML builder, but the output should clearly separate:

- cards
- connector elements
- breakpoint-specific grouping

## Testing Contract

At minimum, tests should lock the new layout contract in `tests/test_style_config_storyboard_planning_ui.py`.

Tests should verify:

- the rendered HTML still includes all expected quick-create nodes
- the new CSS includes explicit desktop, tablet, and phone breakpoints
- old fixed-layout assumptions that caused the bug are removed
- arrow and card class hooks needed for the new layout are present

The tests do not need visual snapshot coverage, but they must be strong enough to prevent accidental regression back to the fixed seven-track layout.

## Risks And Guardrails

Main risk:

- a responsive rewrite can accidentally make one breakpoint cleaner while degrading another

Guardrails:

- keep the step order centralized in Python constants
- avoid separate duplicated copies of the same content for each breakpoint
- verify targeted tests after the rewrite
- keep the component self-contained within `web/components/quick_create_flow.py`

## Acceptance Criteria

This design is satisfied when:

- desktop retains the current quick-flow identity
- tablet no longer shows visibly off-center arrows or compressed card geometry
- phone shows a clean single-column sequence
- card content wraps without overflow hacks
- the implementation remains HTML/CSS-only inside the existing Streamlit render path
