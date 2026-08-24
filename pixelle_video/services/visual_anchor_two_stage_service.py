from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_STAGE_PROMPT_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    ContentStageInput,
    ContentStageModelOutput,
    ContentStageOutput,
    ContinuousSceneContext,
    FusionStageInput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    TargetVisualStyle,
    VisibleTextPolicy,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
)
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.logging_util import emit_stage_event


class VisualAnchorTwoStageError(RuntimeError):
    pass


@dataclass(slots=True)
class _SinglePassStageCallAudit:
    """Enforce and report the one-call, zero-retry stage invariant."""

    stage: str
    frame_id: str
    llm_call_count: int = 0
    started_at: float = field(default_factory=lambda: perf_counter())

    def record_llm_call(self) -> None:
        if self.llm_call_count != 0:
            raise VisualAnchorTwoStageError(
                f"{self.stage} attempted more than one model call for {self.frame_id}"
            )
        self.llm_call_count = 1

    def terminal_event_fields(self) -> dict[str, int]:
        return {
            "llm_call_count": self.llm_call_count,
            "retry_count": 0,
            "latency_ms": max(0, int((perf_counter() - self.started_at) * 1000)),
        }


@dataclass(frozen=True)
class VisualAnchorTwoStageBatchResult:
    frames: tuple[VisualAnchorTwoStageFrameResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "visual_anchor_two_stage_batch.v6",
            "prompt_versions": {
                "content_stage": CONTENT_STAGE_PROMPT_VERSION,
                "fusion_stage": FUSION_STAGE_PROMPT_VERSION,
            },
            "frames": [frame.model_dump(mode="json") for frame in self.frames],
        }


def identity_profile_from_snapshot(
    snapshot: VisualSignatureProfileSnapshot,
    *,
    identity_reference_resource_id: str | None = None,
) -> VisualAnchorIdentityProfile:
    if not isinstance(snapshot, VisualSignatureProfileSnapshot):
        raise TypeError("snapshot must be a VisualSignatureProfileSnapshot")
    source_asset_ids = list(snapshot.source_asset_ids)
    reference_resource_id = str(identity_reference_resource_id or "").strip()
    if reference_resource_id and reference_resource_id not in source_asset_ids:
        source_asset_ids.append(reference_resource_id)
    return VisualAnchorIdentityProfile(
        profile_id=snapshot.profile_id,
        display_name=snapshot.display_name,
        core_identity_traits=list(snapshot.core_identity_traits),
        supporting_identity_traits=list(snapshot.supporting_identity_traits),
        forbidden_traits=list(snapshot.forbidden_traits),
        source_asset_ids=source_asset_ids,
        identity_content_sha256=snapshot.identity_content_sha256,
        identity_resource_version=(
            f"identity:{snapshot.profile_id}:{snapshot.identity_content_sha256}"
        ),
    )


