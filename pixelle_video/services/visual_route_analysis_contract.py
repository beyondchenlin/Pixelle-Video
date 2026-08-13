"""Boundary normalization for model-generated visual-route analysis."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pixelle_video.models.visual_story_engine import (
    DEFAULT_ROUTE_CANDIDATE_COUNT,
    ArticleVisualUnderstanding,
    VisualRouteCandidate,
    VisualRouteScores,
)

ARTICLE_PAYLOAD_KEYS = (
    "article_understanding",
    "article",
    "content_analysis",
    "analysis",
)
ROUTE_CANDIDATE_PAYLOAD_KEYS = (
    "candidate_routes",
    "candidates",
    "routes",
    "route_candidates",
    "visual_routes",
    "data",
    "items",
)
SCORE_REPAIR_PAYLOAD_KEYS = ("score_repairs", "repairs", "items", "data")

_PAYLOAD_WRAPPER_KEYS = ("data", "result", "output", "response")
_SCORE_FIELD_ALIASES = {
    "content_fit": ("content_fit", "content_fit_score"),
    "memorability": (
        "memorability",
        "visual_memorability",
        "visual_memorability_score",
    ),
    "channel_consistency": (
        "channel_consistency",
        "channel_fit",
        "channel_consistency_score",
    ),
    "production_reliability": (
        "production_reliability",
        "production_reliability_score",
    ),
    "risk": ("risk", "risk_score"),
}
CONTENT_ROUTE_SCORE_FIELDS = tuple(_SCORE_FIELD_ALIASES)
_NEUTRAL_ROUTE_SCORES = {
    field_name: 0.0
    for field_name in CONTENT_ROUTE_SCORE_FIELDS
}
_JSON_NUMBER_TEXT_RE = re.compile(
    r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$"
)
_NON_NEGATIVE_INTEGER_TEXT_RE = re.compile(r"^(?:0|[1-9]\d*)$")


class VisualRouteAnalysisContractError(ValueError):
    """Safe contract failure that never retains raw model output."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code).strip() or "visual_route_contract_error"
        super().__init__(message)


