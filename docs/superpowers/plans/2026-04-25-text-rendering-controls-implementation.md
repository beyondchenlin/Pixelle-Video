# Text Rendering Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered text-layer and image-text suppression controls with a first-class `text_rendering` request model, UI section, backend normalization path, and prompt assembly behavior.

**Architecture:** Add typed `text_rendering` models at API and core boundaries, then route both overlay text rendering and generated-image text suppression through that single object. The frontend renders a new `文字渲染` section and emits only `text_rendering`; pipeline code consumes normalized settings and no longer reads old top-level text fields.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, Streamlit UI helpers, pytest, existing Pixelle pipeline and prompt helper modules.

---

## File Structure

- Modify `api/schemas/video.py`: add `TextRenderingRequest`, `TextOverlayRequest`, `ImageTextPolicyRequest`; remove old top-level request fields.
- Modify `api/schemas/content.py`: add `text_rendering` to image prompt generation and remove old top-level no-text field.
- Modify `api/routers/video.py`: map `request_body.text_rendering` into generate params.
- Modify `api/routers/content.py`: pass `text_rendering` to prompt generation.
- Modify `pixelle_video/models/text_overlay.py`: add normalized settings classes and overlay-policy construction from `text_rendering.overlay`.
- Modify `pixelle_video/utils/prompt_helper.py`: apply custom image-text prompt rules instead of fixed `NO_TEXT_POSITIVE_RULE`.
- Modify `pixelle_video/utils/content_generators.py`: replace `forbid_embedded_text_in_image` with `text_rendering`.
- Modify `pixelle_video/pipelines/standard.py` and `pixelle_video/pipelines/custom.py`: normalize and pass `text_rendering`; persist it in metadata context.
- Modify `pixelle_video/services/persistence.py`: include `text_rendering` in persisted config/metadata where config serialization currently carries render/prompt inputs.
- Modify `web/components/style_config.py`: create the `文字渲染` section; remove controls from render backend and storyboard sections.
- Modify `web/components/output_preview.py`: emit `text_rendering` in single and batch requests.
- Modify `web/i18n/locales/zh_CN.json` and `web/i18n/locales/en_US.json`: add labels/help for the new section and fields.
- Update tests in `tests/test_video_api.py`, `tests/test_content_image_prompt_api.py`, `tests/test_output_preview.py`, `tests/test_style_config_storyboard_planning_ui.py`, `tests/test_text_overlay_models.py`, `tests/test_standard_pipeline_prompt_prefix.py`, and `tests/test_custom_pipeline_styled_batch.py`.

## Task 1: API Schema and Router Contract

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/schemas/content.py`
- Modify: `api/routers/video.py`
- Modify: `api/routers/content.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_content_image_prompt_api.py`

- [ ] **Step 1: Write failing video API schema tests**

Add these tests to `tests/test_video_api.py` near the existing text-layer tests:

```python
def test_video_generate_request_accepts_text_rendering_policy():
    request = VideoGenerateRequest(
        text="hello",
        text_rendering={
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["hyperframes"],
                "density": "medium",
                "max_items_per_frame": 2,
            },
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "no letters in image",
                "negative_prompt": "letters, watermark",
            },
        },
    )

    assert request.text_rendering.overlay.enabled is True
    assert request.text_rendering.image_text.suppress_embedded_text is True
    assert request.text_rendering.image_text.positive_prompt == "no letters in image"


def test_video_generate_request_rejects_legacy_text_fields():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", text_layer={"enabled": True})

    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="hello", forbid_embedded_text_in_image=True)
```

- [ ] **Step 2: Run schema tests and verify they fail**

Run: `pytest tests/test_video_api.py::test_video_generate_request_accepts_text_rendering_policy tests/test_video_api.py::test_video_generate_request_rejects_legacy_text_fields -v`

Expected: FAIL because `text_rendering` is not defined and old fields are still accepted.

- [ ] **Step 3: Implement Pydantic request models**

In `api/schemas/video.py`, add:

```python
class TextOverlayRequest(BaseModel):
    enabled: bool = False
    mode: Literal["suppress", "programmatic_only", "native_hint", "hybrid"] = "programmatic_only"
    renderer_targets: List[Literal["hyperframes", "html", "ass", "native_prompt", "python"]] = Field(default_factory=list)
    density: Literal["low", "medium", "high"] = "medium"
    max_items_per_frame: int = Field(2, ge=0)