class VisualAnchorTwoStageService:
    """Content and fusion calls before exactly one image request."""

    async def run_batch(
        self,
        *,
        llm_service,
        storyboard_plan: StoryboardPlan,
        identity_profile: VisualAnchorIdentityProfile,
        identity_reference_condition: IdentityReferenceCondition | None,
        identity_conditioning_mode: str | None = None,
        workflow_identity_condition_summary: str | None = None,
        target_visual_style: TargetVisualStyle | str,
        visible_text_policy: VisibleTextPolicy | None = None,
        target_image_prompt_language: str,
        task_id: str,
        workflow_key: str,
        workflow_version_sha256: str,
        expected_execution: ImageWorkflowExecutionContract,
        random_seeds_by_frame: Mapping[str, int],
        negative_prompt_supported: bool,
        trace_context: LLMTraceContext | None = None,
        trace_recorder=None,
        stage_callback=None,
    ) -> VisualAnchorTwoStageBatchResult:
        if not storyboard_plan.frames:
            raise VisualAnchorTwoStageError("storyboard plan has no frames")
        if not isinstance(expected_execution, ImageWorkflowExecutionContract):
            raise TypeError(
                "expected_execution must be an ImageWorkflowExecutionContract"
            )
        resolved_style = (
            target_visual_style
            if isinstance(target_visual_style, TargetVisualStyle)
            else TargetVisualStyle(description=str(target_visual_style))
        )
        resolved_text_policy = visible_text_policy or VisibleTextPolicy()
        resolved_identity_conditioning_mode = str(
            identity_conditioning_mode
            or (
                "reference_image"
                if identity_reference_condition is not None
                else "text_profile"
            )
        ).strip()
        if resolved_identity_conditioning_mode not in {
            "text_profile",
            "reference_image",
        }:
            raise VisualAnchorTwoStageError(
                "identity conditioning mode must match workflow capabilities"
            )
        resolved_condition_summary = _normalized_text(
            workflow_identity_condition_summary
            or (
                "当前工作流使用真实参考图绑定与文字身份档案共同保持身份"
                if resolved_identity_conditioning_mode == "reference_image"
                else "当前工作流仅支持文字提示；使用身份档案名称、核心识别特征和禁止变化项作为真实身份条件"
            )
        )
        if set(random_seeds_by_frame) != {
            frame.frame_id for frame in storyboard_plan.frames
        }:
            raise VisualAnchorTwoStageError(
                "random seeds must be registered for every storyboard frame and no others"
            )

        scene_ids = _continuous_scene_ids(storyboard_plan.frames)
        decisions_by_scene: dict[str, FusionStageOutput] = {}
        results: list[VisualAnchorTwoStageFrameResult] = []
        for index, frame in enumerate(storyboard_plan.frames):
            frame_result = await self._run_frame(
                llm_service=llm_service,
                storyboard_plan=storyboard_plan,
                frame=frame,
                frame_index=index,
                scene_id=scene_ids[index],
                existing_fusion_decision=decisions_by_scene.get(scene_ids[index]),
                identity_profile=identity_profile,
                identity_reference_condition=identity_reference_condition,
                identity_conditioning_mode=resolved_identity_conditioning_mode,
                workflow_identity_condition_summary=resolved_condition_summary,
                target_visual_style=resolved_style,
                visible_text_policy=resolved_text_policy,
                target_image_prompt_language=target_image_prompt_language,
                task_id=task_id,
                workflow_key=workflow_key,
                workflow_version_sha256=workflow_version_sha256,
                expected_execution=expected_execution,
                random_seed=random_seeds_by_frame[frame.frame_id],
                negative_prompt_supported=negative_prompt_supported,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                stage_callback=stage_callback,
            )
            decisions_by_scene[scene_ids[index]] = frame_result.fusion_stage_output
            results.append(frame_result)
        return VisualAnchorTwoStageBatchResult(frames=tuple(results))

    async def _run_frame(
        self,
        *,
        llm_service,
        storyboard_plan: StoryboardPlan,
        frame: StoryboardPlanFrame,
        frame_index: int,
        scene_id: str,
        existing_fusion_decision: FusionStageOutput | None,
        identity_profile: VisualAnchorIdentityProfile,
        identity_reference_condition: IdentityReferenceCondition | None,
        identity_conditioning_mode: str,
        workflow_identity_condition_summary: str,
        target_visual_style: TargetVisualStyle,
        visible_text_policy: VisibleTextPolicy,
        target_image_prompt_language: str,
        task_id: str,
        workflow_key: str,
        workflow_version_sha256: str,
        expected_execution: ImageWorkflowExecutionContract,
        random_seed: int,
        negative_prompt_supported: bool,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        stage_callback,
    ) -> VisualAnchorTwoStageFrameResult:
        previous_summary = (
            storyboard_plan.frames[frame_index - 1].source_text
            if frame_index > 0
            else "首镜，无前一镜"
        )
        next_summary = (
            storyboard_plan.frames[frame_index + 1].source_text
            if frame_index + 1 < len(storyboard_plan.frames)
            else "末镜，无后一镜"
        )
        content_input = ContentStageInput(
            frame_id=frame.frame_id,
            original_storyboard_text=frame.source_text,
            article_context=storyboard_plan.source_text,
            previous_frame_summary=previous_summary,
            next_frame_summary=next_summary,
            target_visual_style=target_visual_style,
            target_image_prompt_language=target_image_prompt_language,
        )
        _emit_stage(
            stage_callback,
            stage="visual_anchor_content_stage",
            event="start",
            frame_id=frame.frame_id,
            status="running",
        )
        content_call_audit = _SinglePassStageCallAudit(
            stage="visual_anchor_content_stage",
            frame_id=frame.frame_id,
        )
        try:
            content_output = await self._run_content_stage(
                llm_service=llm_service,
                stage_input=content_input,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                call_audit=content_call_audit,
            )
        except Exception:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_content_stage",
                event="fail",
                frame_id=frame.frame_id,
                status="failed",
                **content_call_audit.terminal_event_fields(),
            )
            raise
        _emit_stage(
            stage_callback,
            stage="visual_anchor_content_stage",
            event="end",
            frame_id=frame.frame_id,
            status="completed",
            **content_call_audit.terminal_event_fields(),
        )

        continuity_context = ContinuousSceneContext(
            scene_id=scene_id,
            previous_frame_summary=previous_summary,
            next_frame_summary=next_summary,
            continuity_anchors=list(frame.continuity_anchors),
            existing_fusion_decision=(
                _continuous_fusion_decision(existing_fusion_decision)
                if existing_fusion_decision is not None
                else None
            )
            or "无既有融合决策（当前连续场景首镜或独立镜头）",
            existing_selected_fusion_method=(
                existing_fusion_decision.selected_fusion_method
                if existing_fusion_decision is not None
                else None
            ),
            existing_final_manifestation=(
                existing_fusion_decision.final_manifestation
                if existing_fusion_decision is not None
                else None
            ),
            existing_spatial_contact_and_lighting_relation=(
                existing_fusion_decision.spatial_contact_and_lighting_relation
                if existing_fusion_decision is not None
                else None
            ),
        )

        fusion_input = FusionStageInput(
            frame_id=frame.frame_id,
            original_storyboard_text=frame.source_text,
            content_stage_output=content_output,
            identity_profile=identity_profile,
            identity_conditioning_mode=identity_conditioning_mode,
            identity_reference_condition=identity_reference_condition,
            workflow_identity_condition_summary=workflow_identity_condition_summary,
            continuous_scene_context=continuity_context,
            target_visual_style=target_visual_style,
            visible_text_policy=visible_text_policy,
            negative_prompt_supported=negative_prompt_supported,
            target_image_prompt_language=target_image_prompt_language,
        )
        _emit_stage(
            stage_callback,
            stage="visual_anchor_fusion_stage",
            event="start",
            frame_id=frame.frame_id,
            status="running",
        )
        fusion_call_audit = _SinglePassStageCallAudit(
            stage="visual_anchor_fusion_stage",
            frame_id=frame.frame_id,
        )
        try:
            fusion_output = await self._call_structured(
                llm_service=llm_service,
                prompt_id="visual_anchor_fusion_stage",
                stage_input=fusion_input,
                response_type=FusionStageOutput,
                frame_id=frame.frame_id,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                temperature=0.0,
                call_audit=fusion_call_audit,
            )
        except Exception:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_fusion_stage",
                event="fail",
                frame_id=frame.frame_id,
                status="failed",
                **fusion_call_audit.terminal_event_fields(),
            )
            raise
        _emit_stage(
            stage_callback,
            stage="visual_anchor_fusion_stage",
            event="end",
            frame_id=frame.frame_id,
            status="completed",
            **fusion_call_audit.terminal_event_fields(),
        )

        generation_request = VisualAnchorImageGenerationRequest(
            task_id=task_id,
            frame_id=frame.frame_id,
            random_seed=random_seed,
            selected_fusion_method=fusion_output.selected_fusion_method,
            final_manifestation=fusion_output.final_manifestation,
            final_positive_prompt=fusion_output.final_positive_prompt,
            final_negative_prompt=fusion_output.final_negative_prompt,
            identity_profile_id=identity_profile.profile_id,
            identity_display_name=identity_profile.display_name,
            identity_core_traits=identity_profile.core_identity_traits,
            identity_resource_version=identity_profile.identity_resource_version,
            identity_content_sha256=identity_profile.identity_content_sha256,
            identity_conditioning_mode=identity_conditioning_mode,
            identity_reference_condition=identity_reference_condition,
            target_visual_style=target_visual_style,
            visible_text_policy=visible_text_policy,
            content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
            fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
            negative_prompt_supported=negative_prompt_supported,
            workflow_key=workflow_key,
            workflow_version_sha256=workflow_version_sha256,
            expected_execution=expected_execution,
        )
        return VisualAnchorTwoStageFrameResult(
            frame_id=frame.frame_id,
            content_stage_input=content_input,
            content_stage_output=content_output,
            fusion_stage_input=fusion_input,
            fusion_stage_output=fusion_output,
            generation_request=generation_request,
        )

    async def _run_content_stage(
        self,
        *,
        llm_service,
        stage_input: ContentStageInput,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        call_audit: _SinglePassStageCallAudit | None = None,
    ) -> ContentStageOutput:
        resolved_call_audit = call_audit or _SinglePassStageCallAudit(
            stage="visual_anchor_content_stage",
            frame_id=stage_input.frame_id,
        )
        model_output = await self._call_structured(
            llm_service=llm_service,
            prompt_id="visual_anchor_content_stage",
            stage_input=stage_input,
            response_type=ContentStageModelOutput,
            frame_id=stage_input.frame_id,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            temperature=0.0,
            call_audit=resolved_call_audit,
        )
        output = _materialize_content_stage_output(
            frame_id=stage_input.frame_id,
            model_output=model_output,
        )
        return output

    @staticmethod
    async def _call_structured(
        *,
        llm_service,
        prompt_id: str,
        stage_input: Any,
        response_type,
        frame_id: str,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        temperature: float,
        call_audit: _SinglePassStageCallAudit,
    ):
        rendered = _render_stage_prompt(prompt_id, stage_input)
        call_trace_context = (
            trace_context_with_prompt_template(
                trace_context,
                rendered_prompt=rendered,
                attempt=1,
                stage=rendered.stage,
                frame_id=frame_id,
            )
            if trace_context is not None
            else None
        )
        call_audit.record_llm_call()
        response = await llm_service(
            prompt=rendered.text,
            response_type=response_type,
            temperature=temperature,
            max_tokens=8192,
            trace_context=call_trace_context,
            trace_recorder=trace_recorder,
            single_request=True,
        )
        return response if isinstance(response, response_type) else response_type.model_validate(response)


