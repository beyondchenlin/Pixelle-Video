from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.visual_anchor_integration import VisualAnchorIntegrationResponse
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.prompts.visual_anchor_integration import render_visual_anchor_integration_prompt
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner
from pixelle_video.services.visual_signature_cadence import VisualSignatureCadencePlanner
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualAnchorIntegrationPlanner:
    """LLM-first visual signature planner with sparse cadence and fail-closed fallback."""

    llm_service: Any | None = None
    policy: VisualSignaturePolicy | None = None

    async def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        anchor_profile: IPProfile | None,
        base_packages: Sequence[IPFrameAdaptationPackage] = (),
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        frame_plans: Sequence[Any] = (),
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[VisualAnchorPlacementPlan, ...]:
        policy = self.policy or load_visual_signature_policy()
        briefs = tuple(base_visual_briefs)
        if anchor_profile is None:
            return tuple(
                _hidden_plan(brief.frame_id, reason="no anchor profile", policy=policy)
                for brief in briefs
            )
        if not briefs:
            return ()

        cadence = VisualSignatureCadencePlanner(policy=policy).plan_batch(
            base_visual_briefs=briefs
        )
        cadence_by_frame = {decision.frame_id: decision for decision in cadence}

        fallback_plans = VisualAnchorPlacementPlanner(policy=policy).plan_batch(
            base_visual_briefs=briefs,
            anchor_profile=anchor_profile,
            base_packages=base_packages,
            frame_contexts=frame_contexts,
            frame_plans=frame_plans,
        )
        fallback_plans = _apply_cadence(
            fallback_plans,
            cadence_by_frame=cadence_by_frame,
            policy=policy,
            source="deterministic_fallback_cadence",
        )

        if self.llm_service is None:
            return fallback_plans

        rendered_prompt = render_visual_anchor_integration_prompt(
            base_visual_briefs_json=[brief.to_dict() for brief in briefs],
            anchor_profile_json=_anchor_profile_payload(anchor_profile, policy=policy),
            visual_signature_policy_json=policy.to_dict(),
            cadence_plan_json=[decision.to_dict() for decision in cadence],
        )
        try:
            raw_response = await self.llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=4000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            response = VisualAnchorIntegrationResponse.from_untrusted_payload(
                raw_response,
                frame_ids=[brief.frame_id for brief in briefs],
            )
        except Exception as exc:
            logger.warning("visual signature integration planning failed: {}", exc)
            if policy.fail_closed_on_llm_error:
                return tuple(
                    _hidden_plan(brief.frame_id, reason="llm_error_fail_closed", policy=policy)
                    for brief in briefs
                )
            return fallback_plans

        by_frame = {plan.frame_id: plan for plan in response.visual_anchor_integration_plans}
        result: list[VisualAnchorPlacementPlan] = []
        for index, brief in enumerate(briefs):
            decision = cadence_by_frame.get(brief.frame_id)
            if decision is not None and not decision.visible_allowed:
                result.append(
                    _hidden_plan(
                        brief.frame_id,
                        reason=f"cadence_hidden:{decision.reason}",
                        policy=policy,
                    )
                )
                continue
            llm_plan = by_frame.get(brief.frame_id)
            if llm_plan is None:
                result.append(
                    _hidden_plan(
                        brief.frame_id,
                        reason="llm_missing_frame_fail_closed",
                        policy=policy,
                    )
                )
                continue
            fallback = fallback_plans[index] if index < len(fallback_plans) else None
            result.append(llm_plan.to_placement_plan(fallback=fallback, policy=policy))
        return tuple(result)


def _apply_cadence(
    plans: Sequence[VisualAnchorPlacementPlan],
    *,
    cadence_by_frame: Mapping[str, Any],
    policy: VisualSignaturePolicy,
    source: str,
) -> tuple[VisualAnchorPlacementPlan, ...]:
    result: list[VisualAnchorPlacementPlan] = []
    for plan in plans:
        decision = cadence_by_frame.get(plan.frame_id)
        if decision is not None and not getattr(decision, "visible_allowed", False):
            result.append(
                _hidden_plan(
                    plan.frame_id,
                    reason=f"{source}:{getattr(decision, 'reason', 'hidden')}",
                    policy=policy,
                )
            )
            continue
        result.append(plan)
    return tuple(result)


def _hidden_plan(
    frame_id: str,
    *,
    reason: str,
    policy: VisualSignaturePolicy,
) -> VisualAnchorPlacementPlan:
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
        metadata={"source": reason, "policy": policy.version},
    )


def _anchor_profile_payload(anchor_profile: IPProfile, *, policy: VisualSignaturePolicy) -> dict[str, Any]:
    return {
        "name": anchor_profile.name,
        "visual_summary": anchor_profile.visual_summary,
        "identity_kernel": [
            *anchor_profile.identity_lock,
            *anchor_profile.minimal_traits,
            *anchor_profile.identity_anchors,
        ],
        "style_hint": anchor_profile.style_hint,
        "negative_constraints": list(anchor_profile.negative_constraints),
        "policy_version": policy.version,
        "guidance": [
            "The recurring identity is a visual signature, not a default protagonist.",
            "Prefer material integration: bookplate, stamp, embossing, engraving, mural, map legend, prop detail, wearable symbol, or a small physical prop resting on an existing support.",
            "Preserve only the smallest identity kernel needed for recognition.",
            "Never replace named source subjects or key props.",
            "When cadence says hidden or no natural scene carrier exists, select suppressed.",
            "Canvas corner marks, watermarks, floating stickers, UI badges, and logo overlays are invalid.",
        ],
    }


__all__ = ["VisualAnchorIntegrationPlanner"]