class ImageTextPolicyRequest(BaseModel):
    suppress_embedded_text: bool = False
    positive_prompt: str = Field(
        "no visible text, no Chinese characters, no English letters, no words, no subtitles, no captions, no watermark, no logo text, convey the idea through objects, symbols, composition, and scene elements instead of written text",
        description="Prompt fragment appended only when suppress_embedded_text is true",
    )
    negative_prompt: Optional[str] = None


class TextRenderingRequest(BaseModel):
    overlay: TextOverlayRequest = Field(default_factory=TextOverlayRequest)
    image_text: ImageTextPolicyRequest = Field(default_factory=ImageTextPolicyRequest)
```

Set `model_config = ConfigDict(extra="forbid")` on `VideoGenerateRequest` and remove the old `forbid_embedded_text_in_image` and `text_layer` fields. Add:

```python
text_rendering: Optional[TextRenderingRequest] = Field(
    None,
    description="Unified text rendering and generated-image text policy",
)
```

Apply the same `text_rendering` field and `extra="forbid"` behavior to `api/schemas/content.py` for image prompt generation requests.

- [ ] **Step 4: Update video router mapping**

In `api/routers/video.py`, remove construction of `forbid_embedded_text_in_image` and `text_layer`. Add:

```python
if request_body.text_rendering is not None:
    video_params["text_rendering"] = request_body.text_rendering.model_dump()
```

In `api/routers/content.py`, pass:

```python
text_rendering=(
    request.text_rendering.model_dump()
    if request.text_rendering is not None
    else None
)
```

- [ ] **Step 5: Run API tests**

Run: `pytest tests/test_video_api.py tests/test_content_image_prompt_api.py -v`

Expected: PASS after updating old assertions to expect `text_rendering` and validation failures for old fields.

- [ ] **Step 6: Commit**

Run:

```bash
git add api/schemas/video.py api/schemas/content.py api/routers/video.py api/routers/content.py tests/test_video_api.py tests/test_content_image_prompt_api.py
git commit -m "feat: add text rendering request contract"
git push
```

## Task 2: Core Text Rendering Normalization

**Files:**
- Modify: `pixelle_video/models/text_overlay.py`
- Modify: `pixelle_video/utils/prompt_helper.py`
- Test: `tests/test_text_overlay_models.py`

- [ ] **Step 1: Write failing normalization tests**

Add to `tests/test_text_overlay_models.py`:

```python
def test_build_text_rendering_settings_defaults_do_not_suppress_image_text():
    settings = build_text_rendering_settings(None)

    assert settings.overlay.enabled is False
    assert settings.image_text.suppress_embedded_text is False
    assert settings.image_text.positive_prompt.startswith("no visible text")


def test_build_text_rendering_settings_accepts_custom_image_text_prompt():
    settings = build_text_rendering_settings(
        {
            "image_text": {
                "suppress_embedded_text": True,
                "positive_prompt": "avoid all written marks",
                "negative_prompt": "letters, logo",
            }
        }
    )

    assert settings.image_text.suppress_embedded_text is True
    assert settings.image_text.positive_prompt == "avoid all written marks"
    assert settings.image_text.negative_prompt == "letters, logo"


def test_build_text_rendering_policy_uses_overlay_only():
    settings = build_text_rendering_settings(
        {
            "overlay": {
                "enabled": True,
                "mode": "programmatic_only",
                "renderer_targets": ["ass"],
                "density": "high",
                "max_items_per_frame": 3,
            },
            "image_text": {"suppress_embedded_text": True},
        }
    )

    policy = build_text_rendering_policy(settings.overlay)

    assert policy.image_text_mode == "programmatic_only"
    assert policy.enabled_targets == ("ass",)
    assert policy.density == "high"
    assert policy.max_items_per_frame == 3
```

- [ ] **Step 2: Run normalization tests and verify they fail**

Run: `pytest tests/test_text_overlay_models.py -v`

Expected: FAIL because `build_text_rendering_settings` does not exist and `build_text_rendering_policy` still accepts old arguments.

- [ ] **Step 3: Add normalized dataclasses**

In `pixelle_video/models/text_overlay.py`, add:

```python
DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT = (
    "no visible text, no Chinese characters, no English letters, no words, "
    "no subtitles, no captions, no watermark, no logo text, convey the idea "
    "through objects, symbols, composition, and scene elements instead of written text"
)


