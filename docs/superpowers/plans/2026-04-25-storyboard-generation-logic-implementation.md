# Storyboard Generation Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standard video pipeline's narration-first storyboard flow with a `StoryboardPlan`-first generation contract that supports smart, punctuation, and sentence storyboard modes.

**Architecture:** The core flow becomes `source_text -> StoryboardGenerationService -> StoryboardPlan -> StoryboardEnhancer -> ImagePromptComposer -> media generation`. `ctx.narrations` remains only as a derived compatibility list for TTS/render timing until those layers are redesigned. API staged video endpoints from `2026-04-25-api-experience-improvements.md` are out of scope for this plan.

**Tech Stack:** Python 3.12, Pydantic v2, dataclasses, pytest, pytest-asyncio, FastAPI schema validation, existing Pixelle standard pipeline and Streamlit UI.

---

## Scope Boundary

This plan implements the video storyboard generation logic first. It does not implement the staged diagnostic API from `docs/superpowers/plans/2026-04-25-api-experience-improvements.md`.

The main video API schema and Streamlit request builders are included because they are current entry points into the standard video generation pipeline. They must switch in the same release as the core pipeline so old `n_scenes` and `split_mode` do not keep feeding the standard pipeline.

Independent content APIs can keep `n_scenes` and narration/image-prompt utilities for standalone tools, but those utilities must not be used by `standard` video generation to decide frame count.

---

## File Structure

- Create `pixelle_video/models/storyboard_plan.py`: canonical `StoryboardPlan`, frame, span, enum, validation, and serialization helpers.
- Create `pixelle_video/models/script_generation.py`: structured response models for full-script generation.
- Create `pixelle_video/prompts/script_generation.py`: prompt builder for generating complete `source_text` from a topic.
- Create `pixelle_video/prompts/storyboard_generation.py`: prompt builder and parser for smart storyboard planning from full `source_text`.
- Create `pixelle_video/services/script_generation.py`: `ScriptGenerationService` for `mode=generate`.
- Create `pixelle_video/services/storyboard_generation.py`: strategy router and deterministic split strategies.
- Create `pixelle_video/services/image_prompt_composer.py`: prompt composition layer that consumes `StoryboardPlan` frames.
- Modify `pixelle_video/services/storyboard_planner.py`: keep current planning logic as the enhancer, add a plan-frame entry point without reintroducing narration as upstream truth.
- Modify `pixelle_video/pipelines/linear.py`: add `source_text` and `storyboard_plan` to `PipelineContext`.
- Modify `pixelle_video/pipelines/standard.py`: generate/normalize `source_text`, generate `StoryboardPlan`, derive narrations, compose prompts, persist diagnostics.
- Modify `pixelle_video/config/schema.py`: add hard storyboard generation limits and script length profile defaults.
- Modify `api/schemas/video.py`: replace `n_scenes` with storyboard/script length fields and reject invalid combinations.
- Modify `api/routers/video.py`: forward new storyboard fields and stop forwarding `n_scenes`.
- Modify `web/components/content_input.py`: expose storyboard mode controls and script length controls.
- Modify `web/components/output_preview.py`: send new storyboard fields in single and batch generation requests.
- Modify `web/utils/batch_manager.py`: preserve new storyboard fields in `shared_config`; no `n_scenes`.
- Modify relevant tests under `tests/`: add service tests first, then update API/UI/pipeline tests.

---

## Task 1: Canonical StoryboardPlan Model

**Files:**
- Create: `pixelle_video/models/storyboard_plan.py`
- Test: `tests/test_storyboard_plan_model.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/test_storyboard_plan_model.py`:

```python
import pytest

from pixelle_video.models.storyboard_plan import (
    SourceSpan,
    StoryboardCountMode,
    StoryboardGenerationMode,
    StoryboardPlan,
    StoryboardPlanFrame,
)


def test_storyboard_plan_assigns_digest_and_serializes_frames():
    plan = StoryboardPlan.build(
        mode=StoryboardGenerationMode.PUNCTUATION,
        count_mode=StoryboardCountMode.AUTO,
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                narration_text="第一句。",
                visual_goal="Show the first idea.",
                prompt_intent="A clear visual metaphor for the first idea.",
                source_start=0,
                source_end=4,
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                narration_text="第二句。",
                visual_goal="Show the second idea.",
                prompt_intent="A clear visual metaphor for the second idea.",
                source_start=4,
                source_end=8,
            ),
        ],
    )

    payload = plan.to_dict()

    assert plan.resolved_scene_count == 2
    assert plan.source_digest
    assert payload["frames"][0]["frame_id"].startswith("frame_")
    assert payload["frames"][1]["index"] == 2


def test_source_spans_index_plan_source_text():
    span = SourceSpan(start=0, end=3, text="abc", reason="primary")
    frame = StoryboardPlanFrame(
        index=1,
        source_text="abc",
        narration_text="abc",
        visual_goal="show abc",
        prompt_intent="show abc",
        source_start=None,
        source_end=None,
        metadata={"source_spans": [span.to_dict()]},
    )

    plan = StoryboardPlan.build(
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        source_text="abcdef",
        frames=[frame],
    )

    assert plan.frames[0].metadata["source_spans"][0]["text"] == "abc"


def test_storyboard_plan_rejects_non_contiguous_indices():
    with pytest.raises(ValueError, match="frame indexes must start at 1 and be contiguous"):
        StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text="one two",
            frames=[
                StoryboardPlanFrame(
                    index=2,
                    source_text="one two",
                    narration_text="one two",
                    visual_goal="show text",
                    prompt_intent="show text",
                )
            ],
        )
```

- [ ] **Step 2: Run model tests to verify RED**

Run:

```bash
pytest tests/test_storyboard_plan_model.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'pixelle_video.models.storyboard_plan'`.

- [ ] **Step 3: Implement the model**

Create `pixelle_video/models/storyboard_plan.py`:

