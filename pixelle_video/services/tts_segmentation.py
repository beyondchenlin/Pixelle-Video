from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Optional, Sequence

from pixelle_video.tts_split_strategy import (
    EXTERNAL_ONLY_TTS_SPLIT_MODE,
    TtsSplitMode,
)
from pixelle_video.utils.text_splitting import estimate_tts_text_budget_length


class BoundaryType(StrEnum):
    SENTENCE = "sentence"
    CLAUSE = "clause"
    HARD_LIMIT = "hard_limit"
    INTERNAL = "internal"


SENTENCE_BOUNDARY_CHARS = frozenset("。！？；.!?;")
CLAUSE_BOUNDARY_CHARS = frozenset("，、,")
CLOSING_BOUNDARY_CHARS = frozenset("”’」』）》】〕〉》\"')]}")


@dataclass
class TtsSegment:
    id: str
    text: str
    synthesis_text: str
    source_start: int
    source_end: int
    boundary_type: BoundaryType
    is_continuation: bool
    char_count: int
    token_count: int
    split_reason: str
    synthesis_mode: str
    overflow_policy: str
    audio_path: Optional[str] = None
    duration_ms: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["boundary_type"] = self.boundary_type.value
        return data


@dataclass
class TtsSegmentationPlan:
    plan_id: str
    mode: TtsSplitMode
    source_text_hash: str
    source_char_count: int
    source_unit_type: str
    source_unit_id: str
    segments: list[TtsSegment] = field(default_factory=list)
    engine_segments: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    engine_request: dict[str, Any] = field(default_factory=dict)
    engine_response_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = [segment.to_dict() for segment in self.segments]
        return data


def build_external_tts_segmentation_plan(
    text: str,
    *,
    max_chars_per_segment: int,
    boundary_search_radius: int = 20,
    soft_overflow_chars: int = 0,
    source_unit_type: str = "narration",
    source_unit_id: str = "narration",
    overflow_policy: str = "error",
) -> TtsSegmentationPlan:
    source_text = text or ""
    segments = split_text_by_external_boundaries(
        source_text,
        max_chars_per_segment=max_chars_per_segment,
        boundary_search_radius=boundary_search_radius,
        soft_overflow_chars=soft_overflow_chars,
        synthesis_mode="external_pre_split",
        overflow_policy=overflow_policy,
    )
    _validate_segments_cover_source(source_text, segments)
    return TtsSegmentationPlan(
        plan_id=_build_plan_id(source_text, EXTERNAL_ONLY_TTS_SPLIT_MODE, source_unit_id),
        mode=EXTERNAL_ONLY_TTS_SPLIT_MODE,
        source_text_hash=_hash_text(source_text),
        source_char_count=len(source_text),
        source_unit_type=source_unit_type,
        source_unit_id=source_unit_id,
        segments=segments,
        config={
            "max_chars_per_segment": max_chars_per_segment,
            "boundary_search_radius": boundary_search_radius,
            "soft_overflow_chars": soft_overflow_chars,
            "overflow_policy": overflow_policy,
        },
    )


def split_text_by_external_boundaries(
    text: str,
    *,
    max_chars_per_segment: int,
    boundary_search_radius: int = 20,
    soft_overflow_chars: int = 0,
    synthesis_mode: str = "external_pre_split",
    overflow_policy: str = "error",
) -> list[TtsSegment]:
    if max_chars_per_segment < 1:
        raise ValueError("max_chars_per_segment must be at least 1")
    if boundary_search_radius < 0:
        raise ValueError("boundary_search_radius must be non-negative")
    if soft_overflow_chars < 0:
        raise ValueError("soft_overflow_chars must be non-negative")

    source_text = text or ""
    if not source_text:
        return []

    segments: list[TtsSegment] = []
    cursor = 0
    while cursor < len(source_text):
        target = min(cursor + max_chars_per_segment, len(source_text))
        if target >= len(source_text):
            split_end = len(source_text)
            boundary_type = _classify_terminal_segment(source_text[cursor:split_end])
            split_reason = "end_of_text"
        else:
            split_end, boundary_type, split_reason = _find_split_boundary(
                source_text,
                cursor=cursor,
                target=target,
                boundary_search_radius=boundary_search_radius,
                soft_overflow_chars=soft_overflow_chars,
            )

        if split_end <= cursor:
            split_end = min(cursor + max_chars_per_segment, len(source_text))
            boundary_type = BoundaryType.HARD_LIMIT
            split_reason = "hard_limit_guard"

        segments.append(
            _create_segment(
                source_text,
                index=len(segments) + 1,
                source_start=cursor,
                source_end=split_end,
                boundary_type=boundary_type,
                split_reason=split_reason,
                synthesis_mode=synthesis_mode,
                overflow_policy=overflow_policy,
            )
        )
        cursor = split_end

    return segments


