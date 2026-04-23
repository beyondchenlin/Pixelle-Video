# Prompt Prefix Gallery Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the image prompt-prefix UI into a template-gallery-style experience with preview assets, card-based browsing, side-panel management, and workflow-aware comparison behavior.

**Architecture:** Keep the existing prompt-prefix library behavior and persistence flow, then layer the redesign on top through small helper extensions instead of inventing a new subsystem. Extend the prompt-prefix item schema with preview asset metadata, ship built-in preview cover assets, and refactor the current image-only `style_config` rendering into a gallery grid plus right-side panel fallback that matches the existing Template Gallery rhythm.

**Tech Stack:** Python, Streamlit, Pydantic, pytest, JSON i18n, static SVG assets

---

### Task 1: Extend Prompt Prefix Metadata and Preview Asset Helpers

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/prompt_prefix_library.py`
- Modify: `web/utils/prompt_prefix_ui.py`
- Create: `tests/test_prompt_prefix_preview_assets.py`
- Modify: `tests/test_prompt_prefix_library_config.py`
- Modify: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Write failing tests for preview asset metadata**

```python
def test_builtin_prompt_prefix_defaults_include_preview_asset_paths():
    config = PixelleVideoConfig()
    items = config.comfyui.image.prompt_prefix_library.items
    assert all(item.preview_asset_path for item in items)


def test_create_prompt_prefix_item_preserves_preview_asset_path():
    item = create_prompt_prefix_item(
        item_id="manual-test",
        name="Gallery Card",
        content="flat illustration",
        style_category_id="flat_illustration",
        scene_category_id="knowledge_sharing",
        note="clean and bright",
        source="manual",
        preview_asset_path="resources/prompt_prefix_previews/custom/card.svg",
    )
    assert item["preview_asset_path"] == "resources/prompt_prefix_previews/custom/card.svg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_prefix_library_config.py tests/test_style_config_prompt_prefix_ui.py tests/test_prompt_prefix_preview_assets.py -q`
Expected: FAIL because `preview_asset_path` is missing from the schema/helpers or the new test file does not exist yet.

- [ ] **Step 3: Add preview asset metadata and resolution helpers**

```python
class PromptPrefixItemConfig(BaseModel):
    ...
    preview_asset_path: Optional[str] = Field(default=None)
```

```python
def create_prompt_prefix_item(..., preview_asset_path: str | None = None) -> dict[str, str | bool | None]:
    return {
        ...,
        "preview_asset_path": preview_asset_path.strip() if preview_asset_path else None,
    }
```

```python
BuiltinPromptPrefix(
    ...,
    preview_asset_path="resources/prompt_prefix_previews/builtin/warm_storybook.svg",
)
```

- [ ] **Step 4: Add pure helpers for preview asset resolution and placeholder fallback**

```python
def get_prompt_prefix_preview_asset(item: dict[str, Any]) -> str | None:
    preview_asset_path = item.get("preview_asset_path")
    if preview_asset_path and os.path.exists(preview_asset_path):
        return preview_asset_path
    return DEFAULT_PROMPT_PREFIX_PLACEHOLDER
```

- [ ] **Step 5: Run the targeted tests again**

Run: `uv run pytest tests/test_prompt_prefix_library_config.py tests/test_style_config_prompt_prefix_ui.py tests/test_prompt_prefix_preview_assets.py -q`
Expected: PASS for the new preview-asset assertions.

- [ ] **Step 6: Commit the metadata/helper slice**

```bash
git add pixelle_video/config/schema.py pixelle_video/config/prompt_prefix_library.py web/utils/prompt_prefix_ui.py tests/test_prompt_prefix_library_config.py tests/test_style_config_prompt_prefix_ui.py tests/test_prompt_prefix_preview_assets.py
git commit -m "feat: add prompt prefix preview asset metadata"
```

### Task 2: Ship Built-In Gallery Preview Assets

**Files:**
- Create: `resources/prompt_prefix_previews/builtin/*.svg`
- Create: `resources/prompt_prefix_previews/placeholder.svg`
- Modify: `tests/test_prompt_prefix_preview_assets.py`

- [ ] **Step 1: Write failing tests for the built-in asset pack**

```python
def test_builtin_prompt_prefix_preview_assets_exist_on_disk():
    for item in BUILTIN_PROMPT_PREFIXES:
        assert Path(item.preview_asset_path).exists()


def test_prompt_prefix_preview_placeholder_exists():
    assert Path(DEFAULT_PROMPT_PREFIX_PLACEHOLDER).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompt_prefix_preview_assets.py -q`
Expected: FAIL because the SVG asset files do not exist yet.

- [ ] **Step 3: Add the SVG asset pack**

```svg
<svg viewBox="0 0 720 1080" xmlns="http://www.w3.org/2000/svg">
  <rect width="720" height="1080" rx="36" fill="#f6f2ea"/>
  ...
</svg>
```

Include one unique cover per built-in style plus one neutral placeholder.

- [ ] **Step 4: Run the asset tests again**

