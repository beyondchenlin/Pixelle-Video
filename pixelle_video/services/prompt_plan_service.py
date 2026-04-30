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
) -> PromptPlanBundle:
    prompts = [_normalize_prompt(prompt) for prompt in image_prompts]
    if len(prompts) != len(storyboard_plan.frames):
        raise ValueError("image prompt count must match storyboard frame count")

    drafts: list[ImagePromptDraft] = []
    plans: list[PromptPlan] = []
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
            metadata={"frame_index": frame.index},
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


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


__all__ = ["build_prompt_plan_bundle"]
