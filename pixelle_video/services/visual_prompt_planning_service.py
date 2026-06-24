from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.final_visual_prompt_contract import RenderedMediaPrompt
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignatureEnforcementMode,
    SeriesVisualSignaturePresentationMode,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import (
    SeriesVisualSignatureRequest,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureStrategyControls,
    build_visual_identity_kernel,
)
from pixelle_video.models.visual_anchor_planning import VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.models.visual_style_contract import VisualStyleLayerContract
from pixelle_video.services.base_visual_brief_planner import BaseVisualBriefPlanner
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
from pixelle_video.services.series_visual_signature_anchor_planner import (
    VisualAnchorIntegrationPlanner,
)
from pixelle_video.services.visual_signature_fallback_planner import (
    VisualSignatureFallbackPlanner,
    fallback_ledger_from_plans,
)
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy
from pixelle_video.utils.json_safety import to_json_compatible


@dataclass(frozen=True)
class VisualPromptPlanningResult:
    base_visual_briefs: tuple[BaseVisualBrief, ...]
    visual_anchor_plans: tuple[VisualAnchorPlacementPlan, ...]
    anchor_packages: tuple[IPFrameAdaptationPackage, ...]
    rendered_prompts: tuple[RenderedMediaPrompt, ...]
    visual_expression_decisions: tuple[Any, ...] = ()
    series_visual_signature_plans: tuple[Any, ...] = ()
    series_visual_signature_critiques: tuple[Any, ...] = ()
    series_visual_signature_repair_attempts: Mapping[str, Any] | None = None
    series_visual_signature_request: SeriesVisualSignatureRequest | None = None
    series_visual_signature_profile: SeriesVisualSignatureProfile | None = None
    series_visual_signature_fallback: Mapping[str, Any] | None = None

    def planning_snapshot(self) -> dict[str, Any]:
        snapshot = {
            "base_visual_briefs_by_frame": {brief.frame_id: brief.to_dict() for brief in self.base_visual_briefs},
            "visual_anchor_placement_by_frame": {plan.frame_id: plan.to_dict() for plan in self.visual_anchor_plans},
        }
        if self.series_visual_signature_request is not None:
            snapshot["series_visual_signature_request"] = self.series_visual_signature_request.to_dict()
        if self.series_visual_signature_profile is not None:
            snapshot["series_visual_signature_profile"] = self.series_visual_signature_profile.to_dict()
            snapshot["series_visual_signature_identity_contract"] = (
                self.series_visual_signature_profile.identity_contract.to_dict()
            )
        if self.series_visual_signature_fallback:
            snapshot["series_visual_signature_fallback"] = dict(self.series_visual_signature_fallback)
        if self.visual_expression_decisions:
            snapshot["visual_expression_decision_by_frame"] = {decision.frame_id: decision.to_dict() for decision in self.visual_expression_decisions}
        if self.series_visual_signature_plans:
            snapshot["series_visual_signature_plan_by_frame"] = {plan.frame_id: plan.to_dict() for plan in self.series_visual_signature_plans}
        if self.series_visual_signature_critiques:
            snapshot["series_visual_signature_critique_by_frame"] = {critique.frame_id: critique.to_dict() for critique in self.series_visual_signature_critiques}
        projected_parts_by_frame: dict[str, Any] = {}
        for index, rendered in enumerate(self.rendered_prompts):
            parts = rendered.metadata_to_dict().get("projected_prompt_parts")
            if parts is None:
                continue
            frame_id = (
                self.base_visual_briefs[index].frame_id
                if index < len(self.base_visual_briefs)
                else str(index)
            )
            projected_parts_by_frame[frame_id] = parts
        if projected_parts_by_frame:
            snapshot["series_visual_signature_projected_prompt_parts_by_frame"] = projected_parts_by_frame
        if self.series_visual_signature_repair_attempts:
            snapshot["series_visual_signature_repair_attempts"] = dict(self.series_visual_signature_repair_attempts)
        compatible_snapshot = to_json_compatible(
            snapshot,
            field_name="visual_prompt_planning_snapshot",
        )
        if not isinstance(compatible_snapshot, dict):
            raise TypeError("visual_prompt_planning_snapshot must be a mapping")
        return compatible_snapshot


