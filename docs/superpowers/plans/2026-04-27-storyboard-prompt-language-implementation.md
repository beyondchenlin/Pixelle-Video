# Storyboard Prompt Language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a storyboard prompt language control to the Web UI that defaults to Chinese, preserves the current English behavior when selected, and drives both storyboard planning text and final image prompts from the same source contract.

**Architecture:** Extend the existing storyboard control payload with a typed `storyboard_prompt_language` field and thread it through Web UI request assembly, API schemas, pipeline params, storyboard planning, image prompt generation, persistence, and history/preview metadata. Keep the option colocated with existing storyboard planning controls so the UI boundary stays clean, and avoid ad-hoc translation layers by generating the chosen language at the source prompt builders.

**Tech Stack:** Streamlit Web UI, FastAPI/Pydantic schemas, Pixelle storyboard services, Python dataclasses, pytest

---

### Task 1: Add the language field to the Web/UI and request contracts

**Files:**
- Modify: `web/components/style_config.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Modify: `api/schemas/video.py`
- Modify: `api/schemas/content.py`
- Modify: `api/routers/video.py`
- Modify: `api/routers/content.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_style_config_storyboard_planning_ui.py`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_content_image_prompt_api.py`

- [ ] **Step 1: Write failing UI and contract tests**

```python
def test_build_storyboard_control_payload_keeps_prompt_language():
    payload = build_storyboard_control_payload(
        world_preset_id="neutral_knowledge_storyboard",
        storyboard_prompt_language="zh_CN",
    )
    assert payload["storyboard_prompt_language"] == "zh_CN"


def test_build_single_generation_request_includes_storyboard_prompt_language():
    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "storyboard_prompt_language": "zh_CN",
            "consistency_strength": "standard",
        },
        progress_callback=lambda *_args, **_kwargs: None,
        session_state={"template_media_width": 1080, "template_media_height": 1920},
    )
    assert request["storyboard_prompt_language"] == "zh_CN"


def test_video_generate_request_accepts_storyboard_prompt_language():
    request = VideoGenerateRequest(text="hello", storyboard_prompt_language="zh_CN")
    assert request.storyboard_prompt_language == "zh_CN"


def test_image_prompt_generate_request_accepts_storyboard_prompt_language():
    request = ImagePromptGenerateRequest(
        narrations=["scene one"],
        storyboard_prompt_language="en_US",
    )
    assert request.storyboard_prompt_language == "en_US"
```

- [ ] **Step 2: Run contract-focused tests and verify they fail for the missing field**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_style_config_storyboard_planning_ui.py tests\test_output_preview.py tests\test_video_api.py tests\test_content_image_prompt_api.py -q`

Expected: failures showing `storyboard_prompt_language` is missing from payloads and schema models.

- [ ] **Step 3: Implement the UI control, i18n copy, request plumbing, and persistence field**

```python
# web/components/style_config.py
storyboard_prompt_language = st.segmented_control(
    tr("storyboard.prompt_language"),
    options=["zh_CN", "en_US"],
    default="zh_CN",
    format_func=lambda value: tr(f"storyboard.option.prompt_language.{value}"),
    key="storyboard_prompt_language",
)

payload = {
    "world_preset_id": world_preset_id,
    "shot_preset_id": shot_preset_id,
    "storyboard_prompt_language": storyboard_prompt_language,
    "consistency_strength": consistency_strength,
}
```

```python
# api/schemas/video.py / api/schemas/content.py
storyboard_prompt_language: Optional[Literal["zh_CN", "en_US"]] = Field(
    "zh_CN",
    description="Language used for storyboard planning fields and generated image prompts",
)
```

```python
# web/components/output_preview.py
request["storyboard_prompt_language"] = video_params.get("storyboard_prompt_language", "zh_CN")
shared_config["storyboard_prompt_language"] = video_params.get("storyboard_prompt_language", "zh_CN")
```

```python
# pixelle_video/models/storyboard.py
storyboard_prompt_language: Optional[str] = None
```

- [ ] **Step 4: Re-run the same contract tests and verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_style_config_storyboard_planning_ui.py tests\test_output_preview.py tests\test_video_api.py tests\test_content_image_prompt_api.py -q`

Expected: PASS with the new field present in UI payloads, request builders, and schemas.

### Task 2: Generate image prompts in the selected language