Run: `uv run pytest tests/test_prompt_prefix_preview_assets.py -q`
Expected: PASS with all built-in asset paths resolved.

- [ ] **Step 5: Commit the preview asset pack**

```bash
git add resources/prompt_prefix_previews tests/test_prompt_prefix_preview_assets.py pixelle_video/config/prompt_prefix_library.py
git commit -m "feat: add prompt prefix gallery preview assets"
```

### Task 3: Refactor the Prompt Prefix UI into a Gallery + Side Panel

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Write failing tests for the redesign hooks**

```python
def test_style_config_source_references_gallery_redesign_hooks():
    source = Path(... / "web" / "components" / "style_config.py").read_text(encoding="utf-8")
    assert "prompt_prefix_preview_asset" in source
    assert "prompt_prefix_panel_mode" in source
    assert "style.prefix_library.toolbar_add" in source
```

- [ ] **Step 2: Run the targeted UI tests to verify they fail**

Run: `uv run pytest tests/test_style_config_prompt_prefix_ui.py -q`
Expected: FAIL because the new gallery/panel hooks and locale keys do not exist yet.

- [ ] **Step 3: Replace the text-heavy card list with a gallery layout**

```python
gallery_col, panel_col = st.columns([2.2, 1], gap="large")

with gallery_col:
    _render_prompt_prefix_active_strip(...)
    _render_prompt_prefix_toolbar(...)
    _render_prompt_prefix_gallery_grid(...)

with panel_col:
    _render_prompt_prefix_side_panel(...)
```

Implement:

- active style strip
- toolbar with filters, search, `Add Style`, `AI Generate`, compare count
- gallery grid with preview image, source badge, minimal tags, compare chip, primary select button
- workflow-aware comparison messaging
- side-panel fallback for details, manual create, and AI generate flows

- [ ] **Step 4: Add the new locale keys**

```json
"style.prefix_library.toolbar_add": "Add Style",
"style.prefix_library.toolbar_ai": "AI Generate",
"style.prefix_library.compare_count": "Comparing {count} styles",
"style.prefix_library.panel.details": "Style Details"
```

- [ ] **Step 5: Run the prompt-prefix UI test slice**

Run: `uv run pytest tests/test_style_config_prompt_prefix_ui.py tests/test_prompt_prefix_generation.py -q`
Expected: PASS, including the new gallery-key assertions.

- [ ] **Step 6: Commit the gallery UI refactor**

```bash
git add web/components/style_config.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json tests/test_style_config_prompt_prefix_ui.py
git commit -m "feat: redesign prompt prefix library as gallery"
```

### Task 4: Wire Preview Upload/Generation States and Run Full Verification

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/utils/prompt_prefix_ui.py`
- Modify: `tests/test_prompt_prefix_generation.py`
- Modify: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Write failing tests for explicit preview-generation and upload behaviors**

```python
def test_create_prompt_prefix_item_keeps_preview_asset_path_none_when_missing():
    item = create_prompt_prefix_item(...)
    assert item["preview_asset_path"] is None
```

```python
def test_build_prompt_prefix_preview_batch_preserves_requested_order():
    ...
```

- [ ] **Step 2: Run tests to verify they fail if behavior is missing**

Run: `uv run pytest tests/test_prompt_prefix_generation.py tests/test_style_config_prompt_prefix_ui.py -q`
Expected: FAIL until the side-panel preview and upload helpers are wired.

- [ ] **Step 3: Implement explicit preview-generation and upload persistence flow**

```python
uploaded_file = st.file_uploader(..., type=["png", "jpg", "jpeg", "webp", "svg"])
preview_asset_path = persist_uploaded_prompt_prefix_preview(uploaded_file, item_id)
```

```python
if st.button(tr("style.prefix_library.generate_candidate_previews")):
    preview_results = _generate_prompt_prefix_previews(...)
```

Keep candidate previews session-scoped until save, and keep comparison generation sequential.

- [ ] **Step 4: Run focused verification**

Run: `uv run pytest tests/test_prompt_prefix_generation.py tests/test_prompt_prefix_library_config.py tests/test_style_config_prompt_prefix_ui.py -q`
Expected: PASS

- [ ] **Step 5: Run full verification**

Run: `uv run pytest`
Expected: PASS with no new failures

Run: `uv run python -m py_compile pixelle_video/config/prompt_prefix_library.py pixelle_video/config/schema.py web/utils/prompt_prefix_ui.py web/components/style_config.py`
Expected: no output

- [ ] **Step 6: Commit and push the final implementation**

```bash
git add pixelle_video/config/prompt_prefix_library.py pixelle_video/config/schema.py web/utils/prompt_prefix_ui.py web/components/style_config.py tests/test_prompt_prefix_generation.py tests/test_prompt_prefix_library_config.py tests/test_style_config_prompt_prefix_ui.py resources/prompt_prefix_previews web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json docs/superpowers/plans/2026-04-21-prompt-prefix-gallery-redesign.md
git commit -m "feat: redesign prompt prefix library as template gallery"
git push origin dev
```
