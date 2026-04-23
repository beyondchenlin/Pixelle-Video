# Prompt Prefix Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an image-only prompt prefix library with persistent config storage, built-in presets, LLM-assisted prefix generation, and multi-style preview comparison in the existing style configuration UI.

**Architecture:** Extend `comfyui.image` config with a typed prompt-prefix library, move reusable library logic into focused helper modules, and keep `web/components/style_config.py` as a thin orchestration layer. Preserve legacy `comfyui.image.prompt_prefix` as a fallback path and leave `comfyui.video.prompt_prefix` unchanged.

**Tech Stack:** Python, Pydantic, Streamlit, pytest, existing Pixelle config manager and LLM service

---

### Task 1: Add typed prompt-prefix library config and pure helpers

**Files:**
- Create: `pixelle_video/config/prompt_prefix_library.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `pixelle_video/config/manager.py`
- Test: `tests/test_prompt_prefix_library_config.py`

- [ ] **Step 1: Write the failing config/helper tests**

```python
from pixelle_video.config.prompt_prefix_library import (
    BUILTIN_PROMPT_PREFIXES,
    get_effective_image_prompt_prefix,
    get_prompt_prefix_category_options,
)
from pixelle_video.config.schema import PixelleVideoConfig


def test_image_config_exposes_builtin_prompt_prefix_library_defaults():
    config = PixelleVideoConfig()

    library = config.comfyui.image.prompt_prefix_library

    assert library.active_prefix_id
    assert library.items
    assert library.items[0].style_category_id
    assert library.items[0].scene_category_id


def test_get_effective_image_prompt_prefix_prefers_active_library_item():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "legacy prefix",
                    "prompt_prefix_library": {
                        "active_prefix_id": "custom-flat",
                        "items": [
                            {
                                "id": "custom-flat",
                                "name": "Flat",
                                "content": "flat illustration, simple shapes",
                                "style_category_id": "flat_illustration",
                                "scene_category_id": "knowledge_sharing",
                                "source": "manual",
                                "is_builtin": False,
                            }
                        ],
                    },
                }
            }
        }
    )

    assert get_effective_image_prompt_prefix(config.comfyui.image) == "flat illustration, simple shapes"


def test_get_effective_image_prompt_prefix_falls_back_to_legacy_prefix_when_library_has_no_active_item():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"image": {"prompt_prefix": "legacy prefix", "prompt_prefix_library": {"active_prefix_id": None, "items": []}}}}
    )

    assert get_effective_image_prompt_prefix(config.comfyui.image) == "legacy prefix"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_prefix_library_config.py -v`
Expected: FAIL with missing module, missing schema field, or missing helper functions.

- [ ] **Step 3: Write minimal config models and helper implementation**

```python
class PromptPrefixItemConfig(BaseModel):
    id: str
    name: str
    content: str
    style_category_id: str
    scene_category_id: str
    source: Literal["builtin", "manual", "llm"] = "manual"
    is_builtin: bool = False
    note: str = ""
    created_at: Optional[str] = None


class PromptPrefixLibraryConfig(BaseModel):
    active_prefix_id: Optional[str] = None
    items: list[PromptPrefixItemConfig] = Field(default_factory=list)


def get_effective_image_prompt_prefix(image_config: ImageSubConfig) -> str:
    active_item = next(
        (item for item in image_config.prompt_prefix_library.items if item.id == image_config.prompt_prefix_library.active_prefix_id),
        None,
    )
    if active_item and active_item.content.strip():
        return active_item.content.strip()
    return image_config.prompt_prefix.strip()
```

- [ ] **Step 4: Add config-manager helpers and built-in preset access**

```python
def get_image_prompt_prefix_library(self) -> dict:
    return self.config.comfyui.image.prompt_prefix_library.model_dump()


def set_image_prompt_prefix_library(self, library_updates: dict):
    self.update({"comfyui": {"image": {"prompt_prefix_library": library_updates}}})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_prefix_library_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_prompt_prefix_library_config.py pixelle_video/config/prompt_prefix_library.py pixelle_video/config/schema.py pixelle_video/config/manager.py
git commit -m "feat: add prompt prefix library config"
```

### Task 2: Add LLM prefix-generation contract and deterministic library utilities

**Files:**
- Create: `pixelle_video/prompts/prompt_prefix_generation.py`
- Create: `pixelle_video/utils/prompt_prefix_generation.py`
- Modify: `pixelle_video/prompts/__init__.py`
- Test: `tests/test_prompt_prefix_generation.py`

- [ ] **Step 1: Write the failing generator/helper tests**

```python
from pixelle_video.utils.prompt_prefix_generation import (
    PromptPrefixGenerationResult,
    build_prompt_prefix_preview_batch,
    sanitize_prompt_prefix_candidates,
)


