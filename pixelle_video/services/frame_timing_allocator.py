from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from pixelle_video.models.render_package import SentenceUnit


@dataclass(frozen=True)
class FrameTimingWindow:
    frame_index: int
    start: float
    end: float


def allocate_frame_timing_windows(
    *,
    frame_count: int,
    sentence_units: Sequence[SentenceUnit],
    timeline_start: float | None = None,
    timeline_end: float | None = None,
) -> list[FrameTimingWindow]:
    if frame_count <= 0:
        return []

    frame_segments: dict[int, list[tuple[float, float]]] = {
        frame_index: []
        for frame_index in range(frame_count)
    }
    for sentence in sentence_units:
        sentence_start, sentence_end = _sentence_window(sentence)
        if sentence_start is None or sentence_end is None or sentence_end <= sentence_start:
            continue
        frame_indices = _normalized_frame_indices(sentence.frame_indices, frame_count)
        if not frame_indices:
            continue
        for frame_index, start, end in _split_sentence_window(
            sentence=sentence,
            frame_indices=frame_indices,
            sentence_start=sentence_start,
            sentence_end=sentence_end,
        ):
            if end > start:
                frame_segments[frame_index].append((start, end))

    raw_windows: dict[int, FrameTimingWindow] = {}
    for frame_index in range(frame_count):
        segments = frame_segments[frame_index]
        if not segments:
            continue
        raw_windows[frame_index] = FrameTimingWindow(
            frame_index=frame_index,
            start=min(start for start, _ in segments),
            end=max(end for _, end in segments),
        )

    if timeline_start is None and timeline_end is None:
        return [raw_windows[index] for index in sorted(raw_windows)]
    if timeline_start is None or timeline_end is None:
        raise ValueError("timeline_start and timeline_end must be provided together")
    return _allocate_continuous_windows(
        frame_count=frame_count,
        raw_windows=raw_windows,
        timeline_start=timeline_start,
        timeline_end=timeline_end,
    )


def _allocate_continuous_windows(
    *,
    frame_count: int,
    raw_windows: dict[int, FrameTimingWindow],
    timeline_start: float,
    timeline_end: float,
) -> list[FrameTimingWindow]:
    start = float(timeline_start)
    end = float(timeline_end)
    if not isfinite(start) or not isfinite(end) or end <= start:
        raise ValueError("continuous timeline must have a finite positive duration")

    boundaries: list[float | None] = [start]
    for index in range(frame_count - 1):
        left = raw_windows.get(index)
        right = raw_windows.get(index + 1)
        if left is not None and right is not None:
            boundary = right.start
        elif left is not None:
            boundary = left.end
        elif right is not None:
            boundary = right.start
        else:
            boundary = None
        boundaries.append(boundary)
    boundaries.append(end)

    known_indices = [index for index, value in enumerate(boundaries) if value is not None]
    for left_index, right_index in zip(known_indices, known_indices[1:]):
        left_value = float(boundaries[left_index])
        right_value = float(boundaries[right_index])
        span = right_index - left_index
        for offset in range(1, span):
            boundaries[left_index + offset] = (
                left_value + (right_value - left_value) * (offset / span)
            )

    duration = end - start
    minimum_duration = min(0.001, duration / frame_count)
    resolved = [float(value) for value in boundaries]
    for index in range(1, frame_count):
        lower = resolved[index - 1] + minimum_duration
        upper = end - ((frame_count - index) * minimum_duration)
        resolved[index] = min(max(resolved[index], lower), upper)

    return [
        FrameTimingWindow(
            frame_index=index,
            start=resolved[index],
            end=resolved[index + 1],
        )
        for index in range(frame_count)
    ]


def _sentence_window(sentence: SentenceUnit) -> tuple[float | None, float | None]:
    start = sentence.remapped_start if sentence.remapped_start is not None else sentence.source_start
    end = sentence.remapped_end if sentence.remapped_end is not None else sentence.source_end
    if start is None or end is None:
        return None, None
    return float(start), float(end)


def _normalized_frame_indices(frame_indices: Sequence[int], frame_count: int) -> list[int]:
    normalized: list[int] = []
    for raw_index in frame_indices:
        frame_index = int(raw_index)
        if 0 <= frame_index < frame_count and frame_index not in normalized:
            normalized.append(frame_index)
    return normalized


def _split_sentence_window(
    *,
    sentence: SentenceUnit,
    frame_indices: list[int],
    sentence_start: float,
    sentence_end: float,
) -> list[tuple[int, float, float]]:
    duration = sentence_end - sentence_start
    weights = _frame_weights(sentence, frame_indices)
    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1.0 for _ in frame_indices]
        total_weight = sum(weights)

    segments: list[tuple[int, float, float]] = []
    cursor = sentence_start
    elapsed_weight = 0.0
    for index, (frame_index, weight) in enumerate(zip(frame_indices, weights)):
        if index == len(frame_indices) - 1:
            segment_end = sentence_end
        else:
            elapsed_weight += weight
            segment_end = sentence_start + duration * (elapsed_weight / total_weight)
        segments.append((frame_index, cursor, segment_end))
        cursor = segment_end
    return segments


def _frame_weights(sentence: SentenceUnit, frame_indices: list[int]) -> list[float]:
    raw_weights = getattr(sentence, "frame_weights", {}) or {}
    weights: list[float] = []
    for frame_index in frame_indices:
        try:
            weight = float(raw_weights.get(frame_index, raw_weights.get(str(frame_index), 0.0)))
        except (TypeError, ValueError):
            weight = 0.0
        weights.append(weight if weight > 0 else 0.0)
    if any(weight > 0 for weight in weights):
        return weights
    return [1.0 for _ in frame_indices]


__all__ = ["FrameTimingWindow", "allocate_frame_timing_windows"]
