from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)


class VisualAnchorAffordanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_surfaces: list[str] = Field(default_factory=list)
    replaceable_minor_elements: list[str] = Field(default_factory=list)
    safe_edges: list[str] = Field(default_factory=list)
    forbidden_zones: list[str] = Field(default_factory=list)


class VisualAnchorIntegrationCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier_type: AnchorCarrierType = AnchorCarrierType.EMBEDDED_MARK
    anchor_function: AnchorFunction = AnchorFunction.EMBEDDED_MARK
    prominence: AnchorProminence = AnchorProminence.EMBEDDED_MARK
    style_relation: AnchorStyleRelation = AnchorStyleRelation.BLENDED
    placement: str = ""
    support_anchor: str = ""
    contact_relation: str = ""
    interaction_target: str = ""
    occlusion_relation: str = ""
    visual_weight_clause: str = ""
    image_prompt_clause: str = ""
    scene_coherence_score: int = 5
    disruption_risk: int = 5
    identity_preservation_score: int = 5
    reason: str = ""

    @model_validator(mode="after")
    def _normalize_scores(self) -> "VisualAnchorIntegrationCandidateResponse":
        object.__setattr__(self, "scene_coherence_score", _clamp_score(self.scene_coherence_score))
        object.__setattr__(self, "disruption_risk", _clamp_score(self.disruption_risk))
        object.__setattr__(self, "identity_preservation_score", _clamp_score(self.identity_preservation_score))
        return self


class VisualAnchorIntegrationPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: str
    affordance: VisualAnchorAffordanceResponse = Field(default_factory=VisualAnchorAffordanceResponse)
    candidates: list[VisualAnchorIntegrationCandidateResponse] = Field(default_factory=list)
    selected_index: int = 0

    @field_validator("frame_id", mode="before")
    @classmethod
    def _validate_frame_id(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("frame_id must not be empty")
        return text

    def selected_candidate(self) -> VisualAnchorIntegrationCandidateResponse | None:
        if not self.candidates:
            return None
        index = min(max(int(self.selected_index or 0), 0), len(self.candidates) - 1)
        return self.candidates[index]

    def to_placement_plan(self, fallback: VisualAnchorPlacementPlan | None = None) -> VisualAnchorPlacementPlan:
        candidate = self.selected_candidate()
        if candidate is None or not str(candidate.image_prompt_clause or "").strip():
            if fallback is not None:
                return fallback
            return VisualAnchorPlacementPlan(
                frame_id=self.frame_id,
                anchor_function=AnchorFunction.SUPPRESSED,
                anchor_carrier_type=AnchorCarrierType.SUPPRESSED,
                anchor_prominence=AnchorProminence.HIDDEN,
                visual_weight_clause="",
                placement_zone="",
                support_anchor="",
                scale_ratio="",
                depth_layer="",
                contact_relation="",
                interaction_target="",
                occlusion_relation="",
                style_relation=AnchorStyleRelation.BLENDED,
                image_prompt_clause="",
                metadata={"source": "llm_empty_candidate"},
            )
        return VisualAnchorPlacementPlan(
            frame_id=self.frame_id,
            anchor_function=candidate.anchor_function,
            anchor_carrier_type=candidate.carrier_type,
            anchor_prominence=candidate.prominence,
            visual_weight_clause=candidate.visual_weight_clause,
            placement_zone=candidate.placement,
            support_anchor=candidate.support_anchor,
            scale_ratio=candidate.visual_weight_clause,
            depth_layer=_depth_layer_from_placement(candidate.placement),
            contact_relation=candidate.contact_relation,
            interaction_target=candidate.interaction_target,
            occlusion_relation=candidate.occlusion_relation,
            style_relation=candidate.style_relation,
            image_prompt_clause=candidate.image_prompt_clause,
            metadata={
                "source": "llm_visual_anchor_integration",
                "scene_coherence_score": candidate.scene_coherence_score,
                "disruption_risk": candidate.disruption_risk,
                "identity_preservation_score": candidate.identity_preservation_score,
                "reason": candidate.reason,
                "affordance": self.affordance.model_dump(),
                "candidate_count": len(self.candidates),
            },
        )


class VisualAnchorIntegrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_anchor_integration_plans: list[VisualAnchorIntegrationPlanResponse]


def _clamp_score(value: Any) -> int:
    try:
        score = int(value)
    except Exception:
        return 5
    return min(max(score, 1), 10)


def _depth_layer_from_placement(value: str) -> str:
    text = str(value or "")
    if any(token in text for token in ("前景", "下方", "角落", "桌面")):
        return "前景或画面边缘"
    if any(token in text for token in ("背景", "远处", "墙面", "窗边")):
        return "背景边缘"
    return "画面边缘层"


__all__ = [
    "VisualAnchorAffordanceResponse",
    "VisualAnchorIntegrationCandidateResponse",
    "VisualAnchorIntegrationPlanResponse",
    "VisualAnchorIntegrationResponse",
]