def test_sanitize_prompt_prefix_candidates_keeps_allowed_category_ids_and_trims_content():
    result = PromptPrefixGenerationResult.model_validate(
        {
            "items": [
                {
                    "name": "Warm Storybook",
                    "content": "  warm storybook illustration  ",
                    "style_category_id": "storybook",
                    "scene_category_id": "childrens_story",
                    "note": "soft and healing",
                }
            ]
        }
    )

    sanitized = sanitize_prompt_prefix_candidates(result)

    assert sanitized[0]["content"] == "warm storybook illustration"
    assert sanitized[0]["style_category_id"] == "storybook"


def test_build_prompt_prefix_preview_batch_limits_selection_count():
    selected_ids = ["a", "b", "c", "d", "e"]

    with pytest.raises(ValueError, match="at most 4"):
        build_prompt_prefix_preview_batch(selected_ids)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_prefix_generation.py -v`
Expected: FAIL with missing models or helper functions.

- [ ] **Step 3: Write the minimal generator prompt and helper code**

```python
class PromptPrefixCandidate(BaseModel):
    name: str
    content: str
    style_category_id: str
    scene_category_id: str
    note: str = ""


class PromptPrefixGenerationResult(BaseModel):
    items: list[PromptPrefixCandidate]


def build_prompt_prefix_generation_prompt(user_idea: str, language: str, allowed_style_ids: list[str], allowed_scene_ids: list[str]) -> str:
    return f"...{user_idea}..."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_prefix_generation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_prefix_generation.py pixelle_video/prompts/prompt_prefix_generation.py pixelle_video/utils/prompt_prefix_generation.py pixelle_video/prompts/__init__.py
git commit -m "feat: add prompt prefix generation helpers"
```

### Task 3: Integrate the image prompt-prefix library into the style UI

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `tests/test_streamlit_width_usage.py`
- Test: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Write the failing UI-focused helper tests**

```python
from pixelle_video.config.prompt_prefix_library import filter_prompt_prefix_items


def test_filter_prompt_prefix_items_applies_style_scene_and_keyword_filters():
    items = [
        {"id": "storybook-1", "name": "Warm Storybook", "style_category_id": "storybook", "scene_category_id": "childrens_story", "content": "warm storybook"},
        {"id": "flat-1", "name": "Flat Science", "style_category_id": "flat_illustration", "scene_category_id": "educational_illustration", "content": "flat science"},
    ]

    filtered = filter_prompt_prefix_items(
        items,
        style_category_id="storybook",
        scene_category_id="childrens_story",
        keyword="warm",
    )

    assert [item["id"] for item in filtered] == ["storybook-1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_style_config_prompt_prefix_ui.py -v`
Expected: FAIL because filter helper or UI-specific helpers are missing.

- [ ] **Step 3: Replace the image-only text area with library UI while leaving video behavior unchanged**

```python
if template_media_type == "video":
    prompt_prefix = st.text_area(...)
else:
    library = config_manager.get_image_prompt_prefix_library()
    active_prefix = ...
    style_filter = st.selectbox(...)
    scene_filter = st.selectbox(...)
    keyword = st.text_input(...)
    # render active summary, library actions, manual create, AI generate, preview batch
```

- [ ] **Step 4: Persist library mutations immediately and keep preview state in session only**

```python
if st.button(tr("style.prefix.set_active"), key=f"set_active_{item_id}", width="stretch"):
    config_manager.set_active_image_prompt_prefix(item_id)
    config_manager.save()
    safe_rerun()
```

- [ ] **Step 5: Run targeted tests**

Run: `uv run pytest tests/test_style_config_prompt_prefix_ui.py tests/test_streamlit_width_usage.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_style_config_prompt_prefix_ui.py tests/test_streamlit_width_usage.py web/components/style_config.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json
git commit -m "feat: add prompt prefix library ui"
```

### Task 4: Verify end-to-end compatibility and documentation surfaces

**Files:**
- Modify: `config.example.yaml`
- Modify: `README.md`
- Modify: `README_EN.md`
- Test: `tests/test_prompt_prefix_library_config.py`
- Test: `tests/test_prompt_prefix_generation.py`
- Test: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Add compatibility assertions for legacy fallback and built-in defaults**

```python
def test_legacy_prompt_prefix_remains_effective_without_library_selection():
    config = PixelleVideoConfig.model_validate({"comfyui": {"image": {"prompt_prefix": "legacy only"}}})

    assert get_effective_image_prompt_prefix(config.comfyui.image) == "legacy only"
```

- [ ] **Step 2: Update config example and docs to describe the image-only library**

```yaml
image:
  prompt_prefix: "legacy fallback only"
  prompt_prefix_library:
    active_prefix_id: builtin_childrens_storybook_warm
```

- [ ] **Step 3: Run focused verification**

Run: `uv run pytest tests/test_prompt_prefix_library_config.py tests/test_prompt_prefix_generation.py tests/test_style_config_prompt_prefix_ui.py tests/test_streamlit_width_usage.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add config.example.yaml README.md README_EN.md tests/test_prompt_prefix_library_config.py tests/test_prompt_prefix_generation.py tests/test_style_config_prompt_prefix_ui.py
git commit -m "docs: document prompt prefix library"
```
