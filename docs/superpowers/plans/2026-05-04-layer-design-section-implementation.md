# 图层设计一级配置域 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将内嵌在“分镜模板”中的图层编辑升级为独立一级折叠区“图层设计”，并从源头拆开模板选择、图层设计和最终 `LayeredTemplateSpec` 输出边界。

**Architecture:** `style_config.render_style_config()` 继续作为中栏配置编排器，但模板选择结果先归一化为一个明确的上下文对象，再传给独立的 `layer_design_config` 组件。`LayeredTemplateEditorState` 与 `LayeredTemplateSpec` 继续作为唯一图层事实源，空图层仍由 `active_layered_template_spec()` 过滤。

**Tech Stack:** Python 3.11、Streamlit、pytest、Pixelle 现有 `LayeredTemplateEditorState` / `LayeredTemplateSpec` 模型。

---

## File Structure

- Create: `web/components/layer_design_config.py`
  - 负责渲染“图层设计”一级折叠区内部 UI。
  - 复用现有 `LayeredTemplateEditorState`，不持久化第二套图层状态。
  - 提供 `render_layer_design_config(...) -> LayeredTemplateEditorState`。

- Modify: `web/components/style_config.py`
  - 删除内嵌的 `_render_layered_template_editor()` 调用。
  - 在分镜模板上下文计算完成后调用 `render_layer_design_config(...)`。
  - `render_style_config()` 继续统一组装返回 payload 和 `layered_template_spec`。

- Modify: `web/i18n/locales/zh_CN.json`
  - 新增 `section.layer_design`: `🎛️ 图层设计`。
  - 将 `layered_template.editor.title` 调整为 `图层列表`，用于区块内部小节标题。

- Modify: `web/i18n/locales/en_US.json`
  - 新增 `section.layer_design`: `🎛️ Layer Design`。
  - 将 `layered_template.editor.title` 调整为 `Layer List`。

- Modify: `tests/test_style_config_layered_template_ui.py`
  - 增加一级折叠区位置和无嵌套标题的行为测试。
  - 更新原有图层按钮和 payload 测试，证明功能行为不变。

- Modify: `tests/test_style_config_storyboard_planning_ui.py`
  - 更新中栏折叠区集合断言，纳入 `section.layer_design`。

## Task 1: Lock UI Contract With Failing Tests

**Files:**
- Modify: `tests/test_style_config_layered_template_ui.py`
- Modify: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Write failing test for new layer design expander**

Add a test to `tests/test_style_config_layered_template_ui.py` that renders `style_config.render_style_config(...)` with the existing fake Streamlit object and asserts:

```python
assert ("section.template", False) in fake_st.expanders
assert ("section.layer_design", False) in fake_st.expanders
assert fake_st.expanders.index(("section.template", False)) < fake_st.expanders.index(
    ("section.layer_design", False)
)
assert "**图层**" not in "\n".join(body for body, _kwargs in fake_st.expander_markdowns)
```

The expected failure before implementation is that `("section.layer_design", False)` is absent and the old internal `**图层**` heading is still rendered.

- [ ] **Step 2: Update existing storyboard section test expectation**

In `tests/test_style_config_storyboard_planning_ui.py`, extend `expected_collapsed_sections`:

```python
expected_collapsed_sections = {
    ("section.tts", False),
    ("section.render_backend", False),
    ("section.template", False),
    ("section.layer_design", False),
}
```

Expected failure before implementation: `section.layer_design` is absent.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
pytest tests/test_style_config_layered_template_ui.py tests/test_style_config_storyboard_planning_ui.py::test_render_style_config_uses_middle_column_sections_without_nested_expanders -q
```

Expected: failures mention missing `("section.layer_design", False)` or old internal `**图层**` heading.

## Task 2: Extract Layer Design Component

**Files:**
- Create: `web/components/layer_design_config.py`
- Modify: `web/components/style_config.py`

- [ ] **Step 1: Move layer editor UI into new module**

Create `web/components/layer_design_config.py` with:

```python
from __future__ import annotations