@dataclass(frozen=True)
class VisualPromptPlanningService:
    """Subject-first visual planning with resilient series-visual-signature routing."""

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
        series_visual_signature_expression_mode: str | None = None,
        series_visual_signature_structure_mode: str | None = None,
        series_visual_signature_participation_mode: str | None = None,
        series_visual_signature_request: SeriesVisualSignatureRequest | None = None,
        series_visual_signature_profile: SeriesVisualSignatureProfile | None = None,
        series_visual_signature_mode: str | None = None,
        series_visual_signature_consistency_mode: str | None = None,
    ) -> VisualPromptPlanningResult:
        policy = visual_signature_policy or load_visual_signature_policy()
        if series_visual_signature_request is not None:
            role_strategy = series_visual_signature_request.strategy
            presentation_policy = series_visual_signature_request.presentation_policy
        else:
            presentation_policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
                {
                    "series_visual_signature_mode": series_visual_signature_mode,
                    "series_visual_signature_consistency_mode": series_visual_signature_consistency_mode,
                }
            )
            role_strategy = presentation_policy.strategy_controls()
            if role_strategy == SeriesVisualSignatureStrategyControls():
                role_strategy = SeriesVisualSignatureStrategyControls.from_mapping(
                    {
                        "series_visual_signature_mode": series_visual_signature_mode,
                        "series_visual_signature_consistency_mode": series_visual_signature_consistency_mode,
                    }
                )
        base_visual_briefs = BaseVisualBriefPlanner().plan_batch(
            base_prompts=base_prompts,
            frame_contexts=frame_contexts,
            frame_plans=frame_plans,
            visual_style_contract=visual_style_contract,
            generation_world_profile=generation_world_profile,
            world_preset=world_preset,
        )

        visual_anchor_plans: tuple[VisualAnchorPlacementPlan, ...] = tuple()
        if visual_anchor_enabled and anchor_profile is not None:
            if _should_use_deterministic_anchor_planning(
                presentation_policy=presentation_policy,
                role_strategy=role_strategy,
            ):
                identity_kernel = build_visual_identity_kernel(anchor_profile)
                reasons = {
                    brief.frame_id: (
                        "soft deterministic anchor planning selected",
                    )
                    for brief in base_visual_briefs
                }
                visual_anchor_plans = VisualSignatureFallbackPlanner(
                    anchor_profile=anchor_profile,
                    presentation_policy=presentation_policy,
                    identity_kernel=identity_kernel,
                ).plan_failed_frames(
                    base_visual_briefs=base_visual_briefs,
                    failed_frame_ids=[brief.frame_id for brief in base_visual_briefs],
                    failure_reasons_by_frame=reasons,
                )
            else:
                visual_anchor_plans = await VisualAnchorIntegrationPlanner(
                    llm_service=llm_service,
                    policy=policy,
                    series_visual_signature_strategy=role_strategy,
                    presentation_policy=presentation_policy,
                ).plan_batch(
                    base_visual_briefs=base_visual_briefs,
                    anchor_profile=anchor_profile,
                    base_packages=base_anchor_packages,
                    frame_contexts=frame_contexts,
                    frame_plans=frame_plans,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )
        projection_policy = _projection_policy_for_request(
            policy,
            visual_anchor_enabled=visual_anchor_enabled,
            anchor_profile=anchor_profile,
        )
        active_anchor_profile = anchor_profile if _mandatory_ip_active(
            visual_anchor_enabled=visual_anchor_enabled,
            anchor_profile=anchor_profile,
        ) else None
        rendered_prompts = _project_prompts(
            base_visual_briefs=base_visual_briefs,
            visual_anchor_plans=visual_anchor_plans,
            active_anchor_profile=active_anchor_profile,
            negative_rules=extra_negative_rules,
            capabilities=capabilities,
            workflow=workflow,
            visual_signature_policy=projection_policy,
            series_visual_signature_strategy=role_strategy,
        )
        anchor_packages = _anchor_packages_from_plans(
            visual_anchor_plans=visual_anchor_plans,
            base_anchor_packages=base_anchor_packages,
        )
        fallback_ledger = fallback_ledger_from_plans(visual_anchor_plans) if visual_anchor_plans else None
        return VisualPromptPlanningResult(
            base_visual_briefs=base_visual_briefs,
            visual_anchor_plans=visual_anchor_plans,
            anchor_packages=anchor_packages,
            rendered_prompts=rendered_prompts,
            series_visual_signature_request=series_visual_signature_request,
            series_visual_signature_profile=series_visual_signature_profile,
            series_visual_signature_fallback=fallback_ledger if fallback_ledger and fallback_ledger.get("fallback_applied") else None,
        )


