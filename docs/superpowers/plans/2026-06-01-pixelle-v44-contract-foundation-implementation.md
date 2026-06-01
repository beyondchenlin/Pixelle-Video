# Pixelle V4.4 Contract Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V4.4 contract foundation for article understanding, mode resolution, visual role strategy separation, versioned final prompt contract tracing, API pass-through, and prompt trace manifest without breaking existing V4.2 behavior.

**Architecture:** Phase 1 adds pure Python contracts and compatibility adapters first. Existing `FinalVisualPromptContract` v1 and visual role projectors remain valid; V4.4 trace fields are introduced through versioned dataclasses, metadata helpers, and manifest serializers. API fields default to `auto` and only become active when downstream phases consume them.

**Tech Stack:** Python dataclasses, `str` enums, Pydantic v2 request schemas, existing Pixelle prompt trace artifacts, pytest, ruff.

---

## Scope Guard

This plan implements only the V4.4 foundation layer from `docs/superpowers/specs/2026-06-01-pixelle-v44-article-understanding-mode-resolution-design.md`.

Included:

- New article understanding contracts.
- New visual planning mode and mode resolution contracts.
- Compatible extension of `pixelle_video.models.visual_role_strategy`.
- Versioned V4.4 final prompt contract adapter while keeping v1 intact.
- API/request pass-through for `article_understanding_mode`, `visual_planning_mode`, `visual_role_strategy`, `strict_user_mode`, and `force_v44_planning`.
- `prompt_traces/manifest.json` serializer.
- Focused contract and API tests.

Not included:

- LLM article understanding planner.
- VisualPlanningRouter and concrete visual planners.
- Full UI controls.
- Critic/repair implementation.
- Provider prompt behavior changes.

## File Structure

- Create: `pixelle_video/models/article_understanding.py`
  - Owns `ArticleUnderstandingMode`, `ArticleUnderstandingLens`, `SourceEvidenceSpan`, `SubjectAnchor`, `ArticleUnderstandingPlan`, and `FrameUnderstandingPlan`.

- Create: `pixelle_video/models/visual_planning_mode.py`
  - Owns `VisualPlanningMode`, `PrimaryVisualTask`, and `VisibleTextPolicy`.

- Create: `pixelle_video/models/mode_resolution.py`
  - Owns `ArticleVisualPlanningRequest`, `ArticleVisualPlanningPreflight`, `VisualPlanningRouteDecision`, and V4.2 fallback eligibility helper.

- Modify: `pixelle_video/models/visual_role_strategy.py`
  - Adds `VisualRoleStrategy` enum and context-aware role mode resolver while preserving `VisualRoleStrategyControls`.

- Modify: `pixelle_video/models/final_visual_prompt_contract.py`
  - Adds `ProjectedPromptPart`, `FinalVisualPromptContractV44`, and metadata adapter helper without changing the v1 dataclass constructor.

- Create: `pixelle_video/services/v44_prompt_trace_manifest.py`
  - Owns manifest payload construction and JSON writing.

- Modify: `pixelle_video/models/video_generation_contract.py`
  - Normalizes V4.4 request fields into standard generation params.

- Modify: `api/schemas/video.py`
  - Adds Pydantic request fields for V4.4 high-level controls.

- Modify: `api/routers/video.py`
  - Passes V4.4 fields into `video_params`.

- Tests:
  - Create: `tests/models/test_article_understanding.py`
  - Create: `tests/models/test_visual_planning_mode.py`
  - Create: `tests/models/test_mode_resolution.py`
  - Modify: `tests/models/test_visual_role_request.py`
  - Modify: `tests/models/test_final_visual_prompt_contract.py`
  - Create: `tests/services/test_v44_prompt_trace_manifest.py`
  - Modify: `tests/test_video_api.py`

## Execution Rules

- Use an isolated worktree or confirm the current branch is intended for implementation before executing.
- Each task follows RED -> GREEN -> commit.
- Commit messages must be Chinese and use repository prefixes.
- Do not use `git add --all`.
- Do not commit unrelated dirty worktree changes.

## Task 1: Article Understanding Contracts

**Files:**
- Create: `pixelle_video/models/article_understanding.py`
- Create: `tests/models/test_article_understanding.py`

- [ ] **Step 1: Write failing tests**

Create `tests/models/test_article_understanding.py`:

```python
import pytest

from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingMode,
    ArticleUnderstandingPlan,
    FrameUnderstandingPlan,
    SourceEvidenceSpan,
    SubjectAnchor,
)
from pixelle_video.models.visual_planning_mode import VisibleTextPolicy, VisualPlanningMode


def test_article_understanding_mode_normalizes_invalid_values_to_auto():
    assert ArticleUnderstandingMode.from_value("cognitive_state") is ArticleUnderstandingMode.COGNITIVE_STATE
    assert ArticleUnderstandingMode.from_value("missing") is ArticleUnderstandingMode.AUTO
    assert ArticleUnderstandingMode.from_value(None) is ArticleUnderstandingMode.AUTO


def test_subject_anchor_requires_evidence_span_ids_for_traceability():
    anchor = SubjectAnchor(
        subject_id="subject_loop",
        label="重复路径",
        source_phrase="总是在同样的地方绕回来",
        evidence_span_ids=("evidence_001",),
        importance="critical",
        visual_presence="must_be_visible",
        loss_policy="fail",
    )

    assert anchor.to_dict()["evidence_span_ids"] == ["evidence_001"]

    with pytest.raises(ValueError, match="evidence_span_ids"):
        SubjectAnchor(
            subject_id="subject_without_trace",
            label="主体",
            source_phrase="主体",
            evidence_span_ids=(),
            importance="critical",
            visual_presence="must_be_visible",
            loss_policy="fail",
        )


def test_article_understanding_plan_serializes_lens_keys_as_strings():
    evidence = SourceEvidenceSpan(
        evidence_id="evidence_001",
        source_id="article_001",
        frame_id=None,
        start_char=0,
        end_char=4,
        quote="重复路径",
        evidence_role="required_subject",
    )
    anchor = SubjectAnchor(
        subject_id="subject_loop",
        label="重复路径",
        source_phrase="重复路径",
        evidence_span_ids=("evidence_001",),
        importance="critical",
        visual_presence="must_be_visible",
        loss_policy="fail",
    )

    plan = ArticleUnderstandingPlan(
        article_id="article_001",
        primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE,
        secondary_lenses=(ArticleUnderstandingLens.CONTRAST_CONFLICT,),
        lens_confidence={"cognitive_state": 0.91},
        core_claim="人会重复困境",
        central_problem="知道绕圈但回到原点",
        main_entities=("重复路径",),
        required_subjects=(anchor,),
        lens_payloads={"cognitive_state": {"stuck_loop": "重复路径"}},
        unsuitable_visual_modes=(VisualPlanningMode.RELATIONSHIP_MAP,),
        source_evidence=(evidence,),
    )

    payload = plan.to_dict()

    assert payload["primary_lens"] == "cognitive_state"
    assert payload["lens_confidence"] == {"cognitive_state": 0.91}
    assert payload["lens_payloads"]["cognitive_state"]["stuck_loop"] == "重复路径"
    assert payload["required_subjects"][0]["evidence_span_ids"] == ["evidence_001"]


def test_frame_understanding_plan_defaults_to_no_visible_text_policy():
    evidence = SourceEvidenceSpan(
        evidence_id="evidence_002",
        source_id="article_001",
        frame_id="frame_001",
        start_char=0,
        end_char=2,
        quote="困境",
        evidence_role="emotion_or_cognitive_state",
    )
    anchor = SubjectAnchor(
        subject_id="subject_problem",
        label="困境",
        source_phrase="困境",
        evidence_span_ids=("evidence_002",),
        importance="important",
        visual_presence="may_be_symbolic",
        loss_policy="repair",
    )

    plan = FrameUnderstandingPlan(
        frame_id="frame_001",
        source_text="困境重复出现。",
        frame_claim="困境在重复",
        frame_question=None,
        primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE,
        secondary_lenses=(),
        required_subjects=(anchor,),
        forbidden_subject_losses=("subject_problem",),
        source_evidence=(evidence,),
    )

    assert plan.visible_text_policy is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert plan.to_dict()["visible_text_policy"] == "no_visible_text"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/models/test_article_understanding.py
```