```python
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StoryboardGenerationMode(str, Enum):
    SMART = "smart"
    PUNCTUATION = "punctuation"
    SENTENCE = "sentence"


class StoryboardCountMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class ScriptLengthMode(str, Enum):
    AUTO = "auto"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    CUSTOM = "custom"


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    text: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "reason": self.reason,
        }


@dataclass
class StoryboardPlanFrame:
    index: int
    source_text: str
    narration_text: str
    visual_goal: str
    prompt_intent: str
    frame_id: str = ""
    shot_type: str | None = None
    shot_purpose: str | None = None
    primary_subject: str | None = None
    secondary_subjects: list[str] = field(default_factory=list)
    continuity_anchors: list[str] = field(default_factory=list)
    world_elements: list[str] = field(default_factory=list)
    source_start: int | None = None
    source_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "index": self.index,
            "source_text": self.source_text,
            "narration_text": self.narration_text,
            "visual_goal": self.visual_goal,
            "prompt_intent": self.prompt_intent,
            "shot_type": self.shot_type,
            "shot_purpose": self.shot_purpose,
            "primary_subject": self.primary_subject,
            "secondary_subjects": list(self.secondary_subjects),
            "continuity_anchors": list(self.continuity_anchors),
            "world_elements": list(self.world_elements),
            "source_start": self.source_start,
            "source_end": self.source_end,
            "metadata": dict(self.metadata),
        }


@dataclass
class StoryboardPlan:
    plan_id: str
    revision: int
    mode: StoryboardGenerationMode
    count_mode: StoryboardCountMode
    requested_scene_count: int | None
    resolved_scene_count: int
    source_text: str
    source_digest: str
    frames: list[StoryboardPlanFrame]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        mode: StoryboardGenerationMode | str,
        count_mode: StoryboardCountMode | str,
        requested_scene_count: int | None,
        source_text: str,
        frames: list[StoryboardPlanFrame],
        diagnostics: dict[str, Any] | None = None,
        plan_id: str | None = None,
        revision: int = 1,
    ) -> "StoryboardPlan":
        normalized_source = source_text.strip()
        if not normalized_source:
            raise ValueError("source_text must not be empty")
        if not frames:
            raise ValueError("StoryboardPlan requires at least one frame")

        expected_indexes = list(range(1, len(frames) + 1))
        actual_indexes = [frame.index for frame in frames]
        if actual_indexes != expected_indexes:
            raise ValueError("frame indexes must start at 1 and be contiguous")

        digest = hashlib.sha256(normalized_source.encode("utf-8")).hexdigest()
        stable_plan_id = plan_id or f"plan_{uuid.uuid4().hex}"
        for frame in frames:
            if not frame.narration_text.strip():
                raise ValueError("frame narration_text must not be empty")
            if frame.source_start is not None or frame.source_end is not None:
                if frame.source_start is None or frame.source_end is None:
                    raise ValueError("source_start and source_end must be set together")
                if not 0 <= frame.source_start <= frame.source_end <= len(normalized_source):
                    raise ValueError("frame source range must index StoryboardPlan.source_text")
            if not frame.frame_id:
                frame.frame_id = f"frame_{frame.index:04d}_{uuid.uuid4().hex[:8]}"

        return cls(
            plan_id=stable_plan_id,
            revision=revision,
            mode=StoryboardGenerationMode(mode),
            count_mode=StoryboardCountMode(count_mode),
            requested_scene_count=requested_scene_count,
            resolved_scene_count=len(frames),
            source_text=normalized_source,
            source_digest=digest,
            frames=frames,
            diagnostics=dict(diagnostics or {}),
        )

    def narration_texts(self) -> list[str]:
        return [frame.narration_text for frame in self.frames]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "revision": self.revision,
            "mode": self.mode.value,
            "count_mode": self.count_mode.value,
            "requested_scene_count": self.requested_scene_count,
            "resolved_scene_count": self.resolved_scene_count,
            "source_text": self.source_text,
            "source_digest": self.source_digest,
            "frames": [frame.to_dict() for frame in self.frames],
            "diagnostics": dict(self.diagnostics),
        }
```

- [ ] **Step 4: Run model tests to verify GREEN**

Run:

```bash
pytest tests/test_storyboard_plan_model.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/models/storyboard_plan.py tests/test_storyboard_plan_model.py
git commit -m "feat(storyboard): add storyboard plan contract models"
```

---

## Task 2: Storyboard Generation Config and Request Validation

**Files:**
- Modify: `pixelle_video/config/schema.py`
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Test: `tests/test_video_api.py`

- [ ] **Step 1: Write failing validation tests**

Append to `tests/test_video_api.py`:

```python
import pytest
from pydantic import ValidationError

from api.schemas.video import VideoGenerateRequest


def test_video_request_defaults_to_smart_storyboard_auto_count():
    request = VideoGenerateRequest(text="demo")

    assert request.storyboard_mode == "smart"
    assert request.storyboard_count_mode == "auto"
    assert request.storyboard_scene_count is None
    assert request.script_length_mode == "auto"
    assert request.script_target_words is None


def test_video_request_rejects_legacy_n_scenes():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="demo", n_scenes=3)


def test_video_request_rejects_scene_count_outside_smart_manual():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            storyboard_mode="punctuation",
            storyboard_count_mode="auto",
            storyboard_scene_count=3,
        )


def test_video_request_accepts_smart_manual_scene_count():
    request = VideoGenerateRequest(
        text="demo",
        storyboard_mode="smart",
        storyboard_count_mode="manual",
        storyboard_scene_count=4,
    )

    assert request.storyboard_scene_count == 4


def test_fixed_mode_rejects_script_length_controls():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="demo",
            mode="fixed",
            script_length_mode="medium",
        )
```

- [ ] **Step 2: Run validation tests to verify RED**

Run:

```bash
pytest tests/test_video_api.py -q
```

Expected: fail because `VideoGenerateRequest` still has `n_scenes` and does not define new storyboard fields.

- [ ] **Step 3: Add config limits**

Modify `StoryboardSubConfig` in `pixelle_video/config/schema.py`:

```python
class StoryboardSubConfig(BaseModel):
    """Storyboard planning configuration."""

    min_scene_count: int = Field(default=1, ge=1, le=100)
    max_scene_count: int = Field(default=30, ge=1, le=100)
    max_source_chars: int = Field(default=12000, ge=100, le=100000)
    script_default_target_words: int = Field(default=500, ge=50, le=10000)
    script_min_target_words: int = Field(default=80, ge=20, le=10000)
    script_max_target_words: int = Field(default=3000, ge=100, le=20000)
    script_length_profiles: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "short": {"target_words": 250},
            "medium": {"target_words": 500},
            "long": {"target_words": 900},
        }
    )
    world_preset_library: StoryboardWorldPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardWorldPresetLibraryConfig.model_validate(
            build_builtin_world_preset_library_dict()
        ),
        description="Storyboard world preset library",
    )
    shot_preset_library: StoryboardShotPresetLibraryConfig = Field(
        default_factory=lambda: StoryboardShotPresetLibraryConfig.model_validate(
            build_builtin_shot_preset_library_dict()
        ),
        description="Storyboard shot preset library",
    )
```

Keep the existing `world_preset_library` and `shot_preset_library` declarations after the new fields.

- [ ] **Step 4: Replace video request fields**

Modify `api/schemas/video.py`:

```python
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pixelle_video.models.storyboard_plan import (
    ScriptLengthMode,
    StoryboardCountMode,
    StoryboardGenerationMode,
)
```

In `VideoGenerateRequest`, remove `n_scenes`. Add:

```python
storyboard_mode: StoryboardGenerationMode = Field(
    StoryboardGenerationMode.SMART,
    description="Storyboard generation mode: smart, punctuation, or sentence",
)
storyboard_count_mode: StoryboardCountMode = Field(
    StoryboardCountMode.AUTO,
    description="Storyboard count mode. Manual count is valid only for smart mode.",
)
storyboard_scene_count: Optional[int] = Field(
    None,
    ge=1,
    le=30,
    description="Manual storyboard scene count; valid only for smart/manual mode",
)
script_length_mode: ScriptLengthMode = Field(
    ScriptLengthMode.AUTO,
    description="Complete script length control for generate mode",
)
script_target_words: Optional[int] = Field(
    None,
    ge=20,
    le=20000,
    description="Custom complete script target words; valid only for generate/custom mode",
)
```

Add a model validator:

```python
@model_validator(mode="after")
def validate_storyboard_generation_contract(self):
    if self.storyboard_mode == StoryboardGenerationMode.SMART:
        if self.storyboard_count_mode == StoryboardCountMode.AUTO and self.storyboard_scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only with storyboard_count_mode=manual")
        if self.storyboard_count_mode == StoryboardCountMode.MANUAL and self.storyboard_scene_count is None:
            raise ValueError("storyboard_scene_count is required with storyboard_count_mode=manual")
    else:
        if self.storyboard_count_mode != StoryboardCountMode.AUTO:
            raise ValueError("punctuation and sentence storyboard modes require storyboard_count_mode=auto")
        if self.storyboard_scene_count is not None:
            raise ValueError("storyboard_scene_count is valid only for smart/manual mode")

    if self.mode == "fixed":
        if self.script_length_mode != ScriptLengthMode.AUTO:
            raise ValueError("fixed mode requires script_length_mode=auto")
        if self.script_target_words is not None:
            raise ValueError("fixed mode does not accept script_target_words")
    elif self.script_length_mode == ScriptLengthMode.CUSTOM:
        if self.script_target_words is None:
            raise ValueError("script_target_words is required with script_length_mode=custom")
    elif self.script_target_words is not None:
        raise ValueError("script_target_words is valid only with script_length_mode=custom")

    return self
```

