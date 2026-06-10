from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pixelle_video.models.llm_interaction_trace import trace_context_with_prompt_template
from pixelle_video.models.visual_story_engine import FrameIPFusionPlan, FrameVisualPlan
from pixelle_video.prompts.visual_story_execution import (
    render_frame_ip_fusion_batch_prompt,
    render_frame_visual_plan_batch_prompt,
)
from pixelle_video.utils.json_parsing import parse_llm_json_response


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
            plans = _list_payload(response, "frame_visual_plans")
            return tuple(FrameVisualPlan.from_mapping(item).to_dict() for item in plans)
        except Exception as exc:
            logger.warning("Frame visual plan batch failed; using deterministic fallback: {}", exc)
            return tuple(
                _fallback_visual_plan(item)
                for item in batch_payload.get("frame_contexts", ())
                if isinstance(item, Mapping)
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
        if not ip_profile:
            return tuple(_no_ip_plan(plan) for plan in frame_visual_plans)
        compact_ip_profile = _compact_ip_profile(ip_profile)
        rendered_prompt = render_frame_ip_fusion_batch_prompt(
            selected_visual_route=selected_visual_route,
            style_harmonization=style_harmonization,
            ip_profile=compact_ip_profile,
            frame_visual_plans=frame_visual_plans,
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
                    batch_payload={"frame_visual_plans": list(frame_visual_plans)},
                ),
                trace_recorder=trace_recorder,
            )
            plans = _list_payload(response, "frame_ip_fusion_plans")
            return tuple(FrameIPFusionPlan.from_mapping(item).to_dict() for item in plans)
        except Exception as exc:
            logger.warning("Frame IP fusion batch failed; using deterministic fallback: {}", exc)
            return tuple(
                _fallback_ip_plan(plan, selected_visual_route, style_harmonization)
                for plan in frame_visual_plans
            )


def _stage_trace_context(trace_context: Any, *, rendered_prompt: Any, stage: str, batch_payload: Mapping[str, Any]) -> Any:
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


def _list_payload(response: Any, key: str) -> list[Mapping[str, Any]]:
    if hasattr(response, "model_dump"):
        response = response.model_dump(mode="json")
    elif isinstance(response, str):
        response = parse_llm_json_response(
            response.strip(),
            allow_code_fence=True,
            allow_embedded_json=False,
        )
    if not isinstance(response, Mapping):
        raise ValueError(f"{key} response must be a mapping")
    values = response.get(key) or response.get("frames") or response.get("plans") or []
    if isinstance(values, Mapping):
        values = list(values.values())
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{key} must be a list")
    return [dict(item) for item in values if isinstance(item, Mapping)]


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
    return FrameVisualPlan(
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


def _fallback_ip_plan(
    frame_visual_plan: Mapping[str, Any],
    selected_visual_route: Mapping[str, Any],
    style_harmonization: Mapping[str, Any],
) -> dict[str, Any]:
    return FrameIPFusionPlan(
        frame_id=frame_visual_plan.get("frame_id") or "frame",
        ip_role=selected_visual_route.get("recommended_ip_role") or "silent_witness",
        ip_visibility="low",
        placement_logic="Place the channel IP as a scene-bound, non-disruptive supporting visual signature.",
        action_or_function="Support comprehension of the current frame without becoming the article subject.",
        relation_to_article_subject="The IP observes or guides; it must not replace article subjects.",
        style_harmonization=style_harmonization.get("mode") or "hybrid_layered",
        positive_prompt_clause="visible channel IP integrated naturally as a small supporting in-scene element",
        negative_constraints=("do not replace article subjects", "do not dominate the frame"),
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
        negative_constraints=("do not add recurring channel character",),
    ).to_dict()


def _truncate(value: Any, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


__all__ = ["FrameVisualPlanBatchService", "FrameIPFusionPlanBatchService"]
