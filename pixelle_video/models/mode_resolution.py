from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pixelle_video.models.article_concretization import (
    ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS,
    ArticleConcretizationRequest,
)
from pixelle_video.models.article_understanding import (
    ArticleUnderstandingLens,
    ArticleUnderstandingMode,
)
from pixelle_video.models.series_visual_signature_strategy import SeriesVisualSignatureStrategy
from pixelle_video.models.visual_planning_mode import (
    PrimaryVisualTask,
    VisualPlanningMode,
)

JSONPrimitive = str | int | float | bool | None
JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
ARTICLE_CONCRETIZATION_FLAT_REQUEST_KEYS = ARTICLE_CONCRETIZATION_FLAT_OPTION_KEYS

_ALLOWED_RESOLUTION_STATUSES = frozenset(
    {"resolved", "low_confidence", "planner_failed", "fallback_used"}
)


@dataclass(frozen=True)
class ArticleVisualPlanningRequest:
    article_understanding_mode: ArticleUnderstandingMode | str = ArticleUnderstandingMode.AUTO
    visual_planning_mode: VisualPlanningMode | str = VisualPlanningMode.AUTO
    series_visual_signature_strategy: SeriesVisualSignatureStrategy | str = SeriesVisualSignatureStrategy.AUTO
    user_intent_hint: str | None = None
    allow_mixed_lenses: bool = True
    strict_user_mode: bool = False
    force_v44_planning: bool = False
    article_concretization: ArticleConcretizationRequest = field(
        default_factory=ArticleConcretizationRequest
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "article_understanding_mode",
            _strict_enum_value(
                self.article_understanding_mode,
                ArticleUnderstandingMode,
                "article_understanding_mode",
            ),
        )
        object.__setattr__(
            self,
            "visual_planning_mode",
            _strict_enum_value(
                self.visual_planning_mode,
                VisualPlanningMode,
                "visual_planning_mode",
            ),
        )
        object.__setattr__(
            self,
            "series_visual_signature_strategy",
            _strict_enum_value(
                self.series_visual_signature_strategy,
                SeriesVisualSignatureStrategy,
                "series_visual_signature_strategy",
            ),
        )
        object.__setattr__(self, "user_intent_hint", _optional_text(self.user_intent_hint))
        object.__setattr__(
            self,
            "allow_mixed_lenses",
            _bool_value(self.allow_mixed_lenses, "allow_mixed_lenses"),
        )
        object.__setattr__(
            self,
            "strict_user_mode",
            _bool_value(self.strict_user_mode, "strict_user_mode"),
        )
        object.__setattr__(
            self,
            "force_v44_planning",
            _bool_value(self.force_v44_planning, "force_v44_planning"),
        )
        object.__setattr__(
            self,
            "article_concretization",
            _article_concretization_request_value(self.article_concretization),
        )

    @classmethod
    def from_mapping(
        cls,
        source: Mapping[str, Any] | None,
    ) -> "ArticleVisualPlanningRequest":
        source = dict(source or {})
        return cls(
            article_understanding_mode=source.get(
                "article_understanding_mode",
                ArticleUnderstandingMode.AUTO,
            ),
            visual_planning_mode=source.get("visual_planning_mode", VisualPlanningMode.AUTO),
            series_visual_signature_strategy=source.get("series_visual_signature_strategy", SeriesVisualSignatureStrategy.AUTO),
            user_intent_hint=source.get("user_intent_hint"),
            allow_mixed_lenses=source.get("allow_mixed_lenses", True),
            strict_user_mode=source.get("strict_user_mode", False),
            force_v44_planning=source.get("force_v44_planning", False),
            article_concretization=ArticleConcretizationRequest.from_mapping(
                _article_concretization_source(source)
            ),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "article_understanding_mode": self.article_understanding_mode.value,
            "visual_planning_mode": self.visual_planning_mode.value,
            "series_visual_signature_strategy": self.series_visual_signature_strategy.value,
            "user_intent_hint": self.user_intent_hint,
            "allow_mixed_lenses": self.allow_mixed_lenses,
            "strict_user_mode": self.strict_user_mode,
            "force_v44_planning": self.force_v44_planning,
            "article_concretization": self.article_concretization.to_dict(),
        }


