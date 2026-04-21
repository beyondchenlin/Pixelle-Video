# Image Style Profile Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw image prefix concatenation with runtime style resolution, style-guided prompt generation, and capability-gated negative-prompt plumbing while keeping the existing frontend behavior unchanged.

**Architecture:** Add a runtime style-resolution layer that turns either the active prompt-prefix library item or a request-scoped override into a cached `ResolvedStyleSpec`. Use that spec to guide base image-prompt generation, assemble final prompts by `style_kind`, and thread optional `negative_prompt` through standard generation, content APIs, and preview paths without mutating persisted config during normal generation.

**Tech Stack:** Python 3.12, FastAPI, Streamlit, dataclasses, Pydantic, Loguru, ComfyKit / WorkflowParser, pytest

---

Repository note: this repository's `AGENTS.md` forbids `git worktree`, so execute this plan on the current branch and do not create a worktree even though the generic planning skill usually recommends one.

## File Map

- `pixelle_video/models/style_resolution.py`
  Runtime dataclasses for `StyleSourceSpec`, `ResolvedStyleSpec`, and `StyledImagePromptBatch`.
- `pixelle_video/prompts/style_resolution.py`
  LLM prompt builder that classifies a raw prefix into `style_kind`, `prompt_template`, `negative_prompt`, and `style_profile`.
- `pixelle_video/utils/style_resolution.py`
  Request-vs-library source resolution, runtime cache, strict JSON parsing, and cache-key construction.
- `pixelle_video/config/prompt_prefix_library.py`
  Helper to fetch the active prompt-prefix item instead of only returning raw `content`.
- `pixelle_video/prompts/image_generation.py`
  Extend the base-prompt template to accept `style_profile_json`.
- `pixelle_video/utils/workflow_capabilities.py`
  Detect optional workflow inputs from workflow metadata; default unsupported fields to `False`.
- `pixelle_video/utils/prompt_helper.py`
  Keep legacy concatenation helper and add strategy-based final prompt assembly helpers.
- `pixelle_video/utils/content_generators.py`
  Add a shared `generate_styled_image_prompt_batch(...)` helper used by standard generation, API generation, and preview generation.
- `pixelle_video/pipelines/linear.py`
  Carry resolved style / negative-prompt state in `PipelineContext`.
- `pixelle_video/pipelines/standard.py`
  Replace local prefix concatenation with the shared styled batch helper.
- `pixelle_video/models/storyboard.py`
  Add task-level `media_negative_prompt` to `StoryboardConfig`.
- `pixelle_video/services/frame_processor.py`
  Pass `negative_prompt` into `MediaService` when the active workflow supports it.
- `pixelle_video/services/persistence.py`
  Serialize and deserialize `media_negative_prompt`.
- `api/schemas/content.py`
  Add optional `prompt_prefix` and `workflow` inputs to keep `/content/image-prompt` semantically aligned with standard generation.
- `api/routers/content.py`
  Route `/content/image-prompt` through the same styled batch helper.
- `web/components/style_config.py`
  Route preview generation through the shared styled batch helper instead of raw string concatenation.
- `tests/test_style_resolution.py`
  Unit tests for source resolution, cache keys, and runtime cache reuse.
- `tests/test_styled_image_prompt_batch.py`
  Unit tests for style-guided prompt generation, fallback behavior, and `ip_world` assembly rules.
- `tests/test_workflow_capabilities.py`
  Unit tests for selfhost and wrapper capability detection.
- `tests/test_standard_pipeline_prompt_prefix.py`
  Regression tests for active library items, request-scoped override, and resolved negative prompt capture.
- `tests/test_frame_processor_negative_prompt.py`
  Unit test for forwarding `media_negative_prompt` into `MediaService`.
- `tests/test_content_image_prompt_api.py`
  Unit tests for the content API using the shared styled batch helper.
- `tests/test_style_config_prompt_prefix_ui.py`
  Preview-path regression tests that assert preview uses the same backend prompt path.

Intentionally untouched in V1:

- `pixelle_video/config/schema.py`
  Keep config persistence shape unchanged because structured style metadata is runtime-only in this rollout.

### Task 1: Build Runtime Style Resolution Core