Expected: FAIL because `pixelle_video.models.article_understanding` does not exist.

- [ ] **Step 3: Implement article understanding contracts**

Create `pixelle_video/models/article_understanding.py` with these definitions and helper methods:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.visual_planning_mode import VisibleTextPolicy, VisualPlanningMode


class ArticleUnderstandingMode(str, Enum):
    AUTO = "auto"
    THESIS_ARGUMENT = "thesis_argument"
    CAUSAL_MECHANISM = "causal_mechanism"
    COGNITIVE_STATE = "cognitive_state"
    PROCESS_METHOD = "process_method"
    RELATIONSHIP_STRUCTURE = "relationship_structure"
    CONTRAST_CONFLICT = "contrast_conflict"
    NARRATIVE_EVENT = "narrative_event"
    METAPHOR_SYMBOLIC = "metaphor_symbolic"

    @classmethod
    def from_value(cls, value: Any) -> "ArticleUnderstandingMode":
        return _enum_from_value(value, cls, cls.AUTO)


class ArticleUnderstandingLens(str, Enum):
    THESIS_ARGUMENT = "thesis_argument"
    CAUSAL_MECHANISM = "causal_mechanism"
    COGNITIVE_STATE = "cognitive_state"
    PROCESS_METHOD = "process_method"
    RELATIONSHIP_STRUCTURE = "relationship_structure"
    CONTRAST_CONFLICT = "contrast_conflict"
    NARRATIVE_EVENT = "narrative_event"
    METAPHOR_SYMBOLIC = "metaphor_symbolic"

    @classmethod
    def from_value(cls, value: Any, default: "ArticleUnderstandingLens" | None = None) -> "ArticleUnderstandingLens":
        return _enum_from_value(value, cls, default or cls.THESIS_ARGUMENT)


@dataclass(frozen=True)
class SourceEvidenceSpan:
    evidence_id: str
    source_id: str
    frame_id: str | None
    start_char: int | None
    end_char: int | None
    quote: str
    evidence_role: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _required_text("evidence_id", self.evidence_id))
        object.__setattr__(self, "source_id", _required_text("source_id", self.source_id))
        object.__setattr__(self, "frame_id", _optional_text(self.frame_id))
        object.__setattr__(self, "quote", _required_text("quote", self.quote))
        object.__setattr__(self, "evidence_role", _required_text("evidence_role", self.evidence_role))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "frame_id": self.frame_id,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "quote": self.quote,
            "evidence_role": self.evidence_role,
        }


@dataclass(frozen=True)
class SubjectAnchor:
    subject_id: str
    label: str
    source_phrase: str
    evidence_span_ids: tuple[str, ...]
    importance: str
    visual_presence: str
    loss_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _required_text("subject_id", self.subject_id))
        object.__setattr__(self, "label", _required_text("label", self.label))
        object.__setattr__(self, "source_phrase", _required_text("source_phrase", self.source_phrase))
        evidence_ids = _text_tuple("evidence_span_ids", self.evidence_span_ids)
        if not evidence_ids:
            raise ValueError("evidence_span_ids must not be empty")
        object.__setattr__(self, "evidence_span_ids", evidence_ids)
        object.__setattr__(self, "importance", _required_text("importance", self.importance))
        object.__setattr__(self, "visual_presence", _required_text("visual_presence", self.visual_presence))
        object.__setattr__(self, "loss_policy", _required_text("loss_policy", self.loss_policy))

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "label": self.label,
            "source_phrase": self.source_phrase,
            "evidence_span_ids": list(self.evidence_span_ids),
            "importance": self.importance,
            "visual_presence": self.visual_presence,
            "loss_policy": self.loss_policy,
        }


