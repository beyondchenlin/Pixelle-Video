from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from pixelle_video.models.llm_interaction_trace import trace_context_with_prompt_template
from pixelle_video.models.visual_story_engine import FrameVisualPlan
from pixelle_video.prompts.visual_story_execution import (
    render_frame_visual_plan_batch_prompt,
    render_frame_visual_plan_batch_repair_prompt,
)
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
        try:
            active_prompt = rendered_prompt
            for attempt in (1, 2):
                response = await llm_service(
                    prompt=active_prompt.text,
                    response_type=dict,
                    temperature=0.2 if attempt == 1 else 0.0,
                    max_tokens=2500,
                    trace_context=_stage_trace_context(
                        trace_context,
                        rendered_prompt=active_prompt,
                        stage=(
                            "frame_visual_plan_batch"
                            if attempt == 1
                            else "frame_visual_plan_batch_repair"
                        ),
                        batch_payload=batch_payload,
                        attempt=attempt,
                    ),
                    trace_recorder=trace_recorder,
                )
                try:
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
                    break
                except FrameBatchContractError as exc:
                    if attempt == 2:
                        raise
                    logger.info(
                        "Frame visual plan response violated its contract; "
                        "requesting one bounded schema repair: {}",
                        exc.code,
                    )
                    active_prompt = render_frame_visual_plan_batch_repair_prompt(
                        original_request=rendered_prompt,
                        expected_frame_ids=expected_frame_ids,
                        error_code=exc.code,
                    )
            return FrameBatchPlanOutcome(
                plans=plans,
                source="model_content_only",
                diagnostics={"visual_signature_owner": "canonical_v4_5_projection"},
            )
        except Exception as exc:
            logger.warning(
                "Frame visual plan batch failed; using deterministic content-only fallback: {}",
                exc,
            )
            fallback = tuple(_fallback_visual_plan(item) for item in frame_contexts)
            validated = validate_frame_batch_coverage(
                fallback,
                expected_frame_ids=expected_frame_ids,
                stage="frame_visual_plan_fallback",
            )
            return FrameBatchPlanOutcome(
                plans=validated,
                source="deterministic_content_fallback",
                fallback_used=True,
                fallback_reason_code=_fallback_reason_code(exc),
                diagnostics={"visual_signature_owner": "canonical_v4_5_projection"},
            )


def _stage_trace_context(
    trace_context: Any,
    *,
    rendered_prompt: Any,
    stage: str,
    batch_payload: Mapping[str, Any],
    attempt: int = 1,
) -> Any:
    if trace_context is None:
        return None
    try:
        frame_ids = _frame_ids_from_payload(batch_payload)
        return trace_context_with_prompt_template(
            trace_context,
            rendered_prompt=rendered_prompt,
            attempt=attempt,
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


def _fallback_reason_code(exc: Exception) -> str:
    if isinstance(exc, FrameBatchContractError):
        return exc.code
    return type(exc).__name__


def _fallback_visual_plan(frame: Mapping[str, Any]) -> dict[str, Any]:
    frame_id = str(frame.get("frame_id") or "frame")
    source_text = str(
        frame.get("source_text") or frame.get("frame_source_text") or ""
    )
    visual_goal = str(frame.get("visual_goal") or source_text or "visualize frame")
    return FrameVisualPlan(
        frame_id=frame_id,
        frame_index=int(frame.get("frame_index") or 0),
        source_text=source_text or visual_goal,
        local_claim=visual_goal,
        visual_task=f"Express the local article point for {frame_id}.",
        visual_logic=(
            "Apply the selected visual route to this frame without inventing "
            "unsupported subjects or recurring identity behavior."
        ),
        required_subjects=_fallback_required_subjects(frame),
        forbidden_losses=(
            "do not drop article subjects",
            "do not replace the source claim",
        ),
        evidence_refs=(),
        visible_text_policy="no_visible_text",
    ).to_dict()


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


def _fallback_required_subjects(frame: Mapping[str, Any]) -> tuple[str, ...]:
    subjects: list[str] = []
    for key in (
        "required_subjects",
        "primary_subject",
        "secondary_subjects",
        "continuity_anchors",
    ):
        value = frame.get(key)
        values = (
            value
            if isinstance(value, (list, tuple))
            else (value,)
        )
        for item in values:
            text = str(item or "").strip()
            if text and text not in subjects:
                subjects.append(text)
    if subjects:
        return tuple(subjects)
    return (
        str(
            frame.get("visual_goal")
            or frame.get("prompt_intent")
            or frame.get("source_text")
            or frame.get("frame_source_text")
            or "frame content"
        ).strip(),
    )


__all__ = ["FrameBatchPlanOutcome", "FrameVisualPlanBatchService"]
