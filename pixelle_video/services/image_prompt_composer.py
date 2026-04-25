from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.video_generation_contract import (
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS,
    normalize_plan_frame_overrides,
)
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch


@dataclass
class ImagePromptComposer:
    async def compose(
        self,
        *,
        llm_service,
        storyboard_plan: StoryboardPlan,
        image_config,
        prompt_prefix: Optional[str] = None,
        workflow: Optional[str] = None,
        media_service=None,
        media_type: Literal["image", "video"] = "image",
        min_words: int = 30,
        max_words: int = 60,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        world_preset_id: Optional[str] = None,
        shot_preset_id: Optional[str] = None,
        consistency_strength: str = "standard",
        content_mode: Optional[str] = None,
        role_strategy: Optional[str] = None,
        role_locking_strength: Optional[str] = None,
        shot_strategy: Optional[str] = None,
        frame_overrides: Optional[list[dict[str, Any]]] = None,
        text_rendering: Optional[Mapping[str, Any]] = None,
        native_prompt_hints_by_frame: Optional[Mapping[int, Sequence[NativePromptHint | str]]] = None,
        stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> StyledImagePromptBatch:
        normalized_overrides = normalize_plan_frame_overrides(
            frame_overrides,
            storyboard_plan=storyboard_plan,
        )
        prompt_contexts = _build_prompt_contexts(
            storyboard_plan=storyboard_plan,
            frame_overrides=normalized_overrides,
        )
        batch = await generate_styled_image_prompt_batch(
            llm_service=llm_service,
            narrations=storyboard_plan.narration_texts(),
            prompt_contexts=prompt_contexts,
            image_config=image_config,
            prompt_prefix=prompt_prefix,
            workflow=workflow,
            media_service=media_service,
            media_type=media_type,
            min_words=min_words,
            max_words=max_words,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            progress_callback=progress_callback,
            world_preset_id=world_preset_id,
            shot_preset_id=shot_preset_id,
            consistency_strength=consistency_strength,
            content_mode=content_mode,
            role_strategy=role_strategy,
            role_locking_strength=role_locking_strength,
            shot_strategy=shot_strategy,
            frame_overrides=None,
            text_rendering=text_rendering,
            native_prompt_hints_by_frame=native_prompt_hints_by_frame,
            stage_callback=stage_callback,
        )
        if len(batch.prompts) != storyboard_plan.resolved_scene_count:
            raise ValueError("image prompt count must match storyboard frame count")

        planning_snapshot = dict(batch.planning_snapshot or {})
        planning_snapshot["storyboard_generation"] = storyboard_plan.to_dict()
        return StyledImagePromptBatch(
            prompts=batch.prompts,
            negative_prompt=batch.negative_prompt,
            resolved_style=batch.resolved_style,
            planning_snapshot=planning_snapshot,
        )


def _build_prompt_contexts(
    *,
    storyboard_plan: StoryboardPlan,
    frame_overrides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overrides_by_frame_id = {override["frame_id"]: override for override in frame_overrides}
    contexts: list[dict[str, Any]] = []
    for frame in storyboard_plan.frames:
        context = {
            "plan_id": storyboard_plan.plan_id,
            "plan_revision": storyboard_plan.revision,
            "source_digest": storyboard_plan.source_digest,
            "frame_id": frame.frame_id,
            "frame_index": frame.index,
            "plan_source_text": storyboard_plan.source_text,
            "frame_source_text": frame.source_text,
            "source_text": frame.source_text,
            "narration_text": frame.narration_text,
            "visual_goal": frame.visual_goal,
            "prompt_intent": frame.prompt_intent,
            "shot_type": frame.shot_type,
            "shot_purpose": frame.shot_purpose,
            "primary_subject": frame.primary_subject,
            "secondary_subjects": list(frame.secondary_subjects),
            "continuity_anchors": list(frame.continuity_anchors),
            "world_elements": list(frame.world_elements),
            "source_start": frame.source_start,
            "source_end": frame.source_end,
            "metadata": dict(frame.metadata),
        }
        override = overrides_by_frame_id.get(frame.frame_id)
        if override:
            context["locked_fields"] = list(override["locked_fields"])
            if override.get("override_source") is not None:
                context["override_source"] = override["override_source"]
            for field_name in PLAN_FRAME_OVERRIDE_VALUE_FIELDS:
                if field_name in override and override[field_name] is not None:
                    context[field_name] = override[field_name]
        contexts.append(context)
    return contexts


__all__ = ["ImagePromptComposer"]