def _render_stage_prompt(
    prompt_id: str,
    stage_input: Any,
) -> RenderedPrompt:
    input_payload = stage_input.model_dump(mode="json")
    if isinstance(stage_input, ContentStageInput):
        input_payload.pop("prompt_version", None)
    rendered = render_prompt_template(
        prompt_id,
        {
            "input_json": json.dumps(
                input_payload,
                ensure_ascii=False,
                indent=2,
            ),
        },
    )
    expected_version = {
        "visual_anchor_content_stage": CONTENT_STAGE_PROMPT_VERSION,
        "visual_anchor_fusion_stage": FUSION_STAGE_PROMPT_VERSION,
    }[prompt_id]
    if rendered.version != expected_version:
        raise VisualAnchorTwoStageError(
            f"prompt template version mismatch for {prompt_id}"
        )
    return rendered


def _emit_stage(callback, *, stage: str, event: str, **fields: Any) -> None:
    emit_stage_event(
        channel="ai_creation",
        stage=stage,
        event=event,
        message=f"{stage} {event}",
        callback=callback,
        **fields,
    )


def _materialize_content_stage_output(
    *,
    frame_id: str,
    model_output: ContentStageModelOutput,
) -> ContentStageOutput:
    """Assign server-owned subject identifiers without semantic judgment."""

    primary_subject_id = f"{frame_id}-subject-primary"
    primary_subject = {
        **model_output.primary_subject.model_dump(mode="json"),
        "subject_id": primary_subject_id,
        "role": "primary",
    }

    secondary_subjects: list[dict[str, Any]] = []
    for subject_index, subject in enumerate(
        model_output.secondary_subjects,
        start=1,
    ):
        subject_id = f"{frame_id}-subject-secondary-{subject_index}"
        secondary_subjects.append(
            {
                **subject.model_dump(mode="json"),
                "subject_id": subject_id,
                "role": "secondary",
            }
        )
    return ContentStageOutput(
        core_claim=model_output.core_claim,
        scene_facts=model_output.scene_facts,
        primary_subject=primary_subject,
        secondary_subjects=secondary_subjects,
        adjustable_non_core_content=model_output.adjustable_non_core_content,
        pure_content_prompt=model_output.pure_content_prompt,
    )


