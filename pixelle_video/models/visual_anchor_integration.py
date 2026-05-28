from __future__ import annotations

from collections.abc import Mapping, Sequence
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

    @classmethod
    def from_untrusted_payload(
        cls,
        payload: Any,
        *,
        frame_ids: Sequence[str] = (),
    ) -> "VisualAnchorIntegrationResponse":
        """Repair loose LLM JSON before strict model validation.

        Image-planning LLMs may return almost-correct JSON such as
        ``{"affordance": null, "candidates": "selected_index"}``. The runtime policy is
        fail-closed, so malformed plans are repaired into explicit suppressed candidates
        instead of raising a large Pydantic validation error and polluting logs.
        """

        if isinstance(payload, cls):
            return payload
        normalized = _normalize_response_payload(payload, frame_ids=tuple(frame_ids))
        return cls.model_validate(normalized)


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


def _normalize_response_payload(payload: Any, *, frame_ids: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        raw_plans = (
            payload.get("visual_anchor_integration_plans")
            or payload.get("plans")
            or payload.get("frames")
            or payload.get("items")
            or []
        )
    elif _is_sequence(payload):
        raw_plans = payload
    else:
        raw_plans = []

    if isinstance(raw_plans, Mapping):
        raw_plans = list(raw_plans.values())
    if not _is_sequence(raw_plans):
        raw_plans = []

    raw_plan_list = list(raw_plans)
    target_count = max(len(raw_plan_list), len(frame_ids))
    plans = []
    for index in range(target_count):
        raw_plan = raw_plan_list[index] if index < len(raw_plan_list) else {}
        fallback_frame_id = frame_ids[index] if index < len(frame_ids) else f"frame_{index + 1:04d}"
        plans.append(_normalize_plan_payload(raw_plan, fallback_frame_id=fallback_frame_id))
    return {"visual_anchor_integration_plans": plans}


def _normalize_plan_payload(raw_plan: Any, *, fallback_frame_id: str) -> dict[str, Any]:
    plan = dict(raw_plan) if isinstance(raw_plan, Mapping) else {}
    frame_id = _first_text(
        plan.get("frame_id"),
        plan.get("scene_id"),
        plan.get("id"),
        fallback_frame_id,
    )
    affordance = plan.get("affordance")
    if not isinstance(affordance, Mapping):
        affordance = {}

    raw_candidates = plan.get("candidates")
    if isinstance(raw_candidates, Mapping):
        candidate_items = [raw_candidates]
    elif _is_sequence(raw_candidates):
        candidate_items = list(raw_candidates)
    elif _plan_has_flat_candidate_fields(plan):
        candidate_items = [plan]
    else:
        candidate_items = [_suppressed_candidate_payload("malformed_or_missing_candidates")]

    candidates = [_normalize_candidate_payload(item) for item in candidate_items]
    if not candidates:
        candidates = [_suppressed_candidate_payload("empty_candidates")]

    return {
        "frame_id": frame_id,
        "affordance": dict(affordance),
        "candidates": candidates,
        "selected_index": _safe_int(plan.get("selected_index"), 0),
    }


def _normalize_candidate_payload(raw_candidate: Any) -> dict[str, Any]:
    if not isinstance(raw_candidate, Mapping):
        return _suppressed_candidate_payload("malformed_candidate")

    candidate = dict(raw_candidate)
    carrier_type = _enum_value(
        candidate.get("carrier_type"),
        AnchorCarrierType,
        default=AnchorCarrierType.SUPPRESSED.value,
        aliases={
            "none": AnchorCarrierType.SUPPRESSED.value,
            "not_present": AnchorCarrierType.SUPPRESSED.value,
            "hidden": AnchorCarrierType.SUPPRESSED.value,
            "absent": AnchorCarrierType.SUPPRESSED.value,
            "suppress": AnchorCarrierType.SUPPRESSED.value,
        },
    )
    suppressed = carrier_type == AnchorCarrierType.SUPPRESSED.value
    return {
        "carrier_type": carrier_type,
        "anchor_function": _enum_value(
            candidate.get("anchor_function"),
            AnchorFunction,
            default=AnchorFunction.SUPPRESSED.value if suppressed else AnchorFunction.MATERIAL_SIGNATURE.value,
            aliases={"not_present": AnchorFunction.SUPPRESSED.value, "hidden": AnchorFunction.SUPPRESSED.value},
        ),
        "prominence": _enum_value(
            candidate.get("prominence"),
            AnchorProminence,
            default=AnchorProminence.HIDDEN.value if suppressed else AnchorProminence.EMBEDDED_MARK.value,
            aliases={"suppressed": AnchorProminence.HIDDEN.value, "not_present": AnchorProminence.HIDDEN.value},
        ),
        "style_relation": _enum_value(
            candidate.get("style_relation"),
            AnchorStyleRelation,
            default=AnchorStyleRelation.BLENDED.value,
        ),
        "placement": _first_text(candidate.get("placement")),
        "support_anchor": _first_text(candidate.get("support_anchor")),
        "contact_relation": _first_text(candidate.get("contact_relation")),
        "interaction_target": _first_text(candidate.get("interaction_target")),
        "occlusion_relation": _first_text(candidate.get("occlusion_relation")),
        "visual_weight_clause": _first_text(candidate.get("visual_weight_clause")),
        "image_prompt_clause": _first_text(candidate.get("image_prompt_clause")),
        "scene_coherence_score": _safe_int(candidate.get("scene_coherence_score"), 5),
        "disruption_risk": _safe_int(candidate.get("disruption_risk"), 5),
        "identity_preservation_score": _safe_int(candidate.get("identity_preservation_score"), 5),
        "reason": _first_text(candidate.get("reason")) or ("suppressed malformed candidate" if suppressed else ""),
    }


def _suppressed_candidate_payload(reason: str) -> dict[str, Any]:
    return {
        "carrier_type": AnchorCarrierType.SUPPRESSED.value,
        "anchor_function": AnchorFunction.SUPPRESSED.value,
        "prominence": AnchorProminence.HIDDEN.value,
        "style_relation": AnchorStyleRelation.BLENDED.value,
        "placement": "",
        "support_anchor": "",
        "contact_relation": "",
        "interaction_target": "",
        "occlusion_relation": "",
        "visual_weight_clause": "",
        "image_prompt_clause": "",
        "scene_coherence_score": 5,
        "disruption_risk": 1,
        "identity_preservation_score": 1,
        "reason": reason,
    }


def _plan_has_flat_candidate_fields(plan: Mapping[str, Any]) -> bool:
    return any(
        key in plan
        for key in (
            "carrier_type",
            "anchor_function",
            "prominence",
            "support_anchor",
            "image_prompt_clause",
        )
    )


def _enum_value(
    value: Any,
    enum_cls: Any,
    *,
    default: str,
    aliases: Mapping[str, str] | None = None,
) -> str:
    text = _first_text(value)
    if not text:
        return default
    lowered = text.lower()
    if aliases and lowered in aliases:
        return aliases[lowered]
    try:
        return enum_cls(text).value
    except ValueError:
        return default


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