def _find_split_boundary(
    text: str,
    *,
    cursor: int,
    target: int,
    boundary_search_radius: int,
    soft_overflow_chars: int,
) -> tuple[int, BoundaryType, str]:
    before_start = max(cursor + 1, target - boundary_search_radius)
    before_end = target

    for boundary_chars, boundary_type, reason in (
        (SENTENCE_BOUNDARY_CHARS, BoundaryType.SENTENCE, "sentence_boundary_before_budget"),
        (CLAUSE_BOUNDARY_CHARS, BoundaryType.CLAUSE, "clause_boundary_before_budget"),
    ):
        split_end = _find_last_boundary(text, before_start, before_end, boundary_chars)
        if split_end is not None:
            return split_end, boundary_type, reason

    overflow_end = min(len(text), target + soft_overflow_chars)
    if overflow_end > target:
        for boundary_chars, boundary_type, reason in (
            (SENTENCE_BOUNDARY_CHARS, BoundaryType.SENTENCE, "sentence_boundary_soft_overflow"),
            (CLAUSE_BOUNDARY_CHARS, BoundaryType.CLAUSE, "clause_boundary_soft_overflow"),
        ):
            split_end = _find_first_boundary(text, target + 1, overflow_end, boundary_chars)
            if split_end is not None:
                return split_end, boundary_type, reason

    return target, BoundaryType.HARD_LIMIT, "hard_limit"


def _find_last_boundary(
    text: str,
    start: int,
    end: int,
    boundary_chars: frozenset[str],
) -> Optional[int]:
    for index in range(min(end, len(text)) - 1, start - 2, -1):
        if index < 0:
            break
        if text[index] in boundary_chars:
            return _extend_over_closing_chars(text, index + 1)
    return None


def _find_first_boundary(
    text: str,
    start: int,
    end: int,
    boundary_chars: frozenset[str],
) -> Optional[int]:
    for index in range(max(start - 1, 0), min(end, len(text))):
        if text[index] in boundary_chars:
            return _extend_over_closing_chars(text, index + 1)
    return None


def _extend_over_closing_chars(text: str, split_end: int) -> int:
    while split_end < len(text) and text[split_end] in CLOSING_BOUNDARY_CHARS:
        split_end += 1
    return split_end


def _classify_terminal_segment(text: str) -> BoundaryType:
    stripped = (text or "").rstrip()
    if not stripped:
        return BoundaryType.HARD_LIMIT
    while stripped and stripped[-1] in CLOSING_BOUNDARY_CHARS:
        stripped = stripped[:-1].rstrip()
    if stripped and stripped[-1] in SENTENCE_BOUNDARY_CHARS:
        return BoundaryType.SENTENCE
    if stripped and stripped[-1] in CLAUSE_BOUNDARY_CHARS:
        return BoundaryType.CLAUSE
    return BoundaryType.HARD_LIMIT


def _create_segment(
    source_text: str,
    *,
    index: int,
    source_start: int,
    source_end: int,
    boundary_type: BoundaryType,
    split_reason: str,
    synthesis_mode: str,
    overflow_policy: str,
) -> TtsSegment:
    segment_text = source_text[source_start:source_end]
    return TtsSegment(
        id=f"tts-segment-{index}",
        text=segment_text,
        synthesis_text=segment_text,
        source_start=source_start,
        source_end=source_end,
        boundary_type=boundary_type,
        is_continuation=boundary_type in {BoundaryType.CLAUSE, BoundaryType.HARD_LIMIT},
        char_count=len(segment_text),
        token_count=estimate_tts_text_budget_length(segment_text),
        split_reason=split_reason,
        synthesis_mode=synthesis_mode,
        overflow_policy=overflow_policy,
    )


def _validate_segments_cover_source(text: str, segments: Sequence[TtsSegment]) -> None:
    joined = "".join(segment.text for segment in segments)
    if joined != text:
        raise ValueError("TTS segments must concatenate back to the original source text")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_plan_id(text: str, mode: str, source_unit_id: str) -> str:
    digest = hashlib.sha256(f"{mode}\0{source_unit_id}\0{text}".encode("utf-8")).hexdigest()
    return f"tts-plan-{digest[:16]}"
