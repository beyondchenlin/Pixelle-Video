from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.visual_story_execution import VisualStoryLoopResult
from pixelle_video.services.visual_story_context_contract import PromptBudgetPolicy, VisualStoryContextContractBuilder
from pixelle_video.services.visual_story_continuity_ledger import VisualStoryContinuityLedgerService
from pixelle_video.services.visual_story_execution_planner import VisualStoryExecutionPlanner
from pixelle_video.services.visual_story_frame_services import FrameIPFusionPlanBatchService, FrameVisualPlanBatchService


@dataclass(frozen=True)
class VisualStoryBatchOrchestrator:
    """Local loop planner + batch LLM orchestrator."""

    async def prepare(self, *, llm_service: Any, source_text: str, storyboard_plan: Any, visual_story_plan: Any, ip_profile: Any = None, batch_size: int = 4, max_context_chars: int = 9000, target_language: str = "zh", trace_context: Any = None, trace_recorder: Any = None) -> VisualStoryLoopResult:
        plan_payload = visual_story_plan.to_dict() if hasattr(visual_story_plan, "to_dict") else dict(visual_story_plan or {})
        selected_route = dict(plan_payload.get("selected_visual_route") or plan_payload.get("selected_route") or {})
        style = dict(plan_payload.get("style_harmonization") or {})
        article = dict(plan_payload.get("article") or {})
        ip_payload = _ip_profile_payload(ip_profile)

        ledger_service = VisualStoryContinuityLedgerService()
        ledger = ledger_service.initial(selected_visual_route=selected_route, ip_profile=ip_payload, style_plan=style)
        execution_plan = VisualStoryExecutionPlanner().plan(source_text=source_text, storyboard_plan=storyboard_plan, selected_visual_route=selected_route, batch_size=batch_size, max_context_chars=max_context_chars, continuity_ledger=ledger)

        visual_plans = []
        ip_plans = []
        context_builder = VisualStoryContextContractBuilder(PromptBudgetPolicy(max_total_chars=max_context_chars))
        visual_service = FrameVisualPlanBatchService()
        ip_service = FrameIPFusionPlanBatchService()

        for batch in execution_plan.batches:
            raw_contexts = [
                {"frame_id": ref.frame_id, "frame_index": ref.frame_index, "source_text": ref.source_text, "visual_goal": ref.visual_goal, "prompt_intent": ref.prompt_intent, "selected_visual_route": selected_route}
                for ref in batch.frame_refs
            ]
            contract = context_builder.build_for_visual_anchor(frame_contexts=raw_contexts)
            batch_visual = await visual_service.plan(llm_service=llm_service, article_summary=article, selected_visual_route=selected_route, batch_payload=contract.payload, continuity_ledger=ledger.to_dict(), target_language=target_language, trace_context=trace_context, trace_recorder=trace_recorder)
            batch_ip = await ip_service.plan(llm_service=llm_service, selected_visual_route=selected_route, style_harmonization=style, ip_profile=ip_payload, frame_visual_plans=batch_visual, continuity_ledger=ledger.to_dict(), target_language=target_language, trace_context=trace_context, trace_recorder=trace_recorder)
            visual_plans.extend(dict(item) for item in batch_visual)
            ip_plans.extend(dict(item) for item in batch_ip)
            ledger = ledger_service.update_after_batch(ledger=ledger, batch_id=batch.batch_id, frame_visual_plans=batch_visual, frame_ip_fusion_plans=batch_ip)

        prompt_context = {
            "visual_story_engine": {
                "plan_id": plan_payload.get("plan_id"),
                "article": article,
                "selection": plan_payload.get("selection") or {},
                "selected_visual_route": selected_route,
                "style_harmonization": style,
                "execution_plan": execution_plan.to_dict(),
                "continuity_ledger": ledger.to_dict(),
            },
            "selected_visual_route": selected_route,
            "frame_visual_plans": visual_plans,
            "frame_ip_fusion_plans": ip_plans,
            "visual_story_execution_plan": execution_plan.to_dict(),
            "continuity_ledger": ledger.to_dict(),
        }
        return VisualStoryLoopResult(execution_plan=execution_plan, frame_visual_plans=tuple(visual_plans), frame_ip_fusion_plans=tuple(ip_plans), prompt_context=prompt_context, diagnostics={"batch_count": len(execution_plan.batches), "frame_count": execution_plan.frame_count, "batch_size": execution_plan.batch_size, "max_context_chars": execution_plan.max_context_chars})


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
    for key in ("name", "visual_summary", "identity_lock", "minimal_traits", "identity_anchors", "style_hint", "negative_constraints", "world_hint"):
        value = getattr(ip_profile, key, None)
        if value is not None:
            result[key] = value
    return result


__all__ = ["VisualStoryBatchOrchestrator"]