**Files:**
- Create: `pixelle_video/models/style_resolution.py`
- Create: `pixelle_video/prompts/style_resolution.py`
- Create: `pixelle_video/utils/style_resolution.py`
- Modify: `pixelle_video/prompts/__init__.py`
- Modify: `pixelle_video/config/prompt_prefix_library.py`
- Test: `tests/test_style_resolution.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_style_resolution.py
import pytest

from pixelle_video.models.style_resolution import StyleSourceSpec
from pixelle_video.utils.style_resolution import (
    RESOLVER_VERSION,
    build_style_resolution_cache_key,
    resolve_style_source,
    resolve_style_spec,
    reset_style_resolution_cache,
)


def test_resolve_style_source_prefers_request_override():
    image_config = {
        "prompt_prefix": "legacy prefix",
        "prompt_prefix_library": {
            "active_prefix_id": "warm-story",
            "items": [
                {
                    "id": "warm-story",
                    "content": "warm storybook illustration",
                }
            ],
        },
    }

    source = resolve_style_source(image_config, prompt_prefix_override="  angry birds world  ")

    assert source.origin == "request"
    assert source.raw_content == "angry birds world"
    assert source.item_id is None
    assert source.source_identity.startswith("request:")


def test_build_style_resolution_cache_key_distinguishes_library_and_request():
    library_source = StyleSourceSpec(
        origin="library",
        raw_content="warm storybook illustration",
        content_hash="hash-lib",
        source_identity="library:warm-story",
        item_id="warm-story",
    )
    request_source = StyleSourceSpec(
        origin="request",
        raw_content="warm storybook illustration",
        content_hash="hash-req",
        source_identity="request:hash-req",
        item_id=None,
    )

    assert build_style_resolution_cache_key(library_source) == (
        f"library:warm-story:hash-lib:{RESOLVER_VERSION}"
    )
    assert build_style_resolution_cache_key(request_source) == (
        f"request:hash-req:{RESOLVER_VERSION}"
    )


@pytest.mark.asyncio
async def test_resolve_style_spec_reuses_runtime_cache(monkeypatch):
    reset_style_resolution_cache()
    calls = {"count": 0}

    async def fake_llm(prompt, temperature, max_tokens):
        calls["count"] += 1
        return """
        {
          "style_kind": "ip_world",
          "prompt_template": "{prompt}, same playful bird-universe silhouette",
          "negative_prompt": "photo realism, realistic fur",
          "style_profile": {
            "style_kind": "ip_world",
            "subject_policy": "keep_subject_semantics_but_restyle_into_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "bright playful lighting",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
            "negative_rules": "do not revert to realistic anatomy"
          }
        }
        """

    source = StyleSourceSpec(
        origin="request",
        raw_content="angry birds world",
        content_hash="hash-123",
        source_identity="request:hash-123",
        item_id=None,
    )

    first = await resolve_style_spec(fake_llm, source)
    second = await resolve_style_spec(fake_llm, source)

    assert first.style_kind == "ip_world"
    assert second == first
    assert calls["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_style_resolution.py -v`

Expected: FAIL with import errors because `pixelle_video.models.style_resolution` and `pixelle_video.utils.style_resolution` do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

```python
# pixelle_video/models/style_resolution.py
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

StyleKind = Literal["visual_only", "ip_world", "hybrid"]
StyleSourceOrigin = Literal["request", "library", "legacy"]


@dataclass(frozen=True)
class StyleSourceSpec:
    origin: StyleSourceOrigin
    raw_content: str
    content_hash: str
    source_identity: str
    item_id: Optional[str] = None


@dataclass(frozen=True)
class ResolvedStyleSpec:
    style_kind: StyleKind
    prompt_template: str = ""
    negative_prompt: str = ""
    style_profile: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    resolver_version: str = ""
    source_identity: str = ""
    raw_content: str = ""


@dataclass(frozen=True)
class StyledImagePromptBatch:
    prompts: list[str]
    negative_prompt: Optional[str]
    resolved_style: Optional[ResolvedStyleSpec]
```

```python
# pixelle_video/prompts/style_resolution.py
STYLE_RESOLUTION_PROMPT = """# Role
You convert one raw image-style prefix into structured backend style metadata.

# Input Prefix
{raw_prefix}

# Output JSON
{{
  "style_kind": "visual_only | ip_world | hybrid",
  "prompt_template": "optional wrapper that contains {{prompt}} exactly once",
  "negative_prompt": "optional negative prompt",
  "style_profile": {{
    "style_kind": "visual_only | ip_world | hybrid",
    "subject_policy": "...",
    "shape_language": "...",
    "material": "...",
    "palette": "...",
    "lighting": "...",
    "world_elements": "...",
    "consistency_anchor": "...",
    "negative_rules": "..."
  }}
}}

Rules:
- Return JSON only.
- `style_kind` must be one of `visual_only`, `ip_world`, or `hybrid`.
- If `prompt_template` is non-empty it must contain `{{prompt}}` exactly once.
- For `ip_world`, `subject_policy`, `world_elements`, and `consistency_anchor` must be specific.
- For `visual_only`, do not replace the subject with a named IP character.
"""


def build_style_resolution_prompt(raw_prefix: str) -> str:
    return STYLE_RESOLUTION_PROMPT.format(raw_prefix=raw_prefix.strip())
```

```python
# pixelle_video/config/prompt_prefix_library.py
def get_active_image_prompt_prefix_item(image_config: Any) -> Optional[dict[str, Any]]:
    library = _read_mapping_or_attr(image_config, "prompt_prefix_library", None)
    if library is None:
        return None

    active_prefix_id = _read_mapping_or_attr(library, "active_prefix_id", None)
    items = _read_mapping_or_attr(library, "items", [])
    for item in items:
        if _read_mapping_or_attr(item, "id", None) == active_prefix_id:
            return item if isinstance(item, dict) else item.model_dump()
    return None
```