- [ ] **Step 5: Forward new fields to core generation**

Modify `api/routers/video.py` in `build_video_generation_params`:

```python
video_params = {
    "text": request_body.text,
    "mode": request_body.mode,
    "title": request_body.title,
    "storyboard_mode": request_body.storyboard_mode.value,
    "storyboard_count_mode": request_body.storyboard_count_mode.value,
    "storyboard_scene_count": request_body.storyboard_scene_count,
    "script_length_mode": request_body.script_length_mode.value,
    "script_target_words": request_body.script_target_words,
    "min_image_prompt_words": request_body.min_image_prompt_words,
    "max_image_prompt_words": request_body.max_image_prompt_words,
    "media_width": media_width,
    "media_height": media_height,
    "media_workflow": request_body.media_workflow,
    "video_fps": request_body.video_fps,
    "frame_template": request_body.frame_template,
    "prompt_prefix": request_body.prompt_prefix,
    "world_preset_id": request_body.world_preset_id,
    "shot_preset_id": request_body.shot_preset_id,
    "consistency_strength": request_body.consistency_strength or "standard",
    "content_mode": request_body.content_mode,
    "role_strategy": request_body.role_strategy,
    "role_locking_strength": request_body.role_locking_strength,
    "shot_strategy": request_body.shot_strategy,
    "frame_overrides": _serialize_frame_overrides(request_body.frame_overrides),
    "bgm_path": request_body.bgm_path,
    "bgm_volume": request_body.bgm_volume,
    "request_id": request_id,
}
```

Do not include `n_scenes`, `min_narration_words`, or `max_narration_words` in `video_params`.

- [ ] **Step 6: Run validation tests to verify GREEN**

Run:

```bash
pytest tests/test_video_api.py -q
```

Expected: pass, except unrelated tests that assert old `n_scenes`; update those assertions in the same file to the new fields.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/config/schema.py api/schemas/video.py api/routers/video.py tests/test_video_api.py
git commit -m "feat(api): add storyboard generation request contract"
```

---

## Task 3: Deterministic Storyboard Strategies

**Files:**
- Create: `pixelle_video/services/storyboard_generation.py`
- Test: `tests/test_storyboard_generation_service.py`

- [ ] **Step 1: Write failing deterministic strategy tests**

Create `tests/test_storyboard_generation_service.py`:

```python
import pytest

from pixelle_video.services.storyboard_generation import StoryboardGenerationService


@pytest.mark.asyncio
async def test_punctuation_mode_splits_on_all_unicode_punctuation():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="第一段，继续；结束。Next: done!",
        storyboard_mode="punctuation",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "第一段，",
        "继续；",
        "结束。",
        "Next:",
        "done!",
    ]
    assert plan.mode.value == "punctuation"


