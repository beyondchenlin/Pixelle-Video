from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.visual_story_engine import VisualStoryEnginePlan
from pixelle_video.services.reference_image_visual_context_adapter import (
    current_reference_image_visual_story_context_patch,
)


def visual_story_context_from_plan(plan: VisualStoryEnginePlan | Mapping[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {}
    payload = plan.to_dict() if isinstance(plan, VisualStoryEnginePlan) else dict(plan)
    selected = payload.get("selected_visual_route") or {}
    frame_visual = payload.get("frame_visual_plans") or []
    frame_fusion = payload.get("frame_ip_fusion_plans") or []
    return {
        "visual_story_engine": {
            "plan_id": payload.get("plan_id"),
            "article": payload.get("article") or {},
            "selection": payload.get("selection") or {},
            "selected_visual_route": selected,
            "style_harmonization": payload.get("style_harmonization") or {},
            "channel_memory_intent": payload.get("channel_memory_intent") or "",
        },
        "selected_visual_route": selected,
        "frame_visual_plans": list(frame_visual),
        "frame_ip_fusion_plans": list(frame_fusion),
    }


def attach_visual_story_context(
    prompt_contexts: PromptContextEnvelope,
    visual_story_context: Mapping[str, Any] | None,
) -> PromptContextEnvelope:
    context = _merged_reference_image_context(visual_story_context)
    if not context:
        return prompt_contexts
    plan_context = dict(prompt_contexts.plan_context)
    engine_payload = dict(context.get("visual_story_engine") or {})
    selected_route = dict(context.get("selected_visual_route") or engine_payload.get("selected_visual_route") or {})
    reference_image_payload = dict(context.get("reference_image") or {})
    if engine_payload:
        plan_context["visual_story_engine"] = engine_payload
    if selected_route:
        plan_context["selected_visual_route"] = selected_route
    if reference_image_payload:
        plan_context["reference_image"] = reference_image_payload

    frame_visual_by_id = _by_frame(context.get("frame_visual_plans") or ())
    frame_fusion_by_id = _by_frame(context.get("frame_ip_fusion_plans") or ())
    frame_contexts: list[dict[str, Any]] = []
    for index, frame_context in enumerate(prompt_contexts.frame_contexts):
        frame = dict(frame_context)
        frame_id = str(frame.get("frame_id") or index)
        visual = frame_visual_by_id.get(frame_id)
        fusion = frame_fusion_by_id.get(frame_id)
        if selected_route:
            frame["selected_visual_route"] = selected_route
        if reference_image_payload:
            frame["reference_image"] = reference_image_payload
        if visual:
            frame["visual_story_frame_plan"] = visual
        if fusion:
            frame["visual_story_ip_fusion_plan"] = fusion
        frame_contexts.append(frame)
    return PromptContextEnvelope(plan_context=plan_context, frame_contexts=frame_contexts)


def _merged_reference_image_context(
    visual_story_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = dict(visual_story_context or {})
    reference_patch = current_reference_image_visual_story_context_patch()
    if reference_patch:
        context.update(reference_patch)
    return context


def _by_frame(values: Sequence[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        frame_id = str(value.get("frame_id") or "").strip()
        if frame_id:
            result[frame_id] = dict(value)
    return result


__all__ = ["attach_visual_story_context", "visual_story_context_from_plan"]