@dataclass(frozen=True)
class TextOverlaySettings:
    enabled: bool = False
    mode: str = "programmatic_only"
    renderer_targets: tuple[str, ...] = ()
    density: str = "medium"
    max_items_per_frame: int = 2


@dataclass(frozen=True)
class ImageTextPromptPolicy:
    suppress_embedded_text: bool = False
    positive_prompt: str = DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT
    negative_prompt: str | None = None


@dataclass(frozen=True)
class TextRenderingSettings:
    overlay: TextOverlaySettings = field(default_factory=TextOverlaySettings)
    image_text: ImageTextPromptPolicy = field(default_factory=ImageTextPromptPolicy)
```

Add:

```python
def build_text_rendering_settings(data: Mapping[str, Any] | None) -> TextRenderingSettings:
    payload = dict(data or {})
    overlay_payload = dict(payload.get("overlay") or {})
    image_payload = dict(payload.get("image_text") or {})
    return TextRenderingSettings(
        overlay=TextOverlaySettings(
            enabled=bool(overlay_payload.get("enabled", False)),
            mode=str(overlay_payload.get("mode", "programmatic_only")),
            renderer_targets=tuple(overlay_payload.get("renderer_targets", ())),
            density=str(overlay_payload.get("density", "medium")),
            max_items_per_frame=int(overlay_payload.get("max_items_per_frame", 2)),
        ),
        image_text=ImageTextPromptPolicy(
            suppress_embedded_text=bool(image_payload.get("suppress_embedded_text", False)),
            positive_prompt=str(
                image_payload.get("positive_prompt", DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT) or ""
            ).strip(),
            negative_prompt=(
                str(image_payload.get("negative_prompt")).strip()
                if image_payload.get("negative_prompt") is not None
                else None
            ),
        ),
    )
```

Refactor `build_text_rendering_policy()` to accept `overlay: TextOverlaySettings | Mapping[str, Any] | None` and return disabled/default policy when overlay is missing or `enabled=False`.

- [ ] **Step 4: Add prompt helper functions**

In `pixelle_video/utils/prompt_helper.py`, keep `NO_TEXT_POSITIVE_RULE` for default copy reuse but add:

```python
def apply_image_text_policy(prompt: str, image_text_policy: Any) -> str:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        return cleaned_prompt
    if not _read_value(image_text_policy, "suppress_embedded_text", False):
        return cleaned_prompt
    positive_prompt = str(_read_value(image_text_policy, "positive_prompt", "") or "").strip()
    if not positive_prompt:
        return cleaned_prompt
    return ", ".join(_normalize_prompt_list([cleaned_prompt, positive_prompt]))
```

Add a matching selector for custom negative prompt:

```python
def select_image_text_negative_prompt(image_text_policy: Any) -> tuple[str, ...] | None:
    if not _read_value(image_text_policy, "suppress_embedded_text", False):
        return None
    negative_prompt = str(_read_value(image_text_policy, "negative_prompt", "") or "").strip()
    if not negative_prompt:
        return None
    return tuple(_normalize_negative_rule_list([negative_prompt]))
```

- [ ] **Step 5: Run normalization tests**

Run: `pytest tests/test_text_overlay_models.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add pixelle_video/models/text_overlay.py pixelle_video/utils/prompt_helper.py tests/test_text_overlay_models.py
git commit -m "feat: normalize text rendering settings"
git push
```

## Task 3: Prompt Generation and Pipeline Consumption

**Files:**
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_standard_pipeline_prompt_prefix.py`
- Test: `tests/test_custom_pipeline_styled_batch.py`

- [ ] **Step 1: Write failing prompt assembly tests**

In `tests/test_standard_pipeline_prompt_prefix.py`, update `test_standard_pipeline_plan_visuals_uses_shared_styled_batch` so it asserts the new default behavior. Replace:

```python
assert ctx.image_prompts == [
    apply_no_text_policy(
        "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, bird-universe dog sprint"
    )
]
assert ctx.media_negative_prompt is not None
assert "text" in ctx.media_negative_prompt
assert "Chinese characters" in ctx.media_negative_prompt
```

