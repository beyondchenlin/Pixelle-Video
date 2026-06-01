from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from pixelle_video.models.visual_planning_mode import VisibleTextPolicy

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSONValue = JSONPrimitive | tuple["FrozenJSONValue", ...] | Mapping[str, "FrozenJSONValue"]


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
    def from_value(
        cls,
        value: Any,
        default: "ArticleUnderstandingLens | str | None" = None,
    ) -> "ArticleUnderstandingLens":
        fallback = _enum_from_value(default, cls, cls.THESIS_ARGUMENT) if default is not None else cls.THESIS_ARGUMENT
        return _enum_from_value(value, cls, fallback)


@dataclass(frozen=True)
class SourceEvidenceSpan:
    evidence_id: str
    source_id: str
    quote: str
    evidence_role: str
    frame_id: str | None = None
    start_char: int | None = None
    end_char: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_text("evidence_id", self.evidence_id))
        object.__setattr__(self, "source_id", _require_text("source_id", self.source_id))
        object.__setattr__(self, "quote", _require_text("quote", self.quote))
        object.__setattr__(self, "evidence_role", _require_text("evidence_role", self.evidence_role))
        object.__setattr__(self, "frame_id", _optional_text(self.frame_id))
        object.__setattr__(self, "start_char", _optional_offset("start_char", self.start_char))
        object.__setattr__(self, "end_char", _optional_offset("end_char", self.end_char))
        if self.start_char is not None and self.end_char is not None and self.start_char > self.end_char:
            raise ValueError("start_char must be less than or equal to end_char")

    def to_dict(self) -> dict[str, JSONValue]:
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
    evidence_span_ids: Sequence[str]
    importance: str
    visual_presence: str
    loss_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _require_text("subject_id", self.subject_id))
        object.__setattr__(self, "label", _require_text("label", self.label))
        object.__setattr__(self, "source_phrase", _require_text("source_phrase", self.source_phrase))
        object.__setattr__(
            self,
            "evidence_span_ids",
            _normalize_string_tuple(self.evidence_span_ids, "evidence_span_ids", require_non_empty=True),
        )
        object.__setattr__(self, "importance", _require_label_text("importance", self.importance))
        object.__setattr__(self, "visual_presence", _require_text("visual_presence", self.visual_presence))
        object.__setattr__(self, "loss_policy", _require_text("loss_policy", self.loss_policy))

    def to_dict(self) -> dict[str, JSONValue]:
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
    primary_lens: ArticleUnderstandingLens | str
    secondary_lenses: Sequence[ArticleUnderstandingLens | str] = ()
    lens_confidence: Mapping[Any, Any] = field(default_factory=dict)
    core_claim: str = ""
    central_problem: str = ""
    main_entities: Sequence[str] = ()
    required_subjects: Sequence[SubjectAnchor | Mapping[str, Any]] = ()
    lens_payloads: Mapping[Any, Any] = field(default_factory=dict)
    unsuitable_visual_modes: Sequence[Any] = ()
    source_evidence: Sequence[SourceEvidenceSpan | Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "article_id", _require_text("article_id", self.article_id))
        object.__setattr__(self, "primary_lens", _strict_lens_value(self.primary_lens, "primary_lens"))
        object.__setattr__(self, "secondary_lenses", _normalize_lens_tuple(self.secondary_lenses))
        object.__setattr__(self, "lens_confidence", _normalize_float_mapping(self.lens_confidence, "lens_confidence"))
        object.__setattr__(self, "core_claim", _optional_body_text(self.core_claim))
        object.__setattr__(self, "central_problem", _optional_body_text(self.central_problem))
        object.__setattr__(self, "main_entities", _normalize_string_tuple(self.main_entities, "main_entities"))
        object.__setattr__(self, "source_evidence", _normalize_evidence_spans(self.source_evidence))
        object.__setattr__(self, "required_subjects", _normalize_subject_anchors(self.required_subjects))
        _validate_subject_evidence_refs(self.required_subjects, self.source_evidence)
        object.__setattr__(self, "lens_payloads", _freeze_json_mapping(self.lens_payloads, "lens_payloads"))
        object.__setattr__(
            self,
            "unsuitable_visual_modes",
            _normalize_json_string_tuple(self.unsuitable_visual_modes, "unsuitable_visual_modes"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "article_id": self.article_id,
            "primary_lens": self.primary_lens.value,
            "secondary_lenses": [lens.value for lens in self.secondary_lenses],
            "lens_confidence": _thaw_json_value(self.lens_confidence),
            "core_claim": self.core_claim,
            "central_problem": self.central_problem,
            "main_entities": list(self.main_entities),
            "required_subjects": [subject.to_dict() for subject in self.required_subjects],
            "lens_payloads": _thaw_json_value(self.lens_payloads),
            "unsuitable_visual_modes": list(self.unsuitable_visual_modes),
            "source_evidence": [evidence.to_dict() for evidence in self.source_evidence],
        }


@dataclass(frozen=True)
class FrameUnderstandingPlan:
    frame_id: str
    source_text: str
    frame_claim: str
    frame_question: str
    primary_lens: ArticleUnderstandingLens | str
    secondary_lenses: Sequence[ArticleUnderstandingLens | str] = ()
    required_subjects: Sequence[SubjectAnchor | Mapping[str, Any]] = ()
    forbidden_subject_losses: Sequence[str] = ()
    visible_text_policy: VisibleTextPolicy | str = VisibleTextPolicy.NO_VISIBLE_TEXT
    source_evidence: Sequence[SourceEvidenceSpan | Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(self, "source_text", _require_text("source_text", self.source_text))
        object.__setattr__(self, "frame_claim", _require_text("frame_claim", self.frame_claim))
        object.__setattr__(self, "frame_question", _require_text("frame_question", self.frame_question))
        object.__setattr__(self, "primary_lens", _strict_lens_value(self.primary_lens, "primary_lens"))
        object.__setattr__(self, "secondary_lenses", _normalize_lens_tuple(self.secondary_lenses))
        object.__setattr__(self, "source_evidence", _normalize_evidence_spans(self.source_evidence))
        object.__setattr__(self, "required_subjects", _normalize_subject_anchors(self.required_subjects))
        _validate_subject_evidence_refs(self.required_subjects, self.source_evidence)
        object.__setattr__(
            self,
            "forbidden_subject_losses",
            _normalize_string_tuple(self.forbidden_subject_losses, "forbidden_subject_losses"),
        )
        object.__setattr__(self, "visible_text_policy", VisibleTextPolicy.from_value(self.visible_text_policy))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "source_text": self.source_text,
            "frame_claim": self.frame_claim,
            "frame_question": self.frame_question,
            "primary_lens": self.primary_lens.value,
            "secondary_lenses": [lens.value for lens in self.secondary_lenses],
            "required_subjects": [subject.to_dict() for subject in self.required_subjects],
            "forbidden_subject_losses": list(self.forbidden_subject_losses),
            "visible_text_policy": self.visible_text_policy.value,
            "source_evidence": [evidence.to_dict() for evidence in self.source_evidence],
        }


def _enum_from_value(value: Any, enum_cls: type[Enum], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if not text:
        return default
    for item in enum_cls:
        if text.lower() == str(item.value).lower() or text.lower() == item.name.lower():
            return item
    return default


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_offset(field_name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_body_text(value: Any) -> str:
    return str(value or "").strip()


def _require_label_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _strict_lens_value(value: Any, field_name: str) -> ArticleUnderstandingLens:
    if isinstance(value, ArticleUnderstandingLens):
        return value
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be a valid ArticleUnderstandingLens")
    for lens in ArticleUnderstandingLens:
        if text.lower() == lens.value.lower() or text.lower() == lens.name.lower():
            return lens
    raise ValueError(f"{field_name} must be a valid ArticleUnderstandingLens")


def _normalize_lens_tuple(values: Any) -> tuple[ArticleUnderstandingLens, ...]:
    return tuple(
        _strict_lens_value(value, "secondary_lenses")
        for value in _require_sequence(values, "secondary_lenses")
    )


def _normalize_string_tuple(
    values: Any,
    field_name: str,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(
        text
        for text in (_string_value(value) for value in _require_sequence(values, field_name))
        if text
    )
    if require_non_empty and not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_json_string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    return _normalize_string_tuple(values, field_name)


def _normalize_subject_anchors(values: Any) -> tuple[SubjectAnchor, ...]:
    subjects: list[SubjectAnchor] = []
    for value in _require_sequence(values, "required_subjects"):
        if isinstance(value, SubjectAnchor):
            subjects.append(value)
            continue
        if isinstance(value, Mapping):
            subjects.append(SubjectAnchor(**dict(value)))
            continue
        raise TypeError("required_subjects must contain SubjectAnchor values")
    return tuple(subjects)


def _normalize_evidence_spans(values: Any) -> tuple[SourceEvidenceSpan, ...]:
    evidence_spans: list[SourceEvidenceSpan] = []
    for value in _require_sequence(values, "source_evidence"):
        if isinstance(value, SourceEvidenceSpan):
            evidence_spans.append(value)
            continue
        if isinstance(value, Mapping):
            evidence_spans.append(SourceEvidenceSpan(**dict(value)))
            continue
        raise TypeError("source_evidence must contain SourceEvidenceSpan values")
    evidence_ids: set[str] = set()
    for evidence in evidence_spans:
        if evidence.evidence_id in evidence_ids:
            raise ValueError(f"source_evidence contains duplicate evidence_id: {evidence.evidence_id}")
        evidence_ids.add(evidence.evidence_id)
    return tuple(evidence_spans)


def _validate_subject_evidence_refs(
    subjects: Sequence[SubjectAnchor],
    evidence_spans: Sequence[SourceEvidenceSpan],
) -> None:
    evidence_ids = {evidence.evidence_id for evidence in evidence_spans}
    dangling: list[str] = []
    for subject in subjects:
        for evidence_span_id in subject.evidence_span_ids:
            if evidence_span_id not in evidence_ids:
                dangling.append(f"{subject.subject_id}:{evidence_span_id}")
    if dangling:
        raise ValueError(
            "required_subjects evidence_span_ids must reference source_evidence evidence_id values: "
            + ", ".join(dangling)
        )


def _require_sequence(values: Any, field_name: str) -> Sequence[Any]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    return values


def _freeze_json_mapping(value: Mapping[Any, Any] | None, field_name: str) -> Mapping[str, FrozenJSONValue]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return MappingProxyType({_json_string(key): _freeze_json_value(item) for key, item in value.items()})


def _normalize_float_mapping(value: Mapping[Any, Any] | None, field_name: str) -> Mapping[str, float]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return MappingProxyType({_json_string(key): _finite_float(item, field_name) for key, item in value.items()})


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} values must be finite numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} values must be finite numbers")
    return number


def _freeze_json_value(value: Any) -> FrozenJSONValue:
    if isinstance(value, Enum):
        return _json_string(value)
    if isinstance(value, Mapping):
        return MappingProxyType({_json_string(key): _freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON values must be finite")
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_json_value(item) for item in value)
    if hasattr(value, "to_dict"):
        return _freeze_json_value(value.to_dict())
    raise TypeError(f"Unsupported JSON value type: {type(value).__name__}")


def _thaw_json_value(value: Any) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw_json_value(item) for item in value]
    if isinstance(value, Enum):
        return _json_string(value)
    return value


def _json_string(value: Any) -> str:
    text = _string_value(value)
    if not text:
        raise ValueError("JSON object keys and string values must not be empty")
    return text


def _string_value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value).strip()


__all__ = [
    "ArticleUnderstandingLens",
    "ArticleUnderstandingMode",
    "ArticleUnderstandingPlan",
    "FrameUnderstandingPlan",
    "SourceEvidenceSpan",
    "SubjectAnchor",
]
