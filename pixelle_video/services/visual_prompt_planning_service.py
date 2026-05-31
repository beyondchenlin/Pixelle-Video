from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import RenderedMediaPrompt
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_role_profile import VisualRoleProfile
from pixelle_video.models.visual_role_request import (
    VisualRoleRequest,
    is_supported_visual_role_pipeline_version,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.models.visual_role_strategy import VisualRoleStrategyControls
from pixelle_video.models.visual_style_contract import VisualStyleLayerContract
from pixelle_video.services.base_visual_brief_planner import BaseVisualBriefPlanner
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
from pixelle_video.services.visual_anchor_integration_planner import VisualAnchorIntegrationPlanner
from pixelle_video.services.visual_expression_classifier import VisualExpressionClassifier
from pixelle_video.services.visual_role_prompt_critic import VisualRolePromptCritic
from pixelle_video.services.visual_role_prompt_projector import VisualRolePromptProjector
from pixelle_video.services.visual_role_repair_loop import VisualRoleRepairLoop
from pixelle_video.services.visual_role_scene_planner import VisualRoleScenePlanner
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualPromptPlanningResult:
    base_visual_briefs: tuple[BaseVisualBrief, ...]
    visual_anchor_plans: tuple[VisualAnchorPlacementPlan, ...]
    anchor_packages: tuple[IPFrameAdaptationPackage, ...]
    rendered_prompts: tuple[RenderedMediaPrompt, ...]
    visual_expression_decisions: tuple[Any, ...] = ()
    visual_role_plans: tuple[Any, ...] = ()
    visual_role_critiques: tuple[Any, ...] = ()
    visual_role_repair_attempts: Mapping[str, Any] | None = None
    visual_role_request: VisualRoleRequest | None = None
    visual_role_profile: VisualRoleProfile | None = None

    def planning_snapshot(self) -> dict[str, Any]:
        snapshot = {
            "base_visual_briefs_by_frame": {brief.frame_id: brief.to_dict() for brief in self.base_visual_briefs},
            "visual_anchor_placement_by_frame": {plan.frame_id: plan.to_dict() for plan in self.visual_anchor_plans},
        }
        if self.visual_role_request is not None:
            snapshot["visual_role_request"] = self.visual_role_request.to_dict()
        if self.visual_role_profile is not None:
            snapshot["visual_role_profile"] = self.visual_role_profile.to_dict()
            snapshot["visual_role_identity_contract"] = (
                self.visual_role_profile.identity_contract.to_dict()
            )
        if self.visual_expression_decisions:
            snapshot["visual_expression_decision_by_frame"] = {decision.frame_id: decision.to_dict() for decision in self.visual_expression_decisions}
        if self.visual_role_plans:
            snapshot["visual_role_plan_by_frame"] = {plan.frame_id: plan.to_dict() for plan in self.visual_role_plans}
        if self.visual_role_critiques:
            snapshot["visual_role_critique_by_frame"] = {critique.frame_id: critique.to_dict() for critique in self.visual_role_critiques}
        projected_parts_by_frame: dict[str, Any] = {}
        for index, rendered in enumerate(self.rendered_prompts):
            parts = dict(rendered.metadata or {}).get("projected_prompt_parts")
            if parts is None:
                continue
            frame_id = (
                self.base_visual_briefs[index].frame_id
                if index < len(self.base_visual_briefs)
                else str(index)
            )
            projected_parts_by_frame[frame_id] = parts
        if projected_parts_by_frame:
            snapshot["visual_role_projected_prompt_parts_by_frame"] = projected_parts_by_frame
        if self.visual_role_repair_attempts:
            snapshot["visual_role_repair_attempts"] = dict(self.visual_role_repair_attempts)
        return snapshot


@dataclass(frozen=True)
class VisualPromptPlanningService:
    """Subject-first visual planning with V4 visual-role routing and V3 compatibility."""

    async def plan_image_prompts(
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
        llm_service: Any | None = None,
        trace_context: Any = None,
        trace_recorder: Any = None,
        visual_signature_policy: VisualSignaturePolicy | None = None,
        visual_expression_mode: str | None = None,
        visual_structure_mode: str | None = None,
        visual_participation_mode: str | None = None,
        visual_role_request: VisualRoleRequest | None = None,
        visual_role_profile: VisualRoleProfile | None = None,
        visual_role_mode: str | None = None,
        visual_consistency_mode: str | None = None,
    ) -> VisualPromptPlanningResult:
        policy = visual_signature_policy or load_visual_signature_policy()
        role_strategy = visual_role_request.strategy if visual_role_request is not None else VisualRoleStrategyControls.from_mapping({
            "visual_role_mode": visual_role_mode,
            "visual_consistency_mode": visual_consistency_mode,
        })
        base_visual_briefs = BaseVisualBriefPlanner().plan_batch(
            base_prompts=base_prompts,
            frame_contexts=frame_contexts,
            frame_plans=frame_plans,
            visual_style_contract=visual_style_contract,
            generation_world_profile=generation_world_profile,
            world_preset=world_preset,
        )

        if (
            visual_role_request is not None
            and visual_role_request.enabled
            and is_supported_visual_role_pipeline_version(visual_role_request.pipeline_version)
        ):
            if visual_role_profile is None:
                raise ValueError("visual_role_profile is required when V4 visual role is enabled")
            decisions = VisualExpressionClassifier().classify_batch(
                frame_contexts=frame_contexts,
                base_visual_briefs=base_visual_briefs,
                visual_expression_mode=visual_expression_mode or visual_role_request.expression_mode,
            )
            plans, critiques, repair_attempts = await VisualRoleRepairLoop().run_batch(
                planner=VisualRoleScenePlanner(llm_service=llm_service),
                critic=VisualRolePromptCritic(llm_service=llm_service),
                base_visual_briefs=base_visual_briefs,
                visual_role_request=visual_role_request,
                visual_role_profile=visual_role_profile,
                expression_decisions=decisions,
                frame_contexts=frame_contexts,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            rendered_prompts = tuple(
                VisualRolePromptProjector().project(
                    base_visual_brief=brief,
                    visual_role_plan=plans[index],
                    visual_role_critique=critiques[index],
                    visual_role_request=visual_role_request,
                    visual_role_profile=visual_role_profile,
                    negative_rules=extra_negative_rules,
                    capabilities=capabilities,
                    workflow=workflow,
                )
                for index, brief in enumerate(base_visual_briefs)
            )
            return VisualPromptPlanningResult(
                base_visual_briefs=base_visual_briefs,
                visual_anchor_plans=tuple(),
                anchor_packages=tuple(),
                rendered_prompts=rendered_prompts,
                visual_expression_decisions=decisions,
                visual_role_plans=plans,
                visual_role_critiques=critiques,
                visual_role_repair_attempts=repair_attempts,
                visual_role_request=visual_role_request,
                visual_role_profile=visual_role_profile,
            )

        visual_anchor_plans = (
            await VisualAnchorIntegrationPlanner(llm_service=llm_service, policy=policy, visual_role_strategy=role_strategy).plan_batch(
                base_visual_briefs=base_visual_briefs,
                anchor_profile=anchor_profile,
                base_packages=base_anchor_packages,
                frame_contexts=frame_contexts,
                frame_plans=frame_plans,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            if visual_anchor_enabled and anchor_profile is not None
            else tuple()
        )
        anchor_packages = tuple(
            plan.to_ip_frame_adaptation_package(base_anchor_packages[index])
            for index, plan in enumerate(visual_anchor_plans)
            if index < len(base_anchor_packages)
        )
        rendered_prompts = tuple(
            ProviderPromptProjector().project(
                base_visual_brief=brief,
                visual_anchor_plan=visual_anchor_plans[index] if index < len(visual_anchor_plans) else None,
                negative_rules=extra_negative_rules,
                capabilities=capabilities,
                workflow=workflow,
                visual_signature_policy=policy,
                visual_role_strategy=role_strategy,
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
