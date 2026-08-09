from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from pixelle_video.models.llm_interaction_trace import trace_context_with_prompt_template
from pixelle_video.models.visual_story_engine import FrameIPFusionPlan, FrameVisualPlan
from pixelle_video.prompts.visual_story_execution import (
    render_frame_ip_fusion_batch_prompt,
    render_frame_visual_plan_batch_prompt,
)
from pixelle_video.services.content_bound_ip_planner import ContentBoundIPPlanner
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
        try:
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
            plans = parse_frame_batch_response(
                response,
                primary_key="frame_visual_plans",
                expected_frame_ids=expected_frame_ids,
                stage="frame_visual_plan_response",
            )
            planner = ContentBoundIPPlanner()
            enriched = tuple(
                FrameVisualPlan.from_mapping(
                    planner.enrich_frame_visual_plan(
                        item,
                        selected_visual_route=selected_visual_route,
                        article_summary=article_summary,
                    )
                ).to_dict()
                for item in plans
            )
            validated = validate_frame_batch_coverage(
                enriched,
                expected_frame_ids=expected_frame_ids,
                stage="frame_visual_plan_output",
            )
            return FrameBatchPlanOutcome(plans=validated, source="model")
        except Exception as exc:
            logger.warning("Frame visual plan batch failed; using deterministic fallback: {}", exc)
            fallback = tuple(_fallback_visual_plan(item) for item in frame_contexts)
            validated = validate_frame_batch_coverage(
                fallback,
                expected_frame_ids=expected_frame_ids,
                stage="frame_visual_plan_fallback",
            )
            return FrameBatchPlanOutcome(
                plans=validated,
                source="deterministic_fallback",
                fallback_used=True,
                fallback_reason_code=_fallback_reason_code(exc),
            )


