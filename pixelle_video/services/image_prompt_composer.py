from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.text_overlay import project_prompt_text_rendering_request
from pixelle_video.models.video_generation_contract import (
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS,
    normalize_plan_frame_overrides,
)
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, PromptLanguage
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.llm_trace_refs import merge_llm_trace_refs
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import (
    final_visual_prompt_clause_template_metadata,
    final_visual_prompt_template_metadata,
)


@dataclass
class ImagePromptComposer:
    async def compose(
        self,
        *,
        llm_service,
        storyboard_plan: StoryboardPlan,
        image_config,
        prompt_prefix: Optional[str] = None,
        prompt_language: PromptLanguage = DEFAULT_PROMPT_LANGUAGE,
        workflow: Optional[str] = None,
        media_service=None,
        media_type: Literal["image", "video"] = "image",
        min_words: int = 30,
        max_words: int = 60,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, ProgressI18nMessage], None]] = None,
        world_preset_id: Optional[str] = None,
        generation_world_hint: Optional[str] = None,
        shot_preset_id: Optional[str] = None,
        consistency_strength: str = "standard",
        content_mode: Optional[str] = None,
        role_strategy: Optional[str] = None,
        role_locking_strength: Optional[str] = None,
        shot_strategy: Optional[str] = None,
        frame_overrides: Optional[list[dict[str, Any]]] = None,
        text_rendering: Optional[Mapping[str, Any]] = None,
        native_prompt_hints_by_frame: Optional[Mapping[int, Sequence[NativePromptHint | str]]] = None,
        ip_enabled: bool = False,
        ip_profile=None,
        scene_casts_by_frame=None,
        stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
        upstream_llm_trace_refs: Optional[Sequence[Mapping[str, str]]] = None,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
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
            narrations=[
                str(context["frame_source_text"])
                for context in prompt_contexts.frame_contexts
            ],
            storyboard_plan=storyboard_plan,
            prompt_contexts=prompt_contexts,
            image_config=image_config,
            prompt_language=prompt_language,
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
            generation_world_hint=generation_world_hint,
            shot_preset_id=shot_preset_id,
            consistency_strength=consistency_strength,
            content_mode=content_mode,
            role_strategy=role_strategy,
            role_locking_strength=role_locking_strength,
            shot_strategy=shot_strategy,
            frame_overrides=normalized_overrides,
            text_rendering=project_prompt_text_rendering_request(text_rendering),
            native_prompt_hints_by_frame=native_prompt_hints_by_frame,
            ip_enabled=ip_enabled,
            ip_profile=ip_profile,
            scene_casts_by_frame=scene_casts_by_frame,
            stage_callback=stage_callback,
            upstream_llm_trace_refs=upstream_llm_trace_refs,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        if len(batch.prompts) != storyboard_plan.resolved_scene_count:
            raise ValueError("image prompt count must match storyboard frame count")

        planning_snapshot = dict(batch.planning_snapshot or {})
        llm_trace_refs = merge_llm_trace_refs(
            upstream_llm_trace_refs,
            planning_snapshot.get("llm_trace_refs"),
        )
        if llm_trace_refs:
            planning_snapshot["llm_trace_refs"] = llm_trace_refs
        planning_snapshot.setdefault(
            "final_visual_prompt_template",
            final_visual_prompt_template_metadata(),
        )
        planning_snapshot.setdefault(
            "final_visual_prompt_clause_template",
            final_visual_prompt_clause_template_metadata(),
        )
        planning_snapshot["storyboard_generation"] = storyboard_plan.to_dict()
        prompt_plan_bundle = build_prompt_plan_bundle(
            storyboard_plan=storyboard_plan,
            rendered_prompts=batch.rendered_prompts,
            source_trace_ids_by_frame=_prompt_generation_trace_ids_by_frame(
                storyboard_plan,
                planning_snapshot,
            ),
            planning_snapshot=planning_snapshot,
        )
        planning_snapshot["prompt_plan_bundle_ref"] = {
            "storyboard_plan_id": prompt_plan_bundle.storyboard_plan_id,
            "prompt_plan_count": len(prompt_plan_bundle.prompt_plans),
            "image_prompt_draft_count": len(prompt_plan_bundle.image_prompt_drafts),
        }
        return StyledImagePromptBatch(
            prompts=batch.prompts,
            negative_prompt=batch.negative_prompt,
            resolved_style=batch.resolved_style,
            planning_snapshot=planning_snapshot,
            prompt_plan_bundle=prompt_plan_bundle,
        )


def _build_prompt_contexts(
    *,
    storyboard_plan: StoryboardPlan,
    frame_overrides: list[dict[str, Any]],
) -> PromptContextEnvelope:
    overrides_by_frame_id = {override["frame_id"]: override for override in frame_overrides}
    plan_context = {
        "plan_id": storyboard_plan.plan_id,
        "plan_revision": storyboard_plan.revision,
        "source_digest": storyboard_plan.source_digest,
        "plan_source_text": storyboard_plan.source_text,
    }
    frame_contexts: list[dict[str, Any]] = []
    for frame in storyboard_plan.frames:
        context = {
            "frame_id": frame.frame_id,
            "frame_index": frame.index,
            "frame_source_text": frame.source_text,
            "source_text": frame.source_text,
            "visual_goal": frame.visual_goal,
            "prompt_intent": frame.prompt_intent,
            "shot_type": frame.shot_type,
            "shot_purpose": frame.shot_purpose,
            "primary_subject": frame.primary_subject,
            "secondary_subjects": list(frame.secondary_subjects),
            "continuity_anchors": list(frame.continuity_anchors),
            "world_elements": list(frame.world_elements),
            "focus_detail": frame.metadata.get("focus_detail"),
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
                    if field_name == "source_text":
                        context["frame_source_text"] = override[field_name]
        frame_contexts.append(context)
    return PromptContextEnvelope(
        plan_context=plan_context,
        frame_contexts=frame_contexts,
    )


def _prompt_generation_trace_ids_by_frame(
    storyboard_plan: StoryboardPlan,
    planning_snapshot: Mapping[str, Any],
) -> dict[str, str]:
    refs = planning_snapshot.get("prompt_generation_trace_refs_by_index")
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        return {}
    trace_ids_by_frame: dict[str, str] = {}
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        try:
            prompt_index = int(ref.get("prompt_index"))
        except (TypeError, ValueError):
            continue
        if prompt_index < 0 or prompt_index >= len(storyboard_plan.frames):
            continue
        trace_id = str(ref.get("trace_id") or "").strip()
        if not trace_id:
            continue
        trace_ids_by_frame[storyboard_plan.frames[prompt_index].frame_id] = trace_id
    return trace_ids_by_frame


__all__ = ["ImagePromptComposer"]