@dataclass(frozen=True)
class ArticleVisualPlanningPreflight:
    preflight_id: str
    requested: ArticleVisualPlanningRequest
    normalized_article_mode: ArticleUnderstandingMode | str
    normalized_visual_mode: VisualPlanningMode | str
    normalized_series_visual_signature_strategy: SeriesVisualSignatureStrategy | str
    strict_user_mode: bool
    force_v44_planning: bool
    explicit_fields: Sequence[str]
    legacy_fallback_candidate: bool
    validation_warnings: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "preflight_id", _require_text("preflight_id", self.preflight_id))
        object.__setattr__(self, "requested", _request_value(self.requested))
        object.__setattr__(
            self,
            "normalized_article_mode",
            _strict_enum_value(
                self.normalized_article_mode,
                ArticleUnderstandingMode,
                "normalized_article_mode",
            ),
        )
        object.__setattr__(
            self,
            "normalized_visual_mode",
            _strict_enum_value(
                self.normalized_visual_mode,
                VisualPlanningMode,
                "normalized_visual_mode",
            ),
        )
        object.__setattr__(
            self,
            "normalized_series_visual_signature_strategy",
            _strict_enum_value(
                self.normalized_series_visual_signature_strategy,
                SeriesVisualSignatureStrategy,
                "normalized_series_visual_signature_strategy",
            ),
        )
        object.__setattr__(
            self,
            "strict_user_mode",
            _bool_value(self.strict_user_mode, "strict_user_mode"),
        )
        object.__setattr__(
            self,
            "force_v44_planning",
            _bool_value(self.force_v44_planning, "force_v44_planning"),
        )
        object.__setattr__(
            self,
            "explicit_fields",
            _normalize_string_tuple(self.explicit_fields, "explicit_fields"),
        )
        object.__setattr__(
            self,
            "legacy_fallback_candidate",
            _bool_value(self.legacy_fallback_candidate, "legacy_fallback_candidate"),
        )
        object.__setattr__(
            self,
            "validation_warnings",
            _normalize_string_tuple(self.validation_warnings, "validation_warnings"),
        )

    @classmethod
    def from_request(
        cls,
        requested: ArticleVisualPlanningRequest,
        explicit_fields: Sequence[str],
        legacy_fallback_candidate: Any,
        validation_warnings: Sequence[str] = (),
    ) -> "ArticleVisualPlanningPreflight":
        request = _request_value(requested)
        return cls(
            preflight_id="preflight_v44_001",
            requested=request,
            normalized_article_mode=request.article_understanding_mode,
            normalized_visual_mode=request.visual_planning_mode,
            normalized_series_visual_signature_strategy=request.series_visual_signature_strategy,
            strict_user_mode=request.strict_user_mode,
            force_v44_planning=request.force_v44_planning,
            explicit_fields=explicit_fields,
            legacy_fallback_candidate=legacy_fallback_candidate,
            validation_warnings=validation_warnings,
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "preflight_id": self.preflight_id,
            "requested": self.requested.to_dict(),
            "normalized_article_mode": self.normalized_article_mode.value,
            "normalized_visual_mode": self.normalized_visual_mode.value,
            "normalized_series_visual_signature_strategy": self.normalized_series_visual_signature_strategy.value,
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
    requested_article_mode: ArticleUnderstandingMode | str
    requested_visual_mode: VisualPlanningMode | str
    requested_series_visual_signature_strategy: SeriesVisualSignatureStrategy | str
    resolved_primary_lens: ArticleUnderstandingLens | str
    resolved_secondary_lenses: Sequence[ArticleUnderstandingLens | str]
    resolved_visual_planning_mode: VisualPlanningMode | str
    resolved_series_visual_signature_strategy: SeriesVisualSignatureStrategy | str
    primary_visual_task: PrimaryVisualTask | str
    secondary_visual_tasks: Sequence[PrimaryVisualTask | str]
    confidence: float
    decision_reason: str
    resolution_status: str
    fallback_eligible: bool
    fallback_used: bool
    fallback_target: str | None
    fallback_reason: str | None
    mismatch_warnings: Sequence[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "route_decision_id",
            _require_text("route_decision_id", self.route_decision_id),
        )
        object.__setattr__(self, "frame_id", _require_text("frame_id", self.frame_id))
        object.__setattr__(self, "preflight_id", _require_text("preflight_id", self.preflight_id))
        object.__setattr__(
            self,
            "requested_article_mode",
            _strict_enum_value(
                self.requested_article_mode,
                ArticleUnderstandingMode,
                "requested_article_mode",
            ),
        )
        object.__setattr__(
            self,
            "requested_visual_mode",
            _strict_enum_value(
                self.requested_visual_mode,
                VisualPlanningMode,
                "requested_visual_mode",
            ),
        )
        object.__setattr__(
            self,
            "requested_series_visual_signature_strategy",
            _strict_enum_value(
                self.requested_series_visual_signature_strategy,
                SeriesVisualSignatureStrategy,
                "requested_series_visual_signature_strategy",
            ),
        )
        object.__setattr__(
            self,
            "resolved_primary_lens",
            _strict_enum_value(
                self.resolved_primary_lens,
                ArticleUnderstandingLens,
                "resolved_primary_lens",
            ),
        )
        object.__setattr__(
            self,
            "resolved_secondary_lenses",
            _normalize_lens_tuple(self.resolved_secondary_lenses),
        )
        object.__setattr__(
            self,
            "resolved_visual_planning_mode",
            _strict_enum_value(
                self.resolved_visual_planning_mode,
                VisualPlanningMode,
                "resolved_visual_planning_mode",
            ),
        )
        object.__setattr__(
            self,
            "resolved_series_visual_signature_strategy",
            _strict_enum_value(
                self.resolved_series_visual_signature_strategy,
                SeriesVisualSignatureStrategy,
                "resolved_series_visual_signature_strategy",
            ),
        )
        object.__setattr__(
            self,
            "primary_visual_task",
            _strict_enum_value(
                self.primary_visual_task,
                PrimaryVisualTask,
                "primary_visual_task",
            ),
        )
        object.__setattr__(
            self,
            "secondary_visual_tasks",
            _normalize_visual_task_tuple(self.secondary_visual_tasks),
        )
        object.__setattr__(self, "confidence", _confidence_value(self.confidence))
        object.__setattr__(
            self,
            "decision_reason",
            _require_text("decision_reason", self.decision_reason),
        )
        object.__setattr__(
            self,
            "resolution_status",
            _resolution_status_value(self.resolution_status),
        )
        object.__setattr__(
            self,
            "fallback_eligible",
            _bool_value(self.fallback_eligible, "fallback_eligible"),
        )
        object.__setattr__(
            self,
            "fallback_used",
            _bool_value(self.fallback_used, "fallback_used"),
        )
        object.__setattr__(self, "fallback_target", _optional_text(self.fallback_target))
        object.__setattr__(self, "fallback_reason", _optional_text(self.fallback_reason))
        object.__setattr__(
            self,
            "mismatch_warnings",
            _normalize_string_tuple(self.mismatch_warnings, "mismatch_warnings"),
        )

    @property
    def requested_article_understanding_mode(self) -> ArticleUnderstandingMode:
        return self.requested_article_mode

    @property
    def requested_visual_planning_mode(self) -> VisualPlanningMode:
        return self.requested_visual_mode

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "route_decision_id": self.route_decision_id,
            "frame_id": self.frame_id,
            "preflight_id": self.preflight_id,
            "requested_article_mode": self.requested_article_mode.value,
            "requested_visual_mode": self.requested_visual_mode.value,
            "requested_series_visual_signature_strategy": self.requested_series_visual_signature_strategy.value,
            "resolved_primary_lens": self.resolved_primary_lens.value,
            "resolved_secondary_lenses": [
                lens.value for lens in self.resolved_secondary_lenses
            ],
            "resolved_visual_planning_mode": self.resolved_visual_planning_mode.value,
            "resolved_series_visual_signature_strategy": self.resolved_series_visual_signature_strategy.value,
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
    preflight: ArticleVisualPlanningPreflight,
    route_decisions: Sequence[VisualPlanningRouteDecision],
    article_context_insufficient: bool,
    legacy_series_visual_signature_request_present: bool,
) -> bool:
    if preflight.normalized_article_mode is not ArticleUnderstandingMode.AUTO:
        return False
    if preflight.normalized_visual_mode is not VisualPlanningMode.AUTO:
        return False
    if preflight.normalized_series_visual_signature_strategy is not SeriesVisualSignatureStrategy.AUTO:
        return False
    if preflight.force_v44_planning:
        return False
    if not preflight.legacy_fallback_candidate:
        return False
    if not article_context_insufficient or not legacy_series_visual_signature_request_present:
        return False
    if not route_decisions:
        return True
    return any(
        decision.fallback_eligible
        and decision.fallback_target == "v4.2_series_visual_signature_path"
        for decision in route_decisions
    )


