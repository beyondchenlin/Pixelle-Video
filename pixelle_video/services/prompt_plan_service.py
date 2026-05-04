from __future__ import annotations

import hashlib
from collections.abc import Sequence

from pixelle_video.models.prompt_plan import (
    ImagePromptDraft,
    PromptPlan,
    PromptPlanBundle,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan


def build_prompt_plan_bundle(
    *,
    storyboard_plan: StoryboardPlan,
    image_prompts: Sequence[str],
    source_trace_id: str | None = None,
    planning_snapshot: dict[str, object] | None = None,
) -> PromptPlanBundle:
    prompts = [_normalize_prompt(prompt) for prompt in image_prompts]
    if len(prompts) != len(storyboard_plan.frames):
        raise ValueError("image prompt count must match storyboard frame count")

    drafts: list[ImagePromptDraft] = []
    plans: list[PromptPlan] = []
    ip_adaptations_by_frame = _ip_adaptations_by_frame(planning_snapshot)
    for frame, prompt in zip(storyboard_plan.frames, prompts):
        draft_id = _stable_id(
            "image_prompt_draft",
            storyboard_plan.plan_id,
            frame.frame_id,
            prompt,
        )
        prompt_plan_id = _stable_id(
            "prompt_plan",
            storyboard_plan.plan_id,
            frame.frame_id,
            draft_id,
            prompt,
        )
        draft = ImagePromptDraft(
            image_prompt_draft_id=draft_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            frame_id=frame.frame_id,
            prompt_text=prompt,
            source_trace_id=source_trace_id,
            metadata={"frame_index": frame.index},
        )
        plan = PromptPlan(
            prompt_plan_id=prompt_plan_id,
            storyboard_plan_id=storyboard_plan.plan_id,
            frame_id=frame.frame_id,
            image_prompt_draft_id=draft.image_prompt_draft_id,
            prompt_sections={
                "source_text": frame.source_text,
                "visual_goal": frame.visual_goal,
                "prompt_intent": frame.prompt_intent,
                "generated_prompt": prompt,
            },
            final_prompt=prompt,
            source_trace_id=source_trace_id,
            metadata=_build_prompt_plan_metadata(
                frame_index=frame.index,
                ip_adaptation=ip_adaptations_by_frame.get(frame.frame_id),
            ),
        )
        drafts.append(draft)
        plans.append(plan)

    return PromptPlanBundle(
        storyboard_plan_id=storyboard_plan.plan_id,
        image_prompt_drafts=tuple(drafts),
        prompt_plans=tuple(plans),
        source_trace_id=source_trace_id,
    )


def _normalize_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("image prompts must be non-empty strings")
    return prompt.strip()


def _ip_adaptations_by_frame(planning_snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not isinstance(planning_snapshot, dict):
        return {}
    payload = planning_snapshot.get("ip_adaptations_by_frame")
    if not isinstance(payload, dict):
        return {}
    return {
        str(frame_id): adaptation
        for frame_id, adaptation in payload.items()
        if isinstance(frame_id, str) and isinstance(adaptation, dict)
    }


def _build_prompt_plan_metadata(
    *,
    frame_index: int,
    ip_adaptation: dict[str, object] | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {"frame_index": frame_index}
    if not isinstance(ip_adaptation, dict):
        return metadata

    ip_presence_type = ip_adaptation.get("ip_presence_type")
    if isinstance(ip_presence_type, str) and ip_presence_type.strip():
        metadata["ip_presence_type"] = ip_presence_type.strip()

    image_text_plan = _summarize_image_text_plan(ip_adaptation.get("image_text_plan"))
    if image_text_plan:
        metadata["image_text_plan"] = image_text_plan

    visible_text_whitelist = _normalize_string_list(ip_adaptation.get("visible_text_whitelist"))
    if not visible_text_whitelist and image_text_plan:
        visible_text_whitelist = _normalize_string_list(
            image_text_plan.get("visible_text_whitelist")
        )
    if visible_text_whitelist:
        metadata["visible_text_whitelist"] = visible_text_whitelist

    return metadata


def _summarize_image_text_plan(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    summary: dict[str, object] = {}
    summary_text = value.get("summary_text")
    if isinstance(summary_text, str) and summary_text.strip():
        summary["summary_text"] = summary_text.strip()

    scene_text = _normalize_string_list(value.get("scene_text"))
    if scene_text:
        summary["scene_text"] = scene_text

    visible_text_whitelist = _normalize_string_list(value.get("visible_text_whitelist"))
    if visible_text_whitelist:
        summary["visible_text_whitelist"] = visible_text_whitelist

    return summary or None


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


__all__ = ["build_prompt_plan_bundle"]
