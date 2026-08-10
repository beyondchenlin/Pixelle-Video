from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_engine import (
    FrameIPFusionPlan,
    RouteSelectionDecision,
    RouteSelectionSource,
    VisualStoryEnginePlan,
)
from pixelle_video.models.visual_story_execution import VisualStoryLoopResult
from pixelle_video.services.frame_batch_contract import validate_frame_batch_coverage
from pixelle_video.services.visual_story_context_contract import (
    PromptBudgetPolicy,
    VisualStoryContextContractBuilder,
)
from pixelle_video.services.visual_story_continuity_ledger import VisualStoryContinuityLedgerService
from pixelle_video.services.visual_story_execution_planner import VisualStoryExecutionPlanner
from pixelle_video.services.visual_story_frame_services import FrameVisualPlanBatchService
from pixelle_video.services.visual_story_quality_gate import VisualStoryQualityGate

_CONTENT_ROUTE_KEYS = (
    "route_id",
    "route_name",
    "route_type",
    "visual_premise",
    "why_it_fits_article",
    "frame_storytelling_logic",
    "style_family",
    "route_specific_rules",
    "risk_notes",
    "sample_frame_premise",
)


@dataclass(frozen=True)
class VisualStoryBatchOrchestrator:
    """Content-only local loop planner + batch LLM orchestrator.

    Recurring visual identity is intentionally absent here. The canonical V4.5
    projection stage owns all visual-signature participation after the content
    prompt has been generated.
    """

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
        # ip_profile/max_ip_rewrite_passes remain signature-compatible inputs for
        # existing callers only. They cannot influence this content-only stage.
        del ip_profile, max_ip_rewrite_passes
        plan_payload = (
            visual_story_plan.to_dict()
            if hasattr(visual_story_plan, "to_dict")
            else dict(visual_story_plan or {})
        )
        selected_route = _content_only_route(
            plan_payload.get("selected_visual_route")
            or plan_payload.get("selected_route")
            or {}
        )
        article = dict(plan_payload.get("article") or {})

        ledger_service = VisualStoryContinuityLedgerService()
        ledger = ledger_service.initial(
            selected_visual_route=selected_route,
            ip_profile={},
            style_plan={},
        )
        execution_plan = VisualStoryExecutionPlanner().plan(
            source_text=source_text,
            storyboard_plan=storyboard_plan,
            selected_visual_route=selected_route,
            batch_size=batch_size,
            max_context_chars=max_context_chars,
            continuity_ledger=ledger,
        )

        visual_plans: list[dict[str, Any]] = []
        neutral_ip_plans: list[dict[str, Any]] = []
        context_builder = VisualStoryContextContractBuilder(
            PromptBudgetPolicy(max_total_chars=max_context_chars)
        )
        visual_service = FrameVisualPlanBatchService()
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
            contract = context_builder.build_for_visual_anchor(
                frame_contexts=raw_contexts
            )
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
            batch_visual = validate_frame_batch_coverage(
                visual_outcome.plans,
                expected_frame_ids=expected_batch_frame_ids,
                stage=f"{batch.batch_id}_visual_output",
            )
            batch_ip = tuple(
                _neutral_ip_plan(str(item.get("frame_id") or ""))
                for item in batch_visual
            )
            batch_ip = validate_frame_batch_coverage(
                batch_ip,
                expected_frame_ids=expected_batch_frame_ids,
                stage=f"{batch.batch_id}_neutral_ip_output",
            )
            batch_diagnostics.append(
                {
                    "batch_id": batch.batch_id,
                    "frame_ids": list(expected_batch_frame_ids),
                    "visual_plan_source": visual_outcome.source,
                    "visual_plan_fallback_used": visual_outcome.fallback_used,
                    "visual_plan_fallback_reason_code": visual_outcome.fallback_reason_code,
                    "legacy_ip_planning": "disabled",
                    "visual_signature_owner": "canonical_v4_5_projection",
                }
            )
            visual_plans.extend(dict(item) for item in batch_visual)
            neutral_ip_plans.extend(dict(item) for item in batch_ip)
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
        neutral_ip_plans = list(
            validate_frame_batch_coverage(
                neutral_ip_plans,
                expected_frame_ids=execution_plan.frame_ids,
                stage="visual_story_global_neutral_ip_output",
            )
        )

        prompt_context = {
            "visual_story_engine": {
                "plan_id": plan_payload.get("plan_id"),
                "article": article,
                "selection": plan_payload.get("selection") or {},
                "selected_visual_route": selected_route,
                "execution_plan": execution_plan.to_dict(),
                "continuity_ledger": ledger.to_dict(),
                "legacy_ip_planning": "disabled",
            },
            "selected_visual_route": selected_route,
            "frame_visual_plans": visual_plans,
            "visual_story_execution_plan": execution_plan.to_dict(),
            "continuity_ledger": ledger.to_dict(),
        }
        final_plan = _visual_story_plan_from_payload(
            visual_story_plan,
            visual_plans,
            neutral_ip_plans,
        )
        VisualStoryQualityGate().assert_valid(
            final_plan,
            expected_frame_ids=execution_plan.frame_ids,
        )
        return VisualStoryLoopResult(
            execution_plan=execution_plan,
            frame_visual_plans=tuple(visual_plans),
            frame_ip_fusion_plans=tuple(neutral_ip_plans),
            prompt_context=prompt_context,
            diagnostics={
                "batch_count": len(execution_plan.batches),
                "frame_count": execution_plan.frame_count,
                "batch_size": execution_plan.batch_size,
                "max_context_chars": execution_plan.max_context_chars,
                "legacy_ip_planning": "disabled",
                "visual_signature_owner": "canonical_v4_5_projection",
                "batch_diagnostics": batch_diagnostics,
            },
        )


def _neutral_ip_plan(frame_id: str) -> dict[str, Any]:
    return FrameIPFusionPlan(
        frame_id=frame_id,
        ip_role="none",
        ip_visibility="none",
        placement_logic="Recurring visual identity is not planned in Visual Story.",
        action_or_function="None.",
        relation_to_article_subject="No recurring visual identity participates here.",
        style_harmonization="match_route_style",
        positive_prompt_clause="",
        negative_constraints=(),
        content_relation_type="disabled_in_visual_story",
    ).to_dict()


def _content_only_route(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key]
        for key in _CONTENT_ROUTE_KEYS
        if key in value and value[key] is not None
    }


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
    selected_route = _content_only_route(
        payload.get("selected_visual_route") or payload.get("selected_route") or {}
    )
    selection_payload = (
        payload.get("selection")
        if isinstance(payload.get("selection"), Mapping)
        else {}
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
        selection_source=selection_payload.get("selection_source")
        or RouteSelectionSource.API_AUTO,
        reason=str(
            selection_payload.get("reason") or "selected route from request payload"
        ),
        auto_select_after_seconds=int(
            selection_payload.get("auto_select_after_seconds") or 0
        ),
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


__all__ = ["VisualStoryBatchOrchestrator"]