**Files:**
- Modify: `pixelle_video/prompts/image_generation.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `pixelle_video/services/image_prompt_composer.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_content_generators_structured_output.py`
- Test: `tests/test_styled_image_prompt_batch.py`

- [ ] **Step 1: Write failing tests for prompt-language-aware image prompt generation**

```python
def test_build_image_prompt_prompt_uses_chinese_contract_when_requested():
    prompt = build_image_prompt_prompt(
        narrations=["小习惯会不断累积"],
        min_words=30,
        max_words=60,
        prompt_language="zh_CN",
    )
    assert "必须使用中文" in prompt
    assert "Must use English" not in prompt


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_passes_prompt_language(monkeypatch):
    captured = {}

    async def fake_generate_image_prompts(*args, **kwargs):
        captured["prompt_language"] = kwargs["prompt_language"]
        return ["一个安静的书房，晨光照进桌面"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["small habits compound"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        prompt_language="zh_CN",
    )

    assert captured["prompt_language"] == "zh_CN"
```

- [ ] **Step 2: Run the image prompt tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_content_generators_structured_output.py tests\test_styled_image_prompt_batch.py -q`

Expected: failures because prompt builders and generation helpers do not yet accept or enforce `prompt_language`.

- [ ] **Step 3: Add prompt-language support to the prompt template and generation helpers**

```python
# pixelle_video/prompts/image_generation.py
def build_image_prompt_prompt(..., prompt_language: str = "en_US") -> str:
    language_name = "中文" if prompt_language == "zh_CN" else "English"
    output_requirement = (
        "图片提示词必须使用中文"
        if prompt_language == "zh_CN"
        else "Image prompts must use English"
    )
```

```python
# pixelle_video/utils/content_generators.py
async def generate_image_prompts(..., prompt_language: str = "en_US", ...):
    prompt = build_image_prompt_prompt(
        narrations=batch.items,
        min_words=min_words,
        max_words=max_words,
        style_profile=style_profile,
        prompt_contexts=...,
        prompt_language=prompt_language,
    )
```

```python
# pixelle_video/pipelines/standard.py
styled_batch = await ImagePromptComposer().compose(
    ...,
    prompt_language=ctx.params.get("storyboard_prompt_language", "zh_CN"),
)
```

- [ ] **Step 4: Re-run the image prompt tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_content_generators_structured_output.py tests\test_styled_image_prompt_batch.py -q`

Expected: PASS with `zh_CN` producing Chinese-language prompt instructions and `en_US` preserving the existing English behavior.

### Task 3: Generate storyboard planning fields in the selected language and persist the result cleanly

**Files:**
- Modify: `pixelle_video/prompts/storyboard_generation.py`
- Modify: `pixelle_video/services/storyboard_generation.py`
- Modify: `pixelle_video/prompts/storyboard_planning.py`
- Modify: `pixelle_video/services/storyboard_planner.py`
- Modify: `web/pages/2_📚_History.py`
- Test: `tests/test_storyboard_generation_service.py`
- Test: `tests/test_storyboard_planner.py`
- Test: `tests/test_storyboard_preview_ui.py`

- [ ] **Step 1: Write failing tests for Chinese/English storyboard planning output contracts**

```python
def test_build_smart_storyboard_prompt_uses_chinese_field_descriptions_when_requested():
    prompt = build_smart_storyboard_prompt(
        source_text="先解释概念，再给出结论。",
        count_mode="auto",
        requested_scene_count=None,
        min_scene_count=1,
        max_scene_count=5,
        prompt_language="zh_CN",
    )
    assert "visual_goal" in prompt
    assert "这一帧需要传达的视觉重点" in prompt


@pytest.mark.asyncio
async def test_storyboard_generation_service_manual_segments_use_chinese_defaults():
    plan = await StoryboardGenerationService().generate(
        llm_service=None,
        source_text="第一句。第二句。",
        storyboard_mode="punctuation",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
        prompt_language="zh_CN",
    )
    assert "用画面表达第 1 个分镜段落" in plan.frames[0].visual_goal


@pytest.mark.asyncio
async def test_plan_storyboard_batch_passes_prompt_language_to_prompt_builder(monkeypatch):
    captured = {}

    def fake_build_storyboard_planning_prompt(**kwargs):
        captured["prompt_language"] = kwargs["prompt_language"]
        return "{}"

    monkeypatch.setattr(
        "pixelle_video.services.storyboard_planner.build_storyboard_planning_prompt",
        fake_build_storyboard_planning_prompt,
    )
```

- [ ] **Step 2: Run storyboard generation/planner tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_storyboard_generation_service.py tests\test_storyboard_planner.py tests\test_storyboard_preview_ui.py -q`

Expected: failures because storyboard prompt builders and deterministic fallback text still hardcode English.

- [ ] **Step 3: Implement prompt-language-aware storyboard prompt builders, deterministic defaults, and history metadata**

```python
# pixelle_video/prompts/storyboard_generation.py
def build_smart_storyboard_prompt(..., prompt_language: str = "en_US") -> str:
    frame_schema = {
        "source_text": "该分镜覆盖的原文片段" if prompt_language == "zh_CN" else "Text preview covered by this frame (for reference).",
        "visual_goal": "这一帧需要传达的视觉重点" if prompt_language == "zh_CN" else "What this frame should communicate visually.",
        "prompt_intent": "供后续图片提示词组合使用的创作意图" if prompt_language == "zh_CN" else "Guidance for later image prompt composition.",
    }
```

```python
# pixelle_video/services/storyboard_generation.py
visual_goal = (
    f"用画面表达第 {index} 个分镜段落。"
    if prompt_language == "zh_CN"
    else f"Visualize storyboard segment {index}."
)
```

```python
# pixelle_video/services/storyboard_planner.py
planner_prompt = build_storyboard_planning_prompt(
    ...,
    prompt_language=prompt_language,
)
snapshot["storyboard_prompt_language"] = prompt_language
```

```python
# web/pages/2_📚_History.py
summary_items.append(
    (
        "history.detail.storyboard_prompt_language",
        _translate_storyboard_option("prompt_language", snapshot.get("storyboard_prompt_language")),
    )
)
```

- [ ] **Step 4: Run storyboard-focused tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_storyboard_generation_service.py tests\test_storyboard_planner.py tests\test_storyboard_preview_ui.py -q`

Expected: PASS with Chinese and English storyboard planning prompts producing language-appropriate field guidance and deterministic fallback text.

### Task 4: Run the end-to-end regression slice for the whole feature

**Files:**
- Test: `tests/test_style_config_storyboard_planning_ui.py`
- Test: `tests/test_output_preview.py`
- Test: `tests/test_video_api.py`
- Test: `tests/test_content_image_prompt_api.py`
- Test: `tests/test_content_generators_structured_output.py`
- Test: `tests/test_styled_image_prompt_batch.py`
- Test: `tests/test_storyboard_generation_service.py`
- Test: `tests/test_storyboard_planner.py`
- Test: `tests/test_storyboard_preview_ui.py`

- [ ] **Step 1: Run the full targeted regression set**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_style_config_storyboard_planning_ui.py tests\test_output_preview.py tests\test_video_api.py tests\test_content_image_prompt_api.py tests\test_content_generators_structured_output.py tests\test_styled_image_prompt_batch.py tests\test_storyboard_generation_service.py tests\test_storyboard_planner.py tests\test_storyboard_preview_ui.py -q`

Expected: PASS with zero failures.

- [ ] **Step 2: Review the diff for unintended drift before any commit**

Run: `git -C D:\demo1\Pixelle\Pixelle diff -- web/components/style_config.py web/components/output_preview.py api/schemas/video.py api/schemas/content.py api/routers/video.py api/routers/content.py pixelle_video/prompts/image_generation.py pixelle_video/utils/content_generators.py pixelle_video/services/image_prompt_composer.py pixelle_video/pipelines/standard.py pixelle_video/prompts/storyboard_generation.py pixelle_video/services/storyboard_generation.py pixelle_video/prompts/storyboard_planning.py pixelle_video/services/storyboard_planner.py pixelle_video/models/storyboard.py pixelle_video/services/persistence.py web/pages/2_📚_History.py tests/test_style_config_storyboard_planning_ui.py tests/test_output_preview.py tests/test_video_api.py tests/test_content_image_prompt_api.py tests/test_content_generators_structured_output.py tests/test_styled_image_prompt_batch.py tests/test_storyboard_generation_service.py tests/test_storyboard_planner.py tests/test_storyboard_preview_ui.py`

Expected: only the storyboard prompt language feature changes appear.