```python
# pixelle_video/utils/style_resolution.py
import hashlib
import json
from typing import Optional

from loguru import logger

from pixelle_video.config.prompt_prefix_library import get_active_image_prompt_prefix_item
from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.prompts import build_style_resolution_prompt

RESOLVER_VERSION = "2026-04-21-v1"
_STYLE_RESOLUTION_CACHE: dict[str, ResolvedStyleSpec] = {}


def reset_style_resolution_cache() -> None:
    _STYLE_RESOLUTION_CACHE.clear()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def resolve_style_source(image_config, prompt_prefix_override: Optional[str] = None) -> Optional[StyleSourceSpec]:
    override = (prompt_prefix_override or "").strip()
    if override:
        content_hash = _hash_text(override)
        return StyleSourceSpec(
            origin="request",
            raw_content=override,
            content_hash=content_hash,
            source_identity=f"request:{content_hash}",
            item_id=None,
        )

    active_item = get_active_image_prompt_prefix_item(image_config)
    if active_item:
        raw_content = (active_item.get("content") or "").strip()
        if raw_content:
            content_hash = _hash_text(raw_content)
            return StyleSourceSpec(
                origin="library",
                raw_content=raw_content,
                content_hash=content_hash,
                source_identity=f"library:{active_item['id']}",
                item_id=active_item["id"],
            )

    legacy_prefix = (image_config.get("prompt_prefix") or "").strip()
    if legacy_prefix:
        content_hash = _hash_text(legacy_prefix)
        return StyleSourceSpec(
            origin="legacy",
            raw_content=legacy_prefix,
            content_hash=content_hash,
            source_identity=f"legacy:{content_hash}",
            item_id=None,
        )
    return None


def build_style_resolution_cache_key(source: StyleSourceSpec) -> str:
    if source.origin == "library" and source.item_id:
        return f"library:{source.item_id}:{source.content_hash}:{RESOLVER_VERSION}"
    return f"{source.origin}:{source.content_hash}:{RESOLVER_VERSION}"


def _parse_resolved_style_spec(response: str, source: StyleSourceSpec) -> ResolvedStyleSpec:
    data = json.loads(response)
    return ResolvedStyleSpec(
        style_kind=data["style_kind"],
        prompt_template=(data.get("prompt_template") or "").strip(),
        negative_prompt=(data.get("negative_prompt") or "").strip(),
        style_profile=data["style_profile"],
        content_hash=source.content_hash,
        resolver_version=RESOLVER_VERSION,
        source_identity=source.source_identity,
        raw_content=source.raw_content,
    )


async def resolve_style_spec(llm_service, source: StyleSourceSpec) -> ResolvedStyleSpec:
    cache_key = build_style_resolution_cache_key(source)
    cached = _STYLE_RESOLUTION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prompt = build_style_resolution_prompt(source.raw_content)
    response = await llm_service(prompt=prompt, temperature=0.2, max_tokens=1200)
    resolved = _parse_resolved_style_spec(response, source)
    _STYLE_RESOLUTION_CACHE[cache_key] = resolved
    logger.debug("Resolved style {} via runtime cache key {}", source.source_identity, cache_key)
    return resolved
```

```python
# pixelle_video/prompts/__init__.py
from pixelle_video.prompts.style_resolution import build_style_resolution_prompt

__all__ = [
    # existing exports...
    "build_style_resolution_prompt",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_style_resolution.py -v`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_style_resolution.py pixelle_video/models/style_resolution.py pixelle_video/prompts/style_resolution.py pixelle_video/utils/style_resolution.py pixelle_video/prompts/__init__.py pixelle_video/config/prompt_prefix_library.py
