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
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_anchor_policy import (
    contains_forbidden_overlay_language,
    is_scene_bound_anchor_candidate,
    sanitize_provider_anchor_clause,
)
from pixelle_video.services.visual_signature_clause_renderer import (
    render_visual_signature_candidate_clause,
)
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


class VisualAnchorAffordanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_surfaces: list[str] = Field(default_factory=list)
    replaceable_minor_elements: list[str] = Field(default_factory=list)
    safe_edges: list[str] = Field(default_factory=list)
    forbidden_zones: list[str] = Field(default_factory=list)

    @field_validator("safe_edges")
    @classmethod
    def _reject_canvas_edges(cls, values: list[str]) -> list[str]:
        policy = load_visual_signature_policy()
        return [
            value
            for value in values
            if not contains_forbidden_overlay_language(value, policy=policy)
        ]


class VisualAnchorIntegrationCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier_type: AnchorCarrierType = AnchorCarrierType.BOOKPLATE_OR_STAMP
    anchor_function: AnchorFunction = AnchorFunction.MATERIAL_SIGNATURE
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
    def _normalize_fields(self) -> "VisualAnchorIntegrationCandidateResponse":
        object.__setattr__(self, "scene_coherence_score", _clamp_score(self.scene_coherence_score))
        object.__setattr__(self, "disruption_risk", _clamp_score(self.disruption_risk))
        object.__setattr__(
            self, "identity_preservation_score", _clamp_score(self.identity_preservation_score)
        )
        object.__setattr__(self, "image_prompt_clause", sanitize_provider_anchor_clause(self.image_prompt_clause))
        return self

    @property
    def is_suppressed(self) -> bool:
        return self.carrier_type is AnchorCarrierType.SUPPRESSED or self.prominence is AnchorProminence.HIDDEN


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

    def selected_candidate(
        self,
        *,
        policy: VisualSignaturePolicy | None = None,
    ) -> VisualAnchorIntegrationCandidateResponse | None:
        policy = policy or load_visual_signature_policy()
        valid_candidates = [
            candidate for candidate in self.candidates if _candidate_is_usable(candidate, policy=policy)
        ]
        if not valid_candidates:
            return None

        if self.candidates:
            index = min(max(int(self.selected_index or 0), 0), len(self.candidates) - 1)
            selected = self.candidates[index]
            if _candidate_is_usable(selected, policy=policy):
                return selected

        if policy.prefer_suppressed_when_uncertain:
            suppressed = [candidate for candidate in valid_candidates if candidate.is_suppressed]
            if suppressed:
                return sorted(suppressed, key=lambda candidate: -candidate.scene_coherence_score)[0]

        return sorted(
            valid_candidates,
            key=lambda candidate: (
                candidate.is_suppressed,
                candidate.disruption_risk,
                -candidate.scene_coherence_score,
                -candidate.identity_preservation_score,
            ),
        )[0]

    def to_placement_plan(
        self,
        fallback: VisualAnchorPlacementPlan | None = None,
        *,
        policy: VisualSignaturePolicy | None = None,
    ) -> VisualAnchorPlacementPlan:
        policy = policy or load_visual_signature_policy()
        candidate = self.selected_candidate(policy=policy)
        if candidate is None:
            if fallback is not None and fallback.visible and not policy.fail_closed_on_rejected_candidate:
                return fallback
            return _hidden_plan(self.frame_id, reason="llm_no_usable_candidate")

        if candidate.is_suppressed:
            return _hidden_plan(self.frame_id, reason=candidate.reason or "llm_selected_suppressed")

        clause = render_visual_signature_candidate_clause(
            carrier_type=candidate.carrier_type,
            support_anchor=candidate.support_anchor,
            contact_relation=candidate.contact_relation,
            placement=candidate.placement,
            source_text=candidate.image_prompt_clause,
            policy=policy,
        )
        if contains_forbidden_overlay_language(clause, policy=policy) or not is_scene_bound_anchor_candidate(
            image_prompt_clause=clause,
            support_anchor=candidate.support_anchor,
            placement=candidate.placement,
            contact_relation=candidate.contact_relation,
            carrier_type=candidate.carrier_type,
            policy=policy,
        ):
            if fallback is not None and fallback.visible and not policy.fail_closed_on_rejected_candidate:
                return fallback
            return _hidden_plan(self.frame_id, reason="llm_candidate_rejected_by_scene_bound_gate")

        return VisualAnchorPlacementPlan(
            frame_id=self.frame_id,
            anchor_function=candidate.anchor_function,
            anchor_carrier_type=candidate.carrier_type,
            anchor_prominence=candidate.prominence,
            visual_weight_clause=candidate.visual_weight_clause,
            placement_zone=candidate.placement,
            support_anchor=candidate.support_anchor,
            scale_ratio=candidate.visual_weight_clause,
            depth_layer=_depth_layer_from_placement(candidate.placement, candidate.support_anchor),
            contact_relation=candidate.contact_relation,
            interaction_target=candidate.interaction_target,
            occlusion_relation=candidate.occlusion_relation,
            style_relation=candidate.style_relation,
            image_prompt_clause=clause,
            metadata={
                "source": "llm_visual_anchor_integration",
                "policy": policy.version,
                "scene_coherence_score": candidate.scene_coherence_score,
                "disruption_risk": candidate.disruption_risk,
                "identity_preservation_score": candidate.identity_preservation_score,
                "reason": candidate.reason,
                "affordance": self.affordance.model_dump(),
                "candidate_count": len(self.candidates),
                "projection": "deterministic_visual_signature_clause_renderer",
            },
        )


class VisualAnchorIntegrationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_anchor_integration_plans: list[VisualAnchorIntegrationPlanResponse]


def _candidate_is_usable(
    candidate: VisualAnchorIntegrationCandidateResponse,
    *,
    policy: VisualSignaturePolicy,
) -> bool:
    if candidate.is_suppressed:
        return True
    clause = render_visual_signature_candidate_clause(
        carrier_type=candidate.carrier_type,
        support_anchor=candidate.support_anchor,
        contact_relation=candidate.contact_relation,
        placement=candidate.placement,
        source_text=candidate.image_prompt_clause,
        policy=policy,
    )
    return is_scene_bound_anchor_candidate(
        image_prompt_clause=clause,
        support_anchor=candidate.support_anchor,
        placement=candidate.placement,
        contact_relation=candidate.contact_relation,
        carrier_type=candidate.carrier_type,
        policy=policy,
    )


def _hidden_plan(frame_id: str, *, reason: str) -> VisualAnchorPlacementPlan:
    return VisualAnchorPlacementPlan(
        frame_id=frame_id,
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
        metadata={"source": reason, "policy": "visual_signature_fail_closed"},
    )


def _clamp_score(value: Any) -> int:
    try:
        score = int(value)
    except Exception:
        return 5
    return min(max(score, 1), 10)


def _depth_layer_from_placement(placement: str, support_anchor: str = "") -> str:
    text = f"{placement} {support_anchor}"
    if any(token in text for token in ("书页", "纸面", "卡片", "文件", "桌面", "书签")):
        return "附着在前景或中景实物表面"
    if any(token in text for token in ("背景", "远处", "墙面", "窗边", "路牌", "招牌")):
        return "附着在背景环境实物表面"
    return "附着在场景内实物表面"


__all__ = [
    "VisualAnchorAffordanceResponse",
    "VisualAnchorIntegrationCandidateResponse",
    "VisualAnchorIntegrationPlanResponse",
    "VisualAnchorIntegrationResponse",
]