with:

```python
expected_prompt = (
    "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, "
    "medium_shot, context, strategy board, bird-universe dog sprint"
)
assert ctx.image_prompts == [expected_prompt]
assert "no visible text" not in ctx.image_prompts[0]
assert ctx.media_negative_prompt is None
```

Add a second standard-pipeline test by copying `test_standard_pipeline_plan_visuals_uses_shared_styled_batch`, renaming it to `test_standard_pipeline_plan_visuals_appends_custom_image_text_prompt`, and making these exact changes:

```python
ctx.params["text_rendering"] = {
    "image_text": {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid written marks",
        "negative_prompt": "written marks, letters",
    }
}
```

Use these assertions:

```python
assert "avoid written marks" in ctx.image_prompts[0]
assert "no visible text" not in ctx.image_prompts[0]
assert ctx.media_negative_prompt is not None
assert "written marks" in ctx.media_negative_prompt
assert "letters" in ctx.media_negative_prompt
```

In `tests/test_custom_pipeline_styled_batch.py`, update `test_custom_pipeline_uses_styled_batch_and_threads_negative_prompt` to pass:

```python
text_rendering={
    "image_text": {
        "suppress_embedded_text": True,
        "positive_prompt": "avoid written marks",
        "negative_prompt": "written marks, letters",
    }
},
```

Replace:

```python
assert "text" in captured["media_negative_prompt"]
assert "Chinese characters" in captured["media_negative_prompt"]
assert result.storyboard.frames[0].image_prompt == apply_no_text_policy(
    "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, medium_shot, context, strategy board, styled prompt"
)
```

with:

```python
assert "written marks" in captured["media_negative_prompt"]
assert "letters" in captured["media_negative_prompt"]
assert result.storyboard.frames[0].image_prompt == (
    "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, "
    "medium_shot, context, strategy board, styled prompt, avoid written marks"
)
```

Add a second custom-pipeline test by copying `test_custom_pipeline_uses_styled_batch_and_threads_negative_prompt`, renaming it to `test_custom_pipeline_default_text_rendering_does_not_suppress_image_text`, removing the `text_rendering={...}` call argument, and using:

```python
assert captured["media_negative_prompt"] is None
assert "no visible text" not in result.storyboard.frames[0].image_prompt
assert result.storyboard.frames[0].image_prompt == (
    "flat illustration, Neutral Knowledge Storyboard, clean educational illustration, "
    "medium_shot, context, strategy board, styled prompt"
)
```

- [ ] **Step 2: Run pipeline tests and verify they fail**

Run: `pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py -v`

Expected: FAIL because pipeline still reads `forbid_embedded_text_in_image=True`.

- [ ] **Step 3: Refactor content generator signature**

In `pixelle_video/utils/content_generators.py`, replace:

```python
forbid_embedded_text_in_image: bool = True
```

with:

```python
text_rendering: Optional[Mapping[str, Any]] = None
```

At the start of `generate_styled_image_prompt_batch()`, add:

```python
text_rendering_settings = build_text_rendering_settings(text_rendering)
```

Use `text_rendering_settings.overlay` for `build_text_rendering_policy()` and `text_rendering_settings.image_text` for prompt text suppression.

- [ ] **Step 4: Replace no-text prompt application**

In `generate_styled_image_prompt_batch()`, replace calls to `apply_no_text_policy()` and `apply_text_rendering_policy(... forbid ...)` with:

```python
final_prompts = [
    apply_image_text_policy(prompt, text_rendering_settings.image_text)
    for prompt in final_prompts
]
```

For negative prompts, replace fixed `NO_TEXT_NEGATIVE_RULES` selection with:

```python
extra_negative_rules=select_image_text_negative_prompt(text_rendering_settings.image_text)
```

- [ ] **Step 5: Update standard and custom pipelines**

In `pixelle_video/pipelines/standard.py`, build settings once:

```python
text_rendering_settings = build_text_rendering_settings(ctx.params.get("text_rendering"))
text_policy = build_text_rendering_policy(text_rendering_settings.overlay)
```

Pass:

```python
text_rendering=ctx.params.get("text_rendering")
```

to `generate_styled_image_prompt_batch()`. Remove old `forbid_embedded_text_in_image` references.

Repeat equivalent changes in `pixelle_video/pipelines/custom.py`.

