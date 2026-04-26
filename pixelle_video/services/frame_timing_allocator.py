from __future__ import annotations

from dataclasses import dataclass
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

    windows: list[FrameTimingWindow] = []
    for frame_index in range(frame_count):
        segments = frame_segments[frame_index]
        if not segments:
            continue
        windows.append(
            FrameTimingWindow(
                frame_index=frame_index,
                start=min(start for start, _ in segments),
                end=max(end for _, end in segments),
            )
        )
    return windows


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