def _continuous_scene_ids(
    frames: Sequence[StoryboardPlanFrame],
) -> tuple[str, ...]:
    result: list[str] = []
    previous_anchors: frozenset[str] = frozenset()
    current_derived_scene = ""
    for frame in frames:
        explicit = str(frame.metadata.get("continuous_scene_id") or "").strip()
        anchors = frozenset(
            _normalized_text(anchor).casefold()
            for anchor in frame.continuity_anchors
            if _normalized_text(anchor)
        )
        if explicit:
            scene_id = explicit
        elif anchors and previous_anchors and anchors.intersection(previous_anchors):
            scene_id = current_derived_scene
        elif anchors:
            scene_id = f"continuity:{frame.frame_id}"
        else:
            scene_id = f"independent:{frame.frame_id}"
        result.append(scene_id)
        current_derived_scene = scene_id
        previous_anchors = anchors
    return tuple(result)


def _continuous_fusion_decision(output: FusionStageOutput) -> str:
    return (
        f"所选融合方式：{output.selected_fusion_method}；"
        f"最终表现形态：{output.final_manifestation}；"
        f"空间、接触与光照关系：{output.spatial_contact_and_lighting_relation}"
    )


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def resolve_registered_random_seeds(
    *,
    storyboard_plan: StoryboardPlan,
    task_id: str,
    media_seed: object = None,
    media_seed_by_frame: object = None,
) -> dict[str, int]:
    frame_ids = tuple(frame.frame_id for frame in storyboard_plan.frames)
    if isinstance(media_seed_by_frame, Mapping):
        supplied = {str(key): value for key, value in media_seed_by_frame.items()}
        if set(supplied) != set(frame_ids):
            raise VisualAnchorTwoStageError(
                "media_seed_by_frame must contain every frame id and no unknown frame ids"
            )
        return {
            frame_id: _seed_value(supplied[frame_id], f"seed for {frame_id}")
            for frame_id in frame_ids
        }
    if media_seed_by_frame is not None:
        raise VisualAnchorTwoStageError("media_seed_by_frame must be a mapping")
    if media_seed is not None:
        seed = _seed_value(media_seed, "media_seed")
        return {frame_id: seed for frame_id in frame_ids}
    normalized_task_id = _normalized_text(task_id)
    if not normalized_task_id:
        raise VisualAnchorTwoStageError("task id is required before registering seeds")
    return {
        frame_id: max(
            1,
            int.from_bytes(
                hashlib.sha256(
                    f"{normalized_task_id}:{frame_id}".encode("utf-8")
                ).digest()[:8],
                "big",
            ),
        )
        for frame_id in frame_ids
    }


def _seed_value(value: object, field_name: str) -> int:
    if type(value) is int:
        seed = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value.strip()):
        seed = int(value.strip())
    else:
        raise VisualAnchorTwoStageError(f"{field_name} must be a positive integer")
    if seed < 1 or seed > (2**64 - 1):
        raise VisualAnchorTwoStageError(
            f"{field_name} must be between 1 and 2^64-1"
        )
    return seed


__all__ = [
    "VisualAnchorTwoStageBatchResult",
    "VisualAnchorTwoStageError",
    "VisualAnchorTwoStageService",
    "identity_profile_from_snapshot",
    "resolve_registered_random_seeds",
]