- [ ] **Step 6: Persist new request field**

In `pixelle_video/services/persistence.py`, add `text_rendering` to metadata/config serialization where input params are stored. The persisted shape must be:

```python
"text_rendering": params.get("text_rendering")
```

Do not emit old `text_layer` or `forbid_embedded_text_in_image` for new tasks.

- [ ] **Step 7: Run pipeline tests**

Run: `pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py -v`

Expected: PASS after updating old assertions to `text_rendering`.

- [ ] **Step 8: Commit**

Run:

```bash
git add pixelle_video/utils/content_generators.py pixelle_video/pipelines/standard.py pixelle_video/pipelines/custom.py pixelle_video/services/persistence.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py
git commit -m "feat: route prompt text policy through text rendering"
git push
```

## Task 4: Frontend UI Section and Request Builders

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_style_config_storyboard_planning_ui.py`

- [ ] **Step 1: Write failing request builder tests**

Update `tests/test_output_preview.py`:

```python
def test_build_single_generation_request_includes_text_rendering():
    request = build_single_generation_request(
        {
            "text": "hello",
            "text_rendering": {
                "overlay": {"enabled": False},
                "image_text": {
                    "suppress_embedded_text": True,
                    "positive_prompt": "avoid written marks",
                    "negative_prompt": None,
                },
            },
        },
        progress_callback=lambda *_: None,
        session_state={},
    )

    assert request["text_rendering"]["image_text"]["positive_prompt"] == "avoid written marks"
    assert "text_layer" not in request
    assert "forbid_embedded_text_in_image" not in request
```

Add the equivalent batch test for `build_batch_shared_config()`.

- [ ] **Step 2: Run request builder tests and verify they fail**

Run: `pytest tests/test_output_preview.py::test_build_single_generation_request_includes_text_rendering tests/test_output_preview.py::test_build_batch_shared_config_includes_text_rendering -v`

Expected: FAIL because builders still emit old fields.

- [ ] **Step 3: Add UI payload helper**

In `web/components/style_config.py`, add:

```python
DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT = (
    "no visible text, no Chinese characters, no English letters, no words, "
    "no subtitles, no captions, no watermark, no logo text, convey the idea "
    "through objects, symbols, composition, and scene elements instead of written text"
)


def build_text_rendering_payload(*, overlay: dict | None, suppress_embedded_text: bool, positive_prompt: str, negative_prompt: str | None = None) -> dict:
    return {
        "overlay": overlay or {"enabled": False},
        "image_text": {
            "suppress_embedded_text": bool(suppress_embedded_text),
            "positive_prompt": (positive_prompt or "").strip(),
            "negative_prompt": (negative_prompt or None),
        },
    }
```

- [ ] **Step 4: Move controls into `文字渲染` section**

In `render_style_config()`, remove `text_layer_policy = render_text_layer_controls(render_backend)` from the render backend section. After `element_animation_settings = render_element_animation_controls()`, add:

```python
with render_middle_column_collapsible_section(
    tr("section.text_rendering"),
    expanded=False,
):
    text_layer_policy = render_text_layer_controls(render_backend)
    suppress_embedded_text = st.checkbox(
        tr("text_rendering.image_text.suppress"),
        value=st.session_state.get("text_rendering_suppress_embedded_text", False),
        key="text_rendering_suppress_embedded_text",
        help=tr("text_rendering.image_text.suppress_help"),
    )
    positive_prompt = st.text_area(
        tr("text_rendering.image_text.positive_prompt"),
        value=st.session_state.get(
            "text_rendering_image_text_positive_prompt",
            DEFAULT_IMAGE_TEXT_POSITIVE_PROMPT,
        ),
        key="text_rendering_image_text_positive_prompt",
        help=tr("text_rendering.image_text.positive_prompt_help"),
    )
    if not suppress_embedded_text:
        st.caption(tr("text_rendering.image_text.inactive_hint"))
    text_rendering_payload = build_text_rendering_payload(
        overlay=text_layer_policy,
        suppress_embedded_text=suppress_embedded_text,
        positive_prompt=positive_prompt,
    )