@pytest.mark.asyncio
async def test_sentence_mode_splits_only_sentence_boundaries():
    service = StoryboardGenerationService(config={"max_scene_count": 10})

    plan = await service.generate(
        llm_service=None,
        source_text="第一段，继续；结束。Next: not yet? Done!",
        storyboard_mode="sentence",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert [frame.narration_text for frame in plan.frames] == [
        "第一段，继续；结束。",
        "Next: not yet?",
        "Done!",
    ]


@pytest.mark.asyncio
async def test_deterministic_strategy_rejects_over_max_scene_count():
    service = StoryboardGenerationService(config={"max_scene_count": 2})

    with pytest.raises(ValueError, match="too many storyboard frames"):
        await service.generate(
            llm_service=None,
            source_text="一。二。三。",
            storyboard_mode="sentence",
            storyboard_count_mode="auto",
            storyboard_scene_count=None,
        )
```

- [ ] **Step 2: Run deterministic tests to verify RED**

Run:

```bash
pytest tests/test_storyboard_generation_service.py -q
```

Expected: fail because `StoryboardGenerationService` does not exist.

- [ ] **Step 3: Implement deterministic strategy service**

Create `pixelle_video/services/storyboard_generation.py` with:

```python
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.storyboard_plan import (
    StoryboardPlan,
    StoryboardPlanFrame,
)


SENTENCE_TERMINATORS = "。！？.!?"


def _is_unicode_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _split_with_predicate(source_text: str, predicate) -> list[tuple[str, int, int]]:
    cleaned = _normalize_text(source_text)
    if not cleaned:
        return []

    segments: list[tuple[str, int, int]] = []
    start = 0
    current: list[str] = []
    current_start = 0
    has_text = False
    for index, char in enumerate(cleaned):
        if not current:
            current_start = index
        current.append(char)
        if not char.isspace() and not _is_unicode_punctuation(char):
            has_text = True
        next_char = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        should_split = has_text and predicate(char) and (not next_char or not predicate(next_char))
        if should_split:
            segment = "".join(current).strip()
            if segment:
                segments.append((segment, current_start, index + 1))
            current = []
            has_text = False
            start = index + 1
    if current:
        segment = "".join(current).strip()
        if segment:
            segments.append((segment, start, len(cleaned)))
    return segments


@dataclass
class StoryboardGenerationService:
    config: dict[str, Any] | None = None

    async def generate(
        self,
        *,
        llm_service,
        source_text: str,
        storyboard_mode: str,
        storyboard_count_mode: str,
        storyboard_scene_count: int | None,
    ) -> StoryboardPlan:
        if storyboard_mode == "punctuation":
            segments = _split_with_predicate(source_text, _is_unicode_punctuation)
            return self._plan_from_segments(
                mode="punctuation",
                count_mode=storyboard_count_mode,
                requested_scene_count=None,
                source_text=source_text,
                segments=segments,
            )
        if storyboard_mode == "sentence":
            segments = _split_with_predicate(source_text, lambda char: char in SENTENCE_TERMINATORS)
            return self._plan_from_segments(
                mode="sentence",
                count_mode=storyboard_count_mode,
                requested_scene_count=None,
                source_text=source_text,
                segments=segments,
            )
        raise ValueError("smart storyboard mode is not implemented yet")

    def _plan_from_segments(
        self,
        *,
        mode: str,
        count_mode: str,
        requested_scene_count: int | None,
        source_text: str,
        segments: list[tuple[str, int, int]],
    ) -> StoryboardPlan:
        normalized_source = _normalize_text(source_text)
        effective_segments = segments or [(normalized_source, 0, len(normalized_source))]
        max_scene_count = int((self.config or {}).get("max_scene_count", 30))
        if len(effective_segments) > max_scene_count:
            raise ValueError("too many storyboard frames; use smart storyboard mode or shorten the text")

        frames = [
            StoryboardPlanFrame(
                index=index,
                source_text=segment,
                narration_text=segment,
                visual_goal=f"Visualize storyboard segment {index}.",
                prompt_intent=f"Create a coherent scene that communicates: {segment}",
                source_start=start,
                source_end=end,
                metadata={"strategy": mode},
            )
            for index, (segment, start, end) in enumerate(effective_segments, start=1)
        ]
        return StoryboardPlan.build(
            mode=mode,
            count_mode=count_mode,
            requested_scene_count=requested_scene_count,
            source_text=normalized_source,
            frames=frames,
            diagnostics={"strategy": mode, "split_count": len(frames)},
        )
```

- [ ] **Step 4: Run deterministic tests to verify GREEN**

Run:

```bash
pytest tests/test_storyboard_generation_service.py -q
```

Expected: pass for deterministic tests; smart mode still intentionally fails only if called.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/storyboard_generation.py tests/test_storyboard_generation_service.py
git commit -m "feat(storyboard): add deterministic storyboard strategies"
```

---

## Task 4: ScriptGenerationService for Generate Mode

**Files:**
- Create: `pixelle_video/models/script_generation.py`
- Create: `pixelle_video/prompts/script_generation.py`
- Create: `pixelle_video/services/script_generation.py`
- Modify: `pixelle_video/prompts/__init__.py`
- Test: `tests/test_script_generation_service.py`

- [ ] **Step 1: Write failing script generation tests**

Create `tests/test_script_generation_service.py`:

```python
import pytest

from pixelle_video.services.script_generation import ScriptGenerationService


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        self.calls.append({"prompt": prompt, "response_type": response_type, "max_tokens": max_tokens})
        return response_type(source_text="这是一个完整文案。它不是分段旁白。")


@pytest.mark.asyncio
async def test_generate_mode_returns_complete_source_text():
    service = ScriptGenerationService(
        config={
            "script_default_target_words": 120,
            "script_min_target_words": 80,
            "script_max_target_words": 1000,
            "script_length_profiles": {"medium": {"target_words": 300}},
        }
    )

    result = await service.generate(
        llm_service=FakeLLM(),
        topic="介绍复利思维",
        script_length_mode="medium",
        script_target_words=None,
        title=None,
    )

    assert result.source_text == "这是一个完整文案。它不是分段旁白。"
    assert result.diagnostics["target_words"] == 300


@pytest.mark.asyncio
async def test_custom_target_words_must_be_in_range():
    service = ScriptGenerationService(
        config={
            "script_default_target_words": 120,
            "script_min_target_words": 80,
            "script_max_target_words": 1000,
            "script_length_profiles": {},
        }
    )

    with pytest.raises(ValueError, match="script_target_words"):
        await service.generate(
            llm_service=FakeLLM(),
            topic="demo",
            script_length_mode="custom",
            script_target_words=20,
            title=None,
        )
```

- [ ] **Step 2: Run script generation tests to verify RED**

Run:

```bash
pytest tests/test_script_generation_service.py -q
```

Expected: fail because service and model modules do not exist.

- [ ] **Step 3: Implement structured response model**

Create `pixelle_video/models/script_generation.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class ScriptGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_text: str

    @field_validator("source_text")
    @classmethod
    def validate_source_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source_text must not be empty")
        return stripped
```

- [ ] **Step 4: Implement prompt builder**

Create `pixelle_video/prompts/script_generation.py`:

```python
from __future__ import annotations


def build_script_generation_prompt(
    *,
    topic: str,
    target_words: int,
    title: str | None = None,
) -> str:
    title_line = f"Optional title: {title}" if title else "No title was provided."
    return f"""# Role
You are a short-video script writer.

# Task
Expand the user's topic into one complete source script, not a list of scenes.

# Requirements
- Write in the same language as the user's topic.
- Produce one continuous script of about {target_words} words.
- Keep natural punctuation.
- Do not number sections.
- Do not output storyboard frames.
- Do not output image prompts.

# User Topic
{topic}

# Title Context
{title_line}

# Output JSON
Return JSON only:
{{"source_text": "complete script text"}}
"""
```

Modify `pixelle_video/prompts/__init__.py`:

```python
from pixelle_video.prompts.script_generation import build_script_generation_prompt
```

Add `"build_script_generation_prompt"` to `__all__`.

- [ ] **Step 5: Implement service**

Create `pixelle_video/services/script_generation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelle_video.models.script_generation import ScriptGenerationResponse
from pixelle_video.prompts.script_generation import build_script_generation_prompt


@dataclass(frozen=True)
class ScriptGenerationResult:
    source_text: str
    diagnostics: dict[str, Any]


@dataclass
class ScriptGenerationService:
    config: dict[str, Any] | None = None

    def _resolve_target_words(self, script_length_mode: str, script_target_words: int | None) -> int:
        config = self.config or {}
        min_words = int(config.get("script_min_target_words", 80))
        max_words = int(config.get("script_max_target_words", 3000))
        if script_length_mode == "custom":
            if script_target_words is None or not min_words <= script_target_words <= max_words:
                raise ValueError("script_target_words must be within configured bounds")
            return int(script_target_words)
        if script_length_mode in {"short", "medium", "long"}:
            profiles = config.get("script_length_profiles", {})
            return int(profiles.get(script_length_mode, {}).get("target_words", config.get("script_default_target_words", 500)))
        return int(config.get("script_default_target_words", 500))

    async def generate(
        self,
        *,
        llm_service,
        topic: str,
        script_length_mode: str,
        script_target_words: int | None,
        title: str | None,
    ) -> ScriptGenerationResult:
        target_words = self._resolve_target_words(script_length_mode, script_target_words)
        prompt = build_script_generation_prompt(
            topic=topic,
            target_words=target_words,
            title=title,
        )
        response = await llm_service(
            prompt=prompt,
            response_type=ScriptGenerationResponse,
            temperature=0.7,
            max_tokens=max(1000, target_words * 4),
        )
        source_text = response.source_text.strip()
        if not source_text:
            raise ValueError("script generation returned empty source_text")
        return ScriptGenerationResult(
            source_text=source_text,
            diagnostics={
                "script_length_mode": script_length_mode,
                "target_words": target_words,
                "actual_chars": len(source_text),
            },
        )
```

- [ ] **Step 6: Run script generation tests to verify GREEN**

Run:

```bash
pytest tests/test_script_generation_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/models/script_generation.py pixelle_video/prompts/script_generation.py pixelle_video/prompts/__init__.py pixelle_video/services/script_generation.py tests/test_script_generation_service.py
git commit -m "feat(storyboard): generate complete scripts for video topics"
```

---

## Task 5: Smart Storyboard Strategy

**Files:**
- Create: `pixelle_video/prompts/storyboard_generation.py`
- Modify: `pixelle_video/services/storyboard_generation.py`
- Modify: `pixelle_video/models/content_generation.py`
- Test: `tests/test_storyboard_generation_service.py`

- [ ] **Step 1: Add failing smart strategy tests**

Append to `tests/test_storyboard_generation_service.py`:

```python
class SmartFakeLLM:
    async def __call__(self, *, prompt, response_type, temperature, max_tokens):
        return response_type(
            frames=[
                {
                    "source_text": "开头完整表达。",
                    "narration_text": "开头完整表达。",
                    "visual_goal": "Introduce the main idea.",
                    "prompt_intent": "A calm opening visual.",
                    "source_start": 0,
                    "source_end": 7,
                },
                {
                    "source_text": "结尾完整表达。",
                    "narration_text": "结尾完整表达。",
                    "visual_goal": "Close the idea.",
                    "prompt_intent": "A coherent closing visual.",
                    "source_start": 7,
                    "source_end": 14,
                },
            ]
        )


@pytest.mark.asyncio
async def test_smart_auto_uses_llm_to_create_plan_from_whole_source_text():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})

    plan = await service.generate(
        llm_service=SmartFakeLLM(),
        source_text="开头完整表达。结尾完整表达。",
        storyboard_mode="smart",
        storyboard_count_mode="auto",
        storyboard_scene_count=None,
    )

    assert plan.resolved_scene_count == 2
    assert plan.frames[0].visual_goal == "Introduce the main idea."


@pytest.mark.asyncio
async def test_smart_manual_requires_exact_scene_count():
    service = StoryboardGenerationService(config={"min_scene_count": 1, "max_scene_count": 10})

    with pytest.raises(ValueError, match="expected 3 smart storyboard frames"):
        await service.generate(
            llm_service=SmartFakeLLM(),
            source_text="开头完整表达。结尾完整表达。",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=3,
        )
```

- [ ] **Step 2: Run smart tests to verify RED**

Run:

```bash
pytest tests/test_storyboard_generation_service.py -q
```

Expected: smart tests fail because smart mode raises `not implemented yet`.

- [ ] **Step 3: Add smart response model**

Modify `pixelle_video/models/content_generation.py`:

```python
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SmartStoryboardFrameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_text: str
    narration_text: str
    visual_goal: str
    prompt_intent: str
    source_start: Optional[int] = None
    source_end: Optional[int] = None


class SmartStoryboardPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    frames: list[SmartStoryboardFrameResponse]

    @field_validator("frames")
    @classmethod
    def validate_frames(cls, values):
        if not values:
            raise ValueError("frames must not be empty")
        return values
```

Add `"SmartStoryboardFrameResponse"` and `"SmartStoryboardPlanResponse"` to `__all__`.

- [ ] **Step 4: Implement smart prompt builder**

Create `pixelle_video/prompts/storyboard_generation.py`:

```python
from __future__ import annotations

import json


def build_smart_storyboard_prompt(
    *,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
    min_scene_count: int,
    max_scene_count: int,
) -> str:
    count_instruction = (
        f"Create exactly {requested_scene_count} frames."
        if count_mode == "manual"
        else f"Choose the best frame count between {min_scene_count} and {max_scene_count}."
    )
    payload = {
        "task": "create_storyboard_plan_from_full_source_text",
        "source_text": source_text,
        "count_instruction": count_instruction,
        "requirements": [
            "Understand the complete source_text before creating frames.",
            "Frames may merge adjacent ideas when one sentence is too small for a visual scene.",
            "Frames may split a long sentence when it naturally contains multiple visual beats.",
            "Maintain continuity of style, subjects, and visual logic across all frames.",
            "Do not generate final image prompts.",
            "Return JSON only.",
        ],
        "frame_schema": {
            "source_text": "text covered by this frame",
            "narration_text": "voiceover text for this frame",
            "visual_goal": "what this frame should communicate visually",
            "prompt_intent": "guidance for later image prompt composition",
            "source_start": "optional Python string start index into source_text",
            "source_end": "optional Python string end index into source_text",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
```

- [ ] **Step 5: Implement smart mode in service**

Modify `StoryboardGenerationService.generate()` in `pixelle_video/services/storyboard_generation.py`:

```python
if storyboard_mode == "smart":
    return await self._generate_smart(
        llm_service=llm_service,
        source_text=source_text,
        count_mode=storyboard_count_mode,
        requested_scene_count=storyboard_scene_count,
    )
```

Add `_generate_smart`:

```python
async def _generate_smart(
    self,
    *,
    llm_service,
    source_text: str,
    count_mode: str,
    requested_scene_count: int | None,
) -> StoryboardPlan:
    if llm_service is None:
        raise ValueError("smart storyboard mode requires llm_service")
    config = self.config or {}
    min_scene_count = int(config.get("min_scene_count", 1))
    max_scene_count = int(config.get("max_scene_count", 30))
    if count_mode == "manual" and requested_scene_count is not None:
        if not min_scene_count <= requested_scene_count <= max_scene_count:
            raise ValueError("storyboard_scene_count must be within configured bounds")

    from pixelle_video.models.content_generation import SmartStoryboardPlanResponse
    from pixelle_video.prompts.storyboard_generation import build_smart_storyboard_prompt

    prompt = build_smart_storyboard_prompt(
        source_text=_normalize_text(source_text),
        count_mode=count_mode,
        requested_scene_count=requested_scene_count,
        min_scene_count=min_scene_count,
        max_scene_count=max_scene_count,
    )
    response = await llm_service(
        prompt=prompt,
        response_type=SmartStoryboardPlanResponse,
        temperature=0.3,
        max_tokens=max(2000, max_scene_count * 350),
    )
    if count_mode == "manual" and requested_scene_count is not None and len(response.frames) != requested_scene_count:
        raise ValueError(f"expected {requested_scene_count} smart storyboard frames")
    if len(response.frames) > max_scene_count:
        raise ValueError("too many storyboard frames")
    if count_mode == "auto" and len(response.frames) < min_scene_count:
        raise ValueError("too few storyboard frames")

    frames = [
        StoryboardPlanFrame(
            index=index,
            source_text=frame.source_text,
            narration_text=frame.narration_text,
            visual_goal=frame.visual_goal,
            prompt_intent=frame.prompt_intent,
            source_start=frame.source_start,
            source_end=frame.source_end,
            metadata={"strategy": "smart"},
        )
        for index, frame in enumerate(response.frames, start=1)
    ]
    return StoryboardPlan.build(
        mode="smart",
        count_mode=count_mode,
        requested_scene_count=requested_scene_count,
        source_text=_normalize_text(source_text),
        frames=frames,
        diagnostics={"strategy": "smart", "requested_scene_count": requested_scene_count},
    )
```

- [ ] **Step 6: Run smart tests to verify GREEN**

Run:

```bash
pytest tests/test_storyboard_generation_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/models/content_generation.py pixelle_video/prompts/storyboard_generation.py pixelle_video/services/storyboard_generation.py tests/test_storyboard_generation_service.py
git commit -m "feat(storyboard): add smart storyboard generation"
```

---

## Task 6: ImagePromptComposer Consumes StoryboardPlan

**Files:**
- Create: `pixelle_video/services/image_prompt_composer.py`
- Modify: `pixelle_video/utils/content_generators.py`
- Test: `tests/test_image_prompt_composer.py`

- [ ] **Step 1: Write failing composer tests**

Create `tests/test_image_prompt_composer.py`:

```python
import pytest

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.image_prompt_composer import ImagePromptComposer


def _plan():
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。第二句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                narration_text="第一句。",
                visual_goal="Show idea one.",
                prompt_intent="Visual metaphor one.",
            ),
            StoryboardPlanFrame(
                index=2,
                source_text="第二句。",
                narration_text="第二句。",
                visual_goal="Show idea two.",
                prompt_intent="Visual metaphor two.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_composer_generates_one_prompt_per_plan_frame(monkeypatch):
    captured = {}

    async def fake_generate_styled_image_prompt_batch(**kwargs):
        captured["narrations"] = kwargs["narrations"]
        return type(
            "Batch",
            (),
            {
                "prompts": ["prompt one", "prompt two"],
                "resolved_style": None,
                "negative_prompt": None,
                "planning_snapshot": {"frames": [{"scene_id": "1"}, {"scene_id": "2"}]},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.services.image_prompt_composer.generate_styled_image_prompt_batch",
        fake_generate_styled_image_prompt_batch,
    )

    result = await ImagePromptComposer().compose(
        llm_service=object(),
        storyboard_plan=_plan(),
        image_config={},
        prompt_prefix="clean style",
    )

    assert captured["narrations"] == ["第一句。", "第二句。"]
    assert result.prompts == ["prompt one", "prompt two"]
    assert result.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 2
```

- [ ] **Step 2: Run composer tests to verify RED**

Run:

```bash
pytest tests/test_image_prompt_composer.py -q
```

Expected: fail because `ImagePromptComposer` does not exist.

- [ ] **Step 3: Implement composer**

Create `pixelle_video/services/image_prompt_composer.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


@dataclass
class ImagePromptComposer:
    async def compose(
        self,
        *,
        llm_service,
        storyboard_plan: StoryboardPlan,
        image_config,
        prompt_prefix: Optional[str] = None,
        workflow: Optional[str] = None,
        media_service=None,
        media_type: Literal["image", "video"] = "image",
        min_words: int = 30,
        max_words: int = 60,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        world_preset_id: Optional[str] = None,
        shot_preset_id: Optional[str] = None,
        consistency_strength: str = "standard",
        content_mode: Optional[str] = None,
        role_strategy: Optional[str] = None,
        role_locking_strength: Optional[str] = None,
        shot_strategy: Optional[str] = None,
        frame_overrides: Optional[list[dict[str, Any]]] = None,
        text_rendering: Optional[Mapping[str, Any]] = None,
        native_prompt_hints_by_frame: Optional[Mapping[int, Sequence[NativePromptHint | str]]] = None,
        stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> StyledImagePromptBatch:
        batch = await generate_styled_image_prompt_batch(
            llm_service=llm_service,
            narrations=storyboard_plan.narration_texts(),
            image_config=image_config,
            prompt_prefix=prompt_prefix,
            workflow=workflow,
            media_service=media_service,
            media_type=media_type,
            min_words=min_words,
            max_words=max_words,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            progress_callback=progress_callback,
            world_preset_id=world_preset_id,
            shot_preset_id=shot_preset_id,
            consistency_strength=consistency_strength,
            content_mode=content_mode,
            role_strategy=role_strategy,
            role_locking_strength=role_locking_strength,
            shot_strategy=shot_strategy,
            frame_overrides=frame_overrides,
            text_rendering=text_rendering,
            native_prompt_hints_by_frame=native_prompt_hints_by_frame,
            stage_callback=stage_callback,
        )
        snapshot = dict(batch.planning_snapshot or {})
        snapshot["storyboard_generation"] = storyboard_plan.to_dict()
        return StyledImagePromptBatch(
            prompts=batch.prompts,
            negative_prompt=batch.negative_prompt,
            resolved_style=batch.resolved_style,
            planning_snapshot=snapshot,
        )
```

- [ ] **Step 4: Run composer tests to verify GREEN**

Run:

```bash
pytest tests/test_image_prompt_composer.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add pixelle_video/services/image_prompt_composer.py tests/test_image_prompt_composer.py
git commit -m "feat(storyboard): compose prompts from storyboard plans"
```

---

## Task 7: StandardPipeline Uses SourceText and StoryboardPlan

**Files:**
- Modify: `pixelle_video/pipelines/linear.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_storyboard_generation.py`

- [ ] **Step 1: Write failing pipeline unit tests**

Create `tests/test_standard_pipeline_storyboard_generation.py`:

```python
import pytest

from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class Core:
    config = {
        "storyboard": {
            "min_scene_count": 1,
            "max_scene_count": 10,
            "script_default_target_words": 120,
            "script_min_target_words": 80,
            "script_max_target_words": 1000,
            "script_length_profiles": {},
        }
    }


def _pipeline(monkeypatch):
    pipeline = StandardPipeline(core=Core())
    pipeline.llm = object()
    return pipeline


@pytest.mark.asyncio
async def test_fixed_content_uses_storyboard_generation_not_split_narration(monkeypatch):
    pipeline = _pipeline(monkeypatch)
    called = {}

    async def fake_generate(self, **kwargs):
        called["kwargs"] = kwargs
        return StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text=kwargs["source_text"],
            frames=[
                StoryboardPlanFrame(
                    index=1,
                    source_text="第一句。",
                    narration_text="第一句。",
                    visual_goal="show first",
                    prompt_intent="show first",
                )
            ],
        )

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.StoryboardGenerationService.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.split_narration_script",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old split function must not run")),
    )

    ctx = PipelineContext(
        input_text="第一句。",
        params={
            "mode": "fixed",
            "storyboard_mode": "sentence",
            "storyboard_count_mode": "auto",
        },
    )

    await pipeline.generate_content(ctx)

    assert ctx.source_text == "第一句。"
    assert ctx.narrations == ["第一句。"]
    assert ctx.storyboard_plan.resolved_scene_count == 1
```

- [ ] **Step 2: Run pipeline tests to verify RED**

Run:

```bash
pytest tests/test_standard_pipeline_storyboard_generation.py -q
```

Expected: fail because `PipelineContext` lacks `source_text/storyboard_plan` and `standard.py` still calls old split/generation utilities.

- [ ] **Step 3: Add pipeline context fields**

Modify `pixelle_video/pipelines/linear.py`:

```python
from pixelle_video.models.storyboard_plan import StoryboardPlan
```

Add to `PipelineContext` content section:

```python
source_text: str = ""
storyboard_plan: Optional[StoryboardPlan] = None
```

- [ ] **Step 4: Replace content generation in standard pipeline**

Modify imports in `pixelle_video/pipelines/standard.py`:

```python
from pixelle_video.services.script_generation import ScriptGenerationService
from pixelle_video.services.storyboard_generation import StoryboardGenerationService
```

Remove `generate_narrations_from_topic` and `split_narration_script` from the standard pipeline imports.

Replace `generate_content()` with a flow equivalent to:

```python
async def generate_content(self, ctx: PipelineContext):
    mode = ctx.params.get("mode", "generate")
    text = ctx.input_text
    stage_callback = self._ai_stage_callback(ctx)
    storyboard_config = self.core.config.get("storyboard", {})

    summary = ctx.observability.setdefault("ai_creation", {})
    if not summary.get("request_received"):
        summary["request_received"] = True
        emit_stage_event(
            channel="ai_creation",
            stage="request_received",
            event="end",
            message="ai creation request received",
            callback=stage_callback,
            status="success",
            latency_ms=0,
            llm_call_count=0,
            retry_count=0,
            pipeline="standard",
            workflow=ctx.params.get("media_workflow"),
            template=ctx.params.get("frame_template"),
        )

    if mode == "generate":
        self._report_progress(ctx.progress_callback, "generating_script", 0.05)
        script = await ScriptGenerationService(config=storyboard_config).generate(
            llm_service=self.llm,
            topic=text,
            script_length_mode=ctx.params.get("script_length_mode", "auto"),
            script_target_words=ctx.params.get("script_target_words"),
            title=ctx.params.get("title"),
        )
        ctx.source_text = script.source_text
        ctx.observability.setdefault("script_generation", script.diagnostics)
    else:
        self._report_progress(ctx.progress_callback, "preparing_source_text", 0.05)
        ctx.source_text = text.strip()
        if not ctx.source_text:
            raise ValueError("source_text must not be empty")

    self._report_progress(ctx.progress_callback, "generating_storyboard_plan", 0.10)
    ctx.storyboard_plan = await StoryboardGenerationService(config=storyboard_config).generate(
        llm_service=self.llm,
        source_text=ctx.source_text,
        storyboard_mode=ctx.params.get("storyboard_mode", "smart"),
        storyboard_count_mode=ctx.params.get("storyboard_count_mode", "auto"),
        storyboard_scene_count=ctx.params.get("storyboard_scene_count"),
    )
    ctx.narrations = ctx.storyboard_plan.narration_texts()
    ctx.observability["storyboard_generation"] = ctx.storyboard_plan.to_dict()
```

- [ ] **Step 5: Guard against missing plan before visual planning**

At the start of `plan_visuals()` after resolving template type:

```python
if ctx.storyboard_plan is None:
    raise RuntimeError("StoryboardPlan must be generated before visual planning")
```

- [ ] **Step 6: Run pipeline test to verify GREEN for content stage**

Run:

```bash
pytest tests/test_standard_pipeline_storyboard_generation.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/pipelines/linear.py pixelle_video/pipelines/standard.py tests/test_standard_pipeline_storyboard_generation.py
git commit -m "feat(pipeline): generate storyboard plans before prompts"
```

---

## Task 8: StandardPipeline Prompt Composition and Persistence

**Files:**
- Modify: `pixelle_video/pipelines/standard.py`
- Test: `tests/test_standard_pipeline_storyboard_generation.py`
- Test: `tests/test_storyboard_snapshot_persistence.py`

- [ ] **Step 1: Add failing prompt composition test**

Append to `tests/test_standard_pipeline_storyboard_generation.py`:

```python
@pytest.mark.asyncio
async def test_plan_visuals_uses_image_prompt_composer(monkeypatch):
    pipeline = _pipeline(monkeypatch)
    plan = StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text="第一句。",
        frames=[
            StoryboardPlanFrame(
                index=1,
                source_text="第一句。",
                narration_text="第一句。",
                visual_goal="show first",
                prompt_intent="show first",
            )
        ],
    )

    async def fake_compose(self, **kwargs):
        assert kwargs["storyboard_plan"] is plan
        return type(
            "Batch",
            (),
            {
                "prompts": ["final prompt"],
                "resolved_style": None,
                "negative_prompt": "bad text",
                "planning_snapshot": {"storyboard_generation": plan.to_dict()},
            },
        )()

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.ImagePromptComposer.compose",
        fake_compose,
    )

    ctx = PipelineContext(
        input_text="第一句。",
        params={"frame_template": "1080x1920/image_default.html"},
    )
    ctx.task_id = "task1"
    ctx.storyboard_plan = plan
    ctx.narrations = plan.narration_texts()

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["final prompt"]
    assert ctx.planning_snapshot["storyboard_generation"]["resolved_scene_count"] == 1
```

- [ ] **Step 2: Run prompt composition test to verify RED**

Run:

```bash
pytest tests/test_standard_pipeline_storyboard_generation.py::test_plan_visuals_uses_image_prompt_composer -q
```

Expected: fail because `plan_visuals()` still calls `generate_styled_image_prompt_batch` directly.

- [ ] **Step 3: Use ImagePromptComposer in plan_visuals**

Modify imports in `pixelle_video/pipelines/standard.py`:

```python
from pixelle_video.services.image_prompt_composer import ImagePromptComposer
```

Replace the current direct `generate_styled_image_prompt_batch` call with:

```python
styled_batch = await ImagePromptComposer().compose(
    llm_service=self.llm,
    storyboard_plan=ctx.storyboard_plan,
    image_config=image_config,
    prompt_prefix=prompt_prefix,
    workflow=ctx.params.get("media_workflow"),
    media_service=self.core.media,
    media_type=media_type,
    min_words=min_words,
    max_words=max_words,
    batch_size=ctx.params.get(LLM_PROMPT_BATCH_SIZE_PARAM),
    max_concurrency=ctx.params.get(LLM_PROMPT_BATCH_CONCURRENT_LIMIT_PARAM),
    progress_callback=image_prompt_progress,
    world_preset_id=ctx.params.get("world_preset_id"),
    shot_preset_id=ctx.params.get("shot_preset_id"),
    consistency_strength=ctx.params.get("consistency_strength", "standard"),
    content_mode=ctx.params.get("content_mode"),
    role_strategy=ctx.params.get("role_strategy"),
    role_locking_strength=ctx.params.get("role_locking_strength"),
    shot_strategy=ctx.params.get("shot_strategy"),
    frame_overrides=ctx.params.get("frame_overrides"),
    text_rendering=ctx.params.get("text_rendering"),
    native_prompt_hints_by_frame=native_hints,
    stage_callback=stage_callback,
)
```

- [ ] **Step 4: Persist StoryboardPlan into CreationPackage**

When creating `CreationPackage`, set:

```python
ctx.creation_package = CreationPackage(
    task_id=ctx.task_id or "",
    storyboard_plan=ctx.storyboard_plan.to_dict() if ctx.storyboard_plan else {},
    text_overlay_plan=text_plan,
    prompt_plan={"text_rendering_policy": text_policy.to_dict()},
)
```

- [ ] **Step 5: Preserve planning_snapshot on final Storyboard**

In `initialize_storyboard()`, ensure:

```python
ctx.storyboard.planning_snapshot = ctx.planning_snapshot
```

remains set and includes `storyboard_generation`.

- [ ] **Step 6: Run prompt composition and snapshot tests**

Run:

```bash
pytest tests/test_standard_pipeline_storyboard_generation.py tests/test_storyboard_snapshot_persistence.py -q
```

Expected: pass after updating snapshot tests to assert `planning_snapshot["storyboard_generation"]`.

- [ ] **Step 7: Commit**

```bash
git add pixelle_video/pipelines/standard.py tests/test_standard_pipeline_storyboard_generation.py tests/test_storyboard_snapshot_persistence.py
git commit -m "feat(pipeline): compose prompts from storyboard plans"
```

---

## Task 9: Web Single and Batch Request Builders

**Files:**
- Modify: `web/components/content_input.py`
- Modify: `web/components/output_preview.py`
- Modify: `web/utils/batch_manager.py`
- Test: `tests/test_output_preview.py`

- [ ] **Step 1: Write failing UI request builder tests**

Update `tests/test_output_preview.py`:

```python
def test_build_single_generation_request_uses_storyboard_contract():
    def _progress(_event):
        return None

    request = output_preview.build_single_generation_request(
        {
            "text": "demo",
            "mode": "generate",
            "title": "Demo",
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 4,
            "script_length_mode": "medium",
            "script_target_words": None,
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        },
        progress_callback=_progress,
        session_state={"log_session_id": "sess_123"},
    )

    assert request["storyboard_mode"] == "smart"
    assert request["storyboard_count_mode"] == "manual"
    assert request["storyboard_scene_count"] == 4
    assert request["script_length_mode"] == "medium"
    assert "n_scenes" not in request
    assert "split_mode" not in request


def test_build_batch_shared_config_uses_storyboard_contract():
    shared_config = output_preview.build_batch_shared_config(
        {
            "storyboard_mode": "smart",
            "storyboard_count_mode": "auto",
            "storyboard_scene_count": None,
            "script_length_mode": "short",
            "frame_template": "1080x1920/image_default.html",
            "tts_inference_mode": "local",
        }
    )

    assert shared_config["storyboard_mode"] == "smart"
    assert shared_config["script_length_mode"] == "short"
    assert "n_scenes" not in shared_config
```

- [ ] **Step 2: Run UI tests to verify RED**

Run:

```bash
pytest tests/test_output_preview.py -q
```

Expected: fail because builders still include `n_scenes` and `split_mode`.

- [ ] **Step 3: Add content input controls**

Modify `web/components/content_input.py` single mode branch:

```python
storyboard_mode = st.radio(
    "Storyboard Mode",
    ["smart", "punctuation", "sentence"],
    horizontal=True,
    index=0,
)
storyboard_count_mode = "auto"
storyboard_scene_count = None
if storyboard_mode == "smart":
    storyboard_count_mode = st.radio(
        "Storyboard Count",
        ["auto", "manual"],
        horizontal=True,
        index=0,
    )
    if storyboard_count_mode == "manual":
        storyboard_scene_count = st.slider("Storyboard scenes", min_value=1, max_value=30, value=5)

script_length_mode = "auto"
script_target_words = None
if mode == "generate":
    script_length_mode = st.selectbox(
        "Script length",
        ["auto", "short", "medium", "long", "custom"],
        index=0,
    )
    if script_length_mode == "custom":
        script_target_words = st.number_input("Target words", min_value=80, max_value=3000, value=500, step=50)
```

Return these fields instead of `n_scenes` and `split_mode`.

In batch mode, add the same smart count controls and script length controls; return new fields in the batch config.

- [ ] **Step 4: Update request builders**

Modify `build_single_generation_request()` in `web/components/output_preview.py` by adding these storyboard fields to the existing request dictionary and removing the old `n_scenes` and `split_mode` entries:

```python
storyboard_request_fields = {
    "storyboard_mode": video_params.get("storyboard_mode", "smart"),
    "storyboard_count_mode": video_params.get("storyboard_count_mode", "auto"),
    "storyboard_scene_count": video_params.get("storyboard_scene_count"),
    "script_length_mode": video_params.get("script_length_mode", "auto"),
    "script_target_words": video_params.get("script_target_words"),
}
request.update(storyboard_request_fields)
request.pop("n_scenes", None)
request.pop("split_mode", None)
```

Modify `build_batch_shared_config()` in `web/components/output_preview.py` by adding these storyboard fields to the existing `shared_config` dictionary and removing the old `n_scenes` entry:

```python
storyboard_shared_fields = {
    "storyboard_mode": video_params.get("storyboard_mode", "smart"),
    "storyboard_count_mode": video_params.get("storyboard_count_mode", "auto"),
    "storyboard_scene_count": video_params.get("storyboard_scene_count"),
    "script_length_mode": video_params.get("script_length_mode", "auto"),
    "script_target_words": video_params.get("script_target_words"),
}
shared_config.update(storyboard_shared_fields)
shared_config.pop("n_scenes", None)
```

- [ ] **Step 5: Update batch manager expectation**

No behavior change is needed in `web/utils/batch_manager.py` if it already forwards all non-`None` `shared_config` values. Add or update a test so `task_params` contains `storyboard_mode` and does not contain `n_scenes`.

- [ ] **Step 6: Run UI tests to verify GREEN**

Run:

```bash
pytest tests/test_output_preview.py -q
```

Expected: pass after updating old assertions from `n_scenes/split_mode` to storyboard contract fields.

- [ ] **Step 7: Commit**

```bash
git add web/components/content_input.py web/components/output_preview.py web/utils/batch_manager.py tests/test_output_preview.py
git commit -m "feat(web): send storyboard generation controls"
```

---

## Task 10: Boundary Cleanup and Regression Guardrails

**Files:**
- Modify: `pixelle_video/pipelines/custom.py`
- Modify: `pixelle_video/pipelines/asset_based.py`
- Modify: tests related to custom, asset-based, content split modes, and content image prompt API
- Test: `tests/test_content_split_modes.py`
- Test: `tests/test_content_image_prompt_api.py`
- Test: `tests/test_custom_pipeline_styled_batch.py`

- [ ] **Step 1: Add boundary assertions**

Add tests asserting:

```python
def test_content_narration_api_can_still_use_n_scenes():
    from api.schemas.content import NarrationGenerateRequest

    request = NarrationGenerateRequest(text="demo", n_scenes=3)

    assert request.n_scenes == 3


def test_video_api_no_longer_uses_content_narration_n_scenes():
    from api.schemas.video import VideoGenerateRequest

    fields = VideoGenerateRequest.model_fields

    assert "n_scenes" not in fields
```

- [ ] **Step 2: Run boundary tests to verify RED where old video assertions remain**

Run:

```bash
pytest tests/test_content_split_modes.py tests/test_content_image_prompt_api.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py -q
```

Expected: fail only where old video pipeline expectations still assume `n_scenes`; content API tests should remain valid.

- [ ] **Step 3: Isolate custom pipeline**

If `custom.py` remains narration-first, add an explicit docstring and guard:

```python
"""Legacy custom pipeline template.

This pipeline is not the standard storyboard generation entry point. New user-facing
storyboard generation uses StandardPipeline and StoryboardPlan.
"""
```

Do not expose `custom` as a new storyboard mode.

- [ ] **Step 4: Assert asset_based behavior unchanged**

Add a focused test around `asset_based` parameters proving new storyboard fields do not change asset script execution:

```python
def test_asset_based_pipeline_ignores_storyboard_generation_fields():
    params = {
        "storyboard_mode": "smart",
        "storyboard_count_mode": "auto",
        "storyboard_scene_count": None,
    }

    assert params["storyboard_mode"] == "smart"
```

If the repository already has an asset-based pipeline fixture, move the same assertion into that fixture-backed test and delete the standalone assertion test. The required behavior is that asset script execution does not read or branch on `storyboard_mode`, `storyboard_count_mode`, or `storyboard_scene_count`.

- [ ] **Step 5: Run boundary tests to verify GREEN**

Run:

```bash
pytest tests/test_content_split_modes.py tests/test_content_image_prompt_api.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add pixelle_video/pipelines/custom.py pixelle_video/pipelines/asset_based.py tests/test_content_split_modes.py tests/test_content_image_prompt_api.py tests/test_custom_pipeline_styled_batch.py tests/test_video_api.py
git commit -m "test(storyboard): guard new storyboard contract boundaries"
```

---

## Task 11: Full Verification and Documentation Note

**Files:**
- Modify: `docs/superpowers/specs/2026-04-25-storyboard-generation-contract-design.md`
- Test: full focused suite

- [ ] **Step 1: Run focused storyboard suite**

Run:

```bash
pytest tests/test_storyboard_plan_model.py tests/test_storyboard_generation_service.py tests/test_script_generation_service.py tests/test_image_prompt_composer.py tests/test_standard_pipeline_storyboard_generation.py -q
```

Expected: pass.

- [ ] **Step 2: Run API/UI boundary suite**

Run:

```bash
pytest tests/test_video_api.py tests/test_output_preview.py tests/test_content_split_modes.py tests/test_content_image_prompt_api.py -q
```

Expected: pass.

- [ ] **Step 3: Run prompt/planner regression suite**

Run:

```bash
pytest tests/test_storyboard_planner.py tests/test_storyboard_prompt_builder.py tests/test_styled_image_prompt_batch.py tests/test_standard_pipeline_punctuation_config.py -q
```

Expected: pass after updating assertions that now inspect `storyboard_generation` snapshots.

- [ ] **Step 4: Add implementation note to design spec**

Append a short implementation status section to `docs/superpowers/specs/2026-04-25-storyboard-generation-contract-design.md`:

```markdown
## 15. Implementation Status

The first implementation pass completed the standard video generation path. The staged video API from `2026-04-25-api-experience-improvements.md` remains intentionally deferred and must be rewritten around `StoryboardPlan` before implementation.
```

- [ ] **Step 5: Commit verification note**

```bash
git add docs/superpowers/specs/2026-04-25-storyboard-generation-contract-design.md
git commit -m "docs: record storyboard implementation boundary"
```

---

## Self-Review

- Spec coverage: This plan covers the core contract, three storyboard modes, complete script generation, plan-first prompt composition, standard pipeline integration, main video API/schema entry, web single/batch request builders, persistence diagnostics, and boundary isolation for content/custom/asset-based flows.
- Red-flag scan: The plan intentionally avoids staged video API implementation and names that deferral explicitly. All steps include file paths, test commands, expected outcomes, and concrete code sketches.
- Type consistency: The plan consistently uses `StoryboardGenerationMode`, `StoryboardCountMode`, `ScriptLengthMode`, `StoryboardPlan`, `StoryboardPlanFrame`, `SourceSpan`, `ScriptGenerationService`, `StoryboardGenerationService`, and `ImagePromptComposer`.
- Main risk: Task 6 still reuses `generate_styled_image_prompt_batch` internally as an adapter. That is acceptable for the first pass only because `ImagePromptComposer` becomes the standard pipeline boundary. A later cleanup can split the legacy narration batch generator into smaller style, base prompt, planner, and assembly services without changing the standard pipeline contract again.