git commit -m "feat: add runtime style resolution core"
```

### Task 2: Add Style-Guided Prompt Generation and Assembly Helpers

**Files:**
- Modify: `pixelle_video/prompts/image_generation.py`
- Modify: `pixelle_video/utils/prompt_helper.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Create: `pixelle_video/utils/workflow_capabilities.py`
- Test: `tests/test_styled_image_prompt_batch.py`
- Test: `tests/test_workflow_capabilities.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_styled_image_prompt_batch.py
import pytest

from pixelle_video.models.style_resolution import ResolvedStyleSpec, StyleSourceSpec
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


def _resolved_ip_world() -> ResolvedStyleSpec:
    return ResolvedStyleSpec(
        style_kind="ip_world",
        prompt_template="{prompt}, same playful bird-universe silhouette",
        negative_prompt="photo realism, realistic fur",
        style_profile={
            "style_kind": "ip_world",
            "subject_policy": "keep_subject_semantics_but_restyle_into_world",
            "shape_language": "rounded geometric cartoon forms",
            "material": "clean game-like cartoon surface",
            "palette": "high saturation reds and yellows",
            "lighting": "bright playful lighting",
            "world_elements": "destructible wooden obstacles and game-like props",
            "consistency_anchor": "all frames belong to the same playful bird universe",
            "negative_rules": "do not revert to realistic anatomy",
        },
        content_hash="hash-123",
        resolver_version="2026-04-21-v1",
        source_identity="request:hash-123",
        raw_content="Angry Birds style",
    )


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_blocks_raw_fallback_for_ip_world(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"]["style_kind"] == "ip_world"
        return ["rounded geometric dog sprinting across playful wooden obstacles"]

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_source",
        lambda image_config, prompt_prefix_override=None: StyleSourceSpec(
            origin="request",
            raw_content="Angry Birds style",
            content_hash="hash-123",
            source_identity="request:hash-123",
            item_id=None,
        ),
    )
    async def fake_resolve_style_spec(*args, **kwargs):
        return _resolved_ip_world()

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.get_media_workflow_capabilities",
        lambda *args, **kwargs: type("Caps", (), {"supports_negative_prompt": True})(),
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["一只小狗在奔跑"],
        image_config={"prompt_prefix": "", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=object(),
        workflow="selfhost/image_z_image_turbo.json",
        prompt_prefix="Angry Birds style",
    )

    assert result.prompts == [
        "rounded geometric dog sprinting across playful wooden obstacles, same playful bird-universe silhouette"
    ]
    assert "Angry Birds style" not in result.prompts[0]
    assert result.negative_prompt == "photo realism, realistic fur"


@pytest.mark.asyncio
async def test_generate_styled_image_prompt_batch_falls_back_to_legacy_prefix_when_resolver_fails(monkeypatch):
    async def fake_generate_image_prompts(*args, **kwargs):
        assert kwargs["style_profile"] is None
        return ["base scene prompt"]

    async def fake_resolve_style_spec(*args, **kwargs):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.generate_image_prompts",
        fake_generate_image_prompts,
    )
    monkeypatch.setattr(
        "pixelle_video.utils.content_generators.resolve_style_spec",
        fake_resolve_style_spec,
    )

    result = await generate_styled_image_prompt_batch(
        llm_service=object(),
        narrations=["scene one"],
        image_config={"prompt_prefix": "flat illustration", "prompt_prefix_library": {"active_prefix_id": None, "items": []}},
        media_service=None,
        prompt_prefix=None,
    )

    assert result.prompts == ["flat illustration, base scene prompt"]
    assert result.negative_prompt is None
```

```python
# tests/test_workflow_capabilities.py
import json
from pathlib import Path

from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities


def test_get_workflow_capabilities_reads_negative_prompt_from_selfhost_metadata(monkeypatch, tmp_path):
    workflow_path = tmp_path / "image_test.json"
    workflow_path.write_text("{}", encoding="utf-8")

    class _Metadata:
        params = {"prompt": object(), "negative_prompt": object()}

    class _Parser:
        def parse_workflow_file(self, path):
            assert path == str(workflow_path)
            return _Metadata()

    monkeypatch.setattr("pixelle_video.utils.workflow_capabilities.WorkflowParser", lambda: _Parser())

    caps = get_workflow_capabilities(
        {
            "source": "selfhost",
            "path": str(workflow_path),
            "key": "selfhost/image_test.json",
        }
    )

    assert caps.supports_negative_prompt is True


def test_get_workflow_capabilities_defaults_wrapper_optional_fields_to_false(tmp_path):
    workflow_path = tmp_path / "image_wrapper.json"
    workflow_path.write_text(
        json.dumps({"source": "runninghub", "workflow_id": "wf-1"}),
        encoding="utf-8",
    )

    caps = get_workflow_capabilities(
        {
            "source": "runninghub",
            "path": str(workflow_path),
            "key": "runninghub/image_wrapper.json",
        }
    )

    assert caps.supports_negative_prompt is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_styled_image_prompt_batch.py tests/test_workflow_capabilities.py -v`

Expected: FAIL because `generate_styled_image_prompt_batch(...)` and `get_workflow_capabilities(...)` do not exist yet, and `generate_image_prompts(...)` does not accept `style_profile`.

- [ ] **Step 3: Write the minimal implementation**

```python
# pixelle_video/prompts/image_generation.py
import json
from typing import Any, List, Optional

IMAGE_PROMPT_GENERATION_PROMPT = """# Role Definition
You are a professional visual creative designer...

# Input Style Profile
{style_profile_json}

# Input Narrations
{narrations_json}

# Output Requirements
- Language: **Must use English**
- Description structure: scene + character action + emotion + symbolic elements
- If a style profile is provided, subject design, material, palette, lighting, world elements, and consistency must obey that style profile first.
- When `style_kind` is `ip_world`, redesign the subject into the target universe without replacing the subject semantics.
...
"""


def build_image_prompt_prompt(
    narrations: List[str],
    min_words: int,
    max_words: int,
    style_profile: Optional[dict[str, Any]] = None,
) -> str:
    narrations_json = json.dumps({"narrations": narrations}, ensure_ascii=False, indent=2)
    style_profile_json = json.dumps(style_profile or None, ensure_ascii=False, indent=2)
    return IMAGE_PROMPT_GENERATION_PROMPT.format(
        style_profile_json=style_profile_json,
        narrations_json=narrations_json,
        narrations_count=len(narrations),
        min_words=min_words,
        max_words=max_words,
    )
```

