from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pixelle_video.models.llm_interaction_trace import trace_context_with_prompt_template
from pixelle_video.models.visual_story_engine import FrameVisualPlan
from pixelle_video.prompts.visual_story_execution import render_frame_visual_plan_batch_prompt
from pixelle_video.services.frame_batch_contract import (
    FrameBatchContractError,
    frame_ids_from_records,
    normalize_frame_records,
    parse_frame_batch_response,
    validate_frame_batch_coverage,
)


@dataclass(frozen=True)
class FrameBatchPlanOutcome:
    plans: tuple[dict[str, Any], ...]
    source: str
    fallback_used: bool = False
    fallback_reason_code: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FrameVisualPlanBatchService:
    """Plan article-bound frame visuals only.

    Recurring IP/signature semantics are intentionally absent. The canonical
    V4.6 final projection stage owns visual-signature participation.
    """

    async def plan(
        self,
        *,
        llm_service: Any,
        article_summary: Mapping[str, Any],
        selected_visual_route: Mapping[str, Any],
        batch_payload: Mapping[str, Any],
        continuity_ledger: Mapping[str, Any],
        target_language: str = "zh",
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[dict[str, Any], ...]:
        outcome = await self.plan_with_diagnostics(
            llm_service=llm_service,
            article_summary=article_summary,
            selected_visual_route=selected_visual_route,
            batch_payload=batch_payload,
            continuity_ledger=continuity_ledger,
            target_language=target_language,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        return outcome.plans

    async def plan_with_diagnostics(
        self,
        *,
        llm_service: Any,
        article_summary: Mapping[str, Any],
        selected_visual_route: Mapping[str, Any],
        batch_payload: Mapping[str, Any],
        continuity_ledger: Mapping[str, Any],
        target_language: str = "zh",
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> FrameBatchPlanOutcome:
        frame_contexts = normalize_frame_records(
            batch_payload.get("frame_contexts") or (),
            stage="frame_visual_plan_input",
        )
        expected_frame_ids = frame_ids_from_records(
            frame_contexts,
            stage="frame_visual_plan_input",
        )
        rendered_prompt = render_frame_visual_plan_batch_prompt(
            article_summary=article_summary,
            selected_visual_route=selected_visual_route,
            batch_payload=batch_payload,
            continuity_ledger=continuity_ledger,
            target_language=target_language,
        )
        response = await llm_service(
            prompt=rendered_prompt.text,
            response_type=dict,
            temperature=0.2,
            max_tokens=2500,
            trace_context=_stage_trace_context(
                trace_context,
                rendered_prompt=rendered_prompt,
                stage="frame_visual_plan_batch",
                batch_payload=batch_payload,
            ),
            trace_recorder=trace_recorder,
        )
        raw_plans = parse_frame_batch_response(
            response,
            primary_key="frame_visual_plans",
            expected_frame_ids=expected_frame_ids,
            stage="frame_visual_plan_response",
        )
        plans = _normalize_frame_visual_plans(
            raw_plans,
            expected_frame_ids=expected_frame_ids,
        )
        return FrameBatchPlanOutcome(
            plans=plans,
            source="model_content_only",
            diagnostics={"visual_signature_owner": "canonical_v4_6_projection"},
        )


def _stage_trace_context(
    trace_context: Any,
    *,
    rendered_prompt: Any,
    stage: str,
    batch_payload: Mapping[str, Any],
) -> Any:
    if trace_context is None:
        return None
    try:
        frame_ids = _frame_ids_from_payload(batch_payload)
        return trace_context_with_prompt_template(
            trace_context,
            rendered_prompt=rendered_prompt,
            attempt=1,
            stage=stage,
            metadata={"frame_ids": frame_ids},
        )
    except Exception:
        return trace_context


def _frame_ids_from_payload(payload: Mapping[str, Any]) -> list[str]:
    values = payload.get("frame_contexts") or ()
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            frame_id = str(item.get("frame_id") or "").strip()
            if frame_id:
                result.append(frame_id)
    return result[:20]


def _normalize_frame_visual_plans(
    plans: tuple[dict[str, Any], ...],
    *,
    expected_frame_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for item in plans:
        plan = FrameVisualPlan.from_mapping(item)
        if not plan.required_subjects:
            raise FrameBatchContractError(
                "missing_required_subjects",
                "frame_visual_plan_response",
                f"frame {plan.frame_id} must include at least one required subject",
            )
        normalized.append(plan.to_dict())
    return validate_frame_batch_coverage(
        normalized,
        expected_frame_ids=expected_frame_ids,
        stage="frame_visual_plan_output",
    )


__all__ = ["FrameBatchPlanOutcome", "FrameVisualPlanBatchService"]
