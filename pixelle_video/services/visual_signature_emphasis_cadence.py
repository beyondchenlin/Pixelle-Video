from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from pixelle_video.models.visual_signature_emphasis import VisualSignatureEmphasis

VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL = 10
_SELECTION_NAMESPACE = "visual-signature-emphasis-cadence.v2"


@dataclass(frozen=True, slots=True)
class VisualSignatureEmphasisDecision:
    frame_id: str
    emphasis: VisualSignatureEmphasis
    selection_window_index: int | None = None


@dataclass(frozen=True, slots=True)
class VisualSignatureEmphasisCadencePlanner:
    """Allocate the fixed rounded-up ten-percent budget without reading content."""

    def plan(
        self,
        *,
        frame_ids: Sequence[str],
        storyboard_plan_id: str,
    ) -> tuple[VisualSignatureEmphasisDecision, ...]:
        if isinstance(frame_ids, (str, bytes)):
            raise TypeError("frame_ids must be a sequence of frame id strings")
        ordered_frame_ids = tuple(frame_ids)
        _validate_frame_ids(ordered_frame_ids)
        resolved_storyboard_plan_id = _validate_storyboard_plan_id(
            storyboard_plan_id
        )
        if not ordered_frame_ids:
            return ()

        enhanced_count = (
            len(ordered_frame_ids) + VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL - 1
        ) // VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL
        selected_window_by_frame: dict[str, int] = {}
        for window_index in range(enhanced_count):
            start = window_index * len(ordered_frame_ids) // enhanced_count
            end = (window_index + 1) * len(ordered_frame_ids) // enhanced_count
            candidate_start = start + (1 if window_index > 0 else 0)
            candidate_end = end - (1 if window_index + 1 < enhanced_count else 0)
            candidates = ordered_frame_ids[candidate_start:candidate_end]
            selected_frame_id = min(
                candidates,
                key=lambda frame_id: _selection_digest(
                    frame_id=frame_id,
                    storyboard_plan_id=resolved_storyboard_plan_id,
                    window_index=window_index,
                ),
            )
            selected_window_by_frame[selected_frame_id] = window_index

        return tuple(
            VisualSignatureEmphasisDecision(
                frame_id=frame_id,
                emphasis=(
                    VisualSignatureEmphasis.ENHANCED
                    if frame_id in selected_window_by_frame
                    else VisualSignatureEmphasis.STANDARD
                ),
                selection_window_index=selected_window_by_frame.get(frame_id),
            )
            for frame_id in ordered_frame_ids
        )


def _selection_digest(
    *,
    frame_id: str,
    storyboard_plan_id: str,
    window_index: int,
) -> bytes:
    return hashlib.sha256(
        (
            f"{_SELECTION_NAMESPACE}:{window_index}:"
            f"{storyboard_plan_id}:{frame_id}"
        ).encode("utf-8")
    ).digest()


def _validate_frame_ids(frame_ids: tuple[str, ...]) -> None:
    if any(not isinstance(frame_id, str) or not frame_id.strip() for frame_id in frame_ids):
        raise ValueError("frame_ids must contain non-empty strings")
    if len(set(frame_ids)) != len(frame_ids):
        raise ValueError("frame_ids must be unique")


def _validate_storyboard_plan_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("storyboard_plan_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("storyboard_plan_id must be a non-empty string")
    return normalized


__all__ = [
    "VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL",
    "VisualSignatureEmphasisCadencePlanner",
    "VisualSignatureEmphasisDecision",
]
