from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.visual_anchor_integration import VisualAnchorIntegrationResponse
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.prompts.visual_anchor_integration import render_visual_anchor_integration_prompt
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


@dataclass(frozen=True)
class VisualAnchorIntegrationPlanner:
    """LLM-first visual anchor integration planner with deterministic fallback."""

    llm_service: Any | None = None

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
        fallback_plans = VisualAnchorPlacementPlanner().plan_batch(
            base_visual_briefs=base_visual_briefs,
            anchor_profile=anchor_profile,
            base_packages=base_packages,
            frame_contexts=frame_contexts,
            frame_plans=frame_plans,
        )
        if anchor_profile is None or self.llm_service is None or not base_visual_briefs:
            return fallback_plans

        rendered_prompt = render_visual_anchor_integration_prompt(
            base_visual_briefs_json=[brief.to_dict() for brief in base_visual_briefs],
            anchor_profile_json=_anchor_profile_payload(anchor_profile),
        )
        try:
            response: VisualAnchorIntegrationResponse = await self.llm_service(
                prompt=rendered_prompt.text,
                response_type=VisualAnchorIntegrationResponse,
                temperature=0.2,
                max_tokens=4000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
        except Exception as exc:
            logger.warning(f"visual anchor integration planning failed; using deterministic fallback: {exc}")
            return fallback_plans

        by_frame = {plan.frame_id: plan for plan in response.visual_anchor_integration_plans}
        result: list[VisualAnchorPlacementPlan] = []
        for index, brief in enumerate(base_visual_briefs):
            fallback = fallback_plans[index] if index < len(fallback_plans) else None
            llm_plan = by_frame.get(brief.frame_id)
            if llm_plan is None:
                if fallback is not None:
                    result.append(fallback)
                continue
            result.append(llm_plan.to_placement_plan(fallback=fallback))
        return tuple(result)


def _anchor_profile_payload(anchor_profile: IPProfile) -> dict[str, Any]:
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
        "guidance": [
            "The anchor is a recurring channel signature, not a default protagonist.",
            "Prefer in-world mark, sticker, label, icon, figurine, wall art, or minor background detail when main subjects are clear.",
            "Preserve only the identity kernel needed for recognition.",
            "Never replace named source subjects or key props.",
            "Do not use a canvas corner logo or floating watermark.",
        ],
    }


__all__ = ["VisualAnchorIntegrationPlanner"]