@dataclass(frozen=True)
class FrameIPFusionPlanBatchService:
    async def plan(
        self,
        *,
        llm_service: Any,
        selected_visual_route: Mapping[str, Any],
        style_harmonization: Mapping[str, Any],
        ip_profile: Mapping[str, Any],
        frame_visual_plans: Sequence[Mapping[str, Any]],
        continuity_ledger: Mapping[str, Any],
        target_language: str = "zh",
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[dict[str, Any], ...]:
        outcome = await self.plan_with_diagnostics(
            llm_service=llm_service,
            selected_visual_route=selected_visual_route,
            style_harmonization=style_harmonization,
            ip_profile=ip_profile,
            frame_visual_plans=frame_visual_plans,
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
        selected_visual_route: Mapping[str, Any],
        style_harmonization: Mapping[str, Any],
        ip_profile: Mapping[str, Any],
        frame_visual_plans: Sequence[Mapping[str, Any]],
        continuity_ledger: Mapping[str, Any],
        target_language: str = "zh",
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> FrameBatchPlanOutcome:
        normalized_visual_plans = normalize_frame_records(
            frame_visual_plans,
            stage="frame_ip_fusion_input",
        )
        expected_frame_ids = frame_ids_from_records(
            normalized_visual_plans,
            stage="frame_ip_fusion_input",
        )
        if not ip_profile:
            no_ip_plans = tuple(_no_ip_plan(plan) for plan in normalized_visual_plans)
            validated = validate_frame_batch_coverage(
                no_ip_plans,
                expected_frame_ids=expected_frame_ids,
                stage="frame_ip_fusion_no_profile",
            )
            return FrameBatchPlanOutcome(plans=validated, source="no_ip_profile")
        compact_ip_profile = _compact_ip_profile(ip_profile)
        rendered_prompt = render_frame_ip_fusion_batch_prompt(
            selected_visual_route=selected_visual_route,
            style_harmonization=style_harmonization,
            ip_profile=compact_ip_profile,
            frame_visual_plans=normalized_visual_plans,
            continuity_ledger=continuity_ledger,
            target_language=target_language,
        )
        try:
            response = await llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=2500,
                trace_context=_stage_trace_context(
                    trace_context,
                    rendered_prompt=rendered_prompt,
                    stage="frame_ip_fusion_plan_batch",
                    batch_payload={"frame_visual_plans": list(normalized_visual_plans)},
                ),
                trace_recorder=trace_recorder,
            )
            plans = parse_frame_batch_response(
                response,
                primary_key="frame_ip_fusion_plans",
                expected_frame_ids=expected_frame_ids,
                stage="frame_ip_fusion_response",
            )
            repair = ContentBoundIPPlanner().repair_batch(
                frame_visual_plans=normalized_visual_plans,
                frame_ip_fusion_plans=plans,
                selected_visual_route=selected_visual_route,
                style_harmonization=style_harmonization,
                ip_profile=ip_profile,
            )
            repaired_plans = tuple(
                FrameIPFusionPlan.from_mapping(item).to_dict()
                for item in repair.frame_ip_fusion_plans
            )
            validated = validate_frame_batch_coverage(
                repaired_plans,
                expected_frame_ids=expected_frame_ids,
                stage="frame_ip_fusion_output",
            )
            return FrameBatchPlanOutcome(
                plans=validated,
                source="model_repaired" if repair.diagnostics.get("repair_count") else "model",
                diagnostics=dict(repair.diagnostics),
            )
        except Exception as exc:
            logger.warning("Frame IP fusion batch failed; using deterministic fallback: {}", exc)
            fallback = tuple(
                _fallback_ip_plan(plan, selected_visual_route, style_harmonization)
                for plan in normalized_visual_plans
            )
            validated = validate_frame_batch_coverage(
                fallback,
                expected_frame_ids=expected_frame_ids,
                stage="frame_ip_fusion_fallback",
            )
            return FrameBatchPlanOutcome(
                plans=validated,
                source="deterministic_fallback",
                fallback_used=True,
                fallback_reason_code=_fallback_reason_code(exc),
            )


def _stage_trace_context(
    trace_context: Any, *, rendered_prompt: Any, stage: str, batch_payload: Mapping[str, Any]
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
    values = payload.get("frame_contexts") or payload.get("frame_visual_plans") or ()
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            frame_id = str(item.get("frame_id") or "").strip()
            if frame_id:
                result.append(frame_id)
    return result[:20]


def _fallback_reason_code(exc: Exception) -> str:
    if isinstance(exc, FrameBatchContractError):
        return exc.code
    return type(exc).__name__


def _compact_ip_profile(ip_profile: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "series_visual_signature_profile_id",
        "name",
        "visual_summary",
        "identity_lock",
        "minimal_traits",
        "identity_anchors",
        "style_hint",
        "negative_constraints",
        "visible_text_whitelist",
        "world_hint",
    )
    result: dict[str, Any] = {}
    for key in keys:
        value = ip_profile.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            result[key] = _truncate(value, 360)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            result[key] = [_truncate(item, 160) for item in list(value)[:8]]
        else:
            result[key] = value
    return result


def _fallback_visual_plan(frame: Mapping[str, Any]) -> dict[str, Any]:
    frame_id = str(frame.get("frame_id") or "frame")
    source_text = str(frame.get("source_text") or frame.get("frame_source_text") or "")
    visual_goal = str(frame.get("visual_goal") or source_text or "visualize frame")
    base = FrameVisualPlan(
        frame_id=frame_id,
        frame_index=int(frame.get("frame_index") or 0),
        source_text=source_text or visual_goal,
        local_claim=visual_goal,
        visual_task=f"Express the local article point for {frame_id}.",
        visual_logic="Apply the selected visual route to this frame without inventing unsupported subjects.",
        required_subjects=[v for v in (frame.get("primary_subject"),) if v],
        forbidden_losses=("do not drop article subjects", "do not replace the source claim"),
        evidence_refs=(),
        visible_text_policy="no_visible_text",
    ).to_dict()
    return ContentBoundIPPlanner().enrich_frame_visual_plan(base)


def _fallback_ip_plan(
    frame_visual_plan: Mapping[str, Any],
    selected_visual_route: Mapping[str, Any],
    style_harmonization: Mapping[str, Any],
) -> dict[str, Any]:
    return FrameIPFusionPlan.from_mapping(
        ContentBoundIPPlanner().plan_for_frame(
            frame_visual_plan,
            selected_visual_route=selected_visual_route,
            style_harmonization=style_harmonization,
        )
    ).to_dict()


def _no_ip_plan(frame_visual_plan: Mapping[str, Any]) -> dict[str, Any]:
    return FrameIPFusionPlan(
        frame_id=frame_visual_plan.get("frame_id") or "frame",
        ip_role="none",
        ip_visibility="none",
        placement_logic="No explicit channel IP in this frame.",
        action_or_function="Preserve article visual logic only.",
        relation_to_article_subject="No IP replacement.",
        style_harmonization="match_route_style",
        positive_prompt_clause="",
        negative_constraints=("preserve article visual logic only",),
        ip_duty_preset="none",
    ).to_dict()


def _truncate(value: Any, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


__all__ = [
    "FrameBatchPlanOutcome",
    "FrameVisualPlanBatchService",
    "FrameIPFusionPlanBatchService",
]
