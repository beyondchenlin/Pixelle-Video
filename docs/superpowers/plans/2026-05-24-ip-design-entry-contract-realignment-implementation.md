# Final Visual Prompt Source-Root Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Realign the generation chain so every upstream input, including IP, world, scene, style, text policy, and workflow constraints, produces one complete final visual prompt that is handed unchanged to the media model.

**Architecture:** Work backward from the final prompt. Introduce a shared request contract so web UI and request builders cannot drift, keep `IPProfile` as durable fact source, keep `generation_world_hint` request-scoped, load every LLM prompt body from Markdown templates, feed structured context to the LLM, semantically fuse style/storyboard/IP/world into final prompt text, trace every LLM request/response, and verify the same prompt reaches `StoryboardFrame.image_prompt`, `PromptPlan.final_prompt`, and the media service `prompt` parameter.

**Tech Stack:** Python 3.11, Streamlit, Pydantic v2, pytest, Markdown prompt templates, Pixelle `IPProfile`, `ContentWorldProfile`, `IPUsagePlanner`, `IPFrameAppearancePlanner`, `PromptContextEnvelope`, `LLMTraceContext`, `LLMInteractionRecorder`.

---

## File Structure

- Create: `pixelle_video/contracts/__init__.py`
  - Exports shared generation-request contract helpers.
- Create: `pixelle_video/contracts/ip_generation_request.py`
  - Owns formal content IP/world request fields, helper-only fields, removed legacy fields, and formal payload building.
- Create: `tests/test_ip_generation_request_contract.py`
  - Locks the shared request contract.
- Create: `pixelle_video/prompts/template_loader.py`
  - Loads, validates, and renders Markdown prompt templates.
- Create: `pixelle_video/prompts/templates/__init__.py`
  - Marks the Markdown template directory as a packaged prompt source.
- Create: `pixelle_video/prompts/templates/image_generation.md`
  - Owns the image-prompt generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/video_generation.md`
  - Owns the video-prompt generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/ip_role_selection.md`
  - Owns the IP role/presence selection LLM prompt body.
- Create: `pixelle_video/prompts/templates/topic_narration.md`
  - Owns the topic-to-narration LLM prompt body.
- Create: `pixelle_video/prompts/templates/content_narration.md`
  - Owns the content-to-narration LLM prompt body.