class VisualRouteScoreResponse(BaseModel):
    """Strict contract for the five model-owned route scores."""

    model_config = ConfigDict(extra="ignore", strict=True)

    content_fit: float
    memorability: float
    channel_consistency: float
    production_reliability: float
    risk: float

    @field_validator(*CONTENT_ROUTE_SCORE_FIELDS, mode="before")
    @classmethod
    def _validate_json_number(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("route scores must be JSON numbers between 0 and 1")
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError("route scores must be JSON numbers between 0 and 1")
        return number


class VisualRouteScoreRepairItemResponse(BaseModel):
    """One score-only repair tied to a candidate position."""

    model_config = ConfigDict(extra="ignore", strict=True)

    candidate_index: int = Field(ge=0)
    scores: VisualRouteScoreResponse


@dataclass(frozen=True)
class RouteCandidateParseResult:
    accepted: tuple[tuple[int, VisualRouteCandidate], ...]
    repairable: tuple[tuple[int, VisualRouteCandidate], ...]
    rejected_count: int


def normalize_candidate_count(value: Any) -> int:
    """Preserve positive counts while making invalid configuration safe."""

    if isinstance(value, bool):
        return DEFAULT_ROUTE_CANDIDATE_COUNT
    try:
        requested = int(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_ROUTE_CANDIDATE_COUNT
    return max(1, requested)


def coerce_route_analysis_response(response: Any) -> dict[str, Any]:
    """Normalize supported model response wrappers into a mapping."""

    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        response = model_dump(mode="python")
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, str):
        text = response.strip()
        if not text:
            return {}
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
        if isinstance(parsed, list):
            return {"items": parsed}
        return {}
    if isinstance(response, Sequence) and not isinstance(
        response,
        str | bytes | bytearray,
    ):
        return {"items": list(response)}
    return {}


def extract_article_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return _find_mapping_payload(
        payload,
        ARTICLE_PAYLOAD_KEYS,
        depth=0,
        visited=set(),
    ) or {}


def extract_route_candidates(payload: Mapping[str, Any]) -> Sequence[Any]:
    values = _find_sequence_payload(
        payload,
        ROUTE_CANDIDATE_PAYLOAD_KEYS,
        depth=0,
        visited=set(),
    )
    return values


def parse_route_candidates(
    raw_candidates: Sequence[Any],
) -> RouteCandidateParseResult:
    """Validate scores per candidate while retaining compatible route aliases."""

    accepted: list[tuple[int, VisualRouteCandidate]] = []
    repairable: list[tuple[int, VisualRouteCandidate]] = []
    rejected_count = 0
    for candidate_index, raw_candidate in enumerate(raw_candidates):
        if not isinstance(raw_candidate, Mapping):
            rejected_count += 1
            continue
        candidate_payload = dict(raw_candidate)
        try:
            candidate = VisualRouteCandidate.from_mapping(
                {
                    **candidate_payload,
                    "scores": _NEUTRAL_ROUTE_SCORES,
                }
            )
        except (TypeError, ValueError):
            rejected_count += 1
            continue
        try:
            scores = _strict_route_scores(candidate_payload)
        except (ValidationError, VisualRouteAnalysisContractError):
            repairable.append((candidate_index, candidate))
            continue
        accepted.append((candidate_index, candidate.with_scores(scores)))
    return RouteCandidateParseResult(
        accepted=tuple(accepted),
        repairable=tuple(repairable),
        rejected_count=rejected_count,
    )


def score_repair_article_context(
    article: ArticleVisualUnderstanding,
) -> dict[str, Any]:
    return {
        "summary": _bounded_prompt_text(article.summary, 1000),
        "core_claim": _bounded_prompt_text(article.core_claim, 1000),
        "central_problem": _bounded_prompt_text(article.central_problem, 1000),
        "key_subjects": [
            _bounded_prompt_text(subject, 200)
            for subject in article.key_subjects[:8]
        ],
    }


def score_repair_candidate_context(
    candidate_index: int,
    candidate: VisualRouteCandidate,
) -> dict[str, Any]:
    return {
        "candidate_index": candidate_index,
        "route_id": _bounded_prompt_text(candidate.route_id, 160),
        "route_name": _bounded_prompt_text(candidate.route_name, 240),
        "route_type": candidate.route_type.value,
        "visual_premise": _bounded_prompt_text(candidate.visual_premise, 800),
        "why_it_fits_article": _bounded_prompt_text(
            candidate.why_it_fits_article,
            800,
        ),
        "frame_storytelling_logic": _bounded_prompt_text(
            candidate.frame_storytelling_logic,
            800,
        ),
        "risk_notes": [
            _bounded_prompt_text(note, 240)
            for note in candidate.risk_notes[:6]
        ],
    }


def validate_score_repairs(
    payload: Mapping[str, Any],
    expected_indices: set[int],
) -> dict[int, VisualRouteScores]:
    """Accept only unique, expected, individually valid score repairs."""

    raw_repairs = _find_sequence_payload(
        payload,
        SCORE_REPAIR_PAYLOAD_KEYS,
        depth=0,
        visited=set(),
    )
    parsed: dict[int, VisualRouteScores] = {}
    duplicate_indices: set[int] = set()
    for raw_repair in raw_repairs:
        if not isinstance(raw_repair, Mapping):
            continue
        raw_score_payload = raw_repair.get("scores")
        if "scores" in raw_repair:
            if not isinstance(raw_score_payload, Mapping):
                continue
            score_payload = raw_score_payload
        else:
            score_payload = raw_repair
        try:
            repair = VisualRouteScoreRepairItemResponse.model_validate(
                {
                    "candidate_index": _normalize_candidate_index(
                        raw_repair.get("candidate_index")
                    ),
                    "scores": _canonical_score_payload(score_payload),
                }
            )
        except (ValidationError, VisualRouteAnalysisContractError):
            continue
        candidate_index = repair.candidate_index
        if candidate_index not in expected_indices:
            continue
        if candidate_index in parsed or candidate_index in duplicate_indices:
            parsed.pop(candidate_index, None)
            duplicate_indices.add(candidate_index)
            continue
        parsed[candidate_index] = VisualRouteScores.from_mapping(
            repair.scores.model_dump(mode="python")
        )
    if not parsed:
        raise VisualRouteAnalysisContractError(
            "no_valid_score_repairs",
            "score repair returned no valid candidate scores",
        )
    return parsed


def ensure_unique_route_ids(
    candidates: Sequence[VisualRouteCandidate],
) -> tuple[VisualRouteCandidate, ...]:
    """Preserve the first route ID and suffix later collisions deterministically."""

    unique_candidates: list[VisualRouteCandidate] = []
    used_route_ids: set[str] = set()
    for candidate_index, candidate in enumerate(candidates, start=1):
        route_id = candidate.route_id
        if route_id in used_route_ids:
            suffix = candidate_index
            route_id = _suffixed_route_id(candidate.route_id, suffix)
            while route_id in used_route_ids:
                suffix += 1
                route_id = _suffixed_route_id(candidate.route_id, suffix)
            candidate = replace(candidate, route_id=route_id)
        used_route_ids.add(candidate.route_id)
        unique_candidates.append(candidate)
    return tuple(unique_candidates)


def recognized_payload_keys(payload: Mapping[str, Any]) -> list[str]:
    """Return only hard-coded keys so untrusted output never becomes a log field."""

    known_keys = (
        *ARTICLE_PAYLOAD_KEYS,
        *ROUTE_CANDIDATE_PAYLOAD_KEYS,
        *_PAYLOAD_WRAPPER_KEYS,
    )
    return [key for key in dict.fromkeys(known_keys) if key in payload]


def _strict_route_scores(candidate_payload: Mapping[str, Any]) -> VisualRouteScores:
    if "scores" in candidate_payload:
        score_payload = candidate_payload.get("scores")
        if not isinstance(score_payload, Mapping):
            raise VisualRouteAnalysisContractError(
                "invalid_scores_object",
                "scores must be an object",
            )
    else:
        score_payload = candidate_payload

    canonical_scores = _canonical_score_payload(score_payload)
    validated = VisualRouteScoreResponse.model_validate(canonical_scores)
    return VisualRouteScores.from_mapping(validated.model_dump(mode="python"))


def _canonical_score_payload(score_payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical_scores: dict[str, Any] = {}
    for canonical_name, aliases in _SCORE_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in score_payload:
                canonical_scores[canonical_name] = _normalize_provider_score(
                    score_payload[alias]
                )
                break
        else:
            raise VisualRouteAnalysisContractError(
                "missing_score_field",
                f"missing required score field: {canonical_name}",
            )
    return canonical_scores


def _normalize_provider_score(value: Any) -> Any:
    """Normalize only bounded JSON-number strings at the provider boundary."""

    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if (
        len(normalized) > 32
        or _JSON_NUMBER_TEXT_RE.fullmatch(normalized) is None
    ):
        return value
    return float(normalized)


def _normalize_candidate_index(value: Any) -> Any:
    """Normalize a bounded decimal index without weakening the strict model."""

    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if (
        len(normalized) > 10
        or _NON_NEGATIVE_INTEGER_TEXT_RE.fullmatch(normalized) is None
    ):
        return value
    return int(normalized)


def _find_mapping_payload(
    value: Any,
    keys: Sequence[str],
    *,
    depth: int,
    visited: set[int],
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping) or depth > 4 or id(value) in visited:
        return None
    visited.add(id(value))
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, Mapping):
            return candidate
    for key in _PAYLOAD_WRAPPER_KEYS:
        nested = _find_mapping_payload(
            value.get(key),
            keys,
            depth=depth + 1,
            visited=visited,
        )
        if nested is not None:
            return nested
    return None


def _find_sequence_payload(
    value: Any,
    keys: Sequence[str],
    *,
    depth: int,
    visited: set[int],
) -> Sequence[Any]:
    if not isinstance(value, Mapping) or depth > 4 or id(value) in visited:
        return ()
    visited.add(id(value))
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, Sequence) and not isinstance(
            candidate,
            str | bytes | bytearray,
        ):
            if candidate:
                return candidate
            continue
        nested = _find_sequence_payload(
            candidate,
            keys,
            depth=depth + 1,
            visited=visited,
        )
        if nested:
            return nested
    return ()


def _bounded_prompt_text(value: Any, max_chars: int) -> str:
    return str(value or "").strip()[:max_chars]


def _suffixed_route_id(route_id: str, suffix: int) -> str:
    suffix_text = f"_{suffix}"
    return f"{route_id[: 80 - len(suffix_text)]}{suffix_text}"


__all__ = [
    "CONTENT_ROUTE_SCORE_FIELDS",
    "RouteCandidateParseResult",
    "VisualRouteAnalysisContractError",
    "VisualRouteScoreRepairItemResponse",
    "VisualRouteScoreResponse",
    "coerce_route_analysis_response",
    "ensure_unique_route_ids",
    "extract_article_payload",
    "extract_route_candidates",
    "normalize_candidate_count",
    "parse_route_candidates",
    "recognized_payload_keys",
    "score_repair_article_context",
    "score_repair_candidate_context",
    "validate_score_repairs",
]
