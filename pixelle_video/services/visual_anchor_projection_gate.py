from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_anchor_policy import (
    contains_forbidden_overlay_language,
    is_scene_bound_anchor_candidate,
)
from pixelle_video.services.visual_signature_clause_renderer import render_visual_anchor_plan_clause
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualAnchorProjectionGateResult:
    passed: bool
    anchor_clause: str = ""
    code: str = "passed"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "anchor_clause": self.anchor_clause,
            "code": self.code,
            "reason": self.reason,
        }


def validate_visual_anchor_projection(
    visual_anchor_plan: VisualAnchorPlacementPlan | None,
    *,
    policy: VisualSignaturePolicy | None = None,
) -> VisualAnchorProjectionGateResult:
    policy = policy or load_visual_signature_policy()
    if not visual_anchor_plan or not visual_anchor_plan.visible:
        return VisualAnchorProjectionGateResult(
            passed=False,
            code="visible_anchor_plan_missing",
            reason="visible anchor plan missing",
        )

    clause = render_visual_anchor_plan_clause(visual_anchor_plan, policy=policy)
    if not clause:
        return VisualAnchorProjectionGateResult(
            passed=False,
            code="anchor_clause_rejected",
            reason="anchor clause could not be rendered as provider-facing visual language",
        )
    if contains_forbidden_overlay_language(clause, policy=policy):
        return VisualAnchorProjectionGateResult(
            passed=False,
            code="forbidden_overlay_language",
            reason="anchor clause contains forbidden overlay language",
        )
    if policy.contains_forbidden_final_prompt_text(clause):
        return VisualAnchorProjectionGateResult(
            passed=False,
            code="forbidden_final_prompt_text",
            reason="anchor clause contains forbidden final prompt text",
        )
    if not is_scene_bound_anchor_candidate(
        image_prompt_clause=clause,
        support_anchor=visual_anchor_plan.support_anchor,
        placement=visual_anchor_plan.placement_zone,
        contact_relation=visual_anchor_plan.contact_relation,
        carrier_type=visual_anchor_plan.anchor_carrier_type,
        policy=policy,
    ):
        return VisualAnchorProjectionGateResult(
            passed=False,
            code="scene_bound_anchor_rejected",
            reason="anchor clause is not bound to a concrete in-scene content action or legacy carrier",
        )
    return VisualAnchorProjectionGateResult(
        passed=True,
        anchor_clause=clause,
    )


__all__ = [
    "VisualAnchorProjectionGateResult",
    "validate_visual_anchor_projection",
]