from html import escape

import streamlit as st

from web.components.layered_template_state import (
    LAYERED_TEMPLATE_EDITOR_STATE_KEY,
    LayeredTemplateEditorState,
)
from web.i18n import get_language, tr


def render_layer_design_config(
    state: LayeredTemplateEditorState,
) -> LayeredTemplateEditorState:
    ...
```

Move the existing add-row CSS builder and layer-control rendering functions from `style_config.py` into this module. Keep widget keys unchanged:

```python
"layered_template_add_background_layer"
"layered_template_add_image_layer"
"layered_template_add_text_layer"
"layered_template_layer_{layer.id}_name"
```

The function must update `st.session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY]` before returning.

- [ ] **Step 2: Render as a first-level middle-column section**

In `style_config.py`, import:

```python
from web.components.layer_design_config import render_layer_design_config
```

Replace:

```python
layered_template_state = _render_layered_template_editor(layered_template_state)
```

with:

```python
with render_middle_column_collapsible_section(
    tr("section.layer_design"),
    expanded=False,
):
    layered_template_state = render_layer_design_config(layered_template_state)
```

- [ ] **Step 3: Remove duplicated editor helpers from style_config.py**

Remove these functions from `style_config.py` after the new module compiles:

```python
_layered_template_editor_text
_build_layered_template_editor_css
_render_layered_template_editor
_render_layered_template_layer_controls
_build_layer_source_summary
```

If `_build_layer_source_summary` is only used by the moved controls, move it into `layer_design_config.py`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
pytest tests/test_style_config_layered_template_ui.py tests/test_style_config_storyboard_planning_ui.py::test_render_style_config_uses_middle_column_sections_without_nested_expanders -q
```

Expected: tests pass.

## Task 3: Add I18n Contract and Polish Labels

**Files:**
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_i18n.py`

- [ ] **Step 1: Add locale keys**

Add to both locale files near the existing section keys:

```json
"section.layer_design": "🎛️ 图层设计"
```

and for English:

```json
"section.layer_design": "🎛️ Layer Design"
```

Update `layered_template.editor.title` to avoid repeating the section name:

```json
"layered_template.editor.title": "图层列表"
```

and:

```json
"layered_template.editor.title": "Layer List"
```

- [ ] **Step 2: Update i18n ordering test**

In `tests/test_i18n.py`, add an assertion that `section.layer_design` appears after `section.template` and before `section.text_rendering`:

```python
assert keys.index("section.template") < keys.index("section.layer_design")
assert keys.index("section.layer_design") < keys.index("section.text_rendering")
```

- [ ] **Step 3: Run i18n tests**

Run:

```powershell
pytest tests/test_i18n.py -q
```

Expected: tests pass.

## Task 4: Full Verification and Commit

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run focused regression suite**

Run:

```powershell
pytest tests/test_style_config_layered_template_ui.py tests/test_style_config_storyboard_planning_ui.py::test_render_style_config_uses_middle_column_sections_without_nested_expanders tests/test_i18n.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Inspect diff for unrelated files**

Run:

```powershell
git status --short
git diff -- web/components/style_config.py web/components/layer_design_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_layered_template_ui.py tests/test_style_config_storyboard_planning_ui.py tests/test_i18n.py
```

Expected: only the planned files are modified.

- [ ] **Step 3: Commit implementation**

Run:

```powershell
git add docs/superpowers/plans/2026-05-04-layer-design-section-implementation.md web/components/style_config.py web/components/layer_design_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_style_config_layered_template_ui.py tests/test_style_config_storyboard_planning_ui.py tests/test_i18n.py
git commit -m "feat: 独立图层设计配置域

- 新增图层设计一级折叠区
- 拆分图层编辑组件边界
- 保持 LayeredTemplateSpec 作为图层唯一事实源"
```

- [ ] **Step 4: Push branch**

Run:

```powershell
git push -u origin feat/layer-design-section
```

Expected: branch pushed to GitHub.
