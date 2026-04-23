# Quick Create Flow Responsive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `Quick Create Flow` diagram so it keeps the current visual flow on desktop, switches to a readable two-column layout on tablet, and collapses to a single-column stepper on phone widths.

**Architecture:** Keep the component in `web/components/quick_create_flow.py`, but replace the fixed seven-track grid CSS with a semantic card-and-connector structure driven by breakpoint-specific layout rules. Lock the new contract with focused pytest assertions that prove the legacy fixed-grid layout is gone and the new responsive hooks remain present.

**Tech Stack:** Python 3.12, Streamlit HTML injection, CSS Grid/Flexbox, pytest

---

Repository note: `AGENTS.md` forbids `git worktree`, so execute this plan on the current branch and stage only the files listed in each task for each atomic commit.

## File Structure

- Modify: `web/components/quick_create_flow.py`
  Replace the fixed-track CSS and row markup with a semantic responsive structure that supports desktop, tablet, and phone breakpoints.
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
  Replace the old layout assertions with targeted checks for the new responsive contract.
- Create: `docs/superpowers/specs/2026-04-24-quick-create-flow-responsive-design.md`
  Capture the approved design and acceptance criteria for the responsive rewrite.
- Create: `docs/superpowers/plans/2026-04-24-quick-create-flow-responsive-implementation.md`
  Capture the implementation sequence for future maintenance.

### Task 1: Lock the responsive contract with failing tests

**Files:**
- Modify: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Write the failing responsive-layout test**

```python
def test_build_quick_create_flow_diagram_html_uses_responsive_layout_contract(monkeypatch):
    monkeypatch.setattr(quick_create_flow, "tr", lambda key, **kwargs: key)

    html = quick_create_flow.build_quick_create_flow_diagram_html()

    assert "quick_create_flow.node.script_input.title" in html
    assert "quick_create_flow.node.generate.title" in html
    assert "@media (max-width: 980px)" in html
    assert "@media (max-width: 680px)" in html
    assert "data-node=\"script_input\"" in html
    assert "quick-create-flow-stepper" in html
    assert "grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr) 24px minmax(0, 1fr);" not in html
    assert "grid-column: 7;" not in html
    assert "min-height: 440px;" not in html
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py::test_build_quick_create_flow_diagram_html_uses_responsive_layout_contract -v`

Expected: FAIL because the current HTML still emits the old fixed-grid layout and lacks the new breakpoint hooks.

- [ ] **Step 3: Commit the failing-test intent to the working tree only**

```bash
git diff -- tests/test_style_config_storyboard_planning_ui.py
```

Expected: the diff shows only the new responsive contract assertions. Do not commit yet; implementation is required to satisfy the test.

### Task 2: Rebuild the quick-create flow markup and CSS

**Files:**
- Modify: `web/components/quick_create_flow.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Replace card HTML so each node has semantic hooks**

```python
def _build_card_html(node_key: str, tone: str, *, extra_class: str = "") -> str:
    title = escape(tr(f"quick_create_flow.node.{node_key}.title"))
    description = escape(tr(f"quick_create_flow.node.{node_key}.description"))
    classes = " ".join(
        cls
        for cls in (
            "quick-create-flow-card",
            f"quick-create-flow-card-{tone}",
            extra_class,
        )
        if cls
    )
    return (
        f'<article class="{classes}" data-node="{node_key}">'
        f"<strong>{title}</strong>"
        f"<span>{description}</span>"
        "</article>"
    )
```

- [ ] **Step 2: Replace the fixed-grid CSS with breakpoint-specific layout rules**

```python
@media (max-width: 980px) {
    .quick-create-flow-desktop {
        display: none;
    }

    .quick-create-flow-tablet {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--flow-gap);
    }
}

@media (max-width: 680px) {
    .quick-create-flow-tablet {
        display: none;
    }

    .quick-create-flow-stepper {
        display: flex;
        flex-direction: column;
        gap: 0;
    }
}
```

- [ ] **Step 3: Emit separate desktop, tablet, and phone containers from the builder**

```python
  <div class="quick-create-flow-board quick-create-flow-desktop">
    ...
  </div>
  <div class="quick-create-flow-board quick-create-flow-tablet">
    ...
  </div>
  <div class="quick-create-flow-stepper">
    ...
  </div>
```

- [ ] **Step 4: Re-run the targeted responsive test**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py::test_build_quick_create_flow_diagram_html_uses_responsive_layout_contract -v`

Expected: PASS once the new breakpoints and semantic hooks are present and the legacy fixed-grid CSS is removed.

### Task 3: Verify adjacent quick-create tests and commit atomically

**Files:**
- Modify: `web/components/quick_create_flow.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`
- Create: `docs/superpowers/specs/2026-04-24-quick-create-flow-responsive-design.md`
- Create: `docs/superpowers/plans/2026-04-24-quick-create-flow-responsive-implementation.md`

- [ ] **Step 1: Run the focused quick-create and standard-pipeline tests**

Run: `uv run pytest tests/test_style_config_storyboard_planning_ui.py -k "quick_create_flow or storyboard_default_enabled" -v`

Expected: PASS for the responsive HTML builder test, the render wrapper test, and the standard pipeline integration assertion that the quick-create flow still renders.

- [ ] **Step 2: Inspect the final diff**

```bash
git diff -- web/components/quick_create_flow.py tests/test_style_config_storyboard_planning_ui.py docs/superpowers/specs/2026-04-24-quick-create-flow-responsive-design.md docs/superpowers/plans/2026-04-24-quick-create-flow-responsive-implementation.md
```

Expected: only the responsive flow rewrite, its tests, and the matching spec/plan documents are included.

- [ ] **Step 3: Commit the change**

```bash
git add web/components/quick_create_flow.py tests/test_style_config_storyboard_planning_ui.py docs/superpowers/specs/2026-04-24-quick-create-flow-responsive-design.md docs/superpowers/plans/2026-04-24-quick-create-flow-responsive-implementation.md
git commit -m "fix: make quick create flow responsive"
```

- [ ] **Step 4: Push the commit**

```bash
git push origin dev
```

Expected: the branch updates successfully; if push is rejected, report the exact external blocker instead of claiming completion.
