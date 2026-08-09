from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_engine import (
    RouteSelectionDecision,
    RouteSelectionSource,
    VisualStoryEnginePlan,
)
from pixelle_video.models.visual_story_execution import VisualStoryLoopResult
from pixelle_video.services.content_bound_ip_planner import ContentBoundIPPlanner
from pixelle_video.services.frame_batch_contract import validate_frame_batch_coverage
from pixelle_video.services.visual_story_context_contract import (
    PromptBudgetPolicy,
    VisualStoryContextContractBuilder,
)
from pixelle_video.services.visual_story_continuity_ledger import VisualStoryContinuityLedgerService
from pixelle_video.services.visual_story_execution_planner import VisualStoryExecutionPlanner
from pixelle_video.services.visual_story_frame_services import (
    FrameIPFusionPlanBatchService,
    FrameVisualPlanBatchService,
)
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate


@dataclass(frozen=True)
class VisualStoryBatchOrchestrator:
    """Local loop planner + batch LLM orchestrator."""

    async def prepare(
        self,
        *,
        llm_service: Any,
        source_text: str,
        storyboard_plan: Any,
        visual_story_plan: Any,
        ip_profile: Any = None,
        batch_size: int = 4,
        max_context_chars: int = 9000,
        target_language: str = "zh",
        trace_context: Any = None,
        trace_recorder: Any = None,
        max_ip_rewrite_passes: int = 1,
    ) -> VisualStoryLoopResult:
        plan_payload = (
            visual_story_plan.to_dict()
            if hasattr(visual_story_plan, "to_dict")
            else dict(visual_story_plan or {})
        )
        selected_route = dict(
            plan_payload.get("selected_visual_route") or plan_payload.get("selected_route") or {}
        )
        style = dict(plan_payload.get("style_harmonization") or {})
        article = dict(plan_payload.get("article") or {})
        ip_payload = _ip_profile_payload(ip_profile)

        ledger_service = VisualStoryContinuityLedgerService()
        ledger = ledger_service.initial(
            selected_visual_route=selected_route, ip_profile=ip_payload, style_plan=style
        )
        execution_plan = VisualStoryExecutionPlanner().plan(
            source_text=source_text,
            storyboard_plan=storyboard_plan,
            selected_visual_route=selected_route,
            batch_size=batch_size,
            max_context_chars=max_context_chars,
            continuity_ledger=ledger,
        )

        visual_plans = []
        ip_plans = []
        context_builder = VisualStoryContextContractBuilder(
            PromptBudgetPolicy(max_total_chars=max_context_chars)
        )
        visual_service = FrameVisualPlanBatchService()
        ip_service = FrameIPFusionPlanBatchService()
        content_bound_planner = ContentBoundIPPlanner()
        repair_diagnostics = []
        batch_diagnostics = []

        for batch in execution_plan.batches:
            raw_contexts = [
                {
                    "frame_id": ref.frame_id,
                    "frame_index": ref.frame_index,
                    "source_text": ref.source_text,
                    "visual_goal": ref.visual_goal,
                    "prompt_intent": ref.prompt_intent,
                    "selected_visual_route": selected_route,
                }
                for ref in batch.frame_refs
            ]
            contract = context_builder.build_for_visual_anchor(frame_contexts=raw_contexts)
            expected_batch_frame_ids = batch.frame_ids
            visual_outcome = await visual_service.plan_with_diagnostics(
                llm_service=llm_service,
                article_summary=article,
                selected_visual_route=selected_route,
                batch_payload=contract.payload,
                continuity_ledger=ledger.to_dict(),
                target_language=target_language,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            batch_visual = visual_outcome.plans
            ip_outcome = await ip_service.plan_with_diagnostics(
                llm_service=llm_service,
                selected_visual_route=selected_route,
                style_harmonization=style,
                ip_profile=ip_payload,
                frame_visual_plans=batch_visual,
                continuity_ledger=ledger.to_dict(),
                target_language=target_language,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            batch_ip = ip_outcome.plans
            repaired = content_bound_planner.repair_batch(
                frame_visual_plans=batch_visual,
                frame_ip_fusion_plans=batch_ip,
                selected_visual_route=selected_route,
                style_harmonization=style,
                article_summary=article,
                ip_profile=ip_payload,
                max_rewrite_passes=max_ip_rewrite_passes,
            )
            batch_visual = validate_frame_batch_coverage(
                repaired.frame_visual_plans,
                expected_frame_ids=expected_batch_frame_ids,
                stage=f"{batch.batch_id}_visual_output",
            )
            batch_ip = validate_frame_batch_coverage(
                repaired.frame_ip_fusion_plans,
                expected_frame_ids=expected_batch_frame_ids,
                stage=f"{batch.batch_id}_ip_output",
            )
            if repaired.diagnostics.get("repair_count"):
                repair_diagnostics.append({"batch_id": batch.batch_id, **repaired.diagnostics})
            batch_diagnostics.append(
                {
                    "batch_id": batch.batch_id,
                    "frame_ids": list(expected_batch_frame_ids),
                    "visual_plan_source": visual_outcome.source,
                    "visual_plan_fallback_used": visual_outcome.fallback_used,
                    "visual_plan_fallback_reason_code": visual_outcome.fallback_reason_code,
                    "ip_plan_source": ip_outcome.source,
                    "ip_plan_fallback_used": ip_outcome.fallback_used,
                    "ip_plan_fallback_reason_code": ip_outcome.fallback_reason_code,
                    "ip_plan_diagnostics": dict(ip_outcome.diagnostics),
                    "content_bound_repair_diagnostics": dict(repaired.diagnostics),
                }
            )
            visual_plans.extend(dict(item) for item in batch_visual)
            ip_plans.extend(dict(item) for item in batch_ip)
            ledger = ledger_service.update_after_batch(
                ledger=ledger,
                batch_id=batch.batch_id,
                frame_visual_plans=batch_visual,
                frame_ip_fusion_plans=batch_ip,
            )

        visual_plans = list(
            validate_frame_batch_coverage(
                visual_plans,
                expected_frame_ids=execution_plan.frame_ids,
                stage="visual_story_global_visual_output",
            )
        )
        ip_plans = list(
            validate_frame_batch_coverage(
                ip_plans,
                expected_frame_ids=execution_plan.frame_ids,
                stage="visual_story_global_ip_output",
            )
        )

        prompt_context = {
            "visual_story_engine": {
                "plan_id": plan_payload.get("plan_id"),
                "article": article,
                "selection": plan_payload.get("selection") or {},
                "selected_visual_route": selected_route,
                "style_harmonization": style,
                "execution_plan": execution_plan.to_dict(),
                "continuity_ledger": ledger.to_dict(),
                "content_bound_repair_diagnostics": repair_diagnostics,
            },
            "selected_visual_route": selected_route,
            "frame_visual_plans": visual_plans,
            "frame_ip_fusion_plans": ip_plans,
            "visual_story_execution_plan": execution_plan.to_dict(),
            "continuity_ledger": ledger.to_dict(),
            "content_bound_repair_diagnostics": repair_diagnostics,
        }
        final_plan = _visual_story_plan_from_payload(visual_story_plan, visual_plans, ip_plans)
        VisualStoryQualityGate().assert_valid(
            final_plan, expected_frame_ids=execution_plan.frame_ids
        )
        return VisualStoryLoopResult(
            execution_plan=execution_plan,
            frame_visual_plans=tuple(visual_plans),
            frame_ip_fusion_plans=tuple(ip_plans),
            prompt_context=prompt_context,
            diagnostics={
                "batch_count": len(execution_plan.batches),
                "frame_count": execution_plan.frame_count,
                "batch_size": execution_plan.batch_size,
                "max_context_chars": execution_plan.max_context_chars,
                "content_bound_repair_diagnostics": repair_diagnostics,
                "batch_diagnostics": batch_diagnostics,
            },
        )


def _visual_story_plan_from_payload(
    visual_story_plan: Any,
    visual_plans: Sequence[Mapping[str, Any]],
    ip_plans: Sequence[Mapping[str, Any]],
) -> VisualStoryEnginePlan:
    if isinstance(visual_story_plan, VisualStoryEnginePlan):
        return VisualStoryEnginePlan(
            plan_id=visual_story_plan.plan_id,
            article=visual_story_plan.article,
            candidate_routes=visual_story_plan.candidate_routes,
            compatibility_reports=visual_story_plan.compatibility_reports,
            selection=visual_story_plan.selection,
            style_harmonization=visual_story_plan.style_harmonization,
            frame_visual_plans=tuple(visual_plans),
            frame_ip_fusion_plans=tuple(ip_plans),
            channel_memory_intent=visual_story_plan.channel_memory_intent,
        )
    if not isinstance(visual_story_plan, Mapping):
        raise TypeError("visual_story_plan must be a VisualStoryEnginePlan or mapping")

    payload = dict(visual_story_plan)
    selected_route = dict(
        payload.get("selected_visual_route") or payload.get("selected_route") or {}
    )
    selection_payload = (
        payload.get("selection") if isinstance(payload.get("selection"), Mapping) else {}
    )
    selected_route_id = str(
        selection_payload.get("selected_route_id")
        or selected_route.get("route_id")
        or selected_route.get("id")
        or payload.get("selected_route_id")
        or "route-1"
    )
    if not selected_route:
        selected_route = {"route_id": selected_route_id}
    else:
        selected_route.setdefault("route_id", selected_route_id)

    candidate_routes = list(payload.get("candidate_routes") or ())
    if not any(
        isinstance(route, Mapping)
        and str(route.get("route_id") or route.get("id") or "") == selected_route_id
        for route in candidate_routes
    ):
        candidate_routes.append(selected_route)

    style_harmonization = dict(payload.get("style_harmonization") or {})
    style_harmonization.setdefault("route_id", selected_route_id)
    selection = RouteSelectionDecision(
        recommended_route_id=str(
            selection_payload.get("recommended_route_id") or selected_route_id
        ),
        selected_route_id=selected_route_id,
        selection_source=selection_payload.get("selection_source") or RouteSelectionSource.API_AUTO,
        reason=str(selection_payload.get("reason") or "selected route from request payload"),
        auto_select_after_seconds=int(selection_payload.get("auto_select_after_seconds") or 0),
        user_overrode=bool(selection_payload.get("user_overrode", False)),
        low_confidence=bool(selection_payload.get("low_confidence", False)),
        fallback_used=bool(selection_payload.get("fallback_used", False)),
        fallback_reason=selection_payload.get("fallback_reason"),
    )
    return VisualStoryEnginePlan(
        plan_id=str(payload.get("plan_id") or "visual-story-plan"),
        article=payload.get("article") or {},
        candidate_routes=tuple(candidate_routes),
        compatibility_reports=tuple(payload.get("compatibility_reports") or ()),
        selection=selection,
        style_harmonization=style_harmonization,
        frame_visual_plans=tuple(visual_plans),
        frame_ip_fusion_plans=tuple(ip_plans),
        channel_memory_intent=str(payload.get("channel_memory_intent") or ""),
    )


def _ip_profile_payload(ip_profile: Any) -> dict[str, Any]:
    if ip_profile is None:
        return {}
    if hasattr(ip_profile, "to_dict"):
        try:
            payload = ip_profile.to_dict()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            pass
    if isinstance(ip_profile, Mapping):
        return dict(ip_profile)
    result = {}
    for key in (
        "name",
        "visual_summary",
        "identity_lock",
        "minimal_traits",
        "identity_anchors",
        "style_hint",
        "negative_constraints",
        "world_hint",
    ):
        value = getattr(ip_profile, key, None)
        if value is not None:
            result[key] = value
    return result


__all__ = ["VisualStoryBatchOrchestrator"]