```

Remove the storyboard checkbox for `storyboard_forbid_embedded_text_in_image`.

- [ ] **Step 5: Update returned UI params**

In the final `result` dict from `render_style_config()`, add:

```python
"text_rendering": text_rendering_payload,
```

Remove:

```python
"text_layer": text_layer_policy
"forbid_embedded_text_in_image": ...
```

- [ ] **Step 6: Update output request builders**

In `web/components/output_preview.py`, remove old top-level fields and add:

```python
if video_params.get("text_rendering") is not None:
    request["text_rendering"] = video_params["text_rendering"]
```

Repeat for `build_batch_shared_config()`.

- [ ] **Step 7: Add i18n labels**

In `web/i18n/locales/zh_CN.json`, add keys:

```json
"section.text_rendering": "文字渲染",
"text_rendering.image_text.suppress": "禁止图中文字",
"text_rendering.image_text.suppress_help": "开启后会把下方提示词注入图片生成 prompt，抑制模型在图中生成文字。",
"text_rendering.image_text.positive_prompt": "禁止图中文字提示词",
"text_rendering.image_text.positive_prompt_help": "仅在勾选禁止图中文字时生效。",
"text_rendering.image_text.inactive_hint": "当前未启用禁止图中文字，提示词暂不生效。"
```

Add equivalent English strings in `web/i18n/locales/en_US.json`.

- [ ] **Step 8: Run frontend tests**

Run: `pytest tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py -v`

Expected: PASS after updating tests to no longer expect old fields.

- [ ] **Step 9: Commit**

Run:

```bash
git add web/components/style_config.py web/components/output_preview.py web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py
git commit -m "feat: add text rendering UI controls"
git push
```

## Task 5: End-to-End Cleanup and Verification

**Files:**
- Modify any remaining tests containing old field expectations.
- No new production files expected unless the previous tasks surface a missing boundary.

- [ ] **Step 1: Search for old field usage**

Run:

```bash
rg -n "forbid_embedded_text_in_image|text_layer\\]" api pixelle_video web tests -g "*.py"
```

Expected: no production request-building or pipeline-read paths use `forbid_embedded_text_in_image`; `text_layer_summary` and template text-layer implementation may remain because they describe result artifacts, not request input.

- [ ] **Step 2: Update remaining tests deliberately**

For each remaining old-field test, choose one outcome:

```python
assert "text_rendering" in request
assert "forbid_embedded_text_in_image" not in request
assert "text_layer" not in request
```

or, for historical result summaries:

```python
assert metadata["result"]["text_layer_summary"]["renderer"] == "ass"
```

- [ ] **Step 3: Run focused suite**

Run:

```bash
pytest tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_output_preview.py tests/test_style_config_storyboard_planning_ui.py tests/test_text_overlay_models.py tests/test_standard_pipeline_prompt_prefix.py tests/test_custom_pipeline_styled_batch.py -v
```

Expected: PASS.

- [ ] **Step 4: Run broader regression**

Run:

```bash
pytest tests/test_render_backend_ui.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_standard_pipeline_staged_mode.py -v
```

Expected: PASS. These tests ensure result-side `text_layer_summary` and render-backend behavior were not broken.

- [ ] **Step 5: Manual UI smoke check**

Start the app using the repo’s usual command, then verify:

```text
1. The main panel shows 文字渲染 between 元素微动 and 分镜规划.
2. 渲染后端 no longer shows 启用文字层.
3. 分镜规划 no longer shows 禁止图中文字.
4. 禁止图中文字 is unchecked by default.
5. 禁止图中文字提示词 is visible and editable while unchecked.
6. Generated request payload contains text_rendering and not the two old top-level fields.
```

- [ ] **Step 6: Commit cleanup**

Run:

```bash
git add api pixelle_video web tests
git commit -m "test: verify text rendering migration"
git push
```

If Step 1 found no additional edits, skip this commit and note that cleanup was already covered by earlier commits.

## Self-Review

- Spec coverage: UI placement, default unchecked state, editable positive prompt, `text_rendering` request shape, old-field rejection, prompt assembly behavior, batch parity, persistence, and tests all map to tasks above.
- Placeholder scan: no placeholder markers or unspecified implementation steps remain; each task lists files, test commands, expected failures, implementation snippets, and commit commands.
- Type consistency: plan uses `text_rendering.overlay` and `text_rendering.image_text` throughout; legacy `text_layer` only remains as result summary/template terminology where the spec allows it.