```python
# pixelle_video/utils/workflow_capabilities.py
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from comfykit.comfyui.workflow_parser import WorkflowParser


@dataclass(frozen=True)
class WorkflowCapabilities:
    supports_negative_prompt: bool = False


def get_workflow_capabilities(workflow_info: Dict[str, Any]) -> WorkflowCapabilities:
    if workflow_info["source"] == "selfhost":
        metadata = WorkflowParser().parse_workflow_file(str(workflow_info["path"]))
        return WorkflowCapabilities(
            supports_negative_prompt="negative_prompt" in metadata.params
        )

    wrapper = json.loads(Path(workflow_info["path"]).read_text(encoding="utf-8"))
    declared = wrapper.get("capabilities") or {}
    return WorkflowCapabilities(
        supports_negative_prompt=bool(declared.get("negative_prompt"))
    )


def get_media_workflow_capabilities(media_service, workflow: str | None, media_type: str = "image") -> WorkflowCapabilities:
    workflow_info = media_service._resolve_workflow(workflow=workflow, workflow_domain=media_type)
    return get_workflow_capabilities(workflow_info)
```

```python
# pixelle_video/utils/prompt_helper.py
from typing import Optional

from pixelle_video.models.style_resolution import ResolvedStyleSpec


def build_image_prompt(prompt: str, prefix: str = "") -> str:
    prefix = prefix.strip() if prefix else ""
    prompt = prompt.strip() if prompt else ""
    if prefix and prompt:
        return f"{prefix}, {prompt}"
    if prefix:
        return prefix
    return prompt


def assemble_image_prompt(
    base_prompt: str,
    raw_prefix: str = "",
    resolved_style: Optional[ResolvedStyleSpec] = None,
) -> str:
    if resolved_style is None:
        return build_image_prompt(base_prompt, raw_prefix)

    template = (resolved_style.prompt_template or "").strip()
    if template and "{prompt}" in template:
        templated = template.replace("{prompt}", base_prompt.strip())
    else:
        templated = base_prompt.strip()

    if resolved_style.style_kind == "ip_world":
        return templated

    if resolved_style.style_kind == "hybrid":
        raw_prefix = raw_prefix.strip()
        if raw_prefix and raw_prefix.lower() not in templated.lower():
            return f"{templated}, {raw_prefix}"
        return templated

    if template:
        return templated
    return build_image_prompt(base_prompt, raw_prefix)


def assemble_negative_prompt(
    resolved_style: Optional[ResolvedStyleSpec],
    supports_negative_prompt: bool,
) -> Optional[str]:
    if not resolved_style or not supports_negative_prompt:
        return None
    negative_prompt = (resolved_style.negative_prompt or "").strip()
    return negative_prompt or None
```

```python
# pixelle_video/utils/content_generators.py
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.utils.prompt_helper import assemble_image_prompt, assemble_negative_prompt
from pixelle_video.utils.style_resolution import resolve_style_source, resolve_style_spec
from pixelle_video.utils.workflow_capabilities import WorkflowCapabilities, get_media_workflow_capabilities


async def generate_image_prompts(
    llm_service,
    narrations: List[str],
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    style_profile: Optional[dict] = None,
) -> List[str]:
    ...
    prompt = build_image_prompt_prompt(
        narrations=batch_narrations,
        min_words=min_words,
        max_words=max_words,
        style_profile=style_profile,
    )
    ...


async def generate_styled_image_prompt_batch(
    llm_service,
    narrations: List[str],
    image_config,
    prompt_prefix: Optional[str] = None,
    workflow: Optional[str] = None,
    media_service=None,
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
) -> StyledImagePromptBatch:
    source = resolve_style_source(image_config, prompt_prefix_override=prompt_prefix)
    raw_prefix = source.raw_content if source else ""
    resolved_style = None
    style_profile = None

    if source is not None:
        try:
            resolved_style = await resolve_style_spec(llm_service, source)
            style_profile = resolved_style.style_profile
        except Exception:
            logger.exception("Style resolution failed, falling back to legacy prefix concatenation")

    base_prompts = await generate_image_prompts(
        llm_service=llm_service,
        narrations=narrations,
        min_words=min_words,
        max_words=max_words,
        batch_size=batch_size,
        max_retries=max_retries,
        progress_callback=progress_callback,
        style_profile=style_profile,
    )

    capabilities = (
        get_media_workflow_capabilities(media_service, workflow=workflow, media_type="image")
        if media_service is not None
        else WorkflowCapabilities()
    )

    final_prompts = [
        assemble_image_prompt(base_prompt, raw_prefix=raw_prefix, resolved_style=resolved_style)
        for base_prompt in base_prompts
    ]
    negative_prompt = assemble_negative_prompt(
        resolved_style,
        supports_negative_prompt=capabilities.supports_negative_prompt,
    )
    return StyledImagePromptBatch(
        prompts=final_prompts,
        negative_prompt=negative_prompt,
        resolved_style=resolved_style,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_styled_image_prompt_batch.py tests/test_workflow_capabilities.py -v`

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_styled_image_prompt_batch.py tests/test_workflow_capabilities.py pixelle_video/prompts/image_generation.py pixelle_video/utils/prompt_helper.py pixelle_video/utils/content_generators.py pixelle_video/utils/workflow_capabilities.py
git commit -m "feat: add style-guided image prompt assembly"
```

### Task 3: Integrate Standard Pipeline and Negative Prompt Plumbing

**Files:**
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/models/storyboard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Modify: `pixelle_video/services/persistence.py`
- Test: `tests/test_standard_pipeline_prompt_prefix.py`
- Test: `tests/test_frame_processor_negative_prompt.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_standard_pipeline_prompt_prefix.py
import pytest

