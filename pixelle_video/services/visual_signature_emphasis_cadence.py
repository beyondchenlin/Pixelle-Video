from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pixelle_video.models.visual_signature_emphasis import VisualSignatureEmphasis

VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL = 10
_MAX_RANDOM_SEED = 2**64 - 1
_SELECTION_NAMESPACE = "visual-signature-emphasis-cadence.v1"


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
        random_seeds_by_frame: Mapping[str, int],
    ) -> tuple[VisualSignatureEmphasisDecision, ...]:
        if isinstance(frame_ids, (str, bytes)):
            raise TypeError("frame_ids must be a sequence of frame id strings")
        ordered_frame_ids = tuple(frame_ids)
        _validate_frame_ids(ordered_frame_ids)
        _validate_random_seeds(
            frame_ids=ordered_frame_ids,
            random_seeds_by_frame=random_seeds_by_frame,
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
                    random_seed=random_seeds_by_frame[frame_id],
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
    random_seed: int,
    window_index: int,
) -> bytes:
    return hashlib.sha256(
        (
            f"{_SELECTION_NAMESPACE}:{window_index}:"
            f"{random_seed}:{frame_id}"
        ).encode("utf-8")
    ).digest()


def _validate_frame_ids(frame_ids: tuple[str, ...]) -> None:
    if any(not isinstance(frame_id, str) or not frame_id.strip() for frame_id in frame_ids):
        raise ValueError("frame_ids must contain non-empty strings")
    if len(set(frame_ids)) != len(frame_ids):
        raise ValueError("frame_ids must be unique")


def _validate_random_seeds(
    *,
    frame_ids: tuple[str, ...],
    random_seeds_by_frame: Mapping[str, int],
) -> None:
    if not isinstance(random_seeds_by_frame, Mapping):
        raise TypeError("random_seeds_by_frame must be a mapping")
    if set(random_seeds_by_frame) != set(frame_ids):
        raise ValueError(
            "random_seeds_by_frame must contain every frame id and no unknown frame ids"
        )
    for frame_id in frame_ids:
        seed = random_seeds_by_frame[frame_id]
        if type(seed) is not int or not 1 <= seed <= _MAX_RANDOM_SEED:
            raise ValueError(
                f"random seed for {frame_id} must be between 1 and 2^64-1"
            )


__all__ = [
    "VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL",
    "VisualSignatureEmphasisCadencePlanner",
    "VisualSignatureEmphasisDecision",
]