def _request_value(value: Any) -> ArticleVisualPlanningRequest:
    if isinstance(value, ArticleVisualPlanningRequest):
        return value
    if isinstance(value, Mapping):
        return ArticleVisualPlanningRequest.from_mapping(value)
    raise TypeError("requested must be an ArticleVisualPlanningRequest")


def _article_concretization_source(source: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        key: source[key]
        for key in ARTICLE_CONCRETIZATION_FLAT_REQUEST_KEYS
        if key in source
    }
    if "article_concretization" in source:
        payload["article_concretization"] = source["article_concretization"]
    return payload


def _article_concretization_request_value(value: Any) -> ArticleConcretizationRequest:
    if isinstance(value, ArticleConcretizationRequest):
        return value
    if isinstance(value, Mapping):
        return ArticleConcretizationRequest.from_mapping(value)
    raise TypeError("article_concretization must be an ArticleConcretizationRequest")


def _require_text(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value.value if isinstance(value, Enum) else value).strip()
    return text or None


def _bool_value(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off", ""}:
            return False
        raise ValueError(f"{field_name} must be a boolean value")
    return bool(value)


def _confidence_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("confidence must be a finite number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ValueError("confidence must be a finite number between 0 and 1")
    return number


def _resolution_status_value(value: Any) -> str:
    status = _require_text("resolution_status", value).lower()
    if status not in _ALLOWED_RESOLUTION_STATUSES:
        allowed = ", ".join(sorted(_ALLOWED_RESOLUTION_STATUSES))
        raise ValueError(f"resolution_status must be one of: {allowed}")
    return status


def _normalize_lens_tuple(values: Any) -> tuple[ArticleUnderstandingLens, ...]:
    return tuple(
        _strict_enum_value(value, ArticleUnderstandingLens, "resolved_secondary_lenses")
        for value in _require_sequence(values, "resolved_secondary_lenses")
    )


def _normalize_visual_task_tuple(values: Any) -> tuple[PrimaryVisualTask, ...]:
    return tuple(
        _strict_enum_value(value, PrimaryVisualTask, "secondary_visual_tasks")
        for value in _require_sequence(values, "secondary_visual_tasks")
    )


def _strict_enum_value(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = str(value.value if isinstance(value, Enum) else value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")
    for item in enum_cls:
        if text.lower() == str(item.value).lower() or text.lower() == item.name.lower():
            return item
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _normalize_string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    return tuple(
        text
        for text in (_string_value(value) for value in _require_sequence(values, field_name))
        if text
    )


def _require_sequence(values: Any, field_name: str) -> Sequence[Any]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a list or tuple")
    return values


def _string_value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value).strip()


ARTICLE_VISUAL_PLANNING_REQUEST_KEYS = tuple(ArticleVisualPlanningRequest().to_dict())


__all__ = [
    "ARTICLE_VISUAL_PLANNING_REQUEST_KEYS",
    "ArticleVisualPlanningPreflight",
    "ArticleVisualPlanningRequest",
    "VisualPlanningRouteDecision",
    "should_use_v42_compatibility_path",
]
