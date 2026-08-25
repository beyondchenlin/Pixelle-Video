from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.visual_signature_emphasis import (
    VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION,
    VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL,
    VisualSignatureEmphasis,
    VisualSignatureEmphasisCadencePlan,
    VisualSignatureEmphasisDecision,
)

_SELECTION_NAMESPACE = VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION.encode("ascii")


@dataclass(frozen=True, slots=True)
class VisualSignatureEmphasisCadencePlanner:
    """Allocate the fixed rounded-up ten-percent budget from storyboard semantics."""

    def plan(
        self,
        *,
        storyboard_plan: StoryboardPlan,
    ) -> VisualSignatureEmphasisCadencePlan:
        if not isinstance(storyboard_plan, StoryboardPlan):
            raise TypeError("storyboard_plan must be a StoryboardPlan")

        frames = storyboard_plan.frames
        frame_source_sha256s = tuple(
            hashlib.sha256(frame.source_text.encode("utf-8")).hexdigest()
            for frame in frames
        )

        enhanced_count = (
            len(frames) + VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL - 1
        ) // VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL
        selected_window_by_position: dict[int, int] = {}
        for window_index in range(enhanced_count):
            start = window_index * len(frames) // enhanced_count
            end = (window_index + 1) * len(frames) // enhanced_count
            candidate_start = start + (1 if window_index > 0 else 0)
            candidate_end = end - (1 if window_index + 1 < enhanced_count else 0)
            if candidate_start >= candidate_end:
                raise RuntimeError("cadence selection window has no valid candidates")
            selected_position = min(
                range(candidate_start, candidate_end),
                key=lambda position: _selection_digest(
                    frame_index=frames[position].index,
                    frame_source_sha256=frame_source_sha256s[position],
                    window_index=window_index,
                ),
            )
            selected_window_by_position[selected_position] = window_index

        return VisualSignatureEmphasisCadencePlan(
            storyboard_plan_id=storyboard_plan.plan_id,
            selection_input_sha256=_selection_input_sha256(
                frame_source_sha256s=frame_source_sha256s,
            ),
            enhanced_frame_count=enhanced_count,
            decisions=tuple(
                VisualSignatureEmphasisDecision(
                    frame_id=frame.frame_id,
                    frame_index=frame.index,
                    emphasis=(
                        VisualSignatureEmphasis.ENHANCED
                        if position in selected_window_by_position
                        else VisualSignatureEmphasis.STANDARD
                    ),
                    selection_window_index=selected_window_by_position.get(position),
                )
                for position, frame in enumerate(frames)
            ),
        )


def _selection_digest(
    *,
    frame_index: int,
    frame_source_sha256: str,
    window_index: int,
) -> bytes:
    digest = hashlib.sha256()
    digest.update(_SELECTION_NAMESPACE)
    digest.update(window_index.to_bytes(8, byteorder="big", signed=False))
    digest.update(frame_index.to_bytes(8, byteorder="big", signed=False))
    digest.update(bytes.fromhex(frame_source_sha256))
    return digest.digest()


def _selection_input_sha256(
    *,
    frame_source_sha256s: tuple[str, ...],
) -> str:
    return _canonical_sha256(
        {
            "cadence_version": VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION,
            "frame_interval": VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL,
            "frame_source_sha256s": frame_source_sha256s,
        }
    )


def _canonical_sha256(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = [
    "VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION",
    "VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL",
    "VisualSignatureEmphasisCadencePlanner",
    "VisualSignatureEmphasisCadencePlan",
    "VisualSignatureEmphasisDecision",
]