@dataclass(frozen=True)
class ArticleUnderstandingPlan:
    article_id: str
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...] = ()
    lens_confidence: Mapping[str, float] = field(default_factory=dict)
    core_claim: str = ""
    central_problem: str = ""
    main_entities: tuple[str, ...] = ()
    required_subjects: tuple[SubjectAnchor, ...] = ()
    lens_payloads: Mapping[str, Any] = field(default_factory=dict)
    unsuitable_visual_modes: tuple[VisualPlanningMode, ...] = ()
    source_evidence: tuple[SourceEvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "article_id", _required_text("article_id", self.article_id))
        object.__setattr__(self, "primary_lens", ArticleUnderstandingLens.from_value(self.primary_lens))
        object.__setattr__(
            self,
            "secondary_lenses",
            tuple(ArticleUnderstandingLens.from_value(value) for value in self.secondary_lenses),
        )
        object.__setattr__(self, "lens_confidence", _string_key_float_mapping(self.lens_confidence))
        object.__setattr__(self, "main_entities", _text_tuple("main_entities", self.main_entities))
        object.__setattr__(self, "required_subjects", tuple(self.required_subjects))
        object.__setattr__(self, "lens_payloads", dict(self.lens_payloads or {}))
        object.__setattr__(
            self,
            "unsuitable_visual_modes",
            tuple(VisualPlanningMode.from_value(value) for value in self.unsuitable_visual_modes),
        )
        object.__setattr__(self, "source_evidence", tuple(self.source_evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "primary_lens": self.primary_lens.value,
            "secondary_lenses": [lens.value for lens in self.secondary_lenses],
            "lens_confidence": dict(self.lens_confidence),
            "core_claim": self.core_claim,
            "central_problem": self.central_problem,
            "main_entities": list(self.main_entities),
            "required_subjects": [anchor.to_dict() for anchor in self.required_subjects],
            "lens_payloads": dict(self.lens_payloads),
            "unsuitable_visual_modes": [mode.value for mode in self.unsuitable_visual_modes],
            "source_evidence": [span.to_dict() for span in self.source_evidence],
        }


@dataclass(frozen=True)
class FrameUnderstandingPlan:
    frame_id: str
    source_text: str
    frame_claim: str
    frame_question: str | None
    primary_lens: ArticleUnderstandingLens
    secondary_lenses: tuple[ArticleUnderstandingLens, ...] = ()
    required_subjects: tuple[SubjectAnchor, ...] = ()
    forbidden_subject_losses: tuple[str, ...] = ()
    visible_text_policy: VisibleTextPolicy = VisibleTextPolicy.NO_VISIBLE_TEXT
    source_evidence: tuple[SourceEvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _required_text("frame_id", self.frame_id))
        object.__setattr__(self, "source_text", _required_text("source_text", self.source_text))
        object.__setattr__(self, "frame_claim", _required_text("frame_claim", self.frame_claim))
        object.__setattr__(self, "frame_question", _optional_text(self.frame_question))
        object.__setattr__(self, "primary_lens", ArticleUnderstandingLens.from_value(self.primary_lens))
        object.__setattr__(self, "secondary_lenses", tuple(ArticleUnderstandingLens.from_value(value) for value in self.secondary_lenses))
        object.__setattr__(self, "required_subjects", tuple(self.required_subjects))
        object.__setattr__(self, "forbidden_subject_losses", _text_tuple("forbidden_subject_losses", self.forbidden_subject_losses))
        object.__setattr__(self, "visible_text_policy", VisibleTextPolicy.from_value(self.visible_text_policy))
        object.__setattr__(self, "source_evidence", tuple(self.source_evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "source_text": self.source_text,
            "frame_claim": self.frame_claim,
            "frame_question": self.frame_question,
            "primary_lens": self.primary_lens.value,
            "secondary_lenses": [lens.value for lens in self.secondary_lenses],
            "required_subjects": [anchor.to_dict() for anchor in self.required_subjects],
            "forbidden_subject_losses": list(self.forbidden_subject_losses),
            "visible_text_policy": self.visible_text_policy.value,
            "source_evidence": [span.to_dict() for span in self.source_evidence],
        }


def _enum_from_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    return default


def _required_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_tuple(field_name: str, values: Sequence[Any]) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    result = tuple(str(value).strip() for value in values if str(value).strip())
    if any(not isinstance(value, str) for value in result):
        raise ValueError(f"{field_name} must contain strings")
    return result


def _string_key_float_mapping(values: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in dict(values or {}).items():
        text_key = str(key).strip()
        if text_key:
            result[text_key] = float(value)
    return result


__all__ = [
    "ArticleUnderstandingLens",
    "ArticleUnderstandingMode",
    "ArticleUnderstandingPlan",
    "FrameUnderstandingPlan",
    "SourceEvidenceSpan",
    "SubjectAnchor",
]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/models/test_article_understanding.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- pixelle_video/models/article_understanding.py tests/models/test_article_understanding.py
git commit -m "feat: 新增V4.4文章理解契约"
git push origin $(git branch --show-current)
```

## Task 2: Visual Planning Mode and Mode Resolution Contracts

**Files:**
- Create: `pixelle_video/models/visual_planning_mode.py`
- Create: `pixelle_video/models/mode_resolution.py`
- Create: `tests/models/test_visual_planning_mode.py`
- Create: `tests/models/test_mode_resolution.py`

- [ ] **Step 1: Write failing visual planning tests**

Create `tests/models/test_visual_planning_mode.py`:

```python
from pixelle_video.models.visual_planning_mode import (
    PrimaryVisualTask,
    VisibleTextPolicy,
    VisualPlanningMode,
)


def test_visual_planning_mode_rejects_visual_role_terms_by_falling_back_to_auto():
    assert VisualPlanningMode.from_value("cognitive_illustration") is VisualPlanningMode.COGNITIVE_ILLUSTRATION
    assert VisualPlanningMode.from_value("host_explainer") is VisualPlanningMode.AUTO
    assert VisualPlanningMode.from_value("signature_presence") is VisualPlanningMode.AUTO


def test_visible_text_policy_defaults_to_no_visible_text():
    assert VisibleTextPolicy.from_value(None) is VisibleTextPolicy.NO_VISIBLE_TEXT
    assert VisibleTextPolicy.from_value("source_text_only") is VisibleTextPolicy.SOURCE_TEXT_ONLY
    assert VisibleTextPolicy.from_value("free_text") is VisibleTextPolicy.NO_VISIBLE_TEXT


def test_primary_visual_task_normalizes_known_values():
    assert PrimaryVisualTask.from_value("cognitive_explanation") is PrimaryVisualTask.COGNITIVE_EXPLANATION
    assert PrimaryVisualTask.from_value("missing") is PrimaryVisualTask.SCENE_RECONSTRUCTION
```

Create `tests/models/test_mode_resolution.py`:

```python
from pixelle_video.models.article_understanding import ArticleUnderstandingLens, ArticleUnderstandingMode
from pixelle_video.models.mode_resolution import (
    ArticleVisualPlanningPreflight,
    ArticleVisualPlanningRequest,
    VisualPlanningRouteDecision,
    should_use_v42_compatibility_path,
)
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisualPlanningMode
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


def test_article_visual_planning_request_normalizes_invalid_values():
    request = ArticleVisualPlanningRequest.from_mapping(
        {
            "article_understanding_mode": "unknown",
            "visual_planning_mode": "host_explainer",
            "visual_role_strategy": "observer_guide",
            "strict_user_mode": True,
        }
    )

    assert request.article_understanding_mode is ArticleUnderstandingMode.AUTO
    assert request.visual_planning_mode is VisualPlanningMode.AUTO
    assert request.visual_role_strategy is VisualRoleStrategy.OBSERVER_GUIDE
    assert request.strict_user_mode is True


def test_preflight_records_explicit_fields_and_legacy_candidate():
    request = ArticleVisualPlanningRequest.from_mapping(
        {
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "visual_role_strategy": "auto",
        }
    )
    preflight = ArticleVisualPlanningPreflight.from_request(
        request,
        explicit_fields=("visual_planning_mode",),
        legacy_fallback_candidate=True,
    )

    payload = preflight.to_dict()

    assert payload["preflight_id"].startswith("preflight_")
    assert payload["explicit_fields"] == ["visual_planning_mode"]
    assert payload["legacy_fallback_candidate"] is True


def test_route_decision_contains_trace_id_status_and_fallback_target():
    decision = VisualPlanningRouteDecision(
        route_decision_id="route_frame_001_v44_001",
        frame_id="frame_001",
        preflight_id="preflight_001",
        requested_article_mode=ArticleUnderstandingMode.AUTO,
        requested_visual_mode=VisualPlanningMode.AUTO,
        requested_visual_role_strategy=VisualRoleStrategy.AUTO,
        resolved_primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE,
        resolved_secondary_lenses=(),
        resolved_visual_planning_mode=VisualPlanningMode.COGNITIVE_ILLUSTRATION,
        resolved_visual_role_strategy=VisualRoleStrategy.OBSERVER_GUIDE,
        primary_visual_task=PrimaryVisualTask.COGNITIVE_EXPLANATION,
        secondary_visual_tasks=(),
        confidence=0.41,
        decision_reason="low confidence article context",
        resolution_status="low_confidence",
        fallback_eligible=True,
        fallback_used=False,
        fallback_target="v4.2_visual_role_path",
        fallback_reason="auto modes with insufficient article context",
        mismatch_warnings=("low confidence",),
    )

    payload = decision.to_dict()

    assert payload["route_decision_id"] == "route_frame_001_v44_001"
    assert payload["resolution_status"] == "low_confidence"
    assert payload["fallback_target"] == "v4.2_visual_role_path"


def test_v42_compatibility_allows_fallback_from_low_confidence_route_decision():
    request = ArticleVisualPlanningRequest()
    preflight = ArticleVisualPlanningPreflight.from_request(
        request,
        explicit_fields=(),
        legacy_fallback_candidate=True,
    )
    decision = VisualPlanningRouteDecision(
        route_decision_id="route_frame_001_v44_001",
        frame_id="frame_001",
        preflight_id=preflight.preflight_id,
        requested_article_mode=ArticleUnderstandingMode.AUTO,
        requested_visual_mode=VisualPlanningMode.AUTO,
        requested_visual_role_strategy=VisualRoleStrategy.AUTO,
        resolved_primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE,
        resolved_secondary_lenses=(),
        resolved_visual_planning_mode=VisualPlanningMode.SCENE_INTEGRATION,
        resolved_visual_role_strategy=VisualRoleStrategy.SIGNATURE_PRESENCE,
        primary_visual_task=PrimaryVisualTask.SCENE_RECONSTRUCTION,
        secondary_visual_tasks=(),
        confidence=0.33,
        decision_reason="planner failed",
        resolution_status="planner_failed",
        fallback_eligible=True,
        fallback_used=False,
        fallback_target="v4.2_visual_role_path",
        fallback_reason="planner failed before V4.4 concretization",
        mismatch_warnings=(),
    )

    assert should_use_v42_compatibility_path(
        preflight=preflight,
        route_decisions=(decision,),
        article_context_insufficient=True,
        legacy_visual_role_request_present=True,
    )
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/models/test_visual_planning_mode.py tests/models/test_mode_resolution.py
```

Expected: FAIL because the V4.4 modules do not exist yet.

- [ ] **Step 3: Implement `visual_planning_mode.py`**

Create `pixelle_video/models/visual_planning_mode.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any


class VisualPlanningMode(str, Enum):
    AUTO = "auto"
    SCENE_INTEGRATION = "scene_integration"
    COGNITIVE_ILLUSTRATION = "cognitive_illustration"
    STRUCTURAL_EXPLAINER = "structural_explainer"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAP = "relationship_map"

    @classmethod
    def from_value(cls, value: Any) -> "VisualPlanningMode":
        return _enum_from_value(value, cls, cls.AUTO)


class PrimaryVisualTask(str, Enum):
    SCENE_RECONSTRUCTION = "scene_reconstruction"
    COGNITIVE_EXPLANATION = "cognitive_explanation"
    STRUCTURE_EXPLANATION = "structure_explanation"
    PROCESS_WALKTHROUGH = "process_walkthrough"
    CONTRAST_ARGUMENT = "contrast_argument"
    RELATIONSHIP_MAPPING = "relationship_mapping"

    @classmethod
    def from_value(cls, value: Any) -> "PrimaryVisualTask":
        return _enum_from_value(value, cls, cls.SCENE_RECONSTRUCTION)


class VisibleTextPolicy(str, Enum):
    NO_VISIBLE_TEXT = "no_visible_text"
    SOURCE_TEXT_ONLY = "source_text_only"
    SYMBOLIC_LABELS_ONLY = "symbolic_labels_only"
    APPROVED_LABELS_ONLY = "approved_labels_only"

    @classmethod
    def from_value(cls, value: Any) -> "VisibleTextPolicy":
        return _enum_from_value(value, cls, cls.NO_VISIBLE_TEXT)


def _enum_from_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text == item.value or text.lower() == item.name.lower():
            return item
    return default


__all__ = [
    "PrimaryVisualTask",
    "VisibleTextPolicy",
    "VisualPlanningMode",
]
```

- [ ] **Step 4: Implement `mode_resolution.py`**

Create `pixelle_video/models/mode_resolution.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.article_understanding import ArticleUnderstandingLens, ArticleUnderstandingMode
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisualPlanningMode
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


@dataclass(frozen=True)
class ArticleVisualPlanningRequest:
    article_understanding_mode: ArticleUnderstandingMode = ArticleUnderstandingMode.AUTO
    visual_planning_mode: VisualPlanningMode = VisualPlanningMode.AUTO
    visual_role_strategy: VisualRoleStrategy = VisualRoleStrategy.AUTO
    user_intent_hint: str | None = None
    allow_mixed_lenses: bool = True
    strict_user_mode: bool = False
    force_v44_planning: bool = False

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None) -> "ArticleVisualPlanningRequest":
        mapping = dict(source or {})
        return cls(
            article_understanding_mode=ArticleUnderstandingMode.from_value(mapping.get("article_understanding_mode")),
            visual_planning_mode=VisualPlanningMode.from_value(mapping.get("visual_planning_mode")),
            visual_role_strategy=VisualRoleStrategy.from_value(mapping.get("visual_role_strategy")),
            user_intent_hint=_optional_text(mapping.get("user_intent_hint")),
            allow_mixed_lenses=bool(mapping.get("allow_mixed_lenses", True)),
            strict_user_mode=bool(mapping.get("strict_user_mode", False)),
            force_v44_planning=bool(mapping.get("force_v44_planning", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_understanding_mode": self.article_understanding_mode.value,
            "visual_planning_mode": self.visual_planning_mode.value,
            "visual_role_strategy": self.visual_role_strategy.value,
            "user_intent_hint": self.user_intent_hint,
            "allow_mixed_lenses": self.allow_mixed_lenses,
            "strict_user_mode": self.strict_user_mode,
            "force_v44_planning": self.force_v44_planning,
        }


@dataclass(frozen=True)
class ArticleVisualPlanningPreflight:
    preflight_id: str
    requested: ArticleVisualPlanningRequest
    normalized_article_mode: ArticleUnderstandingMode
    normalized_visual_mode: VisualPlanningMode
    normalized_visual_role_strategy: VisualRoleStrategy
    strict_user_mode: bool
    force_v44_planning: bool
    explicit_fields: tuple[str, ...]
    legacy_fallback_candidate: bool
    validation_warnings: tuple[str, ...] = ()

    @classmethod
    def from_request(
        cls,
        requested: ArticleVisualPlanningRequest,
        *,
        explicit_fields: Sequence[str],
        legacy_fallback_candidate: bool,
        validation_warnings: Sequence[str] = (),
    ) -> "ArticleVisualPlanningPreflight":
        return cls(
            preflight_id="preflight_v44_001",
            requested=requested,
            normalized_article_mode=requested.article_understanding_mode,
            normalized_visual_mode=requested.visual_planning_mode,
            normalized_visual_role_strategy=requested.visual_role_strategy,
            strict_user_mode=requested.strict_user_mode,
            force_v44_planning=requested.force_v44_planning,
            explicit_fields=tuple(str(field).strip() for field in explicit_fields if str(field).strip()),
            legacy_fallback_candidate=legacy_fallback_candidate,
            validation_warnings=tuple(str(warning).strip() for warning in validation_warnings if str(warning).strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "preflight_id": self.preflight_id,
            "requested": self.requested.to_dict(),
            "normalized_article_mode": self.normalized_article_mode.value,
            "normalized_visual_mode": self.normalized_visual_mode.value,
            "normalized_visual_role_strategy": self.normalized_visual_role_strategy.value,
            "strict_user_mode": self.strict_user_mode,
            "force_v44_planning": self.force_v44_planning,
            "explicit_fields": list(self.explicit_fields),
            "legacy_fallback_candidate": self.legacy_fallback_candidate,
            "validation_warnings": list(self.validation_warnings),
        }


@dataclass(frozen=True)
class VisualPlanningRouteDecision:
    route_decision_id: str
    frame_id: str
    preflight_id: str
    requested_article_mode: ArticleUnderstandingMode
    requested_visual_mode: VisualPlanningMode
    requested_visual_role_strategy: VisualRoleStrategy
    resolved_primary_lens: ArticleUnderstandingLens
    resolved_secondary_lenses: tuple[ArticleUnderstandingLens, ...]
    resolved_visual_planning_mode: VisualPlanningMode
    resolved_visual_role_strategy: VisualRoleStrategy
    primary_visual_task: PrimaryVisualTask
    secondary_visual_tasks: tuple[PrimaryVisualTask, ...]
    confidence: float
    decision_reason: str
    resolution_status: str
    fallback_eligible: bool
    fallback_used: bool
    fallback_target: str | None
    fallback_reason: str | None
    mismatch_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_decision_id", _required_text("route_decision_id", self.route_decision_id))
        object.__setattr__(self, "frame_id", _required_text("frame_id", self.frame_id))
        object.__setattr__(self, "preflight_id", _required_text("preflight_id", self.preflight_id))
        object.__setattr__(self, "requested_article_mode", ArticleUnderstandingMode.from_value(self.requested_article_mode))
        object.__setattr__(self, "requested_visual_mode", VisualPlanningMode.from_value(self.requested_visual_mode))
        object.__setattr__(self, "requested_visual_role_strategy", VisualRoleStrategy.from_value(self.requested_visual_role_strategy))
        object.__setattr__(self, "resolved_primary_lens", ArticleUnderstandingLens.from_value(self.resolved_primary_lens))
        object.__setattr__(self, "resolved_secondary_lenses", tuple(ArticleUnderstandingLens.from_value(value) for value in self.resolved_secondary_lenses))
        object.__setattr__(self, "resolved_visual_planning_mode", VisualPlanningMode.from_value(self.resolved_visual_planning_mode))
        object.__setattr__(self, "resolved_visual_role_strategy", VisualRoleStrategy.from_value(self.resolved_visual_role_strategy))
        object.__setattr__(self, "primary_visual_task", PrimaryVisualTask.from_value(self.primary_visual_task))
        object.__setattr__(self, "secondary_visual_tasks", tuple(PrimaryVisualTask.from_value(value) for value in self.secondary_visual_tasks))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "decision_reason", _required_text("decision_reason", self.decision_reason))
        object.__setattr__(self, "resolution_status", _required_text("resolution_status", self.resolution_status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_decision_id": self.route_decision_id,
            "frame_id": self.frame_id,
            "preflight_id": self.preflight_id,
            "requested_article_mode": self.requested_article_mode.value,
            "requested_visual_mode": self.requested_visual_mode.value,
            "requested_visual_role_strategy": self.requested_visual_role_strategy.value,
            "resolved_primary_lens": self.resolved_primary_lens.value,
            "resolved_secondary_lenses": [lens.value for lens in self.resolved_secondary_lenses],
            "resolved_visual_planning_mode": self.resolved_visual_planning_mode.value,
            "resolved_visual_role_strategy": self.resolved_visual_role_strategy.value,
            "primary_visual_task": self.primary_visual_task.value,
            "secondary_visual_tasks": [task.value for task in self.secondary_visual_tasks],
            "confidence": self.confidence,
            "decision_reason": self.decision_reason,
            "resolution_status": self.resolution_status,
            "fallback_eligible": self.fallback_eligible,
            "fallback_used": self.fallback_used,
            "fallback_target": self.fallback_target,
            "fallback_reason": self.fallback_reason,
            "mismatch_warnings": list(self.mismatch_warnings),
        }


def should_use_v42_compatibility_path(
    *,
    preflight: ArticleVisualPlanningPreflight,
    route_decisions: Sequence[VisualPlanningRouteDecision],
    article_context_insufficient: bool,
    legacy_visual_role_request_present: bool,
) -> bool:
    route_allows_v42_fallback = not route_decisions or any(
        decision.fallback_eligible and decision.fallback_target == "v4.2_visual_role_path"
        for decision in route_decisions
    )
    return (
        preflight.requested.article_understanding_mode is ArticleUnderstandingMode.AUTO
        and preflight.requested.visual_planning_mode is VisualPlanningMode.AUTO
        and preflight.requested.visual_role_strategy is VisualRoleStrategy.AUTO
        and not preflight.requested.force_v44_planning
        and article_context_insufficient
        and legacy_visual_role_request_present
        and route_allows_v42_fallback
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(field_name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


__all__ = [
    "ArticleVisualPlanningPreflight",
    "ArticleVisualPlanningRequest",
    "VisualPlanningRouteDecision",
    "should_use_v42_compatibility_path",
]
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/models/test_visual_planning_mode.py tests/models/test_mode_resolution.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add -- pixelle_video/models/visual_planning_mode.py pixelle_video/models/mode_resolution.py tests/models/test_visual_planning_mode.py tests/models/test_mode_resolution.py
git commit -m "feat: 新增V4.4模式解析契约"
git push origin $(git branch --show-current)
```

## Task 3: Compatible Visual Role Strategy Extension

**Files:**
- Modify: `pixelle_video/models/visual_role_strategy.py`
- Modify: `tests/models/test_visual_role_request.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/models/test_visual_role_request.py`:

```python
from pixelle_video.models.visual_role_strategy import (
    VisualConsistencyMode,
    VisualRoleMode,
    VisualRoleStrategy,
    resolve_effective_role_mode_with_v44_context,
)


def test_visual_role_strategy_normalizes_new_v44_values():
    assert VisualRoleStrategy.from_value("host_explainer") is VisualRoleStrategy.HOST_EXPLAINER
    assert VisualRoleStrategy.from_value("observer_guide") is VisualRoleStrategy.OBSERVER_GUIDE
    assert VisualRoleStrategy.from_value("bad") is VisualRoleStrategy.AUTO


def test_observer_guide_downgrades_subject_replacement_without_subject_permission():
    result = resolve_effective_role_mode_with_v44_context(
        requested_role_mode=VisualRoleMode.SUBJECT_REPLACEMENT,
        consistency_mode=VisualConsistencyMode.PRIMARY_CHARACTER,
        visual_role_strategy=VisualRoleStrategy.OBSERVER_GUIDE,
        subject_replacement_allowed=False,
    )

    assert result == VisualRoleMode.SUPPORTING_INTEGRATION


def test_primary_character_can_replace_only_when_subject_replacement_allowed():
    result = resolve_effective_role_mode_with_v44_context(
        requested_role_mode=VisualRoleMode.AUTO,
        consistency_mode=VisualConsistencyMode.PRIMARY_CHARACTER,
        visual_role_strategy=VisualRoleStrategy.PARTICIPANT,
        subject_replacement_allowed=True,
    )

    assert result == VisualRoleMode.SUBJECT_REPLACEMENT
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/models/test_visual_role_request.py
```

Expected: FAIL because `VisualRoleStrategy` and the resolver do not exist.

- [ ] **Step 3: Extend visual role strategy module**

Modify `pixelle_video/models/visual_role_strategy.py` by adding this enum and helper while keeping existing `VisualRoleStrategyControls` behavior unchanged:

```python
class VisualRoleStrategy(str, Enum):
    AUTO = "auto"
    HOST_EXPLAINER = "host_explainer"
    SIGNATURE_PRESENCE = "signature_presence"
    OBSERVER_GUIDE = "observer_guide"
    PARTICIPANT = "participant"
    BACKGROUND_SIGNATURE = "background_signature"

    @classmethod
    def from_value(cls, value: Any) -> "VisualRoleStrategy":
        return _enum_value(value, cls, cls.AUTO)


def resolve_effective_role_mode_with_v44_context(
    *,
    requested_role_mode: VisualRoleMode,
    consistency_mode: VisualConsistencyMode,
    visual_role_strategy: VisualRoleStrategy,
    subject_replacement_allowed: bool,
) -> VisualRoleMode:
    role_mode = VisualRoleMode(requested_role_mode)
    strategy = VisualRoleStrategy.from_value(visual_role_strategy)
    consistency = VisualConsistencyMode(consistency_mode)

    if strategy in {
        VisualRoleStrategy.SIGNATURE_PRESENCE,
        VisualRoleStrategy.OBSERVER_GUIDE,
        VisualRoleStrategy.BACKGROUND_SIGNATURE,
    }:
        if role_mode is VisualRoleMode.SUBJECT_REPLACEMENT or consistency is VisualConsistencyMode.PRIMARY_CHARACTER:
            return VisualRoleMode.SUPPORTING_INTEGRATION

    if subject_replacement_allowed:
        if role_mode is VisualRoleMode.SUBJECT_REPLACEMENT:
            return VisualRoleMode.SUBJECT_REPLACEMENT
        if consistency is VisualConsistencyMode.PRIMARY_CHARACTER and strategy is VisualRoleStrategy.PARTICIPANT:
            return VisualRoleMode.SUBJECT_REPLACEMENT

    if consistency is VisualConsistencyMode.SUPPORTING_CHARACTER:
        return VisualRoleMode.SUPPORTING_INTEGRATION

    return role_mode
```

Update `__all__` to include:

```python
"VisualRoleStrategy",
"resolve_effective_role_mode_with_v44_context",
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/models/test_visual_role_request.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- pixelle_video/models/visual_role_strategy.py tests/models/test_visual_role_request.py
git commit -m "feat: 扩展V4.4视觉角色策略契约"
git push origin $(git branch --show-current)
```

## Task 4: Versioned Final Prompt Contract Adapter

**Files:**
- Modify: `pixelle_video/models/final_visual_prompt_contract.py`
- Modify: `tests/models/test_final_visual_prompt_contract.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/models/test_final_visual_prompt_contract.py`:

```python
from pixelle_video.models.final_visual_prompt_contract import (
    FinalVisualPromptContract,
    FinalVisualPromptContractV44,
    ProjectedPromptPart,
    attach_v44_contract_metadata,
)
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisibleTextPolicy
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy


def test_existing_v1_final_visual_prompt_contract_constructor_still_works():
    contract = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
    )

    assert contract.version == "final_visual_prompt_contract.v1"
    assert contract.to_dict()["scene"] == "scene"


def test_v44_contract_serializes_trace_fields_and_projected_parts():
    part = ProjectedPromptPart(
        part_id="part_primary_task",
        priority=10,
        source_plan_type="visual_concretization_plan",
        source_field="primary_visual_task",
        content="cognitive explanation",
        locked=True,
        critic_check_required=True,
    )
    contract = FinalVisualPromptContractV44(
        contract_id="contract_frame_001_v44_001",
        frame_id="frame_001",
        primary_visual_task=PrimaryVisualTask.COGNITIVE_EXPLANATION,
        article_anchor="人会重复困境",
        required_subjects=("重复路径",),
        visual_concretization_summary="迷宫中的重复路径",
        identity_contract=None,
        visual_role_strategy=VisualRoleStrategy.OBSERVER_GUIDE,
        weight_contract=None,
        visible_text_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
        projected_prompt_parts=(part,),
        negative_semantics=("no random text",),
        route_decision_id="route_frame_001_v44_001",
    )

    payload = contract.to_dict()

    assert payload["contract_schema_version"] == "final_visual_prompt_contract.v4_4"
    assert payload["route_decision_id"] == "route_frame_001_v44_001"
    assert payload["projected_prompt_parts"][0]["part_id"] == "part_primary_task"


def test_v44_metadata_can_be_attached_to_existing_v1_contract():
    v1 = FinalVisualPromptContract(
        scene="scene",
        composition="composition",
        style_assignment="style",
        character_layer_style="character",
        world_layer_style="world",
        integration_priority="priority",
    )
    v44 = FinalVisualPromptContractV44(
        contract_id="contract_frame_001_v44_001",
        frame_id="frame_001",
        primary_visual_task=PrimaryVisualTask.SCENE_RECONSTRUCTION,
        article_anchor="scene",
        required_subjects=("source subject",),
        visual_concretization_summary="scene summary",
        identity_contract=None,
        visual_role_strategy=VisualRoleStrategy.SIGNATURE_PRESENCE,
        weight_contract=None,
        visible_text_policy=VisibleTextPolicy.NO_VISIBLE_TEXT,
        projected_prompt_parts=(),
        negative_semantics=(),
        route_decision_id="route_frame_001_v44_001",
    )

    upgraded = attach_v44_contract_metadata(v1, v44)

    assert upgraded.metadata["v44_contract"]["route_decision_id"] == "route_frame_001_v44_001"
    assert upgraded.scene == "scene"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/models/test_final_visual_prompt_contract.py
```

Expected: FAIL because V4.4 classes do not exist.

- [ ] **Step 3: Add V4.4 contract classes without changing v1**

Modify `pixelle_video/models/final_visual_prompt_contract.py` by adding these classes after `RenderedMediaPrompt`:

```python
@dataclass(frozen=True)
class ProjectedPromptPart:
    part_id: str
    priority: int
    source_plan_type: str
    source_field: str
    content: str
    locked: bool
    critic_check_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "part_id", _require_non_empty("part_id", self.part_id))
        object.__setattr__(self, "source_plan_type", _require_non_empty("source_plan_type", self.source_plan_type))
        object.__setattr__(self, "source_field", _require_non_empty("source_field", self.source_field))
        object.__setattr__(self, "content", _require_non_empty("content", self.content))

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_id": self.part_id,
            "priority": self.priority,
            "source_plan_type": self.source_plan_type,
            "source_field": self.source_field,
            "content": self.content,
            "locked": self.locked,
            "critic_check_required": self.critic_check_required,
        }


@dataclass(frozen=True)
class FinalVisualPromptContractV44:
    contract_id: str
    frame_id: str
    primary_visual_task: Any
    article_anchor: str
    required_subjects: tuple[Any, ...]
    visual_concretization_summary: str
    identity_contract: Any
    visual_role_strategy: Any
    weight_contract: Any
    visible_text_policy: Any
    projected_prompt_parts: tuple[ProjectedPromptPart, ...]
    negative_semantics: tuple[str, ...]
    route_decision_id: str
    contract_schema_version: str = "final_visual_prompt_contract.v4_4"

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _require_non_empty("contract_id", self.contract_id))
        object.__setattr__(self, "frame_id", _require_non_empty("frame_id", self.frame_id))
        object.__setattr__(self, "article_anchor", _require_non_empty("article_anchor", self.article_anchor))
        object.__setattr__(self, "visual_concretization_summary", _require_non_empty("visual_concretization_summary", self.visual_concretization_summary))
        object.__setattr__(self, "projected_prompt_parts", tuple(self.projected_prompt_parts or ()))
        object.__setattr__(self, "negative_semantics", _normalize_rule_tuple(self.negative_semantics or ()))
        object.__setattr__(self, "route_decision_id", _require_non_empty("route_decision_id", self.route_decision_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_schema_version": self.contract_schema_version,
            "contract_id": self.contract_id,
            "frame_id": self.frame_id,
            "primary_visual_task": _enum_or_value(self.primary_visual_task),
            "article_anchor": self.article_anchor,
            "required_subjects": [_serializable_value(item) for item in self.required_subjects],
            "visual_concretization_summary": self.visual_concretization_summary,
            "identity_contract": _serializable_value(self.identity_contract),
            "visual_role_strategy": _enum_or_value(self.visual_role_strategy),
            "weight_contract": _serializable_value(self.weight_contract),
            "visible_text_policy": _enum_or_value(self.visible_text_policy),
            "projected_prompt_parts": [part.to_dict() for part in self.projected_prompt_parts],
            "negative_semantics": list(self.negative_semantics),
            "route_decision_id": self.route_decision_id,
        }
```

Add helpers:

```python
def attach_v44_contract_metadata(
    contract: FinalVisualPromptContract,
    v44_contract: FinalVisualPromptContractV44,
) -> FinalVisualPromptContract:
    metadata = dict(contract.metadata or {})
    metadata["v44_contract"] = v44_contract.to_dict()
    return replace(contract, metadata=metadata)


def _enum_or_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _serializable_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return _enum_or_value(value)
```

Update `__all__` to include:

```python
"ProjectedPromptPart",
"FinalVisualPromptContractV44",
"attach_v44_contract_metadata",
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/models/test_final_visual_prompt_contract.py tests/services/test_final_visual_prompt_contract_builder.py tests/services/test_visual_role_projector_and_service_v4.py tests/services/test_provider_prompt_projector.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- pixelle_video/models/final_visual_prompt_contract.py tests/models/test_final_visual_prompt_contract.py
git commit -m "feat: 增加V4.4最终提示词合约适配器"
git push origin $(git branch --show-current)
```

## Task 5: API and Generation Parameter Pass-Through

**Files:**
- Modify: `pixelle_video/models/video_generation_contract.py`
- Modify: `api/schemas/video.py`
- Modify: `api/routers/video.py`
- Modify: `tests/test_video_api.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_video_api.py`:

```python
def test_video_generate_request_accepts_v44_planning_controls():
    request = VideoGenerateRequest(
        text="demo",
        article_understanding_mode="cognitive_state",
        visual_planning_mode="cognitive_illustration",
        visual_role_strategy="observer_guide",
        strict_user_mode=True,
        force_v44_planning=True,
    )

    assert request.article_understanding_mode == "cognitive_state"
    assert request.visual_planning_mode == "cognitive_illustration"
    assert request.visual_role_strategy == "observer_guide"
    assert request.strict_user_mode is True
    assert request.force_v44_planning is True


def test_build_video_generation_params_copies_v44_planning_controls():
    params = build_video_generation_params(
        VideoGenerateRequest(
            text="demo",
            article_understanding_mode="cognitive_state",
            visual_planning_mode="cognitive_illustration",
            visual_role_strategy="observer_guide",
            strict_user_mode=True,
            force_v44_planning=True,
        ),
        request_id="req_v44",
    )

    assert params["article_understanding_mode"] == "cognitive_state"
    assert params["visual_planning_mode"] == "cognitive_illustration"
    assert params["visual_role_strategy"] == "observer_guide"
    assert params["strict_user_mode"] is True
    assert params["force_v44_planning"] is True


def test_normalize_standard_video_generation_params_preserves_v44_defaults():
    params = normalize_standard_video_generation_params({"text": "demo"})

    assert params["article_understanding_mode"] == "auto"
    assert params["visual_planning_mode"] == "auto"
    assert params["visual_role_strategy"] == "auto"
    assert params["strict_user_mode"] is False
    assert params["force_v44_planning"] is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_video_api.py
```

Expected: FAIL because request fields are not in the schemas and normalization.

- [ ] **Step 3: Add API schema fields**

Modify `api/schemas/video.py` in `VideoGenerateRequest`:

```python
    article_understanding_mode: Literal[
        "auto",
        "thesis_argument",
        "causal_mechanism",
        "cognitive_state",
        "process_method",
        "relationship_structure",
        "contrast_conflict",
        "narrative_event",
        "metaphor_symbolic",
    ] = Field("auto", description="V4.4 article understanding mode.")
    visual_planning_mode: Literal[
        "auto",
        "scene_integration",
        "cognitive_illustration",
        "structural_explainer",
        "process_walkthrough",
        "contrast_argument",
        "relationship_map",
    ] = Field("auto", description="V4.4 visual concretization mode.")
    visual_role_strategy: Literal[
        "auto",
        "host_explainer",
        "signature_presence",
        "observer_guide",
        "participant",
        "background_signature",
    ] = Field("auto", description="V4.4 visual role participation strategy.")
    strict_user_mode: bool = Field(False, description="Respect explicit V4.4 mode choices when possible.")
    force_v44_planning: bool = Field(False, description="Force V4.4 structured planning path.")
```

Modify `api/routers/video.py` in `build_video_generation_params()`:

```python
        "article_understanding_mode": request_body.article_understanding_mode,
        "visual_planning_mode": request_body.visual_planning_mode,
        "visual_role_strategy": request_body.visual_role_strategy,
        "strict_user_mode": request_body.strict_user_mode,
        "force_v44_planning": request_body.force_v44_planning,
```

- [ ] **Step 4: Add normalization defaults**

Modify `pixelle_video/models/video_generation_contract.py` in `normalize_standard_video_generation_params()` before returning:

```python
    normalized["article_understanding_mode"] = normalized.get("article_understanding_mode") or "auto"
    normalized["visual_planning_mode"] = normalized.get("visual_planning_mode") or "auto"
    normalized["visual_role_strategy"] = normalized.get("visual_role_strategy") or "auto"
    normalized["strict_user_mode"] = bool(normalized.get("strict_user_mode", False))
    normalized["force_v44_planning"] = bool(normalized.get("force_v44_planning", False))
```

Extend `validate_standard_video_generation_params()`:

```python
    ArticleVisualPlanningRequest.from_mapping(params)
```

Add import:

```python
from pixelle_video.models.mode_resolution import ArticleVisualPlanningRequest
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_video_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add -- api/schemas/video.py api/routers/video.py pixelle_video/models/video_generation_contract.py tests/test_video_api.py
git commit -m "feat: 透传V4.4文章理解与视觉路由参数"
git push origin $(git branch --show-current)
```

## Task 6: Prompt Trace Manifest Serializer

**Files:**
- Create: `pixelle_video/services/v44_prompt_trace_manifest.py`
- Create: `tests/services/test_v44_prompt_trace_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Create `tests/services/test_v44_prompt_trace_manifest.py`:

```python
import json

from pixelle_video.models.article_understanding import ArticleUnderstandingLens, ArticleUnderstandingMode
from pixelle_video.models.mode_resolution import VisualPlanningRouteDecision
from pixelle_video.models.visual_planning_mode import PrimaryVisualTask, VisualPlanningMode
from pixelle_video.models.visual_role_strategy import VisualRoleStrategy
from pixelle_video.services.v44_prompt_trace_manifest import (
    build_v44_prompt_trace_manifest,
    write_v44_prompt_trace_manifest,
)


def _decision(frame_id: str) -> VisualPlanningRouteDecision:
    return VisualPlanningRouteDecision(
        route_decision_id=f"route_{frame_id}_v44_001",
        frame_id=frame_id,
        preflight_id="preflight_v44_001",
        requested_article_mode=ArticleUnderstandingMode.AUTO,
        requested_visual_mode=VisualPlanningMode.AUTO,
        requested_visual_role_strategy=VisualRoleStrategy.AUTO,
        resolved_primary_lens=ArticleUnderstandingLens.COGNITIVE_STATE,
        resolved_secondary_lenses=(),
        resolved_visual_planning_mode=VisualPlanningMode.COGNITIVE_ILLUSTRATION,
        resolved_visual_role_strategy=VisualRoleStrategy.OBSERVER_GUIDE,
        primary_visual_task=PrimaryVisualTask.COGNITIVE_EXPLANATION,
        secondary_visual_tasks=(),
        confidence=0.88,
        decision_reason="cognitive state lens matched",
        resolution_status="resolved",
        fallback_eligible=False,
        fallback_used=False,
        fallback_target=None,
        fallback_reason=None,
        mismatch_warnings=(),
    )


def test_manifest_records_route_decision_ids_and_modes():
    manifest = build_v44_prompt_trace_manifest(
        article_id="article_001",
        frame_ids=("frame_001", "frame_002"),
        requested_modes={
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "visual_role_strategy": "auto",
        },
        route_decisions=(_decision("frame_001"), _decision("frame_002")),
        critic_status="not_run",
        repair_rounds=0,
    )

    assert manifest["schema_version"] == "v4.4"
    assert manifest["route_decision_ids"]["frame_001"] == "route_frame_001_v44_001"
    assert manifest["resolved_modes"]["visual_planning_mode"] == "cognitive_illustration"


def test_manifest_writer_creates_prompt_traces_manifest_json(tmp_path):
    output_path = write_v44_prompt_trace_manifest(
        tmp_path,
        article_id="article_001",
        frame_ids=("frame_001",),
        requested_modes={
            "article_understanding_mode": "auto",
            "visual_planning_mode": "auto",
            "visual_role_strategy": "auto",
        },
        route_decisions=(_decision("frame_001"),),
        critic_status="not_run",
        repair_rounds=0,
    )

    assert output_path == tmp_path / "prompt_traces" / "manifest.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["route_decision_ids"]["frame_001"] == "route_frame_001_v44_001"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/services/test_v44_prompt_trace_manifest.py
```

Expected: FAIL because the manifest service does not exist.

- [ ] **Step 3: Implement manifest service**

Create `pixelle_video/services/v44_prompt_trace_manifest.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pixelle_video.models.mode_resolution import VisualPlanningRouteDecision


def build_v44_prompt_trace_manifest(
    *,
    article_id: str,
    frame_ids: Sequence[str],
    requested_modes: Mapping[str, Any],
    route_decisions: Sequence[VisualPlanningRouteDecision],
    critic_status: str,
    repair_rounds: int,
) -> dict[str, Any]:
    decisions = tuple(route_decisions)
    route_decision_ids = {
        decision.frame_id: decision.route_decision_id
        for decision in decisions
    }
    first_decision = decisions[0] if decisions else None
    fallbacks = [
        {
            "frame_id": decision.frame_id,
            "fallback_target": decision.fallback_target,
            "fallback_reason": decision.fallback_reason,
        }
        for decision in decisions
        if decision.fallback_used or decision.fallback_target
    ]
    return {
        "schema_version": "v4.4",
        "article_id": str(article_id).strip(),
        "frames": [str(frame_id).strip() for frame_id in frame_ids if str(frame_id).strip()],
        "requested_modes": dict(requested_modes),
        "resolved_modes": {
            "primary_lens": first_decision.resolved_primary_lens.value if first_decision else None,
            "visual_planning_mode": first_decision.resolved_visual_planning_mode.value if first_decision else None,
            "visual_role_strategy": first_decision.resolved_visual_role_strategy.value if first_decision else None,
        },
        "route_decision_ids": route_decision_ids,
        "fallbacks": fallbacks,
        "critic_status": str(critic_status).strip(),
        "repair_rounds": int(repair_rounds),
    }


def write_v44_prompt_trace_manifest(
    task_dir: str | Path,
    *,
    article_id: str,
    frame_ids: Sequence[str],
    requested_modes: Mapping[str, Any],
    route_decisions: Sequence[VisualPlanningRouteDecision],
    critic_status: str,
    repair_rounds: int,
) -> Path:
    root = Path(task_dir)
    output_path = root / "prompt_traces" / "manifest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_v44_prompt_trace_manifest(
        article_id=article_id,
        frame_ids=frame_ids,
        requested_modes=requested_modes,
        route_decisions=route_decisions,
        critic_status=critic_status,
        repair_rounds=repair_rounds,
    )
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


__all__ = [
    "build_v44_prompt_trace_manifest",
    "write_v44_prompt_trace_manifest",
]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/services/test_v44_prompt_trace_manifest.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- pixelle_video/services/v44_prompt_trace_manifest.py tests/services/test_v44_prompt_trace_manifest.py
git commit -m "feat: 增加V4.4提示词追踪manifest"
git push origin $(git branch --show-current)
```

## Task 7: Contract Foundation Verification

**Files:**
- No new planned files

- [ ] **Step 1: Run targeted contract tests**

Run:

```powershell
python -m pytest -q tests/models/test_article_understanding.py tests/models/test_visual_planning_mode.py tests/models/test_mode_resolution.py tests/models/test_visual_role_request.py tests/models/test_final_visual_prompt_contract.py tests/services/test_v44_prompt_trace_manifest.py tests/test_video_api.py
```

Expected: PASS.

- [ ] **Step 2: Run existing projector compatibility tests**

Run:

```powershell
python -m pytest -q tests/services/test_final_visual_prompt_contract_builder.py tests/services/test_visual_role_projector_and_service_v4.py tests/services/test_provider_prompt_projector.py tests/services/test_model_prompt_renderer.py
```

Expected: PASS. This proves the v1 final prompt contract path still works.

- [ ] **Step 3: Run formatting checks**

Run:

```powershell
ruff check pixelle_video api tests
git diff --check
```

Expected: both commands exit with code 0.

- [ ] **Step 4: Inspect working tree**

Run:

```powershell
git status --short
```

Expected: no unstaged changes from this plan. If the repository has unrelated pre-existing changes, do not touch or stage them.

- [ ] **Step 5: Stop on verification failure**

If any command in Steps 1-3 fails, stop execution and return to the task that introduced the failing behavior. Do not create a generic verification-fix commit from this step; the fix must be made in the specific task section that owns the broken file.

## Acceptance Criteria

- Article understanding contracts serialize with string lens keys.
- `SubjectAnchor` requires `evidence_span_ids`.
- `VisualPlanningRouteDecision` always has `route_decision_id`, `resolution_status`, and fallback trace fields.
- V4.2 fallback helper allows low-confidence route decisions to trigger visible fallback.
- `VisualRoleStrategy` is distinct from `VisualRoleStrategyControls`.
- Existing v1 `FinalVisualPromptContract` constructor and projectors continue to pass tests.
- V4.4 contract adapter can attach metadata to v1 contracts.
- API request and generation params carry V4.4 controls with safe defaults.
- `prompt_traces/manifest.json` can be generated with frame-to-route mappings.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-01-pixelle-v44-contract-foundation-implementation.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using `superpowers:executing-plans`, with checkpoints after each task.