- Create: `pixelle_video/prompts/templates/title_generation.md`
  - Owns the title-generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/style_conversion.md`
  - Owns the style-conversion LLM prompt body.
- Create: `pixelle_video/prompts/templates/style_resolution.md`
  - Owns the style-resolution LLM prompt body.
- Create: `pixelle_video/prompts/templates/content_world.md`
  - Owns the content-world planning LLM prompt body.
- Create: `pixelle_video/prompts/templates/storyboard_planning.md`
  - Owns the storyboard planning LLM prompt body.
- Create: `pixelle_video/prompts/templates/storyboard_generation.md`
  - Owns the smart storyboard generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/prompt_prefix_generation.md`
  - Owns the prompt-prefix generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/script_generation.md`
  - Owns the complete script-generation LLM prompt body.
- Create: `pixelle_video/prompts/templates/asset_script_generation.md`
  - Owns the asset script-generation LLM prompt body.
- Create: `tests/test_prompt_template_registry.py`
  - Proves Markdown prompt templates have valid metadata and render without unresolved variables.
- Create: `tests/test_prompt_template_no_inline_bodies.py`
  - Fails when prompt bodies are reintroduced as Python triple-quoted constants.
- Modify: `pixelle_video/prompts/*.py`
  - Converts prompt modules into Markdown-template adapters instead of prompt-body owners.
- Modify: `web/components/content_ip_world_controls.py`
  - Renders left-side IP/world controls and returns only the formal payload.
- Modify: `web/i18n/locales/zh_CN.json`
  - Removes old legacy field labels and adds request world-hint labels.
- Modify: `web/i18n/locales/en_US.json`
  - Removes old legacy field labels and adds request world-hint labels.
- Modify: `tests/test_content_ip_world_controls.py`
  - Locks payload, helper-state, action-button, and fake UI behavior.
- Create: `tests/test_content_ip_world_static_contract.py`
  - Fails when removed legacy fields reappear in the left-entry UI or i18n files.
- Modify: `tests/test_output_preview.py`
  - Proves helper-only and removed fields are not forwarded to final generation requests.
- Create: `pixelle_video/services/ip_color_palette.py`
  - Builds planner-readable color palette prompt entries and separates hex values from prompt text.
- Modify: `pixelle_video/services/ip_profile_readiness.py`
  - Makes `ip_generation_identity_terms()` work for both `IPProfile` objects and mapping payloads.
- Modify: `web/components/ip_design_workbench.py`
  - Uses shared readiness and shared color-palette builder.
- Modify: `tests/test_ip_design_workbench_ui.py`
  - Locks anchor-only readiness and saved color-palette shape.
- Modify: `tests/test_ip_usage_planner.py`
  - Locks color consumption, full planner input, SceneCast policy, and invalid SceneCast fallback.
- Modify: `pixelle_video/services/ip_usage_planner.py`
  - Passes full actorization and generation world context into LLM role selection.
- Modify: `pixelle_video/prompts/ip_role_selection.py`
  - Separates stable identity, adaptable actor choices, and per-frame presence rules in the LLM prompt.
- Modify: `pixelle_video/utils/content_generators.py`
  - Carries structured `ip_adaptation` into prompt contexts and continues sanitizing final prompt text near result assembly.
- Modify: `pixelle_video/utils/prompt_helper.py`
  - Locks semantic final prompt assembly and extends final prompt sanitization to cover the expanded IP/world internal key set.
- Create: `tests/test_visual_prompt_final_product_contract.py`
  - Proves the final prompt is a fused visual instruction, not a raw block list.
- Modify: `tests/test_frame_processor_negative_prompt.py`
  - Proves the final frame prompt is handed unchanged to the media model.
- Modify: `tests/test_ip_prompt_integration.py`
  - Proves prompt contexts receive structured `ip_adaptation`.
- Modify: `tests/test_styled_image_prompt_batch.py`
  - Proves the main styled-image path strips stale IP context when disabled and validates prompt leakage when enabled.
- Modify: `pixelle_video/models/llm_interaction_trace.py`
  - Adds template provenance, chain id, and attempt metadata to LLM traces.
- Modify: `pixelle_video/services/llm_service.py`
  - Rejects untraced production LLM calls and persists exact request/response payloads.
- Modify: `pixelle_video/services/llm_interaction_recorder.py`
  - Stores raw rendered prompts and raw response payloads for every interaction.
- Create: `pixelle_video/services/prompt_trace_artifacts.py`
  - Persists per-generation prompt-chain and final-prompt artifacts.
- Create: `tests/test_generation_llm_trace_contract.py`
  - Proves every generation LLM call records prompt, response, stage, attempt, and template provenance.
- Create: `tests/test_prompt_trace_artifacts.py`
  - Proves per-frame final prompt artifacts link prompt planning to media generation.

---

## Product Contract

The final artifact of this plan is not an IP payload and not a group of prompt fragments. The final artifact is one complete visual prompt per generated frame.

The invariant is:

```python
media_params["prompt"] == storyboard_frame.image_prompt == prompt_plan.final_prompt
```

The prompt must be suitable for the target image/video model:

- one coherent visual instruction.
- style expressed as visual language.
- IP integrated into the scene role, not appended as an extra object.
- world and storyboard constraints expressed as image semantics.
- no raw JSON keys, field labels, enum names, hex codes, or section headers.
- no unresolved block-list order such as `style, shot_type, world_elements, base_prompt`.

All tasks below serve this contract.

---

## Prompt Provenance And Trace Contract

Every prompt used with a large model is source-controlled as Markdown. Code renders templates; code does not own the prompt prose.

The runtime trace must answer these questions for every generation:

- Which Markdown template produced the prompt?
- What exact rendered text did the LLM receive?
- What exact response did the LLM return?
- How many LLM interactions happened, in what order, and at which generation stage?
- Which final prompt was handed to ComfyUI or the media model?

Required invariants:

```python
trace.request_payload["messages"][0]["content"] == rendered_prompt.text
trace.context.metadata["prompt_template"]["prompt_id"] == rendered_prompt.prompt_id
media_params["prompt"] in final_prompt_artifact_path.read_text(encoding="utf-8")
```

No task may add a new LLM prompt as a Python triple-quoted prompt body. New prompt work starts by adding or updating a Markdown template.

---

## Task 0: Markdown Prompt Templates And Mandatory Trace Foundation

**Files:**
- Create: `pixelle_video/prompts/template_loader.py`
- Create: `pixelle_video/prompts/templates/__init__.py`
- Create: `pixelle_video/prompts/templates/image_generation.md`
- Create: `pixelle_video/prompts/templates/video_generation.md`
- Create: `pixelle_video/prompts/templates/ip_role_selection.md`
- Create: `pixelle_video/prompts/templates/topic_narration.md`
- Create: `pixelle_video/prompts/templates/content_narration.md`
- Create: `pixelle_video/prompts/templates/title_generation.md`
- Create: `pixelle_video/prompts/templates/style_conversion.md`
- Create: `pixelle_video/prompts/templates/style_resolution.md`
- Create: `pixelle_video/prompts/templates/content_world.md`
- Create: `pixelle_video/prompts/templates/storyboard_planning.md`
- Create: `pixelle_video/prompts/templates/storyboard_generation.md`
- Create: `pixelle_video/prompts/templates/prompt_prefix_generation.md`
- Create: `pixelle_video/prompts/templates/asset_script_generation.md`
- Create: `pixelle_video/prompts/templates/script_generation.md`
- Create: `tests/test_prompt_template_registry.py`
- Create: `tests/test_prompt_template_no_inline_bodies.py`
- Modify: `pixelle_video/prompts/image_generation.py`
- Modify: `pixelle_video/prompts/video_generation.py`
- Modify: `pixelle_video/prompts/ip_role_selection.py`
- Modify: `pixelle_video/prompts/topic_narration.py`
- Modify: `pixelle_video/prompts/content_narration.py`
- Modify: `pixelle_video/prompts/title_generation.py`
- Modify: `pixelle_video/prompts/style_conversion.py`
- Modify: `pixelle_video/prompts/style_resolution.py`
- Modify: `pixelle_video/prompts/content_world.py`
- Modify: `pixelle_video/prompts/storyboard_planning.py`
- Modify: `pixelle_video/prompts/storyboard_generation.py`
- Modify: `pixelle_video/prompts/prompt_prefix_generation.py`
- Modify: `pixelle_video/prompts/script_generation.py`
- Modify: `pixelle_video/prompts/asset_script_generation.py`

- [ ] **Step 1: Write prompt-template registry tests**

Create `tests/test_prompt_template_registry.py`:

```python
import pytest

from pixelle_video.prompts.template_loader import (
    PROMPT_TEMPLATE_IDS,
    PromptTemplateError,
    load_prompt_template,
    render_prompt_template,
)


REQUIRED_TEMPLATE_IDS = {
    "image_generation",
    "video_generation",
    "ip_role_selection",
    "topic_narration",
    "content_narration",
    "title_generation",
    "style_conversion",
    "style_resolution",
    "content_world",
    "storyboard_planning",
    "storyboard_generation",
    "prompt_prefix_generation",
    "script_generation",
    "asset_script_generation",
}


def test_prompt_registry_contains_every_generation_template():
    assert REQUIRED_TEMPLATE_IDS <= set(PROMPT_TEMPLATE_IDS)


@pytest.mark.parametrize("prompt_id", sorted(REQUIRED_TEMPLATE_IDS))
def test_prompt_template_has_required_frontmatter(prompt_id):
    template = load_prompt_template(prompt_id)

    assert template.prompt_id == prompt_id
    assert template.version
    assert template.stage
    assert template.purpose
    assert template.output_contract
    assert template.path.name == f"{prompt_id}.md"
    assert "# " in template.body


def test_render_prompt_template_returns_text_and_source_metadata():
    rendered = render_prompt_template(
        "image_generation",
        {
            "input_payload": {"frame_source_texts": ["A guide enters the market."]},
            "min_words": 50,
            "max_words": 100,
            "style_profile_json": "null",
            "narrations_json": "{\"frame_source_texts\": [\"A guide enters the market.\"]}",
            "narrations_count": 1,
            "output_language_chinese": False,
            "output_language_english": True,
        },
    )

    assert rendered.prompt_id == "image_generation"
    assert rendered.version
    assert rendered.path.endswith("image_generation.md")
    assert "A guide enters the market." in rendered.text
    assert "{input_payload}" not in rendered.text
    assert "{{input_payload}}" not in rendered.text


def test_render_prompt_template_rejects_unresolved_variables():
    with pytest.raises(PromptTemplateError, match="missing template variables"):
        render_prompt_template("title_generation", {"content": "Only one variable"})
```

- [ ] **Step 2: Write the static no-inline-prompt test**

Create `tests/test_prompt_template_no_inline_bodies.py`:

```python
import re
from pathlib import Path


PROMPT_MODULE_DIR = Path("pixelle_video/prompts")
INLINE_PROMPT_CONSTANT_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*PROMPT[A-Z0-9_]*\s*=\s*(?:f|r|fr|rf)?[\"']{3}",
    re.MULTILINE,
)


def test_prompt_modules_do_not_own_long_form_prompt_bodies():
    offenders = []
    for path in sorted(PROMPT_MODULE_DIR.glob("*.py")):
        if path.name in {"__init__.py", "template_loader.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if INLINE_PROMPT_CONSTANT_RE.search(text):
            offenders.append(str(path))

    assert offenders == []
```

- [ ] **Step 3: Run the new tests and confirm current failures**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_prompt_template_registry.py tests/test_prompt_template_no_inline_bodies.py -q
```

Expected now:

```text
FAILED
```

The failures should mention the missing `pixelle_video.prompts.template_loader` module and existing inline prompt constants in `pixelle_video/prompts/*.py`.

- [ ] **Step 4: Implement the Markdown template loader**

Create `pixelle_video/prompts/template_loader.py`:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any


TEMPLATE_DIR = Path(__file__).with_name("templates")
PROMPT_TEMPLATE_IDS = frozenset(
    path.stem for path in TEMPLATE_DIR.glob("*.md")
    if path.name != "__init__.py"
)
REQUIRED_FRONTMATTER_FIELDS = frozenset(
    {"prompt_id", "version", "stage", "purpose", "output_contract"}
)


class PromptTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    stage: str
    purpose: str
    output_contract: str
    path: Path
    body: str


@dataclass(frozen=True)
class RenderedPrompt:
    prompt_id: str
    version: str
    stage: str
    purpose: str
    output_contract: str
    path: str
    text: str

    def trace_metadata(self) -> dict[str, str]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "stage": self.stage,
            "purpose": self.purpose,
            "output_contract": self.output_contract,
            "path": self.path,
        }


def load_prompt_template(prompt_id: str) -> PromptTemplate:
    safe_id = _validate_prompt_id(prompt_id)
    path = TEMPLATE_DIR / f"{safe_id}.md"
    if not path.exists():
        raise PromptTemplateError(f"unknown prompt template: {prompt_id}")
    frontmatter, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    missing = REQUIRED_FRONTMATTER_FIELDS - set(frontmatter)
    if missing:
        raise PromptTemplateError(f"{safe_id} missing frontmatter fields: {sorted(missing)}")
    if frontmatter["prompt_id"] != safe_id:
        raise PromptTemplateError(f"{safe_id} prompt_id does not match file name")
    return PromptTemplate(
        prompt_id=safe_id,
        version=str(frontmatter["version"]).strip(),
        stage=str(frontmatter["stage"]).strip(),
        purpose=str(frontmatter["purpose"]).strip(),
        output_contract=str(frontmatter["output_contract"]).strip(),
        path=path,
        body=body.strip(),
    )


def render_prompt_template(prompt_id: str, variables: dict[str, Any]) -> RenderedPrompt:
    template = load_prompt_template(prompt_id)
    normalized = {
        key: _stringify_template_value(value)
        for key, value in variables.items()
    }
    required = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template.body)
        if field_name
    }
    missing = required - set(normalized)
    if missing:
        raise PromptTemplateError(f"{prompt_id} missing template variables: {sorted(missing)}")
    text = template.body.format(**normalized)
    unresolved = sorted(set(re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", text)))
    if unresolved:
        raise PromptTemplateError(f"{prompt_id} unresolved template variables: {unresolved}")
    return RenderedPrompt(
        prompt_id=template.prompt_id,
        version=template.version,
        stage=template.stage,
        purpose=template.purpose,
        output_contract=template.output_contract,
        path=str(template.path),
        text=text.strip(),
    )


def _validate_prompt_id(prompt_id: str) -> str:
    value = str(prompt_id or "").strip()
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise PromptTemplateError("prompt_id must contain lowercase letters, numbers, and underscores only")
    return value


def _split_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---\n"):
        raise PromptTemplateError("prompt template must start with frontmatter")
    end = markdown.find("\n---", 4)
    if end < 0:
        raise PromptTemplateError("prompt template frontmatter is not closed")
    frontmatter_text = markdown[4:end].strip()
    body = markdown[end + len("\n---"):].strip()
    frontmatter: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        if ":" not in line:
            raise PromptTemplateError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def _stringify_template_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
```

- [ ] **Step 5: Move prompt bodies into Markdown templates**

Create each Markdown file listed in this task. For `image_generation.md`, use this front matter, then copy the complete current body of `IMAGE_PROMPT_GENERATION_PROMPT` from `pixelle_video/prompts/image_generation.py` directly below it. The copied body starts with `# Role Definition` and keeps the current JSON output rules intact.

```markdown
---
prompt_id: image_generation
version: 2026-05-24-v1
stage: image_prompt_generation
purpose: Generate integrated per-frame visual prompts from structured storyboard context.
output_contract: ImagePromptBatchResponse
---
```

Use these `prompt_id` to `output_contract` mappings:

```python
{
    "image_generation": "ImagePromptBatchResponse",
    "video_generation": "VideoPromptBatchResponse",
    "ip_role_selection": "IPRoleSelectionResponse",
    "topic_narration": "NarrationBatchResponse",
    "content_narration": "NarrationBatchResponse",
    "title_generation": "str",
    "style_conversion": "str",
    "style_resolution": "StyleResolutionResponse",
    "content_world": "ContentWorldProfile",
    "storyboard_planning": "StoryboardPromptPlanResponse",
    "storyboard_generation": "SmartStoryboardResponse",
    "prompt_prefix_generation": "PromptPrefixGenerationResponse",
    "script_generation": "ScriptGenerationResponse",
    "asset_script_generation": "AssetScriptGenerationResponse",
}
```

- [ ] **Step 6: Convert Python prompt modules into adapters**

In each `pixelle_video/prompts/*.py` builder, replace the prompt-body constant with `render_prompt_template(...)`.

For `pixelle_video/prompts/image_generation.py`, keep a text-returning compatibility function and add a metadata-preserving render function:

```python
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template


def render_image_prompt_prompt(
    narrations: list[str],
    min_words: int = 50,
    max_words: int = 100,
    prompt_contexts: Any | None = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
) -> RenderedPrompt:
    resolved_prompt_language = normalize_prompt_language(prompt_language)
    input_payload = (
        {"frame_source_texts": narrations}
        if prompt_contexts is not None
        else {"narrations": narrations}
    )
    if prompt_contexts is not None:
        input_payload["prompt_contexts"] = _serialize_prompt_contexts(prompt_contexts)
    return render_prompt_template(
        "image_generation",
        {
            "input_payload": input_payload,
            "min_words": min_words,
            "max_words": max_words,
            "output_language_chinese": resolved_prompt_language == CHINESE_PROMPT_LANGUAGE,
            "output_language_english": resolved_prompt_language != CHINESE_PROMPT_LANGUAGE,
        },
    )


def build_image_prompt_prompt(*args, **kwargs) -> str:
    return render_image_prompt_prompt(*args, **kwargs).text
```

Use this exact adapter map for the remaining prompt modules:

```python
{
    "video_generation": ("render_video_prompt_prompt", "build_video_prompt_prompt"),
    "ip_role_selection": ("render_ip_role_selection_prompt", "build_ip_role_selection_prompt"),
    "topic_narration": ("render_topic_narration_prompt", "build_topic_narration_prompt"),
    "content_narration": ("render_content_narration_prompt", "build_content_narration_prompt"),
    "title_generation": ("render_title_generation_prompt", "build_title_generation_prompt"),
    "style_conversion": ("render_style_conversion_prompt", "build_style_conversion_prompt"),
    "style_resolution": ("render_style_resolution_prompt", "build_style_resolution_prompt"),
    "content_world": ("render_content_world_prompt", "build_content_world_prompt"),
    "storyboard_planning": ("render_storyboard_planning_prompt", "build_storyboard_planning_prompt"),
    "storyboard_generation": ("render_smart_storyboard_prompt", "build_smart_storyboard_prompt"),
    "prompt_prefix_generation": ("render_prompt_prefix_generation_prompt", "build_prompt_prefix_generation_prompt"),
    "script_generation": ("render_script_generation_prompt", "build_script_generation_prompt"),
    "asset_script_generation": ("render_asset_script_generation_prompt", "build_asset_script_generation_prompt"),
}
```

Each `render_*` function returns `RenderedPrompt`. Each `build_*` function returns `render_*(...).text` for compatibility with existing callers. Production LLM call sites use the `render_*` function so trace metadata can include the template id, version, stage, output contract, and path.

- [ ] **Step 7: Run template tests and static gate**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_prompt_template_registry.py tests/test_prompt_template_no_inline_bodies.py -q
```

Expected:

```text
passed
```

Run:

```powershell
rg -n "PROMPT\\s*=\\s*\"\"\"|_PROMPT\\s*=\\s*\"\"\"" pixelle_video/prompts
```

Expected:

```text
```

- [ ] **Step 8: Commit**

```powershell
git add pixelle_video/prompts tests/test_prompt_template_registry.py tests/test_prompt_template_no_inline_bodies.py
git commit -m "refactor: move LLM prompt templates to markdown"
```

---

## Task 1: Baseline And Shared Request Contract

**Files:**
- Create: `pixelle_video/contracts/__init__.py`
- Create: `pixelle_video/contracts/ip_generation_request.py`
- Create: `tests/test_ip_generation_request_contract.py`

- [ ] **Step 1: Run the current failing and passing baseline**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint -q
```

Expected now:

```text
11 failed, 4 passed
```

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Expected now:

```text
4 passed
```

- [ ] **Step 2: Write the failing shared contract tests**

Create `tests/test_ip_generation_request_contract.py`:

```python
from pixelle_video.contracts.ip_generation_request import (
    FORMAL_CONTENT_IP_WORLD_FIELDS,
    HELPER_ONLY_CONTENT_IP_WORLD_FIELDS,
    REMOVED_CONTENT_IP_WORLD_FIELDS,
    build_formal_content_ip_world_payload,
    dropped_content_ip_world_fields,
)


def test_formal_field_set_is_narrow():
    assert FORMAL_CONTENT_IP_WORLD_FIELDS == {
        "ip_enabled",
        "ip_asset_bible_id",
        "ip_profile_id",
        "generation_world_hint",
    }


def test_removed_and_helper_field_sets_are_not_formal():
    forbidden = HELPER_ONLY_CONTENT_IP_WORLD_FIELDS | REMOVED_CONTENT_IP_WORLD_FIELDS
    assert FORMAL_CONTENT_IP_WORLD_FIELDS.isdisjoint(forbidden)
    assert REMOVED_CONTENT_IP_WORLD_FIELDS == {
        "generation_notes",
        "slot_preference_override",
        "presence_strength",
    }


def test_build_formal_payload_drops_helper_and_removed_fields():
    payload = build_formal_content_ip_world_payload(
        {
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "script world",
            "ip_profile_world_hint": "asset helper",
            "generation_world_hint_source": "ip_default",
            "generation_notes": "old notes",
            "slot_preference_override": "prefer_main",
            "presence_strength": "strong",
        }
    )

    assert payload == {
        "ip_enabled": True,
        "ip_asset_bible_id": "bible_demo",
        "ip_profile_id": "ip_main",
        "generation_world_hint": "script world",
    }


def test_disabled_ip_still_carries_request_world_hint():
    assert build_formal_content_ip_world_payload(
        {
            "ip_enabled": False,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "world without selected IP",
        }
    ) == {
        "ip_enabled": False,
        "generation_world_hint": "world without selected IP",
    }


def test_dropped_content_ip_world_fields_reports_only_known_non_formal_fields():
    assert dropped_content_ip_world_fields(
        {
            "ip_profile_world_hint": "asset helper",
            "generation_notes": "old notes",
            "unknown": "ignored",
        }
    ) == {"ip_profile_world_hint", "generation_notes"}
```

- [ ] **Step 3: Run the new tests and confirm import failure**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_generation_request_contract.py -q
```

Expected now:

```text
ERROR
```

The error should mention `pixelle_video.contracts`.

- [ ] **Step 4: Implement the shared contract module**

Create `pixelle_video/contracts/__init__.py`:

```python
from pixelle_video.contracts.ip_generation_request import (
    FORMAL_CONTENT_IP_WORLD_FIELDS,
    HELPER_ONLY_CONTENT_IP_WORLD_FIELDS,
    REMOVED_CONTENT_IP_WORLD_FIELDS,
    build_formal_content_ip_world_payload,
    dropped_content_ip_world_fields,
)

__all__ = [
    "FORMAL_CONTENT_IP_WORLD_FIELDS",
    "HELPER_ONLY_CONTENT_IP_WORLD_FIELDS",
    "REMOVED_CONTENT_IP_WORLD_FIELDS",
    "build_formal_content_ip_world_payload",
    "dropped_content_ip_world_fields",
]
```

Create `pixelle_video/contracts/ip_generation_request.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


FORMAL_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "ip_enabled",
        "ip_asset_bible_id",
        "ip_profile_id",
        "generation_world_hint",
    }
)
HELPER_ONLY_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "ip_profile_world_hint",
        "generation_world_hint_source",
        "generation_world_hint_last_value",
    }
)
REMOVED_CONTENT_IP_WORLD_FIELDS = frozenset(
    {
        "generation_notes",
        "slot_preference_override",
        "presence_strength",
    }
)


def build_formal_content_ip_world_payload(source: Mapping[str, Any] | None) -> dict[str, Any]:
    values = dict(source or {})
    payload: dict[str, Any] = {"ip_enabled": bool(values.get("ip_enabled"))}
    if payload["ip_enabled"]:
        asset_bible_id = _first_text(values.get("ip_asset_bible_id"))
        profile_id = _first_text(values.get("ip_profile_id"))
        if asset_bible_id:
            payload["ip_asset_bible_id"] = asset_bible_id
        if profile_id:
            payload["ip_profile_id"] = profile_id
    world_hint = _first_text(values.get("generation_world_hint"))
    if world_hint:
        payload["generation_world_hint"] = world_hint
    return payload


def dropped_content_ip_world_fields(source: Mapping[str, Any] | None) -> set[str]:
    keys = set(dict(source or {}))
    return keys & (HELPER_ONLY_CONTENT_IP_WORLD_FIELDS | REMOVED_CONTENT_IP_WORLD_FIELDS)


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text
```

- [ ] **Step 5: Run the shared contract tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_generation_request_contract.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/contracts tests/test_ip_generation_request_contract.py
git commit -m "feat: add shared IP generation request contract"
```

---

## Task 2: Rebuild The Left IP/World Entry At The Source

**Files:**
- Modify: `web/components/content_ip_world_controls.py`
- Modify: `tests/test_content_ip_world_controls.py`

- [ ] **Step 1: Lock the formal payload behavior in the existing tests**

Keep or add these assertions in `tests/test_content_ip_world_controls.py`:

```python
assert payload == {
    "ip_enabled": True,
    "ip_asset_bible_id": "bible_demo",
    "ip_profile_id": "ip_main",
    "generation_world_hint": "Manual request world.",
}
assert fake_ui.session_state["content_ip_profile_world_hint"] == "Friendly guide world."
assert "ip_profile_world_hint" not in payload
assert "generation_notes" not in payload
assert "slot_preference_override" not in payload
assert "presence_strength" not in payload
```

For disabled IP:

```python
assert payload == {
    "ip_enabled": False,
    "generation_world_hint": "Manual request world.",
}
```

Add `container()` to `_FakeContentIPWorldUI`:

```python
def container(self, **kwargs):
    return _FakeContext()
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 3: Replace local payload construction with the shared contract**

In `web/components/content_ip_world_controls.py`, import:

```python
from pixelle_video.contracts.ip_generation_request import build_formal_content_ip_world_payload
from web.utils.content_api import generate_world_hint_draft
from web.utils.streamlit_helpers import safe_rerun
```

Use these state keys:

```python
CONTENT_GENERATION_WORLD_HINT_KEY = "content_generation_world_hint"
CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY = "content_generation_world_hint_source"
CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY = "content_generation_world_hint_last_value"
CONTENT_IP_PROFILE_WORLD_HINT_KEY = "content_ip_profile_world_hint"
```

Delete the old state keys:

```python
CONTENT_GENERATION_NOTES_KEY
CONTENT_SLOT_PREFERENCE_KEY
CONTENT_PRESENCE_STRENGTH_KEY
```

Replace the old local `build_content_ip_world_payload()` body with:

```python
def build_content_ip_world_payload(
    *,
    ip_payload: Mapping[str, Any] | None = None,
    generation_world_hint: str | None = None,
) -> dict[str, Any]:
    source = dict(ip_payload or {})
    source["generation_world_hint"] = generation_world_hint
    return build_formal_content_ip_world_payload(source)
```

- [ ] **Step 4: Restore helper state and request world-hint actions**

Add:

```python
def _sync_ip_profile_world_hint(session_state, ip_profile_world_hint: str) -> None:
    hint = _first_text(ip_profile_world_hint)
    if hint:
        session_state[CONTENT_IP_PROFILE_WORLD_HINT_KEY] = hint
        return
    session_state.pop(CONTENT_IP_PROFILE_WORLD_HINT_KEY, None)
```

Add:

```python
def _mark_world_hint_manual_if_user_edited(session_state, current_hint: str) -> None:
    current = _first_text(current_hint)
    source = _first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY))
    last = _first_text(session_state.get(CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY))
    if source in {"generated_from_script", "ip_default"} and current != last:
        session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "manual"
    if current:
        session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = current
```

Add the "use IP default" handler:

```python
def _handle_use_ip_default_world_hint(
    *,
    session_state,
    ui,
    translate: Translate,
    ip_default_world_hint: str,
) -> None:
    hint = _first_text(ip_default_world_hint)
    if not hint:
        ui.warning(translate("content.ip_world.missing_ip_default"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "ip_default"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()
```

Add the "generate from script" handler:

```python
def _handle_generate_world_hint_from_content(
    *,
    session_state,
    ui,
    translate: Translate,
    content_context: Mapping[str, Any] | None,
    storyboard_prompt_language: str,
    world_preset_id: str | None,
    ip_default_world_hint: str,
    world_hint_draft_generator: Callable,
) -> None:
    context = dict(content_context or {})
    source_text = _first_text(context.get("text"))
    if not source_text:
        ui.warning(translate("content.ip_world.missing_content"))
        return
    try:
        response = world_hint_draft_generator(
            source_text=source_text,
            title=_first_text(context.get("title")) or None,
            world_preset_id=world_preset_id,
            storyboard_prompt_language=storyboard_prompt_language,
            ip_default_world_hint=_first_text(ip_default_world_hint) or None,
        )
    except Exception:
        logger.exception("failed to generate content world hint draft")
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    hint = _first_text(response.get("world_hint_draft")) if isinstance(response, Mapping) else ""
    if not hint:
        ui.warning(translate("content.ip_world.generate_failed"))
        return
    session_state[CONTENT_GENERATION_WORLD_HINT_KEY] = hint
    session_state[CONTENT_GENERATION_WORLD_HINT_SOURCE_KEY] = "generated_from_script"
    session_state[CONTENT_GENERATION_WORLD_HINT_LAST_VALUE_KEY] = hint
    safe_rerun()
```

- [ ] **Step 5: Render only the request world hint controls**

In the expander, after the existing `render_ip_prompt_chain_controls()` call, render:

```python
ip_default_world_hint = (
    _first_text(ip_payload.get("ip_profile_world_hint"))
    if ip_payload.get("ip_enabled")
    else ""
)
_sync_ip_profile_world_hint(session_state, ip_default_world_hint)

generation_world_hint = ui.text_area(
    translate("content.ip_world.generation_world_hint"),
    key=CONTENT_GENERATION_WORLD_HINT_KEY,
    value=session_state.get(CONTENT_GENERATION_WORLD_HINT_KEY, ""),
    height=92,
    help=translate("content.ip_world.generation_world_hint_help"),
)
_mark_world_hint_manual_if_user_edited(session_state, generation_world_hint)

action_col, default_col = ui.columns((1, 1))
with action_col:
    if ui.button(
        translate("content.ip_world.generate_from_content"),
        key="content_world_hint_generate_from_content",
    ):
        _handle_generate_world_hint_from_content(
            session_state=session_state,
            ui=ui,
            translate=translate,
            content_context=content_context,
            storyboard_prompt_language=storyboard_prompt_language,
            world_preset_id=world_preset_id,
            ip_default_world_hint=ip_default_world_hint,
            world_hint_draft_generator=world_hint_draft_generator or generate_world_hint_draft,
        )
with default_col:
    if ui.button(
        translate("content.ip_world.use_ip_default"),
        key="content_world_hint_use_ip_default",
    ):
        _handle_use_ip_default_world_hint(
            session_state=session_state,
            ui=ui,
            translate=translate,
            ip_default_world_hint=ip_default_world_hint,
        )
```

Return:

```python
return build_content_ip_world_payload(
    ip_payload=ip_payload,
    generation_world_hint=session_state.get(
        CONTENT_GENERATION_WORLD_HINT_KEY,
        generation_world_hint,
    ),
)
```

- [ ] **Step 6: Run the left-entry tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_controls.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 7: Commit**

```powershell
git add web/components/content_ip_world_controls.py tests/test_content_ip_world_controls.py
git commit -m "fix: restore content IP world request entry"
```

---

## Task 3: Delete Removed UI Fields And Add Static Gates

**Files:**
- Modify: `web/i18n/locales/zh_CN.json`
- Modify: `web/i18n/locales/en_US.json`
- Create: `tests/test_content_ip_world_static_contract.py`
- Modify: `tests/test_output_preview.py`

- [ ] **Step 1: Replace i18n keys**

Remove these key names from both locale files:

```json
[
  "content.ip_world.generation_notes",
  "content.ip_world.generation_notes_help",
  "content.ip_world.slot_preference_override",
  "content.ip_world.presence_strength"
]
```

Add these English keys to `web/i18n/locales/en_US.json`:

```json
"content.ip_world.generation_world_hint": "World Hint",
"content.ip_world.generation_world_hint_help": "Describe the current script world, narrative boundaries, and how the IP should naturally fit this generation. This does not overwrite the IP design world hint.",
"content.ip_world.generate_from_content": "Generate from Script",
"content.ip_world.use_ip_default": "Use IP Default",
"content.ip_world.missing_content": "Fill in the script before generating a world hint draft.",
"content.ip_world.missing_ip_default": "The selected IP has no default world hint.",
"content.ip_world.generate_failed": "World hint draft generation failed. Please try again."
```

Add these Chinese keys to `web/i18n/locales/zh_CN.json`:

```json
"content.ip_world.generation_world_hint": "世界观提示",
"content.ip_world.generation_world_hint_help": "描述本次文案发生的世界、叙事边界，以及 IP 在本次内容里如何自然融入；不会覆盖 IP 设计页的长期世界观。",
"content.ip_world.generate_from_content": "根据文案生成",
"content.ip_world.use_ip_default": "使用 IP 默认",
"content.ip_world.missing_content": "请先填写文案，再生成世界观提示草稿。",
"content.ip_world.missing_ip_default": "当前 IP 没有可用的默认世界观提示。",
"content.ip_world.generate_failed": "世界观提示草稿生成失败，请稍后重试。"
```

- [ ] **Step 2: Add static field gate tests**

Create `tests/test_content_ip_world_static_contract.py`:

```python
from pathlib import Path


FORBIDDEN_FIELDS = (
    "generation_notes",
    "slot_preference_override",
    "presence_strength",
)

CHECKED_FILES = (
    Path("web/components/content_ip_world_controls.py"),
    Path("web/i18n/locales/en_US.json"),
    Path("web/i18n/locales/zh_CN.json"),
)


def test_removed_content_ip_world_fields_do_not_reappear_in_entry_or_i18n():
    for path in CHECKED_FILES:
        text = path.read_text(encoding="utf-8")
        for field in FORBIDDEN_FIELDS:
            assert field not in text, f"{field} reappeared in {path}"
```

- [ ] **Step 3: Add final request forwarding regression**

In `tests/test_output_preview.py`, add:

```python
def test_build_single_generation_request_drops_content_ip_non_formal_fields():
    request = output_preview.build_single_generation_request(
        {
            "mode": "generate",
            "text": "demo",
            "ip_enabled": True,
            "ip_asset_bible_id": "bible_demo",
            "ip_profile_id": "ip_main",
            "generation_world_hint": "market morning, IP blends in as a guide",
            "generation_notes": "old UI field",
            "slot_preference_override": "prefer_main",
            "presence_strength": "strong",
            "ip_profile_world_hint": "helper only",
            "generation_world_hint_source": "ip_default",
        },
        progress_callback=lambda _event: None,
        session_state={},
    )

    assert request["generation_world_hint"] == "market morning, IP blends in as a guide"
    assert "generation_notes" not in request
    assert "slot_preference_override" not in request
    assert "presence_strength" not in request
    assert "ip_profile_world_hint" not in request
    assert "generation_world_hint_source" not in request
```

- [ ] **Step 4: Run tests and grep gate**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_content_ip_world_static_contract.py tests/test_output_preview.py -k "content_ip_non_formal_fields or removed_content_ip_world_fields" -q
```

Expected:

```text
passed
```

Run:

```powershell
rg -n "generation_notes|slot_preference_override|presence_strength" web/components/content_ip_world_controls.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json
```

Expected:

```text
```

- [ ] **Step 5: Commit**

```powershell
git add web/i18n/locales/zh_CN.json web/i18n/locales/en_US.json tests/test_content_ip_world_static_contract.py tests/test_output_preview.py
git commit -m "test: prevent removed IP world fields from returning"
```

---

## Task 4: Align Workbench Fact Sources

**Files:**
- Create: `pixelle_video/services/ip_color_palette.py`
- Modify: `pixelle_video/services/ip_profile_readiness.py`
- Modify: `web/components/ip_design_workbench.py`
- Modify: `tests/test_ip_design_workbench_ui.py`
- Modify: `tests/test_ip_usage_planner.py`

- [ ] **Step 1: Add readiness and color tests**

In `tests/test_ip_design_workbench_ui.py`, add:

```python
def test_ip_profile_ready_for_generation_accepts_identity_anchors():
    from web.components.ip_design_workbench import _ip_profile_ready_for_generation

    assert _ip_profile_ready_for_generation(
        {"identity_lock": [], "identity_anchors": ["blue tie"]}
    )
```

In the workbench save test, set:

```python
fake_ui.session_state["ip_design_color_rules"] = "#FFFFFF white body, bright blue tie"
```

Assert:

```python
assert profile["color_palette"] == {
    "rule_1": {"hex": "#FFFFFF", "prompt": "white body"},
    "rule_2": {"prompt": "bright blue tie"},
}
```

In `tests/test_ip_usage_planner.py`, add:

```python
def test_identity_color_terms_reads_workbench_palette_entries():
    from pixelle_video.models.asset_bible import IPProfile
    from pixelle_video.services.ip_usage_planner import _identity_color_terms

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Guide",
        identity_lock=("white rabbit",),
        color_palette={
            "rule_1": {"hex": "#FFFFFF", "prompt": "white body"},
            "rule_2": {"prompt": "bright blue tie"},
        },
    )

    assert _identity_color_terms(profile) == ("white body", "bright blue tie")
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py::test_ip_profile_ready_for_generation_accepts_identity_anchors tests/test_ip_usage_planner.py::test_identity_color_terms_reads_workbench_palette_entries -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 3: Implement shared color builder**

Create `pixelle_video/services/ip_color_palette.py`:

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


HEX_COLOR_RE = re.compile(
    r"(?<![0-9a-fA-F])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])"
)


def build_color_palette_prompt_entries(
    existing_palette: Mapping[str, Any] | None,
    color_rules: str,
) -> dict[str, Any]:
    palette = {
        str(key): dict(value)
        for key, value in dict(existing_palette or {}).items()
        if isinstance(value, Mapping) and not str(key).startswith("rule_")
    }
    for index, raw_rule in enumerate(_split_color_rules(color_rules), start=1):
        entry = _color_rule_entry(raw_rule)
        if entry:
            palette[f"rule_{index}"] = entry
    return palette


def _split_color_rules(value: str) -> list[str]:
    normalized = str(value or "").replace("，", ",")
    return [item.strip() for item in re.split(r"[\n,]+", normalized) if item.strip()]


def _color_rule_entry(raw_rule: str) -> dict[str, str]:
    text = raw_rule.strip()
    match = HEX_COLOR_RE.search(text)
    hex_value = match.group(0).upper() if match else ""
    prompt = HEX_COLOR_RE.sub("", text).strip(" -:;，,")
    if not prompt:
        return {}
    entry = {"prompt": prompt}
    if hex_value:
        entry["hex"] = hex_value
    return entry
```

- [ ] **Step 4: Make readiness shared**

In `pixelle_video/services/ip_profile_readiness.py`, import `Mapping` and change field reading:

```python
from collections.abc import Iterable, Mapping
```

Add:

```python
def _read_field(source: Any, field_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name, ())
    return getattr(source, field_name, ())
```

Change `ip_generation_identity_terms()`:

```python
def ip_generation_identity_terms(ip_profile: Any) -> tuple[str, ...]:
    return _unique_text(
        [
            *_read_text_sequence(_read_field(ip_profile, "identity_lock")),
            *_read_text_sequence(_read_field(ip_profile, "identity_anchors")),
        ]
    )
```

In `web/components/ip_design_workbench.py`, import:

```python
from pixelle_video.services.ip_color_palette import build_color_palette_prompt_entries
from pixelle_video.services.ip_profile_readiness import ip_generation_identity_terms
```

Change readiness:

```python
def _ip_profile_ready_for_generation(ip_profile: Mapping[str, Any]) -> bool:
    return bool(ip_generation_identity_terms(ip_profile))
```

Change the saved `color_palette` field:

```python
"color_palette": build_color_palette_prompt_entries(
    ip_profile.get("color_palette", {}),
    color_rules,
),
```

Update `_read_color_palette_prompt()` so existing mapping entries render back into the textarea:

```python
def _read_color_palette_prompt(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    prompts = []
    for item in value.values():
        if isinstance(item, Mapping):
            prompt = _first_text(item.get("prompt"))
            if prompt:
                prompts.append(prompt)
    return ", ".join(prompts)
```

- [ ] **Step 5: Run workbench and planner fact tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py tests/test_ip_usage_planner.py::test_identity_color_terms_reads_workbench_palette_entries -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/services/ip_color_palette.py pixelle_video/services/ip_profile_readiness.py web/components/ip_design_workbench.py tests/test_ip_design_workbench_ui.py tests/test_ip_usage_planner.py
git commit -m "fix: align IP workbench fact sources"
```

---

## Task 5: Feed The Planner Full Actorization Context

**Files:**
- Modify: `pixelle_video/services/ip_usage_planner.py`
- Modify: `pixelle_video/prompts/ip_role_selection.py`
- Modify: `tests/test_ip_usage_planner.py`

- [ ] **Step 1: Add an LLM input regression test**

In `tests/test_ip_usage_planner.py`, add:

```python
import json


async def test_appearance_planner_llm_receives_full_actorization_context():
    from pixelle_video.models.content_world import ContentWorldProfile
    from pixelle_video.services.ip_usage_planner import IPFrameAppearancePlanner

    captured = {}

    async def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            [
                {
                    "frame_index": 0,
                    "role_slot": "supporting",
                    "role_label": "scene guide",
                    "presence_level": "half body",
                    "appearance_description": "white rabbit guide blends into the market light",
                    "reason": "supports the travel scene",
                }
            ]
        )

    profile = _universal_ip_profile()
    world = ContentWorldProfile(
        summary="morning travel market",
        story_constraints="do not replace the street vendor",
        ip_integration_guidance="the IP should guide quietly from the side",
    )

    await IPFrameAppearancePlanner(llm_client=fake_llm).plan_batch(
        storyboard_plan=_plan(
            StoryboardPlanFrame(
                index=1,
                source_text="A market route opens.",
                visual_goal="show the travel path",
                primary_subject="street vendor",
            )
        ),
        ip_profile=profile,
        generation_world_profile=world,
        scene_casts_by_frame={"frame_1": {"metadata": {"ip_presence_type": "scene_integrated"}}},
    )

    prompt = captured["prompt"]
    for token in (
        "minimal_traits",
        "semantic_boundary",
        "negative_constraints",
        "presence_spectrum",
        "adaptable_slots",
        "default_slot_preference",
        "generation_world_profile",
        "story_constraints",
        "ip_integration_guidance",
        "scene_cast_presence",
    ):
        assert token in prompt
```

- [ ] **Step 2: Run the test and confirm failure**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_usage_planner.py::test_appearance_planner_llm_receives_full_actorization_context -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 3: Pass world and SceneCast data into LLM role selection**

In `IPFrameAppearancePlanner.plan_batch()`, change the call:

```python
llm_roles = await self._llm_role_selection(
    storyboard_plan=storyboard_plan,
    ip_profile=ip_profile,
    base_packages=base_packages,
    generation_world_profile=generation_world_profile,
    scene_casts_by_frame=scene_casts,
)
```

Change `_llm_role_selection()` signature:

```python
async def _llm_role_selection(
    self,
    *,
    storyboard_plan: StoryboardPlan,
    ip_profile: IPProfile,
    base_packages: list[IPFrameAdaptationPackage],
    generation_world_profile: ContentWorldInput = None,
    scene_casts_by_frame: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
```

Build `ip_profile_json` with:

```python
world_profile = _normalize_generation_world_profile(generation_world_profile)
ip_profile_json = json.dumps(
    {
        "name": ip_profile.name,
        "identity_lock": list(ip_profile.identity_lock),
        "identity_anchors": list(ip_profile.identity_anchors),
        "visual_summary": ip_profile.visual_summary,
        "minimal_traits": list(ip_profile.minimal_traits),
        "semantic_boundary": list(ip_profile.semantic_boundary),
        "negative_constraints": list(ip_profile.negative_constraints),
        "role_presets": list(ip_profile.role_presets),
        "presence_spectrum": list(ip_profile.presence_spectrum),
        "adaptable_slots": list(ip_profile.adaptable_slots),
        "default_slot_preference": ip_profile.default_slot_preference,
        "style_hint": ip_profile.style_hint,
        "world_hint": ip_profile.world_hint,
        "generation_world_profile": world_profile.to_dict() if world_profile else {},
    },
    ensure_ascii=False,
    indent=2,
)
```

Build each frame item with:

```python
scene_cast = _scene_cast_for_frame(scene_casts_by_frame or {}, frame)
{
    "frame_index": i,
    "frame_id": frame.frame_id,
    "source_text": frame.source_text,
    "visual_goal": frame.visual_goal,
    "shot_type": frame.shot_type,
    "primary_subject": frame.primary_subject,
    "presence_type": base.ip_presence_type.value,
    "presence_mode": base.presence_mode.value,
    "semantic_reason": base.semantic_reason,
    "must_not_replace": list(base.must_not_replace),
    "identity_anchors_visible": list(base.identity_anchors_visible),
    "identity_anchors_suppressed": list(base.identity_anchors_suppressed),
    "scene_cast_presence": _raw_scene_cast_presence(scene_cast),
}
```

Add helper:

```python
def _raw_scene_cast_presence(scene_cast: Any | None) -> str | None:
    if not isinstance(scene_cast, Mapping):
        return None
    value = scene_cast.get("ip_presence_type") or scene_cast.get("presence_type")
    metadata = scene_cast.get("metadata")
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get("ip_presence_type") or metadata.get("presence_type")
    return str(value) if value is not None else None
```

- [ ] **Step 4: Update LLM role-selection prompt wording**

In `pixelle_video/prompts/ip_role_selection.py`, update the instruction section so it says:

```text
Use stable identity fields as hard visual anchors.
Use minimal_traits when the IP is partial, far away, or low intrusion.
Use adaptable_slots for clothing, props, pose, occupation, and scene behavior.
Use semantic_boundary and negative_constraints as hard boundaries.
Use generation_world_profile to decide how the IP should fit this script world.
Use scene_cast_presence as the per-frame presence directive when it is present and valid.
Never force the IP to dominate frames whose source text or world profile protects another subject.
```

- [ ] **Step 5: Run planner tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_usage_planner.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/services/ip_usage_planner.py pixelle_video/prompts/ip_role_selection.py tests/test_ip_usage_planner.py
git commit -m "feat: feed full IP actorization context to planner"
```

---

## Task 6: Lock SceneCast Policy And Prompt Context Auditability

**Files:**
- Modify: `pixelle_video/services/ip_usage_planner.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `tests/test_ip_usage_planner.py`
- Modify: `tests/test_ip_prompt_integration.py`

- [ ] **Step 1: Add invalid SceneCast fallback test**

In `tests/test_ip_usage_planner.py`, add:

```python
def test_usage_planner_ignores_invalid_scene_cast_presence_type():
    frame = StoryboardPlanFrame(
        index=2,
        source_text="A guide explains the route through a lively street.",
        visual_goal="show a balanced narrative travel scene",
        primary_subject="street route",
    )
    plan = _plan(frame)

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={
            plan.frames[0].frame_id: {
                "metadata": {"ip_presence_type": "giant_logo_takeover"}
            }
        },
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE
```

- [ ] **Step 2: Add prompt context audit test**

In `tests/test_ip_prompt_integration.py`, add:

```python
def test_enrich_prompt_contexts_with_ip_adds_structured_ip_adaptation():
    from pixelle_video.models.prompt_context import PromptContextEnvelope
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    frame = StoryboardPlanFrame(
        index=1,
        source_text="A guide enters the market.",
        visual_goal="show integrated IP presence",
        primary_subject="market route",
    )
    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    result = _enrich_prompt_contexts_with_ip(
        PromptContextEnvelope(plan_context={}, frame_contexts=({},)),
        expected_count=1,
        packages=(package,),
        style_context={"style_kind": "visual_only"},
    )

    context = result.frame_contexts[0]
    assert context["ip_scene_description"] == package.appearance_description
    assert context["ip_adaptation"]["frame_id"] == package.frame_id
    assert context["ip_adaptation"]["ip_presence_type"] == package.ip_presence_type.value
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_usage_planner.py::test_usage_planner_ignores_invalid_scene_cast_presence_type tests/test_ip_prompt_integration.py::test_enrich_prompt_contexts_with_ip_adds_structured_ip_adaptation -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 4: Keep invalid SceneCast fallback explicit**

In `pixelle_video/services/ip_usage_planner.py`, keep `_presence_type_from_scene_cast()` returning `None` for invalid enum values:

```python
try:
    return IPPresenceType(value)
except ValueError:
    logger.info("Ignoring invalid SceneCast IP presence type: %s", value)
    return None
```

- [ ] **Step 5: Carry structured adaptation into prompt contexts**

In `_enrich_prompt_contexts_with_ip()`, add:

```python
package_dict = (
    package.to_dict()
    if hasattr(package, "to_dict")
    else dict(package)
    if isinstance(package, Mapping)
    else {}
)
frame_contexts[index]["ip_adaptation"] = package_dict
```

Leave `_strip_ip_prompt_context_fields()` removing `ip_adaptation` when IP prompt chain is disabled.

- [ ] **Step 6: Run integration tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_usage_planner.py tests/test_ip_prompt_integration.py tests/test_styled_image_prompt_batch.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit**

```powershell
git add pixelle_video/services/ip_usage_planner.py pixelle_video/utils/content_generators.py tests/test_ip_usage_planner.py tests/test_ip_prompt_integration.py
git commit -m "feat: lock SceneCast IP policy and prompt context audit"
```

---

## Task 7: Lock Final Visual Prompt Assembly Contract

**Files:**
- Create: `tests/test_visual_prompt_final_product_contract.py`
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `tests/test_frame_processor_negative_prompt.py`

- [ ] **Step 1: Add final prompt assembly contract tests**

Create `tests/test_visual_prompt_final_product_contract.py`:

```python
from types import SimpleNamespace

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle
from pixelle_video.utils.prompt_helper import assemble_image_prompt, assemble_storyboard_prompt


def test_assemble_storyboard_prompt_returns_fused_scene_language_not_block_list():
    frame_plan = SimpleNamespace(
        shot_type="medium_shot",
        shot_purpose="establish_market_space",
        world_elements=("ancient gate", "morning market"),
    )

    prompt = assemble_storyboard_prompt(
        base_prompt=(
            "A white rabbit guide with a blue tie stands beside the tea stall, "
            "naturally pointing visitors toward the old city gate."
        ),
        frame_plan=frame_plan,
        world_preset={
            "display_name": "Neutral Knowledge Storyboard",
            "style_core": "clean educational illustration",
        },
        normalized_style=None,
    )

    assert not prompt.startswith("Neutral Knowledge Storyboard,")
    assert "medium_shot" not in prompt
    assert "establish_market_space" not in prompt
    assert "clean educational illustration" in prompt
    assert "ancient gate" in prompt
    assert "morning market" in prompt
    assert "white rabbit guide with a blue tie" in prompt


def test_assemble_image_prompt_uses_resolved_style_template_without_raw_prefix_append():
    resolved_style = ResolvedStyleSpec(
        style_kind="visual_only",
        source_identity="test",
        raw_content="raw watercolor prefix that should not be appended",
        prompt_template="warm watercolor scene: {prompt}, soft hand-painted texture",
        negative_prompt="",
        style_profile={"style_kind": "visual_only"},
    )

    prompt = assemble_image_prompt(
        "A rabbit guide walks through a quiet morning market.",
        raw_prefix="raw watercolor prefix that should not be appended",
        resolved_style=resolved_style,
    )

    assert prompt == (
        "warm watercolor scene: A rabbit guide walks through a quiet morning market., "
        "soft hand-painted texture"
    )
    assert prompt.count("raw watercolor prefix") == 0


def test_prompt_plan_final_prompt_matches_generated_visual_prompt():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="The guide introduces the old city gate.",
        visual_goal="show a coherent travel illustration",
        prompt_intent="visualize the guide and gate in one image",
        primary_subject="old city gate",
    )
    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="The guide introduces the old city gate.",
        frames=[frame],
        plan_id="plan_1",
    )
    final_prompt = (
        "A white rabbit guide with a blue tie points toward the old city gate "
        "inside a warm educational illustration."
    )

    bundle = build_prompt_plan_bundle(
        storyboard_plan=plan,
        image_prompts=(final_prompt,),
        planning_snapshot={},
    )

    assert bundle.image_prompt_drafts[0].prompt_text == final_prompt
    assert bundle.prompt_plans[0].final_prompt == final_prompt
```

- [ ] **Step 2: Add media handoff test**

In `tests/test_frame_processor_negative_prompt.py`, add:

```python
@pytest.mark.asyncio
async def test_step_generate_media_forwards_final_frame_prompt_to_media_model(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    final_prompt = (
        "A white rabbit guide with a blue tie stands naturally in the morning market, "
        "warm watercolor light, old city gate in the background."
    )
    frame = StoryboardFrame(index=0, narration="scene", image_prompt=final_prompt)
    config = StoryboardConfig(media_width=1024, media_height=1024, task_id="task-1")

    await processor._step_generate_media(frame, config)

    assert captured["prompt"] == final_prompt
```

- [ ] **Step 3: Run tests and confirm current prompt assembly gap**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_visual_prompt_final_product_contract.py tests/test_frame_processor_negative_prompt.py::test_step_generate_media_forwards_final_frame_prompt_to_media_model -q
```

Expected now:

```text
FAILED
```

The failure should come from the storyboard prompt assembly test because the current implementation emits a comma-separated block list with raw values such as `Neutral Knowledge Storyboard` and `medium_shot`.

- [ ] **Step 4: Replace storyboard block assembly with semantic visual assembly**

In `pixelle_video/utils/prompt_helper.py`, add:

```python
def _humanize_prompt_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[_-]+", " ", text).strip()


def _sentence_clause(*values: Any) -> str:
    return ", ".join(_normalize_prompt_list(_humanize_prompt_token(value) for value in values))
```

Replace `assemble_storyboard_prompt()` with:

```python
def assemble_storyboard_prompt(
    *,
    base_prompt: str,
    frame_plan: Any,
    world_preset: Any,
    normalized_style: dict[str, Any] | None = None,
) -> str:
    base = sanitize_visual_prompt_text(base_prompt)
    style_core = _humanize_prompt_token(_read_value(world_preset, "style_core", ""))
    shot_type = _humanize_prompt_token(_read_value(frame_plan, "shot_type", ""))
    shot_purpose = _humanize_prompt_token(_read_value(frame_plan, "shot_purpose", ""))
    world_elements = _sentence_clause(*_normalize_prompt_list(_read_value(frame_plan, "world_elements", ())))

    clauses = [base]
    if style_core:
        clauses.append(f"rendered as {style_core}")
    if shot_type or shot_purpose:
        camera_parts = _sentence_clause(shot_type, shot_purpose)
        if camera_parts:
            clauses.append(f"framed as {camera_parts}")
    if world_elements:
        clauses.append(f"with {world_elements} integrated into the environment")

    prompt = "; ".join(_normalize_prompt_list(clauses))
    if normalized_style is not None:
        prompt = _apply_prompt_template(prompt, normalized_style.get("prompt_template", ""))
        visual_suffix = _humanize_prompt_token(normalized_style.get("visual_suffix", ""))
        if visual_suffix and visual_suffix.lower() not in prompt.lower():
            prompt = "; ".join(_normalize_prompt_list([prompt, visual_suffix]))
    return sanitize_visual_prompt_text(prompt)
```

This keeps style, shot, and world information as meaning around the base visual prompt. It does not emit the preset display name, raw enum spelling, or a plain block list.

- [ ] **Step 5: Run final prompt assembly tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_visual_prompt_final_product_contract.py tests/test_frame_processor_negative_prompt.py::test_step_generate_media_forwards_final_frame_prompt_to_media_model -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/utils/prompt_helper.py tests/test_visual_prompt_final_product_contract.py tests/test_frame_processor_negative_prompt.py
git commit -m "test: lock final visual prompt product contract"
```

---

## Task 8: Extend Final Prompt Sanitization

**Files:**
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `tests/test_styled_image_prompt_batch.py`

- [ ] **Step 1: Add sanitizer coverage for the expanded internal key set**

In `tests/test_styled_image_prompt_batch.py`, add:

```python
def test_sanitize_visual_prompt_text_removes_ip_adaptation_field_labels():
    prompt = sanitize_visual_prompt_text(
        '"ip_adaptation": {"identity_anchors_visible": ["blue tie"]}, '
        "generation_world_profile: morning market, "
        "semantic_reason: scene integrated, "
        "image_text_plan: planned sign, "
        "#FFFFFF white body"
    )

    assert "ip_adaptation" not in prompt
    assert "identity_anchors_visible" not in prompt
    assert "generation_world_profile" not in prompt
    assert "semantic_reason" not in prompt
    assert "image_text_plan" not in prompt
    assert "#FFFFFF" not in prompt
```

- [ ] **Step 2: Add styled batch regression for final prompt cleanup**

In `tests/test_styled_image_prompt_batch.py`, add:

```python
@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_sanitizes_expanded_ip_internal_keys(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        return [
            "ip_adaptation: white rabbit guide, "
            "identity_anchors_visible: blue tie, "
            "generation_world_profile: morning market, "
            "semantic_reason: scene integrated, "
            "#FFFFFF white body"
        ]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["A guide enters the morning market."],
        image_config={},
    )

    prompt = result.prompts[0]
    assert "ip_adaptation" not in prompt
    assert "identity_anchors_visible" not in prompt
    assert "generation_world_profile" not in prompt
    assert "semantic_reason" not in prompt
    assert "#FFFFFF" not in prompt
    assert "white rabbit guide" in prompt
```

- [ ] **Step 3: Run tests and confirm current sanitizer gap**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_styled_image_prompt_batch.py -k "expanded_ip_internal_keys or ip_adaptation_field_labels" -q
```

Expected now:

```text
FAILED
```

- [ ] **Step 4: Extend the existing sanitizer instead of adding a duplicate safety path**

In `pixelle_video/utils/prompt_helper.py`, extend `_FIELD_LABEL_RE`:

```python
r"['\"]?\b(?:summary_text|scene_text|title_hex|ip_presence_type|presence_mode|"
r"visible_text_whitelist|negative_constraints|identity_color_terms|"
r"generation_world_profile|story_constraints|ip_integration_guidance|"
r"ip_adaptation|identity_anchors_visible|identity_anchors_suppressed|"
r"semantic_reason|image_text_plan|must_not_replace"
r")\b['\"]?\s*[:：]\s*"
```

Keep the existing final prompt cleanup in `pixelle_video/utils/content_generators.py`:

```python
final_prompts = [
    sanitize_visual_prompt_text(prompt)
    for prompt in final_prompts
]
```

- [ ] **Step 5: Run final prompt cleanup tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_styled_image_prompt_batch.py -k "sanitize_visual_prompt_text or never_leaks_hex_codes_or_field_names or expanded_ip_internal_keys" -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```powershell
git add pixelle_video/utils/prompt_helper.py pixelle_video/utils/content_generators.py tests/test_styled_image_prompt_batch.py
git commit -m "fix: sanitize expanded IP internal prompt keys"
```

---

## Task 9: Mandatory LLM Trace Artifacts

**Files:**
- Modify: `pixelle_video/models/llm_interaction_trace.py`
- Modify: `pixelle_video/services/llm_service.py`
- Modify: `pixelle_video/services/llm_interaction_recorder.py`
- Create: `pixelle_video/services/prompt_trace_artifacts.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Modify: `pixelle_video/utils/style_resolution.py`
- Modify: `pixelle_video/services/content_world_planner.py`
- Modify: `pixelle_video/services/script_generation.py`
- Modify: `pixelle_video/services/storyboard_generation.py`
- Modify: `pixelle_video/services/storyboard_planner.py`
- Modify: `pixelle_video/services/image_prompt_composer.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `tests/test_llm_service_trace_capture.py`
- Modify: `tests/test_llm_interaction_trace_model.py`
- Modify: `tests/test_llm_interaction_recorder.py`
- Create: `tests/test_generation_llm_trace_contract.py`
- Create: `tests/test_prompt_trace_artifacts.py`

- [ ] **Step 1: Add trace metadata model tests**

In `tests/test_llm_interaction_trace_model.py`, add:

```python
def test_trace_context_records_prompt_template_and_chain_metadata():
    context = LLMTraceContext(
        workspace_id="workspace_1",
        task_id="task_123",
        operation="image_prompt_generation",
        stage="base_prompt_batch",
        frame_id="frame_0001",
        metadata={
            "chain_id": "chain_abc",
            "attempt": 2,
            "prompt_template": {
                "prompt_id": "image_generation",
                "version": "2026-05-24-v1",
                "path": "pixelle_video/prompts/templates/image_generation.md",
                "output_contract": "ImagePromptBatchResponse",
            },
        },
    )

    restored = LLMTraceContext.from_dict(context.to_dict())

    assert restored.metadata["chain_id"] == "chain_abc"
    assert restored.metadata["attempt"] == 2
    assert restored.metadata["prompt_template"]["prompt_id"] == "image_generation"
    assert restored.metadata["prompt_template"]["path"].endswith("image_generation.md")
```

- [ ] **Step 2: Make untraced production LLM calls fail before provider IO**

In `tests/test_llm_service_trace_capture.py`, add:

```python
@pytest.mark.asyncio
async def test_llm_service_rejects_untraced_generation_calls_before_provider_request(monkeypatch):
    fake_client, create_recorder = _fake_client(
        base_url="https://api.deepseek.com/v1",
        content="plain answer",
    )
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: fake_client)

    with pytest.raises(ValueError, match="LLM trace_context and trace_recorder are required"):
        await service(
            prompt="Explain atomic habits",
            model="deepseek-chat",
        )

    assert create_recorder.calls == []
```

Then update `pixelle_video/services/llm_service.py` at the start of `__call__`:

```python
if trace_context is None or trace_recorder is None:
    raise LLMTraceRequiredError(LLM_TRACE_REQUIRED_MESSAGE)
```

No production or unit-test escape hatch is allowed here; provider compatibility tests must provide a real trace fixture.

- [ ] **Step 3: Prove raw request and response payloads contain inspectable prompt text**

In `tests/test_llm_service_trace_capture.py`, extend `test_llm_service_records_successful_text_calls_at_gateway`:

```python
request_payload = raw_store.payloads[0]["payload"]
response_payload = raw_store.payloads[1]["payload"]

assert request_payload["messages"][0]["content"] == "Explain atomic habits"
assert response_payload["content"] == "plain answer"
assert trace_repository.appended[0]["trace"]["request_preview"]
assert trace_repository.appended[0]["trace"]["response_preview"]
```

- [ ] **Step 4: Add generation call-site trace contract tests**

Create `tests/test_generation_llm_trace_contract.py`:

```python
import ast
from pathlib import Path


GENERATION_LLM_CALL_FILES = [
    Path("pixelle_video/utils/content_generators.py"),
    Path("pixelle_video/utils/style_resolution.py"),
    Path("pixelle_video/services/content_world_planner.py"),
    Path("pixelle_video/services/script_generation.py"),
    Path("pixelle_video/services/storyboard_generation.py"),
    Path("pixelle_video/services/storyboard_planner.py"),
]


def _llm_service_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "llm_service":
                yield node


def test_generation_llm_calls_pass_trace_context_and_recorder():
    offenders = []
    for path in GENERATION_LLM_CALL_FILES:
        for call in _llm_service_calls(path):
            keyword_names = {keyword.arg for keyword in call.keywords if keyword.arg}
            if "trace_context" not in keyword_names or "trace_recorder" not in keyword_names:
                offenders.append(f"{path}:{call.lineno}")

    assert offenders == []


def test_untraced_llm_escape_hatch_does_not_exist_in_production_code():
    offenders = []
    for root in (Path("pixelle_video"), Path("api"), Path("web")):
      for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "allow_untraced_llm_call" in text:
            offenders.append(str(path))

    assert offenders == []
```

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_generation_llm_trace_contract.py -q
```

Expected now:

```text
FAILED
```

The failure should list current generation call sites that still call `llm_service(...)` without trace metadata.

- [ ] **Step 5: Thread trace context and recorder through generation APIs**

Update public generation functions that call LLMs to accept trace metadata:

```python
async def generate_image_prompts(
    llm_service,
    narrations: list[str],
    min_words: int = 50,
    max_words: int = 100,
    *,
    prompt_contexts: PromptContextEnvelope | Mapping[str, Any] | None = None,
    prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
    trace_context: LLMTraceContext,
    trace_recorder: LLMInteractionRecorder,
) -> list[str]:
    rendered_prompt = render_image_prompt_prompt(
        narrations,
        min_words=min_words,
        max_words=max_words,
        prompt_contexts=prompt_contexts,
        prompt_language=prompt_language,
    )
    response: ImagePromptBatchResponse = await llm_service(
        rendered_prompt.text,
        temperature=0.7,
        max_tokens=2000,
        response_type=ImagePromptBatchResponse,
        trace_context=_with_prompt_template(
            trace_context,
            stage="image_prompt_generation",
            prompt=rendered_prompt,
        ),
        trace_recorder=trace_recorder,
    )
    return list(response.image_prompts)
```

Add a small helper near the generation utilities:

```python
def _with_prompt_template(
    context: LLMTraceContext,
    *,
    stage: str,
    prompt: RenderedPrompt,
    frame_id: str | None = None,
    attempt: int = 1,
) -> LLMTraceContext:
    metadata = dict(context.metadata)
    metadata["prompt_template"] = prompt.trace_metadata()
    metadata["attempt"] = attempt
    return LLMTraceContext(
        workspace_id=context.workspace_id,
        task_id=context.task_id,
        operation=context.operation,
        stage=stage,
        frame_id=frame_id or context.frame_id,
        metadata=metadata,
    )
```

Apply the same pattern to `generate_video_prompts`, narration generation, style resolution, content-world planning, script generation, storyboard generation, and storyboard planning.

- [ ] **Step 6: Create per-generation prompt artifact writer**

Create `pixelle_video/services/prompt_trace_artifacts.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def write_final_prompt_artifact(
    *,
    output_dir: Path,
    task_id: str,
    frames: Sequence[Mapping[str, Any]],
    generation_context: Mapping[str, Any] | None = None,
) -> Path:
    trace_dir = output_dir / "prompt_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = trace_dir / "final_visual_prompts.md"
    lines = [
        f"# Final Visual Prompts",
        "",
        f"- task_id: `{task_id}`",
        f"- frame_count: `{len(frames)}`",
        "",
    ]
    if generation_context:
        lines.extend([
            "## Generation Context",
            "",
            "```json",
            json.dumps(generation_context, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
        ])
    for frame in frames:
        index = frame["index"]
        prompt = str(frame["prompt"]).strip()
        negative_prompt = str(frame.get("negative_prompt") or "").strip()
        lines.extend(
            [
                f"## Frame {index}",
                "",
                "### Positive Prompt",
                "",
                "```text",
                prompt,
                "```",
                "",
                "### Negative Prompt",
                "",
                "```text",
                negative_prompt,
                "```",
                "",
            ]
        )
    artifact_path.write_text("\n".join(lines), encoding="utf-8")
    return artifact_path
```

- [ ] **Step 7: Add final prompt artifact tests**

Create `tests/test_prompt_trace_artifacts.py`:

```python
from pixelle_video.services.prompt_trace_artifacts import write_final_prompt_artifact


def test_final_prompt_artifact_persists_exact_media_prompt(tmp_path):
    final_prompt = "A white rabbit guide with a blue tie stands in a morning market."
    artifact = write_final_prompt_artifact(
        output_dir=tmp_path,
        task_id="task-1",
        frames=[
            {
                "index": 1,
                "prompt": final_prompt,
                "negative_prompt": "blurry, unreadable text",
            }
        ],
    )

    text = artifact.read_text(encoding="utf-8")
    assert "task-1" in text
    assert final_prompt in text
    assert "Generation Context" in text
    assert "blurry, unreadable text" in text
    assert artifact.name == "final_visual_prompts.md"
```

- [ ] **Step 8: Write final prompt artifacts before media generation**

In `pixelle_video/pipelines/standard.py`, after prompt plans are built and before frame media generation starts, call `write_final_prompt_artifact(...)` with the same prompt values assigned to `StoryboardFrame.image_prompt`, plus a `Generation Context` snapshot containing workflow, prompt prefix, world hint, IP controls, storyboard controls, resolved style, planning snapshot, and prompt plan bundle.

Use this frame payload shape:

```python
artifact_frames = [
    {
        "index": frame.index,
        "prompt": frame.image_prompt,
        "negative_prompt": getattr(frame, "negative_prompt", "") or "",
    }
    for frame in frames
]
```

Store the artifact path in the task planning snapshot so the UI/log layer can show where the prompt chain lives.

- [ ] **Step 9: Run trace tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_llm_interaction_trace_model.py tests/test_llm_interaction_recorder.py tests/test_llm_service_trace_capture.py tests/test_generation_llm_trace_contract.py tests/test_prompt_trace_artifacts.py -q
```

Expected:

```text
passed
```

- [ ] **Step 10: Commit**

```powershell
git add pixelle_video/models/llm_interaction_trace.py pixelle_video/services/llm_service.py pixelle_video/services/llm_interaction_recorder.py pixelle_video/services/prompt_trace_artifacts.py pixelle_video/utils/content_generators.py pixelle_video/utils/style_resolution.py pixelle_video/services/content_world_planner.py pixelle_video/services/script_generation.py pixelle_video/services/storyboard_generation.py pixelle_video/services/storyboard_planner.py pixelle_video/services/image_prompt_composer.py pixelle_video/pipelines/standard.py tests/test_llm_service_trace_capture.py tests/test_llm_interaction_trace_model.py tests/test_llm_interaction_recorder.py tests/test_generation_llm_trace_contract.py tests/test_prompt_trace_artifacts.py
git commit -m "feat: require traceable LLM prompt interactions"
```

---

## Task 10: Full Verification And Contract Audit

**Files:**
- Verify all files touched by Tasks 0-9.

- [ ] **Step 1: Run focused request-entry tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_generation_request_contract.py tests/test_content_ip_world_controls.py tests/test_content_ip_world_static_contract.py tests/test_content_input_storyboard_ui.py::test_left_content_ip_payload_render_content_input tests/test_output_preview.py::test_build_single_generation_request_includes_generation_world_hint tests/test_output_preview.py::test_build_single_generation_request_does_not_forward_ip_profile_world_hint tests/test_video_api.py::test_build_video_generation_params_copies_generation_world_hint tests/test_image_prompt_composer.py::test_composer_passes_generation_world_hint_to_styled_batch -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run prompt template provenance tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_prompt_template_registry.py tests/test_prompt_template_no_inline_bodies.py -q
```

Expected:

```text
passed
```

Run:

```powershell
rg -n "PROMPT\\s*=\\s*\"\"\"|_PROMPT\\s*=\\s*\"\"\"" pixelle_video/prompts
```

Expected:

```text
```

- [ ] **Step 3: Run LLM traceability tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_llm_interaction_trace_model.py tests/test_llm_interaction_recorder.py tests/test_llm_service_trace_capture.py tests/test_generation_llm_trace_contract.py tests/test_prompt_trace_artifacts.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run focused IP fact and planner tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ip_design_workbench_ui.py tests/test_ip_usage_planner.py tests/test_ip_prompt_integration.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Run final visual prompt product contract tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_visual_prompt_final_product_contract.py tests/test_frame_processor_negative_prompt.py::test_step_generate_media_forwards_final_frame_prompt_to_media_model -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Run styled generation and API regression tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_styled_image_prompt_batch.py tests/test_output_preview.py tests/test_video_api.py tests/test_image_prompt_composer.py tests/test_standard_pipeline_storyboard_generation.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Run static request-field gates**

Run:

```powershell
rg -n "generation_notes|slot_preference_override|presence_strength" web/components/content_ip_world_controls.py web/i18n/locales/en_US.json web/i18n/locales/zh_CN.json
```

Expected:

```text
```

Run:

```powershell
rg -n "ip_profile_world_hint|generation_world_hint_source" web/components/output_preview.py api/schemas/video.py api/routers/video.py pixelle_video/models/video_generation_contract.py
```

Expected:

```text
```

- [ ] **Step 8: Run final prompt cleanup tests**

Run:

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_styled_image_prompt_batch.py -k "never_leaks_hex_codes_or_field_names or expanded_ip_internal_keys" -q
```

Expected:

```text
passed
```

- [ ] **Step 9: Inspect git state**

Run:

```powershell
git status --short
git diff --stat
```

Expected:

```text
Only files listed in this plan are modified before the final commit.
```

- [ ] **Step 10: Final commit**

```powershell
git add pixelle_video web tests docs/superpowers/specs/2026-05-24-ip-design-entry-contract-realignment-design.md docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md
git commit -m "feat: realign IP design generation source chain"
```

---

## Self-Review

Review pass 1, source ownership:

- All LLM prompt bodies move to Markdown prompt templates with front matter.
- Python prompt modules become render adapters rather than prompt prose owners.
- Static tests and ripgrep gates prevent triple-quoted prompt constants from returning.
- Shared request fields live in `pixelle_video/contracts/ip_generation_request.py`.
- The left UI returns formal fields only.
- Legacy UI fields are deleted from code and i18n.
- Workbench facts are stored in the same shape consumed by the planner.
- Frontend readiness calls backend readiness logic.

Review pass 2, execution verification:

- Every changed contract has a failing test before implementation.
- Removed fields have both unit tests and ripgrep gates.
- Planner input completeness is tested by capturing the LLM prompt.
- SceneCast valid and invalid presence paths are both tested.
- Prompt contexts carry structured `ip_adaptation`.
- Final visual prompt assembly has product-contract tests.
- Media handoff proves the frame prompt is sent unchanged as the model prompt.
- Final prompt sanitization removes internal keys and hex codes.
- LLM trace tests prove exact request payloads, response payloads, template provenance, stage, and attempt metadata are saved.
- Final prompt artifact tests prove the prompt sent to media generation is inspectable after the run.

Placeholder scan:

- The plan contains concrete file paths, code snippets, commands, and expected outcomes for every task.

Type consistency:

- `generation_world_hint` is request-level.
- `IPProfile.world_hint` remains asset-level.
- `ip_profile_world_hint` remains helper-only.
- `color_palette[*].prompt` contains prompt-safe color language.
- `color_palette[*].hex` can preserve UI color values without entering prompt text.
- `ip_adaptation` is allowed in prompt contexts and forbidden in final prompt strings.
- `PromptPlan.final_prompt`, `StoryboardFrame.image_prompt`, and media `prompt` are one artifact.
- `RenderedPrompt.text` is the exact string sent to the LLM.
- `RenderedPrompt.trace_metadata()` is stored in `LLMTraceContext.metadata["prompt_template"]`.
- No `allow_untraced_llm_call` escape hatch exists; every LLM generation call must provide trace context and a trace recorder.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-24-ip-design-entry-contract-realignment-implementation.md`.

Execution mode:

**Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, with review checkpoints after each task.
