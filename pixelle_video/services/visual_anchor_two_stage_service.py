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
    CONTENT_PROMPT_PASSTHROUGH_VERSION,
    CONTENT_STAGE_PROMPT_VERSION,
    FINALIZATION_PROMPT_PASSTHROUGH_VERSION,
    FINALIZATION_STAGE_PROMPT_VERSION,
    FUSION_PROMPT_PASSTHROUGH_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    ContentStageInput,
    ContentStagePromptPassthrough,
    ContinuousSceneContext,
    FinalizationStageInput,
    FinalizationStagePromptPassthrough,
    FusionStageInput,
    FusionStagePromptPassthrough,
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


_FRAME_SOURCE_MAX_CHARS = 6000
_ARTICLE_CONTEXT_MAX_CHARS = 6000


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
            "schema_version": "visual_anchor_two_stage_batch.v10",
            "prompt_versions": {
                "content_stage": CONTENT_STAGE_PROMPT_VERSION,
                "fusion_stage": FUSION_STAGE_PROMPT_VERSION,
                "finalization_stage": FINALIZATION_STAGE_PROMPT_VERSION,
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
    """Three fixed text-model stages before exactly one image request."""

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
        if not isinstance(storyboard_plan, StoryboardPlan):
            raise TypeError("storyboard_plan must be a StoryboardPlan")
        if not storyboard_plan.frames:
            raise VisualAnchorTwoStageError("storyboard plan has no frames")
        oversized_frame = next(
            (
                frame
                for frame in storyboard_plan.frames
                if len(frame.source_text) > _FRAME_SOURCE_MAX_CHARS
            ),
            None,
        )
        if oversized_frame is not None:
            raise VisualAnchorTwoStageError(
                "storyboard frame source text exceeds 6000 characters; split the frame "
                f"before visual planning: {oversized_frame.frame_id}"
            )
        if not isinstance(expected_execution, ImageWorkflowExecutionContract):
            raise TypeError(
                "expected_execution must be an ImageWorkflowExecutionContract"
            )
        if not isinstance(identity_profile, VisualAnchorIdentityProfile):
            raise TypeError("identity_profile must be a VisualAnchorIdentityProfile")
        if identity_reference_condition is not None and not isinstance(
            identity_reference_condition,
            IdentityReferenceCondition,
        ):
            raise TypeError(
                "identity_reference_condition must be an IdentityReferenceCondition"
            )
        if visible_text_policy is not None and not isinstance(
            visible_text_policy,
            VisibleTextPolicy,
        ):
            raise TypeError("visible_text_policy must be a VisibleTextPolicy")
        if not isinstance(target_visual_style, (TargetVisualStyle, str)):
            raise TypeError("target_visual_style must be a TargetVisualStyle or string")
        if type(negative_prompt_supported) is not bool:
            raise TypeError("negative_prompt_supported must be a boolean")
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
        if resolved_identity_conditioning_mode == "reference_image":
            if identity_reference_condition is None:
                raise VisualAnchorTwoStageError(
                    "reference-image conditioning requires a real reference condition"
                )
            if (
                identity_reference_condition.resource_version
                not in identity_profile.source_asset_ids
            ):
                raise VisualAnchorTwoStageError(
                    "identity profile must be bound to the reference resource"
                )
        elif identity_reference_condition is not None:
            raise VisualAnchorTwoStageError(
                "text-profile conditioning cannot include a reference condition"
            )
        resolved_task_id = _required_text(task_id, "task_id")
        resolved_workflow_key = _required_text(workflow_key, "workflow_key")
        resolved_prompt_language = _required_text(
            target_image_prompt_language,
            "target_image_prompt_language",
        )
        resolved_workflow_version = _normalized_text(workflow_version_sha256).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", resolved_workflow_version):
            raise VisualAnchorTwoStageError(
                "workflow_version_sha256 must be a lowercase SHA-256 digest"
            )
        resolved_condition_summary = _required_text(
            workflow_identity_condition_summary
            or (
                "当前工作流使用真实参考图绑定与文字身份档案共同保持身份"
                if resolved_identity_conditioning_mode == "reference_image"
                else "当前工作流仅支持文字提示；使用身份档案名称、核心识别特征和禁止变化项作为真实身份条件"
            ),
            "workflow_identity_condition_summary",
        )
        if not isinstance(random_seeds_by_frame, Mapping):
            raise VisualAnchorTwoStageError("random_seeds_by_frame must be a mapping")
        if set(random_seeds_by_frame) != {
            frame.frame_id for frame in storyboard_plan.frames
        }:
            raise VisualAnchorTwoStageError(
                "random seeds must be registered for every storyboard frame and no others"
            )
        registered_seeds = {
            frame.frame_id: _seed_value(
                random_seeds_by_frame[frame.frame_id],
                f"seed for {frame.frame_id}",
            )
            for frame in storyboard_plan.frames
        }

        scene_ids = _continuous_scene_ids(storyboard_plan.frames)
        decisions_by_scene: dict[str, FinalizationStagePromptPassthrough] = {}
        series_final_prompt_history: list[str] = []
        results: list[VisualAnchorTwoStageFrameResult] = []
        for index, frame in enumerate(storyboard_plan.frames):
            frame_result = await self._run_frame(
                llm_service=llm_service,
                storyboard_plan=storyboard_plan,
                frame=frame,
                frame_index=index,
                scene_id=scene_ids[index],
                existing_fusion_decision=decisions_by_scene.get(scene_ids[index]),
                series_final_prompt_history=list(series_final_prompt_history[-3:]),
                identity_profile=identity_profile,
                identity_reference_condition=identity_reference_condition,
                identity_conditioning_mode=resolved_identity_conditioning_mode,
                workflow_identity_condition_summary=resolved_condition_summary,
                target_visual_style=resolved_style,
                visible_text_policy=resolved_text_policy,
                target_image_prompt_language=resolved_prompt_language,
                task_id=resolved_task_id,
                workflow_key=resolved_workflow_key,
                workflow_version_sha256=resolved_workflow_version,
                expected_execution=expected_execution,
                random_seed=registered_seeds[frame.frame_id],
                negative_prompt_supported=negative_prompt_supported,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                stage_callback=stage_callback,
            )
            finalization_output = frame_result.finalization_stage_output
            if finalization_output is None:
                raise VisualAnchorTwoStageError(
                    "current runtime did not produce a finalization response"
                )
            decisions_by_scene[scene_ids[index]] = finalization_output
            series_final_prompt_history.append(finalization_output.raw_prompt)
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
        existing_fusion_decision: FinalizationStagePromptPassthrough | None,
        series_final_prompt_history: list[str],
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
            article_context=_relevant_article_context(
                source_text=storyboard_plan.source_text,
                frame=frame,
            ),
            previous_frame_summary=previous_summary,
            next_frame_summary=next_summary,
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
                existing_fusion_decision.raw_prompt
                if existing_fusion_decision is not None
                else "无既有融合结果（当前连续场景首镜或独立镜头）"
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
            series_fusion_history=[],
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
            fusion_output = await self._run_fusion_stage(
                llm_service=llm_service,
                stage_input=fusion_input,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
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

        finalization_input = FinalizationStageInput(
            frame_id=frame.frame_id,
            original_storyboard_text=frame.source_text,
            content_stage_input=content_input,
            fusion_stage_input=fusion_input,
            fusion_stage_output=fusion_output,
            series_final_prompt_history=series_final_prompt_history,
        )
        _emit_stage(
            stage_callback,
            stage="visual_anchor_finalization_stage",
            event="start",
            frame_id=frame.frame_id,
            status="running",
        )
        finalization_call_audit = _SinglePassStageCallAudit(
            stage="visual_anchor_finalization_stage",
            frame_id=frame.frame_id,
        )
        try:
            finalization_output = await self._run_finalization_stage(
                llm_service=llm_service,
                stage_input=finalization_input,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                call_audit=finalization_call_audit,
            )
        except Exception:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_finalization_stage",
                event="fail",
                frame_id=frame.frame_id,
                status="failed",
                **finalization_call_audit.terminal_event_fields(),
            )
            raise
        _emit_stage(
            stage_callback,
            stage="visual_anchor_finalization_stage",
            event="end",
            frame_id=frame.frame_id,
            status="completed",
            **finalization_call_audit.terminal_event_fields(),
        )

        generation_request = VisualAnchorImageGenerationRequest(
            task_id=task_id,
            frame_id=frame.frame_id,
            random_seed=random_seed,
            selected_fusion_method="",
            final_manifestation="",
            prompt_assembly_trace=None,
            final_positive_prompt=finalization_output.raw_prompt,
            final_negative_prompt="",
            identity_profile_id=identity_profile.profile_id,
            identity_display_name=identity_profile.display_name,
            identity_core_traits=identity_profile.core_identity_traits,
            identity_forbidden_traits=identity_profile.forbidden_traits,
            identity_resource_version=identity_profile.identity_resource_version,
            identity_content_sha256=identity_profile.identity_content_sha256,
            identity_conditioning_mode=identity_conditioning_mode,
            identity_reference_condition=identity_reference_condition,
            target_visual_style=target_visual_style,
            visible_text_policy=visible_text_policy,
            content_stage_prompt_version=CONTENT_STAGE_PROMPT_VERSION,
            fusion_stage_prompt_version=FUSION_STAGE_PROMPT_VERSION,
            finalization_stage_prompt_version=FINALIZATION_STAGE_PROMPT_VERSION,
            negative_prompt_supported=negative_prompt_supported,
            target_image_prompt_language=target_image_prompt_language,
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
            finalization_stage_input=finalization_input,
            finalization_stage_output=finalization_output,
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
    ) -> ContentStagePromptPassthrough:
        resolved_call_audit = call_audit or _SinglePassStageCallAudit(
            stage="visual_anchor_content_stage",
            frame_id=stage_input.frame_id,
        )
        raw_prompt = await self._call_text(
            llm_service=llm_service,
            prompt_id="visual_anchor_content_stage",
            stage_input=stage_input,
            frame_id=stage_input.frame_id,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            temperature=0.0,
            max_tokens=4096,
            call_audit=resolved_call_audit,
        )
        return ContentStagePromptPassthrough(
            passthrough_version=CONTENT_PROMPT_PASSTHROUGH_VERSION,
            raw_prompt=raw_prompt,
        )

    async def _run_fusion_stage(
        self,
        *,
        llm_service,
        stage_input: FusionStageInput,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        call_audit: _SinglePassStageCallAudit,
    ) -> FusionStagePromptPassthrough:
        raw_prompt = await self._call_text(
            llm_service=llm_service,
            prompt_id="visual_anchor_fusion_stage",
            stage_input=stage_input,
            frame_id=stage_input.frame_id,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            temperature=0.0,
            max_tokens=4096,
            call_audit=call_audit,
        )
        return FusionStagePromptPassthrough(
            passthrough_version=FUSION_PROMPT_PASSTHROUGH_VERSION,
            raw_prompt=raw_prompt,
        )

    async def _run_finalization_stage(
        self,
        *,
        llm_service,
        stage_input: FinalizationStageInput,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        call_audit: _SinglePassStageCallAudit,
    ) -> FinalizationStagePromptPassthrough:
        raw_prompt = await self._call_text(
            llm_service=llm_service,
            prompt_id="visual_anchor_finalization_stage",
            stage_input=stage_input,
            frame_id=stage_input.frame_id,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
            temperature=0.0,
            max_tokens=4096,
            call_audit=call_audit,
        )
        return FinalizationStagePromptPassthrough(
            passthrough_version=FINALIZATION_PROMPT_PASSTHROUGH_VERSION,
            raw_prompt=raw_prompt,
        )

    @staticmethod
    async def _call_text(
        *,
        llm_service,
        prompt_id: str,
        stage_input: Any,
        frame_id: str,
        trace_context: LLMTraceContext | None,
        trace_recorder,
        temperature: float,
        max_tokens: int,
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
            response_type=None,
            temperature=temperature,
            max_tokens=max_tokens,
            trace_context=call_trace_context,
            trace_recorder=trace_recorder,
            single_request=True,
            allow_blank_text_response=True,
        )
        return response


def _render_stage_prompt(
    prompt_id: str,
    stage_input: Any,
) -> RenderedPrompt:
    expected_version = {
        "visual_anchor_content_stage": CONTENT_STAGE_PROMPT_VERSION,
        "visual_anchor_fusion_stage": FUSION_STAGE_PROMPT_VERSION,
        "visual_anchor_finalization_stage": FINALIZATION_STAGE_PROMPT_VERSION,
    }[prompt_id]
    if getattr(stage_input, "prompt_version", None) != expected_version:
        raise VisualAnchorTwoStageError(
            f"stage input version mismatch for {prompt_id}"
        )
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


def _relevant_article_context(
    *,
    source_text: str,
    frame: StoryboardPlanFrame,
) -> str:
    """Keep local article evidence without repeating an unbounded article per frame."""

    if len(source_text) <= _ARTICLE_CONTEXT_MAX_CHARS:
        return source_text
    if frame.source_start is not None and frame.source_end is not None:
        anchor_start = frame.source_start
        anchor_end = frame.source_end
    else:
        anchor_start = source_text.find(frame.source_text)
        anchor_end = (
            anchor_start + len(frame.source_text)
            if anchor_start >= 0
            else -1
        )
    if anchor_start < 0 or anchor_end < anchor_start:
        separator = "\n…\n"
        side_length = (_ARTICLE_CONTEXT_MAX_CHARS - len(separator)) // 2
        return (
            source_text[:side_length]
            + separator
            + source_text[-(_ARTICLE_CONTEXT_MAX_CHARS - side_length - len(separator)) :]
        )

    available_context = _ARTICLE_CONTEXT_MAX_CHARS - (anchor_end - anchor_start)
    left_budget = max(0, available_context // 2)
    window_start = max(0, anchor_start - left_budget)
    window_end = min(len(source_text), window_start + _ARTICLE_CONTEXT_MAX_CHARS)
    if window_end - window_start < _ARTICLE_CONTEXT_MAX_CHARS:
        window_start = max(0, window_end - _ARTICLE_CONTEXT_MAX_CHARS)
    return source_text[window_start:window_end]


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise VisualAnchorTwoStageError(f"{field_name} must be a non-empty string")
    normalized = " ".join(value.split())
    if not normalized:
        raise VisualAnchorTwoStageError(f"{field_name} must be a non-empty string")
    return normalized


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