def _project_prompts(
    *,
    base_visual_briefs: Sequence[BaseVisualBrief],
    visual_anchor_plans: Sequence[VisualAnchorPlacementPlan],
    active_anchor_profile: IPProfile | None,
    negative_rules: Sequence[str],
    capabilities: Any,
    workflow: str | None,
    visual_signature_policy: VisualSignaturePolicy,
    series_visual_signature_strategy: SeriesVisualSignatureStrategyControls,
) -> tuple[RenderedMediaPrompt, ...]:
    projector = ProviderPromptProjector()
    plans_by_frame = {plan.frame_id: plan for plan in visual_anchor_plans}
    rendered_prompts: list[RenderedMediaPrompt] = []

    for brief in base_visual_briefs:
        rendered_prompts.append(
            projector.project(
                base_visual_brief=brief,
                anchor_profile=active_anchor_profile,
                visual_anchor_plan=plans_by_frame.get(brief.frame_id),
                negative_rules=negative_rules,
                capabilities=capabilities,
                workflow=workflow,
                visual_signature_policy=visual_signature_policy,
                series_visual_signature_strategy=series_visual_signature_strategy,
            )
        )

    return tuple(rendered_prompts)


def _anchor_packages_from_plans(
    *,
    visual_anchor_plans: Sequence[VisualAnchorPlacementPlan],
    base_anchor_packages: Sequence[IPFrameAdaptationPackage],
) -> tuple[IPFrameAdaptationPackage, ...]:
    if not base_anchor_packages or not visual_anchor_plans:
        return ()
    if not all(isinstance(package, IPFrameAdaptationPackage) for package in base_anchor_packages):
        return ()

    plans_by_frame = {plan.frame_id: plan for plan in visual_anchor_plans}
    packages: list[IPFrameAdaptationPackage] = []
    for base_package in base_anchor_packages:
        plan = plans_by_frame.get(base_package.frame_id)
        if plan is None:
            return ()
        packages.append(plan.to_ip_frame_adaptation_package(base_package))
    return tuple(packages)


def _should_use_deterministic_anchor_planning(
    *,
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    role_strategy: SeriesVisualSignatureStrategyControls,
) -> bool:
    if presentation_policy.enforcement is SeriesVisualSignatureEnforcementMode.STRICT:
        return False
    if not presentation_policy.fallback_enabled:
        return False
    if role_strategy.requires_subject_replacement:
        return False
    return presentation_policy.presentation_mode in {
        SeriesVisualSignaturePresentationMode.AUTO,
        SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK,
    }


def _mandatory_ip_active(
    *,
    visual_anchor_enabled: bool,
    anchor_profile: IPProfile | None,
) -> bool:
    return bool(visual_anchor_enabled and anchor_profile is not None)


def _projection_policy_for_request(
    policy: VisualSignaturePolicy,
    *,
    visual_anchor_enabled: bool,
    anchor_profile: IPProfile | None,
) -> VisualSignaturePolicy:
    if _mandatory_ip_active(
        visual_anchor_enabled=visual_anchor_enabled,
        anchor_profile=anchor_profile,
    ):
        return policy
    if not policy.requires_every_frame_signature:
        return policy
    return replace(
        policy,
        coverage_mode="sparse",
        suppress_allowed=True,
        projection_failure="allow_anchor_free",
        require_concrete_identity=False,
    )


__all__ = ["VisualPromptPlanningResult", "VisualPromptPlanningService"]
