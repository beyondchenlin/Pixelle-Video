from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.utils.text_splitting import (
    DEFAULT_CAPTION_PUNCTUATION_MODE,
    format_caption_text,
)


@dataclass(frozen=True)
class CaptionSpeechUnit:
    index: int
    speech_text: str
    display_text: str
    source_start: int
    source_end: int
    unit_id: str = ""
    frame_indices: tuple[int, ...] = field(default_factory=tuple)
    frame_weights: Mapping[int, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 1:
            raise ValueError("caption speech unit index must be a positive integer")
        if not self.speech_text.strip():
            raise ValueError("caption speech unit speech_text must not be empty")
        if not self.display_text.strip():
            raise ValueError("caption speech unit display_text must not be empty")
        if type(self.source_start) is not int or type(self.source_end) is not int:
            raise ValueError("caption speech unit source range must use integers")
        if self.source_start < 0 or self.source_end < self.source_start:
            raise ValueError("caption speech unit source range is invalid")
        object.__setattr__(self, "frame_indices", tuple(int(item) for item in self.frame_indices))
        object.__setattr__(
            self,
            "frame_weights",
            MappingProxyType({
                int(key): float(value)
                for key, value in dict(self.frame_weights).items()
                if float(value) > 0
            }),
        )
        object.__setattr__(self, "metadata", _deep_freeze(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "index": self.index,
            "speech_text": self.speech_text,
            "display_text": self.display_text,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "frame_indices": list(self.frame_indices),
            "frame_weights": {str(key): value for key, value in self.frame_weights.items()},
            "metadata": _json_safe_copy(self.metadata),
        }


@dataclass(frozen=True)
class CaptionSpeechPlan:
    plan_id: str
    source_text: str
    source_digest: str
    units: tuple[CaptionSpeechUnit, ...]
    punctuation_mode: str = DEFAULT_CAPTION_PUNCTUATION_MODE
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_source = normalize_caption_source_text(self.source_text)
        if not normalized_source:
            raise ValueError("caption speech source_text must not be empty")
        if self.source_digest != _source_digest(normalized_source):
            raise ValueError("caption speech source_digest must match source_text")
        units = tuple(self.units)
        if not units:
            raise ValueError("CaptionSpeechPlan requires at least one unit")
        expected_indexes = list(range(1, len(units) + 1))
        actual_indexes = [unit.index for unit in units]
        if actual_indexes != expected_indexes:
            raise ValueError("caption speech unit indexes must start at 1 and be contiguous")
        unit_ids: set[str] = set()
        for unit in units:
            if not unit.unit_id:
                raise ValueError("caption speech unit_id must not be empty")
            if unit.unit_id in unit_ids:
                raise ValueError("caption speech unit_id must be unique")
            unit_ids.add(unit.unit_id)
            if unit.source_end > len(normalized_source):
                raise ValueError("caption speech unit source range must index source_text")
            if normalized_source[unit.source_start : unit.source_end] != unit.speech_text:
                raise ValueError("caption speech unit speech_text must match source_text slice")
        object.__setattr__(self, "source_text", normalized_source)
        object.__setattr__(self, "units", units)
        object.__setattr__(self, "diagnostics", _deep_freeze(self.diagnostics))

    def speech_texts(self) -> list[str]:
        return [unit.speech_text for unit in self.units]

    def display_texts(self) -> list[str]:
        return [unit.display_text for unit in self.units]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source_text": self.source_text,
            "source_digest": self.source_digest,
            "punctuation_mode": self.punctuation_mode,
            "units": [unit.to_dict() for unit in self.units],
            "diagnostics": _json_safe_copy(self.diagnostics),
        }


def build_caption_speech_plan(
    source_text: str,
    *,
    storyboard_plan: StoryboardPlan | None = None,
    punctuation_mode: str = DEFAULT_CAPTION_PUNCTUATION_MODE,
) -> CaptionSpeechPlan:
    normalized_source = normalize_caption_source_text(source_text)
    source_digest = _source_digest(normalized_source)
    raw_segments = _split_source_text_on_punctuation(normalized_source)
    frame_ranges = _frame_ranges_for_storyboard_plan(storyboard_plan)
    frame_allocations = [
        _frame_allocation_for_source_range(
            start=start,
            end=end,
            frame_ranges=frame_ranges,
        )
        for _, start, end in raw_segments
    ]
    units = tuple(
        CaptionSpeechUnit(
            index=index,
            unit_id=_stable_unit_id(source_digest=source_digest, index=index, source_start=start, source_end=end),
            speech_text=segment,
            display_text=format_caption_text(segment, punctuation_mode=punctuation_mode),
            source_start=start,
            source_end=end,
            frame_indices=frame_indices,
            frame_weights=frame_weights,
        )
        for index, ((segment, start, end), (frame_indices, frame_weights)) in enumerate(
            zip(raw_segments, frame_allocations),
            start=1,
        )
    )
    return CaptionSpeechPlan(
        plan_id=f"caption_speech_{source_digest[:16]}",
        source_text=normalized_source,
        source_digest=source_digest,
        punctuation_mode=punctuation_mode,
        units=units,
        diagnostics={
            "strategy": "punctuation",
            "unit_count": len(units),
        },
    )


def normalize_caption_source_text(source_text: str) -> str:
    return (source_text or "").strip()


def _split_source_text_on_punctuation(source_text: str) -> list[tuple[str, int, int]]:
    if not source_text:
        return []

    segments: list[tuple[str, int, int]] = []
    current_start: int | None = None
    has_text = False
    for index, char in enumerate(source_text):
        if current_start is None:
            if char.isspace():
                continue
            current_start = index
        if not char.isspace() and not _is_unicode_punctuation(char):
            has_text = True

        next_char = source_text[index + 1] if index + 1 < len(source_text) else ""
        should_split = has_text and _is_unicode_punctuation(char) and (
            not next_char or not _is_unicode_punctuation(next_char)
        )
        if should_split and current_start is not None:
            end = index + 1
            _append_displayable_segment(segments, source_text, current_start, end)
            current_start = None
            has_text = False

    if current_start is not None and has_text:
        _append_displayable_segment(segments, source_text, current_start, len(source_text))
    return segments


def _append_displayable_segment(
    segments: list[tuple[str, int, int]],
    source_text: str,
    start: int,
    end: int,
) -> None:
    segment = source_text[start:end].strip()
    if not segment:
        return
    display = format_caption_text(segment, punctuation_mode=DEFAULT_CAPTION_PUNCTUATION_MODE)
    if display:
        leading = len(source_text[start:end]) - len(source_text[start:end].lstrip())
        trailing = len(source_text[start:end].rstrip())
        adjusted_start = start + leading
        adjusted_end = start + trailing
        segments.append((source_text[adjusted_start:adjusted_end], adjusted_start, adjusted_end))


def _frame_allocation_for_source_range(
    *,
    start: int,
    end: int,
    frame_ranges: tuple[tuple[int, int, int], ...],
) -> tuple[tuple[int, ...], Mapping[int, float]]:
    if not frame_ranges:
        return (), {}
    frame_weights: dict[int, float] = {}
    for frame_index, frame_start, frame_end in frame_ranges:
        if frame_start < end and start < frame_end:
            frame_weights[frame_index] = float(
                max(1, min(frame_end, end) - max(frame_start, start))
            )
    if frame_weights:
        return tuple(frame_weights), frame_weights

    unit_center = start + ((end - start) / 2)
    nearest_frame = min(
        frame_ranges,
        key=lambda item: min(abs(unit_center - item[1]), abs(unit_center - item[2])),
    )
    return (nearest_frame[0],), {nearest_frame[0]: float(max(1, end - start))}


def _frame_ranges_for_storyboard_plan(
    storyboard_plan: StoryboardPlan | None,
) -> tuple[tuple[int, int, int], ...]:
    if storyboard_plan is None:
        return ()

    located_ranges = _explicit_or_located_frame_source_text_ranges(storyboard_plan)
    if located_ranges:
        return located_ranges

    return _proportional_frame_ranges(storyboard_plan)


def _explicit_or_located_frame_source_text_ranges(
    storyboard_plan: StoryboardPlan,
) -> tuple[tuple[int, int, int], ...]:
    ranges: list[tuple[int, int, int]] = []
    cursor = 0
    for frame in storyboard_plan.frames:
        if frame.source_start is not None and frame.source_end is not None:
            ranges.append((frame.index - 1, frame.source_start, frame.source_end))
            cursor = max(cursor, frame.source_end)
            continue

        frame_text = frame.source_text.strip()
        if not frame_text:
            continue
        start = storyboard_plan.source_text.find(frame_text, cursor)
        if start < 0:
            start = storyboard_plan.source_text.find(frame_text)
        if start < 0:
            return ()
        end = start + len(frame_text)
        ranges.append((frame.index - 1, start, end))
        cursor = end
    return tuple(ranges)


def _proportional_frame_ranges(
    storyboard_plan: StoryboardPlan,
) -> tuple[tuple[int, int, int], ...]:
    frame_count = len(storyboard_plan.frames)
    if frame_count <= 0:
        return ()
    source_length = len(storyboard_plan.source_text)
    if source_length <= 0:
        return ()
    ranges: list[tuple[int, int, int]] = []
    for position, frame in enumerate(storyboard_plan.frames):
        start = round(source_length * position / frame_count)
        end = round(source_length * (position + 1) / frame_count)
        ranges.append((frame.index - 1, start, max(start + 1, end)))
    return tuple(ranges)


def _stable_unit_id(
    *,
    source_digest: str,
    index: int,
    source_start: int,
    source_end: int,
) -> str:
    seed = f"{source_digest}|{index}|{source_start}|{source_end}"
    return f"speech_{index:04d}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _source_digest(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _is_unicode_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return deepcopy(value)


def _json_safe_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_safe_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    return deepcopy(value)


__all__ = [
    "CaptionSpeechPlan",
    "CaptionSpeechUnit",
    "build_caption_speech_plan",
    "normalize_caption_source_text",
]
