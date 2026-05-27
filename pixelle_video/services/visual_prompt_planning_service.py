from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import RenderedMediaPrompt
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_style_contract import VisualStyleLayerContract
from pixelle_video.services.base_visual_brief_planner import BaseVisualBriefPlanner
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


@dataclass(frozen=True)
class VisualPromptPlanningResult:
    base_visual_briefs: tuple[BaseVisualBrief, ...]
    visual_anchor_plans: tuple[VisualAnchorPlacementPlan, ...]
    anchor_packages: tuple[IPFrameAdaptationPackage, ...]
    rendered_prompts: tuple[RenderedMediaPrompt, ...]

    def planning_snapshot(self) -> dict[str, Any]:
        return {
            "base_visual_briefs_by_frame": {brief.frame_id: brief.to_dict() for brief in self.base_visual_briefs},
            "visual_anchor_placement_by_frame": {plan.frame_id: plan.to_dict() for plan in self.visual_anchor_plans},
        }


@dataclass(frozen=True)
class VisualPromptPlanningService:
    """Subject-first visual prompt planning pipeline."""

    def plan_image_prompts(
        self,
        *,
        base_prompts: Sequence[str],
        frame_contexts: Sequence[Mapping[str, Any]],
        frame_plans: Sequence[Any] = (),
        visual_style_contract: VisualStyleLayerContract | None = None,
        generation_world_profile: Any = None,
        world_preset: Mapping[str, Any] | None = None,
        visual_anchor_enabled: bool = False,
        anchor_profile: IPProfile | None = None,
        base_anchor_packages: Sequence[IPFrameAdaptationPackage] = (),
        workflow: str | None = None,
        capabilities: Any = None,
        extra_negative_rules: Sequence[str] = (),
    ) -> VisualPromptPlanningResult:
        base_visual_briefs = BaseVisualBriefPlanner().plan_batch(
            base_prompts=base_prompts,
            frame_contexts=frame_contexts,
            frame_plans=frame_plans,
            visual_style_contract=visual_style_contract,
            generation_world_profile=generation_world_profile,
            world_preset=world_preset,
        )
        visual_anchor_plans = (
            VisualAnchorPlacementPlanner().plan_batch(
                base_visual_briefs=base_visual_briefs,
                anchor_profile=anchor_profile,
                base_packages=base_anchor_packages,
                frame_contexts=frame_contexts,
                frame_plans=frame_plans,
            )
            if visual_anchor_enabled and anchor_profile is not None
            else tuple()
        )
        anchor_packages = tuple(
            plan.to_ip_frame_adaptation_package(base_anchor_packages[index])
            for index, plan in enumerate(visual_anchor_plans)
            if index < len(base_anchor_packages)
        )
        projector = ProviderPromptProjector()
        rendered_prompts = tuple(
            projector.project(
                base_visual_brief=brief,
                visual_anchor_plan=visual_anchor_plans[index] if index < len(visual_anchor_plans) else None,
                negative_rules=extra_negative_rules,
                capabilities=capabilities,
                workflow=workflow,
            )
            for index, brief in enumerate(base_visual_briefs)
        )
        return VisualPromptPlanningResult(
            base_visual_briefs=base_visual_briefs,
            visual_anchor_plans=visual_anchor_plans,
            anchor_packages=anchor_packages,
            rendered_prompts=rendered_prompts,
        )


__all__ = ["VisualPromptPlanningResult", "VisualPromptPlanningService"]
