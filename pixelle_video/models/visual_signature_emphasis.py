from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.models.frame_identity import normalize_storyboard_frame_id

VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION = "visual_signature_emphasis_cadence.v2"
VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL = 10


class VisualSignatureEmphasis(str, Enum):
    """Series-level visual prominence assigned before per-frame model calls."""

    STANDARD = "standard"
    ENHANCED = "enhanced"


class VisualSignatureEmphasisDecision(BaseModel):
    """One replayable series-level emphasis decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_id: str
    frame_index: int = Field(ge=1)
    emphasis: VisualSignatureEmphasis
    selection_window_index: int | None = Field(default=None, ge=0)

    @field_validator("frame_id", mode="before")
    @classmethod
    def _normalize_frame_id(cls, value: Any) -> str:
        return normalize_storyboard_frame_id(value)

    @model_validator(mode="after")
    def _validate_selection_window_contract(
        self,
    ) -> "VisualSignatureEmphasisDecision":
        is_enhanced = self.emphasis is VisualSignatureEmphasis.ENHANCED
        has_window = self.selection_window_index is not None
        if is_enhanced != has_window:
            raise ValueError("enhanced emphasis and selection_window_index must be set together")
        return self


class VisualSignatureEmphasisCadencePlan(BaseModel):
    """Versioned cadence contract persisted with the generated frame batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cadence_version: Literal[VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION] = (
        VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION
    )
    storyboard_plan_id: str = Field(min_length=1)
    selection_input_sha256: str
    frame_interval: Literal[VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL] = (
        VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL
    )
    enhanced_frame_count: int = Field(ge=1)
    decisions: tuple[VisualSignatureEmphasisDecision, ...] = Field(min_length=1)

    @field_validator("storyboard_plan_id", mode="before")
    @classmethod
    def _validate_storyboard_plan_id(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("storyboard_plan_id must be a string")
        if not value.strip():
            raise ValueError("storyboard_plan_id must be a non-empty string")
        return value

    @field_validator("selection_input_sha256", mode="before")
    @classmethod
    def _validate_selection_input_digest(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("selection_input_sha256 must be a string")
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("selection_input_sha256 must be a lowercase SHA-256 digest")
        return normalized

    @model_validator(mode="after")
    def _validate_cadence_contract(self) -> "VisualSignatureEmphasisCadencePlan":
        expected_indexes = list(range(1, len(self.decisions) + 1))
        actual_indexes = [decision.frame_index for decision in self.decisions]
        if actual_indexes != expected_indexes:
            raise ValueError("decision frame indexes must start at 1 and be contiguous")

        frame_ids = [decision.frame_id for decision in self.decisions]
        if len(set(frame_ids)) != len(frame_ids):
            raise ValueError("decision frame ids must be unique")

        expected_enhanced_count = (
            len(self.decisions) + self.frame_interval - 1
        ) // self.frame_interval
        if self.enhanced_frame_count != expected_enhanced_count:
            raise ValueError("enhanced_frame_count must equal the rounded-up cadence budget")

        enhanced_decisions = [
            decision
            for decision in self.decisions
            if decision.emphasis is VisualSignatureEmphasis.ENHANCED
        ]
        if len(enhanced_decisions) != self.enhanced_frame_count:
            raise ValueError("enhanced_frame_count must match the enhanced decisions")

        actual_windows = [decision.selection_window_index for decision in enhanced_decisions]
        if actual_windows != list(range(self.enhanced_frame_count)):
            raise ValueError("enhanced decisions must cover each selection window exactly once")

        decision_count = len(self.decisions)
        for window_index, decision in enumerate(enhanced_decisions):
            window_start = window_index * decision_count // self.enhanced_frame_count
            window_end = (
                (window_index + 1) * decision_count // self.enhanced_frame_count
            )
            decision_position = decision.frame_index - 1
            if not window_start <= decision_position < window_end:
                raise ValueError(
                    "enhanced decisions must remain inside their balanced windows"
                )

        enhanced_indexes = [decision.frame_index for decision in enhanced_decisions]
        if any(
            current_index - previous_index < 3
            for previous_index, current_index in zip(
                enhanced_indexes,
                enhanced_indexes[1:],
            )
        ):
            raise ValueError("enhanced decisions must be at least three frames apart")
        return self


__all__ = [
    "VISUAL_SIGNATURE_EMPHASIS_CADENCE_VERSION",
    "VISUAL_SIGNATURE_EMPHASIS_FRAME_INTERVAL",
    "VisualSignatureEmphasis",
    "VisualSignatureEmphasisCadencePlan",
    "VisualSignatureEmphasisDecision",
]