from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class _DummyCore:
    def __init__(self, config: dict):
        self.config = config
        self.llm = object()
        self.tts = None
        self.media = object()
        self.video = None


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_uses_shared_styled_batch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        return StyledImagePromptBatch(
            prompts=["bird-universe dog sprint"],
            negative_prompt="photo realism",
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(
        _DummyCore(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix": "legacy prefix",
                        "prompt_prefix_library": {
                            "active_prefix_id": "custom-flat",
                            "items": [
                                {"id": "custom-flat", "content": "flat illustration"}
                            ],
                        },
                    }
                }
            }
        )
    )
    ctx = PipelineContext(
        input_text="topic",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["bird-universe dog sprint"]
    assert ctx.media_negative_prompt == "photo realism"


@pytest.mark.asyncio
async def test_standard_pipeline_plan_visuals_passes_explicit_override(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["override prompt"],
            negative_prompt=None,
            resolved_style=None,
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    pipeline = StandardPipeline(_DummyCore({"comfyui": {"image": {"prompt_prefix": "legacy"}}}))
    ctx = PipelineContext(
        input_text="topic",
        params={
            "frame_template": "1080x1920/image_default.html",
            "prompt_prefix": "explicit override",
        },
    )
    ctx.narrations = ["scene one"]

    await pipeline.plan_visuals(ctx)

    assert captured["prompt_prefix"] == "explicit override"
    assert ctx.image_prompts == ["override prompt"]
```

```python
# tests/test_frame_processor_negative_prompt.py
import pytest

from pixelle_video.models.media import MediaResult
from pixelle_video.models.storyboard import StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor


@pytest.mark.asyncio
async def test_step_generate_media_forwards_media_negative_prompt(monkeypatch, tmp_path):
    captured = {}

    class _FakeCore:
        async def media(self, **kwargs):
            captured.update(kwargs)
            return MediaResult(media_type="image", url="https://example.com/frame.png")

    processor = FrameProcessor(_FakeCore())

    async def fake_download_media(*args, **kwargs):
        return str(tmp_path / "frame.png")

    monkeypatch.setattr(processor, "_download_media", fake_download_media)

    frame = StoryboardFrame(index=0, narration="scene", image_prompt="bird-universe dog sprint")
    config = StoryboardConfig(
        media_width=1024,
        media_height=1024,
        task_id="task-1",
        media_negative_prompt="photo realism",
    )

    await processor._step_generate_media(frame, config)

    assert captured["negative_prompt"] == "photo realism"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_frame_processor_negative_prompt.py -v`

Expected: FAIL because `generate_styled_image_prompt_batch(...)` is not wired into `StandardPipeline`, `PipelineContext` has no `media_negative_prompt`, and `StoryboardConfig` / `FrameProcessor` do not carry `negative_prompt`.

- [ ] **Step 3: Write the minimal implementation**

```python
# pixelle_video/pipelines/linear.py
from pixelle_video.models.style_resolution import ResolvedStyleSpec


@dataclass
class PipelineContext:
    ...
    image_prompts: List[Optional[str]] = field(default_factory=list)
    resolved_style: Optional[ResolvedStyleSpec] = None
    media_negative_prompt: Optional[str] = None
```

```python
# pixelle_video/models/storyboard.py
@dataclass
class StoryboardConfig:
    media_width: int
    media_height: int
    ...
    media_workflow: Optional[str] = None
    media_negative_prompt: Optional[str] = None
    frame_template: str = "1080x1920/default.html"
```

```python
# pixelle_video/pipelines/standard.py
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    generate_styled_image_prompt_batch,
    generate_narrations_from_topic,
    generate_title,
    split_narration_script,
)


async def plan_visuals(self, ctx: PipelineContext):
    ...
    styled_batch = await generate_styled_image_prompt_batch(
        llm_service=self.llm,
        narrations=ctx.narrations,
        image_config=image_config,
        prompt_prefix=prompt_prefix,
        workflow=ctx.params.get("media_workflow"),
        media_service=self.core.media,
        min_words=min_words,
        max_words=max_words,
        progress_callback=image_prompt_progress,
    )
    ctx.image_prompts = styled_batch.prompts
    ctx.resolved_style = styled_batch.resolved_style
    ctx.media_negative_prompt = styled_batch.negative_prompt
```

```python
# pixelle_video/pipelines/standard.py (initialize_storyboard)
ctx.config = StoryboardConfig(
    task_id=ctx.task_id,
    n_storyboard=len(ctx.narrations),
    ...
    media_workflow=ctx.params.get("media_workflow"),
    media_negative_prompt=ctx.media_negative_prompt,
    frame_template=ctx.params.get("frame_template") or "1080x1920/default.html",
    template_params=ctx.params.get("template_params"),
)
```

```python
# pixelle_video/services/frame_processor.py
media_params = {
    "prompt": frame.image_prompt,
    "workflow": config.media_workflow,
    "media_type": media_type,
    "width": config.media_width,
    "height": config.media_height,
    "index": frame.index + 1,
}
if config.media_negative_prompt:
    media_params["negative_prompt"] = config.media_negative_prompt
```

```python
# pixelle_video/services/persistence.py
def _config_to_dict(self, config: StoryboardConfig) -> Dict[str, Any]:
    return {
        ...
        "media_workflow": config.media_workflow,
        "media_negative_prompt": config.media_negative_prompt,
        "frame_template": config.frame_template,
        "template_params": config.template_params,
    }


def _dict_to_config(self, data: Dict[str, Any]) -> StoryboardConfig:
    return StoryboardConfig(
        ...
        media_workflow=data.get("media_workflow", data.get("image_workflow")),
        media_negative_prompt=data.get("media_negative_prompt"),
        frame_template=data.get("frame_template", "1080x1920/default.html"),
        template_params=data.get("template_params"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_standard_pipeline_prompt_prefix.py tests/test_frame_processor_negative_prompt.py -v`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_standard_pipeline_prompt_prefix.py tests/test_frame_processor_negative_prompt.py pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py pixelle_video/models/storyboard.py pixelle_video/services/frame_processor.py pixelle_video/services/persistence.py
git commit -m "feat: thread resolved image styles through standard pipeline"
```

### Task 4: Unify Content API and Preview Paths with the Shared Backend Prompt Pipeline

**Files:**
- Modify: `api/schemas/content.py`
- Modify: `api/routers/content.py`
- Modify: `web/components/style_config.py`
- Test: `tests/test_content_image_prompt_api.py`
- Test: `tests/test_style_config_prompt_prefix_ui.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_content_image_prompt_api.py
import pytest

from api.routers.content import generate_image_prompt
from api.schemas.content import ImagePromptGenerateRequest
from pixelle_video.models.style_resolution import StyledImagePromptBatch


class _FakePixelleVideo:
    def __init__(self):
        self.llm = object()
        self.media = object()
        self.core = type(
            "Core",
            (),
            {
                "config": {
                    "comfyui": {
                        "image": {
                            "prompt_prefix": "legacy prefix",
                            "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                        }
                    }
                }
            },
        )()


@pytest.mark.asyncio
async def test_generate_image_prompt_endpoint_uses_shared_styled_batch(monkeypatch):
    async def fake_generate_styled_image_prompt_batch(**kwargs):
        assert kwargs["prompt_prefix"] == "angry birds world"
        assert kwargs["workflow"] == "selfhost/image_z_image_turbo.json"
        return StyledImagePromptBatch(
            prompts=["styled prompt"],
            negative_prompt="photo realism",
            resolved_style=None,
        )

    monkeypatch.setattr(
        "api.routers.content.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    response = await generate_image_prompt(
        ImagePromptGenerateRequest(
            narrations=["scene one"],
            prompt_prefix="angry birds world",
            workflow="selfhost/image_z_image_turbo.json",
        ),
        _FakePixelleVideo(),
    )

    assert response.image_prompts == ["styled prompt"]
```

```python
# tests/test_style_config_prompt_prefix_ui.py
import asyncio

from web.components import style_config
from pixelle_video.models.style_resolution import StyledImagePromptBatch


def test_generate_prompt_prefix_preview_results_uses_shared_styled_batch(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["prompt_prefix"] = kwargs["prompt_prefix"]
        return StyledImagePromptBatch(
            prompts=["preview final prompt"],
            negative_prompt="avoid realism",
            resolved_style=None,
        )

    class _FakePixelleVideo:
        llm = object()
        core = type(
            "Core",
            (),
            {
                "config": {
                    "comfyui": {
                        "image": {
                            "prompt_prefix": "",
                            "prompt_prefix_library": {"active_prefix_id": None, "items": []},
                        }
                    }
                }
            },
        )()

        async def media(self, **kwargs):
            captured["media_kwargs"] = kwargs
            return type("MediaResult", (), {"url": "preview.png"})()

    monkeypatch.setattr(style_config, "generate_styled_image_prompt_batch", fake_generate_styled_image_prompt_batch)
    monkeypatch.setattr(style_config, "run_async", lambda coro: asyncio.run(coro))

    preview_results = style_config._generate_prompt_prefix_preview_results(
        pixelle_video=_FakePixelleVideo(),
        workflow_key="selfhost/image_z_image_turbo.json",
        media_width=1024,
        media_height=1024,
        test_prompt="a dog",
        items=[{"id": "prefix-1", "name": "Bird World", "content": "angry birds world"}],
    )

    assert preview_results[0]["final_prompt"] == "preview final prompt"
    assert captured["media_kwargs"]["negative_prompt"] == "avoid realism"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_content_image_prompt_api.py tests/test_style_config_prompt_prefix_ui.py::test_generate_prompt_prefix_preview_results_uses_shared_styled_batch -v`

Expected: FAIL because the content API schema has no `prompt_prefix` / `workflow`, and preview helpers still build prompts with `build_image_prompt(...)`.

- [ ] **Step 3: Write the minimal implementation**

```python
# api/schemas/content.py
class ImagePromptGenerateRequest(BaseModel):
    narrations: List[str] = Field(..., description="List of narrations")
    min_words: int = Field(30, ge=10, le=100, description="Minimum words per prompt")
    max_words: int = Field(60, ge=10, le=200, description="Maximum words per prompt")
    prompt_prefix: Optional[str] = Field(
        None,
        description="Request-scoped image style prefix override",
    )
    workflow: Optional[str] = Field(
        None,
        description="Workflow key used for capability-gated optional fields",
    )
```

```python
# api/routers/content.py
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    generate_narrations_from_topic,
    generate_styled_image_prompt_batch,
    generate_title,
)


@router.post("/image-prompt", response_model=ImagePromptGenerateResponse)
async def generate_image_prompt(
    request: ImagePromptGenerateRequest,
    pixelle_video: PixelleVideoDep
):
    image_config = pixelle_video.core.config.get("comfyui", {}).get("image", {})
    batch = await generate_styled_image_prompt_batch(
        llm_service=pixelle_video.llm,
        narrations=request.narrations,
        image_config=image_config,
        prompt_prefix=request.prompt_prefix,
        workflow=request.workflow,
        media_service=pixelle_video.media,
        min_words=request.min_words,
        max_words=request.max_words,
    )
    return ImagePromptGenerateResponse(image_prompts=batch.prompts)
```

```python
# web/components/style_config.py
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


def _generate_prompt_prefix_preview_results(
    pixelle_video,
    workflow_key: str,
    media_width: int,
    media_height: int,
    test_prompt: str,
    items: list[dict],
) -> list[dict]:
    preview_results: list[dict] = []
    image_config = pixelle_video.core.config.get("comfyui", {}).get("image", {})

    for item in items:
        styled_batch = run_async(
            generate_styled_image_prompt_batch(
                llm_service=pixelle_video.llm,
                narrations=[test_prompt],
                image_config=image_config,
                prompt_prefix=item["content"],
                workflow=workflow_key,
                media_service=pixelle_video.media,
            )
        )
        final_prompt = styled_batch.prompts[0]
        media_result = run_async(
            pixelle_video.media(
                prompt=final_prompt,
                negative_prompt=styled_batch.negative_prompt,
                workflow=workflow_key,
                media_type="image",
                width=int(media_width),
                height=int(media_height),
            )
        )
        if media_result.url:
            preview_results.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "content": item["content"],
                    "final_prompt": final_prompt,
                    "preview_media_path": media_result.url,
                }
            )
    return preview_results
```

```python
# web/components/style_config.py (inside the expander preview button branch)
preview_results = _generate_prompt_prefix_preview_results(
    pixelle_video=pixelle_video,
    workflow_key=workflow_key,
    media_width=int(media_width),
    media_height=int(media_height),
    test_prompt=test_prompt,
    items=preview_items,
)
st.session_state["prompt_prefix_preview_results"] = preview_results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_content_image_prompt_api.py tests/test_style_config_prompt_prefix_ui.py::test_generate_prompt_prefix_preview_results_uses_shared_styled_batch -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_content_image_prompt_api.py tests/test_style_config_prompt_prefix_ui.py api/schemas/content.py api/routers/content.py web/components/style_config.py
git commit -m "feat: align preview and content api with styled prompt pipeline"
```

## Final Regression Sweep

Run this full focused suite before opening a PR or requesting review:

```bash
pytest tests/test_style_resolution.py tests/test_styled_image_prompt_batch.py tests/test_workflow_capabilities.py tests/test_standard_pipeline_prompt_prefix.py tests/test_frame_processor_negative_prompt.py tests/test_content_image_prompt_api.py tests/test_style_config_prompt_prefix_ui.py -v
```

Expected: all selected tests PASS.

Also run a quick diff sanity check before pushing:

```bash
git status --short
git log --oneline -n 4
```

Expected:

- `git status --short` shows only intended tracked changes for the current task before each commit, and a clean tree after the final commit.
- `git log --oneline -n 4` shows the four task commits in order.

## Spec Coverage Check

- `style_kind = visual_only | ip_world | hybrid`
  Covered by Task 1 resolver schema and Task 2 assembly rules.
- Request-scoped temporary `prompt_prefix`
  Covered by Task 1 source resolution and Task 3 / Task 4 integrations.
- Runtime cache only, no auto-persist back into config
  Covered by Task 1 runtime cache implementation; no schema/config write task exists.
- `style_profile` enters image prompt generation
  Covered by Task 2 prompt-template and batch-helper changes.
- `negative_prompt` capability-gated
  Covered by Task 2 capability helper and Task 3 frame/media plumbing.
- Preview parity
  Covered by Task 4 preview helper switch and preview regression test.
- Backward-compatible fallback to raw prefix concatenation
  Covered by Task 2 fallback test and `assemble_image_prompt(...)`.

## Placeholder Scan

This plan has been checked for placeholder markers and vague directives. Every task above names exact files, code changes, test names, commands, and commit messages.
