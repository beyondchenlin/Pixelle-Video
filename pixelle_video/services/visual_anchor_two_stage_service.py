from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, get_args

from pydantic import ValidationError

from pixelle_video.models.llm_interaction_trace import (
    LLMTraceContext,
    trace_context_with_prompt_template,
)
from pixelle_video.models.llm_response import LLMResponseContractError
from pixelle_video.models.series_visual_signature import VisualSignatureProfileSnapshot
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.visual_anchor_two_stage import (
    CONTENT_STAGE_PROMPT_VERSION,
    FUSION_STAGE_PROMPT_VERSION,
    PREFLIGHT_REVIEW_PROMPT_VERSION,
    ContentFact,
    ContentStageInput,
    ContentStageModelOutput,
    ContentStageOutput,
    ContentStageValidationCode,
    ContinuousSceneContext,
    FusionStageInput,
    FusionStageOutput,
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    PreflightReviewInput,
    PreflightReviewOutput,
    TargetVisualStyle,
    VisibleTextPolicy,
    VisualAnchorIdentityProfile,
    VisualAnchorImageGenerationRequest,
    VisualAnchorTwoStageFrameResult,
)
from pixelle_video.prompts.template_loader import RenderedPrompt, render_prompt_template
from pixelle_video.utils.logging_util import emit_stage_event

_CANDIDATE_TERMS = (
    "候选方案",
    "未选方案",
    "方案一",
    "方案二",
    "方案三",
    "或者",
    "也可以",
    "另一种形式",
    "可选择",
    "同时还可以",
    "alternatively",
    "another option",
    "could also",
    "or it could",
    "candidate option",
    "unselected option",
    "option one",
    "option two",
    "option three",
)
_INTERNAL_PLANNING_TERMS = (
    "视觉锚点",
    "知识产权角色",
    "受保护事实",
    "融合方案",
    "visual anchor",
    "protected fact",
    "fusion option",
    "final manifestation",
    "identity trait checks",
    "single instance prompt evidence",
)
_SINGLE_INSTANCE_TERMS = (
    "只有一个",
    "仅有一个",
    "唯一一个",
    "只有一只",
    "仅有一只",
    "唯一一只",
    "只有一名",
    "仅有一名",
    "唯一一名",
    "exactly one",
    "only one",
    "a single",
)
_SINGLE_INSTANCE_CLAUSE_DELIMITERS = ",，;；。.!！?？\n"
_SINGLE_INSTANCE_NEGATION_SUFFIXES = (
    "不",
    "没",
    "没有",
    "不止",
    "不只",
    "不只是",
    "并非",
    "不是",
    "并不是",
    "并不止",
    "未",
    "并未",
    "not",
    "is not",
    "isn't",
)
_CONTENT_STAGE_FORBIDDEN_TERMS = (
    "视觉锚点",
    "知识产权角色",
    "系列角色",
    "品牌形象",
    "吉祥物",
    "预留角落",
    "预留位置",
    "anchor slot",
    "reserved corner",
    "visual anchor",
    "mascot",
)
_CONTENT_STAGE_RESERVATION_TERMS = (
    "预留角落",
    "预留位置",
    "anchor slot",
    "reserved corner",
)
_EMPTY_CONTINUITY_REASONS = frozenset(
    {
        "",
        "无",
        "无变化",
        "未变化",
        "不适用",
        "无需说明",
        "none",
        "n/a",
        "not applicable",
    }
)
_CONTINUITY_CHANGE_TRIGGER_TERMS = (
    "镜头",
    "镜头切换",
    "镜头变化",
    "景别变化",
    "视角变化",
    "景别",
    "视角",
    "时间跳跃",
    "时间变化",
    "时间",
    "地点变化",
    "地点切换",
    "地点",
    "场景变化",
    "场景",
    "叙事需要",
    "叙事要求",
    "叙事",
    "剧情",
    "camera change",
    "shot change",
    "time jump",
    "time change",
    "location change",
    "scene change",
    "narrative need",
    "camera",
    "shot",
    "time",
    "location",
    "scene",
    "narrative",
    "story",
)
_CONTENT_STAGE_VALIDATION_MESSAGES: dict[ContentStageValidationCode, str] = {
    "schema_contract_invalid": "输出缺少字段、字段类型错误或违反结构合同",
    "self_check_failed": "输出自检未通过",
    "subject_source_evidence_invalid": "主体的原文证据不是输入中的连续原文",
    "subject_prompt_evidence_invalid": "主体没有真实出现在纯内容提示词中",
    "concrete_fact_missing": "输出没有具体可见事实",
    "fact_subject_reference_invalid": "事实引用了不存在的主体",
    "fact_subject_evidence_mismatch": "事实证据与所引用主体的证据不对应",
    "subject_fact_missing": "主体没有由服务端关联的受保护事实",
    "fact_source_evidence_invalid": "事实的原文证据不是输入中的连续原文",
    "fact_prompt_evidence_invalid": "事实没有真实出现在纯内容提示词中",
    "identity_isolation_failed": "内容阶段混入了视觉锚点身份或预留信息",
    "server_control_leaked": "内容字段泄漏了服务端校验代码或修复指令",
}
if set(_CONTENT_STAGE_VALIDATION_MESSAGES) != set(
    get_args(ContentStageValidationCode)
):
    raise RuntimeError("content-stage validation codes and messages must stay aligned")


class VisualAnchorTwoStageError(RuntimeError):
    pass


class ContentStageContractError(VisualAnchorTwoStageError):
    def __init__(self, codes: Sequence[ContentStageValidationCode]) -> None:
        self.codes = _ordered_content_stage_validation_codes(codes)
        details = "; ".join(
            _CONTENT_STAGE_VALIDATION_MESSAGES[code] for code in self.codes
        )
        code_summary = ",".join(self.codes)
        super().__init__(
            f"content stage contract validation failed [{code_summary}]: {details}"
        )


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
            "schema_version": "visual_anchor_two_stage_batch.v5",
            "prompt_versions": {
                "content_stage": CONTENT_STAGE_PROMPT_VERSION,
                "fusion_stage": FUSION_STAGE_PROMPT_VERSION,
                "preflight_review": PREFLIGHT_REVIEW_PROMPT_VERSION,
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
    """Content, fusion, and preflight calls before exactly one image request."""

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
        _validate_content_stage_identity_isolation(
            storyboard_plan=storyboard_plan,
            identity_profile=identity_profile,
            target_visual_style=resolved_style,
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
            required_single_instance_prompt_fragment=(
                _required_single_instance_prompt_fragment(
                    identity_profile.display_name,
                    target_image_prompt_language,
                )
            ),
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
            fusion_output = _normalize_fusion_protected_fact_evidence(
                fusion_input,
                fusion_output,
            )
            fusion_output = _normalize_fusion_single_instance_evidence(
                fusion_input,
                fusion_output,
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
        try:
            _validate_fusion_stage_output(fusion_input, fusion_output)
        except VisualAnchorTwoStageError:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_fusion_stage",
                event="fail",
                frame_id=frame.frame_id,
                status="rejected",
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

        review_input = PreflightReviewInput(
            frame_id=frame.frame_id,
            original_storyboard_text=frame.source_text,
            content_stage_output=content_output,
            identity_profile=identity_profile,
            identity_conditioning_mode=identity_conditioning_mode,
            identity_reference_condition=identity_reference_condition,
            continuous_scene_context=continuity_context,
            target_visual_style=target_visual_style,
            visible_text_policy=visible_text_policy,
            fusion_stage_output=fusion_output,
            negative_prompt_supported=negative_prompt_supported,
        )
        _emit_stage(
            stage_callback,
            stage="visual_anchor_preflight_review",
            event="start",
            frame_id=frame.frame_id,
            status="running",
        )
        review_call_audit = _SinglePassStageCallAudit(
            stage="visual_anchor_preflight_review",
            frame_id=frame.frame_id,
        )
        try:
            review_output = await self._call_structured(
                llm_service=llm_service,
                prompt_id="visual_anchor_preflight_review",
                stage_input=review_input,
                response_type=PreflightReviewOutput,
                frame_id=frame.frame_id,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                temperature=0.0,
                call_audit=review_call_audit,
            )
            review_passed = _preflight_review_passes(review_input, review_output)
        except Exception:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_preflight_review",
                event="fail",
                frame_id=frame.frame_id,
                status="failed",
                **review_call_audit.terminal_event_fields(),
            )
            raise
        if not review_passed:
            _emit_stage(
                stage_callback,
                stage="visual_anchor_preflight_review",
                event="fail",
                frame_id=frame.frame_id,
                status="rejected",
                **review_call_audit.terminal_event_fields(),
            )
            evidence = "; ".join(review_output.failures)
            raise VisualAnchorTwoStageError(
                f"preflight review rejected frame {frame.frame_id}: {evidence}"
            )
        _emit_stage(
            stage_callback,
            stage="visual_anchor_preflight_review",
            event="end",
            frame_id=frame.frame_id,
            status="passed",
            **review_call_audit.terminal_event_fields(),
        )

        generation_request = VisualAnchorImageGenerationRequest(
            task_id=task_id,
            frame_id=frame.frame_id,
            random_seed=random_seed,
            selected_fusion_method=fusion_output.selected_fusion_method,
            final_manifestation=fusion_output.final_manifestation,
            protected_fact_checks=fusion_output.protected_fact_checks,
            primary_subject_name=content_output.primary_subject.name,
            primary_subject_preserved=True,
            primary_subject_final_prompt_evidence=(
                fusion_output.primary_subject_final_prompt_evidence
            ),
            visual_anchor_replaces_primary_subject=False,
            identity_trait_checks=fusion_output.identity_trait_checks,
            single_instance_prompt_evidence=(
                fusion_output.single_instance_prompt_evidence
            ),
            final_positive_prompt=review_output.allowed_final_positive_prompt,
            final_negative_prompt=review_output.allowed_final_negative_prompt,
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
            preflight_review_prompt_version=PREFLIGHT_REVIEW_PROMPT_VERSION,
            preflight_review_decision="pass",
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
            preflight_review_input=review_input,
            preflight_review_output=review_output,
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
        try:
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
        except Exception as exc:
            if _is_content_stage_output_contract_error(exc):
                raise ContentStageContractError(("schema_contract_invalid",)) from exc
            raise
        output = _materialize_content_stage_output(
            frame_id=stage_input.frame_id,
            model_output=model_output,
        )
        _validate_content_stage_output(stage_input, output)
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
    if isinstance(stage_input, FusionStageInput):
        input_payload.pop("review_feedback", None)
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
        "visual_anchor_preflight_review": PREFLIGHT_REVIEW_PROMPT_VERSION,
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


def _ordered_content_stage_validation_codes(
    codes: Sequence[ContentStageValidationCode],
) -> tuple[ContentStageValidationCode, ...]:
    known_codes = tuple(_CONTENT_STAGE_VALIDATION_MESSAGES)
    unknown_codes = set(codes).difference(known_codes)
    if unknown_codes:
        raise ValueError("unknown content-stage validation code")
    requested = set(codes)
    return tuple(code for code in known_codes if code in requested)


def _is_content_stage_output_contract_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(
            current,
            (json.JSONDecodeError, LLMResponseContractError, ValidationError),
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _validate_content_stage_output(
    stage_input: ContentStageInput,
    output: ContentStageOutput,
) -> None:
    validation_codes: list[ContentStageValidationCode] = []
    if output.self_check != "pass":
        validation_codes.append("self_check_failed")
    source = _normalized_text(
        f"{stage_input.original_storyboard_text}\n{stage_input.article_context}"
    )
    normalized_source = source.casefold()
    normalized_pure_prompt = _normalized_text(
        output.pure_content_prompt
    ).casefold()
    subjects = [output.primary_subject, *output.secondary_subjects]
    for subject in subjects:
        source_evidence = _normalized_text(subject.source_evidence).casefold()
        if source_evidence not in normalized_source:
            validation_codes.append("subject_source_evidence_invalid")
        prompt_evidence = _normalized_text(
            subject.pure_content_prompt_evidence
        ).casefold()
        if prompt_evidence not in normalized_pure_prompt:
            validation_codes.append("subject_prompt_evidence_invalid")
    subjects_by_id = {subject.subject_id: subject for subject in subjects}
    matched_subject_ids: set[str] = set()
    for fact in output.protected_facts:
        fact_source_evidence = _normalized_text(fact.source_evidence).casefold()
        fact_prompt_evidence = _normalized_text(
            fact.pure_content_prompt_evidence
        ).casefold()
        for subject_id in fact.subject_ids:
            if subject_id not in subjects_by_id:
                validation_codes.append("fact_subject_reference_invalid")
                continue
            matched_subject_ids.add(subject_id)
        if fact_source_evidence not in normalized_source:
            validation_codes.append("fact_source_evidence_invalid")
        if (
            not fact_prompt_evidence
            or fact_prompt_evidence not in normalized_pure_prompt
        ):
            validation_codes.append("fact_prompt_evidence_invalid")
    if matched_subject_ids != set(subjects_by_id):
        validation_codes.append("subject_fact_missing")

    content_payload = _normalized_text(
        "\n".join(
            [
                output.core_claim,
                output.pure_content_prompt,
                *output.adjustable_non_core_content,
            ]
        )
    ).casefold()
    for term in _CONTENT_STAGE_FORBIDDEN_TERMS:
        normalized = _normalized_text(term).casefold()
        is_unconditionally_forbidden = any(
            _contains_term(normalized, reservation_term)
            for reservation_term in _CONTENT_STAGE_RESERVATION_TERMS
        )
        if (
            normalized
            and _contains_term(content_payload, normalized)
            and (
                is_unconditionally_forbidden
                or not _contains_term(normalized_source, normalized)
            )
        ):
            validation_codes.append("identity_isolation_failed")

    server_control_terms = (
        "server_validation",
        "validation_codes",
        *_CONTENT_STAGE_VALIDATION_MESSAGES,
        *_CONTENT_STAGE_VALIDATION_MESSAGES.values(),
    )
    if any(
        _contains_term(content_payload, _normalized_text(term).casefold())
        for term in server_control_terms
    ):
        validation_codes.append("server_control_leaked")

    if validation_codes:
        raise ContentStageContractError(validation_codes)


def _materialize_content_stage_output(
    *,
    frame_id: str,
    model_output: ContentStageModelOutput,
) -> ContentStageOutput:
    """Assign server-owned identifiers after the model response has been validated."""

    protected_facts: list[dict[str, Any]] = []
    protected_fact_keys: set[tuple[str, str, str, tuple[str, ...]]] = set()

    def subject_facts(subject) -> Sequence[ContentFact]:
        if (
            subject.protected_facts
            or "protected_facts" in subject.model_fields_set
        ):
            return subject.protected_facts
        return (
            ContentFact(
                category=subject.category,
                statement=subject.name,
                source_evidence=subject.source_evidence,
                pure_content_prompt_evidence=subject.pure_content_prompt_evidence,
            ),
        )

    def append_facts(*, facts, subject_ids: list[str]) -> None:
        for fact in facts:
            fact_key = (
                fact.category,
                _normalized_text(fact.source_evidence).casefold(),
                _normalized_text(fact.pure_content_prompt_evidence).casefold(),
                tuple(sorted(subject_ids)),
            )
            if fact_key in protected_fact_keys:
                continue
            protected_fact_keys.add(fact_key)
            fact_index = len(protected_facts) + 1
            protected_facts.append(
                {
                    **fact.model_dump(mode="json"),
                    "fact_id": f"{frame_id}-fact-{fact_index}",
                    "subject_ids": subject_ids,
                }
            )

    primary_subject_id = f"{frame_id}-subject-primary"
    primary_subject = {
        **model_output.primary_subject.model_dump(
            mode="json",
            exclude={"protected_facts"},
        ),
        "subject_id": primary_subject_id,
        "role": "primary",
    }
    append_facts(
        facts=subject_facts(model_output.primary_subject),
        subject_ids=[primary_subject_id],
    )

    secondary_subjects: list[dict[str, Any]] = []
    for subject_index, subject in enumerate(
        model_output.secondary_subjects,
        start=1,
    ):
        subject_id = f"{frame_id}-subject-secondary-{subject_index}"
        secondary_subjects.append(
            {
                **subject.model_dump(
                    mode="json",
                    exclude={"protected_facts"},
                ),
                "subject_id": subject_id,
                "role": "secondary",
            }
        )
        append_facts(
            facts=subject_facts(subject),
            subject_ids=[subject_id],
        )

    subject_fact_refs = [
        (primary_subject_id, model_output.primary_subject),
        *[
            (f"{frame_id}-subject-secondary-{subject_index}", subject)
            for subject_index, subject in enumerate(
                model_output.secondary_subjects,
                start=1,
            )
        ],
    ]
    for fact in model_output.scene_facts:
        fact_text = _normalized_text(
            "\n".join(
                [
                    fact.statement,
                    fact.source_evidence,
                    fact.pure_content_prompt_evidence,
                ]
            )
        ).casefold()
        matching_subject_ids = [
            subject_id
            for subject_id, subject in subject_fact_refs
            if any(
                _normalized_text(alias).casefold() in fact_text
                for alias in {subject.name, subject.identity}
                if _normalized_text(alias)
            )
        ]
        append_facts(facts=[fact], subject_ids=matching_subject_ids)
    return ContentStageOutput(
        core_claim=model_output.core_claim,
        protected_facts=protected_facts,
        primary_subject=primary_subject,
        secondary_subjects=secondary_subjects,
        adjustable_non_core_content=model_output.adjustable_non_core_content,
        pure_content_prompt=model_output.pure_content_prompt,
        self_check=model_output.self_check,
        self_check_failures=model_output.self_check_failures,
    )


def _validate_content_stage_identity_isolation(
    *,
    storyboard_plan: StoryboardPlan,
    identity_profile: VisualAnchorIdentityProfile,
    target_visual_style: TargetVisualStyle,
) -> None:
    """Reject identity-bearing style data before the content-only model call."""

    content_source = _normalized_text(
        "\n".join(
            [
                storyboard_plan.source_text,
                *(frame.source_text for frame in storyboard_plan.frames),
            ]
        )
    ).casefold()
    normalized_style = _normalized_text(
        json.dumps(target_visual_style.model_dump(mode="json"), ensure_ascii=False)
    ).casefold()
    for forbidden_term in _CONTENT_STAGE_FORBIDDEN_TERMS:
        if _contains_term(normalized_style, forbidden_term):
            raise VisualAnchorTwoStageError(
                "content-stage visual style contains visual-anchor planning information"
            )
    identity_values = [
        identity_profile.profile_id,
        identity_profile.display_name,
        identity_profile.identity_resource_version,
        *identity_profile.core_identity_traits,
        *identity_profile.supporting_identity_traits,
        *identity_profile.forbidden_traits,
        *identity_profile.source_asset_ids,
    ]
    for value in identity_values:
        normalized_identity_value = _normalized_text(value).casefold()
        if not normalized_identity_value:
            continue
        if (
            _contains_term(normalized_style, normalized_identity_value)
            and not _contains_term(content_source, normalized_identity_value)
        ):
            raise VisualAnchorTwoStageError(
                "content-stage visual style contains identity-profile information"
            )


def _validate_fusion_stage_output(
    stage_input: FusionStageInput,
    output: FusionStageOutput,
) -> None:
    if output.self_check != "pass":
        raise VisualAnchorTwoStageError("fusion self-check did not pass")
    expected_fact_ids = {
        fact.fact_id for fact in stage_input.content_stage_output.protected_facts
    }
    actual_fact_id_list = [check.fact_id for check in output.protected_fact_checks]
    actual_fact_ids = set(actual_fact_id_list)
    if (
        actual_fact_ids != expected_fact_ids
        or len(actual_fact_id_list) != len(expected_fact_ids)
    ):
        raise VisualAnchorTwoStageError(
            "fusion protected-fact checks do not exactly cover the content-stage contract"
        )
    if any(not check.preserved for check in output.protected_fact_checks):
        raise VisualAnchorTwoStageError("fusion changed a protected fact")
    normalized_positive = _normalized_text(output.final_positive_prompt).casefold()
    primary_subject = stage_input.content_stage_output.primary_subject
    primary_evidence = _normalized_text(
        output.primary_subject_final_prompt_evidence
    ).casefold()
    normalized_primary_name = _normalized_text(primary_subject.name).casefold()
    if not output.primary_subject_preserved:
        raise VisualAnchorTwoStageError("fusion dropped the concrete primary subject")
    if (
        not primary_evidence
        or primary_evidence != normalized_primary_name
        or primary_evidence not in normalized_positive
    ):
        raise VisualAnchorTwoStageError(
            "primary-subject evidence is not present in the final positive prompt"
        )
    normalized_source = _normalized_text(stage_input.original_storyboard_text).casefold()
    normalized_identity_name = _normalized_text(
        stage_input.identity_profile.display_name
    ).casefold()
    if (
        _normalized_text(primary_subject.name).casefold() == normalized_identity_name
        and not _contains_term(normalized_source, normalized_identity_name)
    ):
        raise VisualAnchorTwoStageError(
            "visual-anchor identity cannot become the default primary subject"
        )
    for check in output.protected_fact_checks:
        evidence = _normalized_text(check.final_image_evidence).casefold()
        if not evidence or evidence not in normalized_positive:
            raise VisualAnchorTwoStageError(
                f"protected fact {check.fact_id} evidence is not present in the final positive prompt"
            )
    expected_traits = [
        _normalized_text(trait).casefold()
        for trait in stage_input.identity_profile.core_identity_traits
    ]
    actual_traits = [
        _normalized_text(check.trait).casefold()
        for check in output.identity_trait_checks
    ]
    if (
        set(actual_traits) != set(expected_traits)
        or len(actual_traits) != len(expected_traits)
    ):
        raise VisualAnchorTwoStageError(
            "fusion identity-trait checks do not exactly cover the identity profile"
        )
    identity_evidence_values: list[str] = []
    for check in output.identity_trait_checks:
        if not check.preserved:
            raise VisualAnchorTwoStageError(
                f"fusion dropped core identity trait: {check.trait}"
            )
        evidence = _normalized_text(check.final_prompt_evidence).casefold()
        normalized_trait = _normalized_text(check.trait).casefold()
        if (
            not evidence
            or (
                evidence == normalized_identity_name
                and normalized_trait != normalized_identity_name
            )
            or evidence not in normalized_positive
        ):
            raise VisualAnchorTwoStageError(
                f"identity trait evidence is not present in the final positive prompt: {check.trait}"
            )
        identity_evidence_values.append(evidence)
    if len(set(identity_evidence_values)) != len(identity_evidence_values):
        raise VisualAnchorTwoStageError(
            "each core identity trait must have distinct visible evidence in the final positive prompt"
        )
    single_instance_evidence = _normalized_text(
        output.single_instance_prompt_evidence
    ).casefold()
    if single_instance_evidence not in normalized_positive:
        raise VisualAnchorTwoStageError(
            "single-instance evidence is not present in the final positive prompt"
        )
    if not any(
        _contains_term(single_instance_evidence, term)
        for term in _SINGLE_INSTANCE_TERMS
    ):
        raise VisualAnchorTwoStageError(
            "single-instance evidence does not explicitly describe exactly one identity instance"
        )
    if not _contains_term(
        single_instance_evidence,
        normalized_identity_name,
    ):
        raise VisualAnchorTwoStageError(
            "single-instance evidence does not identify the selected identity"
        )
    if (
        _extract_single_instance_prompt_evidence(
            single_instance_evidence,
            normalized_identity_name,
        )
        is None
    ):
        raise VisualAnchorTwoStageError(
            "single-instance evidence is negated or does not form one continuous clause"
        )
    existing_method = (
        stage_input.continuous_scene_context.existing_selected_fusion_method
    )
    existing_manifestation = (
        stage_input.continuous_scene_context.existing_final_manifestation
    )
    existing_spatial_relation = (
        stage_input.continuous_scene_context.existing_spatial_contact_and_lighting_relation
    )
    has_existing_decision = existing_method is not None
    change_reason = _normalized_text(output.continuity_change_reason).casefold()
    if not output.inherited_existing_fusion_decision and (
        has_existing_decision
        and change_reason in _EMPTY_CONTINUITY_REASONS
    ):
        raise VisualAnchorTwoStageError(
            "continuous-scene fusion changed without an explicit scene-change reason"
        )
    if (
        not output.inherited_existing_fusion_decision
        and has_existing_decision
        and not any(
            _contains_term(change_reason, term)
            for term in _CONTINUITY_CHANGE_TRIGGER_TERMS
        )
    ):
        raise VisualAnchorTwoStageError(
            "continuous-scene fusion change reason must identify a camera, time, location, scene, or narrative trigger"
        )
    if (
        not has_existing_decision
        and output.inherited_existing_fusion_decision
    ):
        raise VisualAnchorTwoStageError(
            "the first frame of a scene cannot claim to inherit a fusion decision"
        )
    if output.inherited_existing_fusion_decision and (
        output.selected_fusion_method != existing_method
        or output.final_manifestation != existing_manifestation
        or output.spatial_contact_and_lighting_relation != existing_spatial_relation
    ):
        raise VisualAnchorTwoStageError(
            "an inherited continuous-scene decision must preserve its method, manifestation, and basic spatial relation exactly"
        )
    decision_boundary = (
        f"{output.selected_fusion_method}\n{output.final_manifestation}"
    ).casefold()
    for term in _CANDIDATE_TERMS:
        if _contains_term(decision_boundary, term):
            raise VisualAnchorTwoStageError(
                "fusion decision contains more than one candidate method"
            )
    for candidate in output.unselected_candidate_summaries:
        normalized_image_prompt_boundary = _normalized_text(
            f"{output.final_positive_prompt}\n{output.final_negative_prompt}"
        ).casefold()
        for candidate_text in (
            candidate.manifestation,
            candidate.audit_summary,
        ):
            normalized_candidate_text = _normalized_text(
                candidate_text
            ).casefold()
            if (
                normalized_candidate_text
                and normalized_candidate_text in normalized_image_prompt_boundary
            ):
                raise VisualAnchorTwoStageError(
                    "an unselected candidate leaked into the image-model prompts"
                )
    positive = normalized_positive
    for term in (*_CANDIDATE_TERMS, *_INTERNAL_PLANNING_TERMS):
        if _contains_term(positive, term):
            raise VisualAnchorTwoStageError(
                "final positive prompt contains candidate or internal planning language"
            )
    normalized_negative = _normalized_text(output.final_negative_prompt).casefold()
    for fragment in stage_input.target_visual_style.required_final_prompt_fragments:
        if _normalized_text(fragment).casefold() not in normalized_positive:
            raise VisualAnchorTwoStageError(
                "fusion dropped a required global style fragment"
            )
    if stage_input.negative_prompt_supported:
        for fragment in stage_input.target_visual_style.required_negative_prompt_fragments:
            if _normalized_text(fragment).casefold() not in normalized_negative:
                raise VisualAnchorTwoStageError(
                    "fusion dropped a required negative style fragment"
                )
    elif normalized_negative:
        raise VisualAnchorTwoStageError(
            "positive-only image workflow must leave the final negative prompt empty"
        )
    if stage_input.visible_text_policy.suppress_visible_text:
        if (
            not _contains_required_prompt_fragment_contract(
                normalized_positive,
                stage_input.visible_text_policy.required_positive_prompt_fragment,
            )
            or (
                stage_input.negative_prompt_supported
                and not _contains_required_prompt_fragment_contract(
                    normalized_negative,
                    stage_input.visible_text_policy.required_negative_prompt_fragment,
                )
            )
        ):
            raise VisualAnchorTwoStageError(
                "fusion dropped the visible-text suppression policy"
            )


def _preflight_review_passes(
    review_input: PreflightReviewInput,
    output: PreflightReviewOutput,
) -> bool:
    if output.decision != "pass":
        return False
    fusion_output = review_input.fusion_stage_output
    if output.allowed_final_positive_prompt != fusion_output.final_positive_prompt:
        raise VisualAnchorTwoStageError(
            "preflight reviewer modified the final positive prompt"
        )
    expected_negative = (
        fusion_output.final_negative_prompt
        if review_input.negative_prompt_supported
        else ""
    )
    if output.allowed_final_negative_prompt != expected_negative:
        raise VisualAnchorTwoStageError(
            "preflight reviewer modified or incorrectly allowed the negative prompt"
        )
    return True


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


def _contains_required_prompt_fragment_contract(prompt: str, required: str) -> bool:
    normalized_prompt = _normalized_text(prompt).casefold()
    fragments = [
        _normalized_text(fragment).casefold()
        for fragment in re.split(r"[,，;；]+", str(required or ""))
        if _normalized_text(fragment)
    ]
    return bool(fragments) and all(fragment in normalized_prompt for fragment in fragments)


def _required_single_instance_prompt_fragment(
    identity_display_name: str,
    target_image_prompt_language: str,
) -> str:
    display_name = _normalized_text(identity_display_name)
    language = _normalized_text(target_image_prompt_language).casefold()
    if "中文" in language or language.startswith("zh"):
        return f"画面中只有一只{display_name}"
    return f"There is exactly one {display_name} in the entire image"


def _normalize_fusion_single_instance_evidence(
    stage_input: FusionStageInput,
    output: FusionStageOutput,
) -> FusionStageOutput:
    normalized_positive = _normalized_text(output.final_positive_prompt)
    normalized_evidence = _normalized_text(output.single_instance_prompt_evidence)
    extracted_evidence = _extract_single_instance_prompt_evidence(
        normalized_positive,
        stage_input.identity_profile.display_name,
    )
    if extracted_evidence is None:
        promoted_positive = _promote_local_single_instance_clause(
            normalized_positive,
            stage_input.identity_profile.display_name,
        )
        if promoted_positive == normalized_positive:
            return output
        normalized_positive = promoted_positive
        extracted_evidence = _extract_single_instance_prompt_evidence(
            normalized_positive,
            stage_input.identity_profile.display_name,
        )
        if extracted_evidence is None:
            return output
        output = output.model_copy(
            update={"final_positive_prompt": normalized_positive}
        )
    if (
        normalized_evidence.casefold() in normalized_positive.casefold()
        and extracted_evidence.casefold() in normalized_evidence.casefold()
    ):
        return output
    return output.model_copy(
        update={"single_instance_prompt_evidence": extracted_evidence}
    )


def _promote_local_single_instance_clause(
    final_positive_prompt: str,
    identity_display_name: str,
) -> str:
    prompt = _normalized_text(final_positive_prompt)
    identity = _normalized_text(identity_display_name)
    if not prompt or not identity:
        return prompt

    candidates: list[tuple[int, int, str]] = []
    for local_term, global_term, blocked_prefix_characters in (
        ("有一个", "只有一个", "只仅唯"),
        ("有一只", "只有一只", "只仅唯"),
        ("有一名", "只有一名", "只仅唯"),
        ("一个", "只有一个", "只有仅唯另每各第多少任"),
        ("一只", "只有一只", "只有仅唯另每各第多少任"),
        ("一名", "只有一名", "只有仅唯另每各第多少任"),
    ):
        pattern = (
            rf"(?<![{re.escape(blocked_prefix_characters)}])"
            rf"{re.escape(local_term)}"
        )
        for term_match in re.finditer(pattern, prompt):
            clause_start = max(
                prompt.rfind(delimiter, 0, term_match.start())
                for delimiter in _SINGLE_INSTANCE_CLAUSE_DELIMITERS
            ) + 1
            prefix = prompt[clause_start : term_match.start()].strip().casefold()
            if any(
                prefix.endswith(suffix.casefold())
                for suffix in _SINGLE_INSTANCE_NEGATION_SUFFIXES
            ):
                continue
            identity_match = re.search(
                re.escape(identity),
                prompt[term_match.end() :],
                flags=re.IGNORECASE,
            )
            if identity_match is None:
                continue
            identity_start = term_match.end() + identity_match.start()
            between = prompt[term_match.end() : identity_start]
            if any(
                delimiter in between
                for delimiter in _SINGLE_INSTANCE_CLAUSE_DELIMITERS
            ):
                continue
            candidates.append((term_match.start(), term_match.end(), global_term))

    if len(candidates) != 1:
        return prompt
    start, end, replacement = candidates[0]
    return f"{prompt[:start]}{replacement}{prompt[end:]}"


def _normalize_fusion_protected_fact_evidence(
    stage_input: FusionStageInput,
    output: FusionStageOutput,
) -> FusionStageOutput:
    normalized_positive = _normalized_text(output.final_positive_prompt).casefold()
    facts_by_id = {
        fact.fact_id: fact
        for fact in stage_input.content_stage_output.protected_facts
    }
    normalized_checks = []
    changed = False
    for check in output.protected_fact_checks:
        current_evidence = _normalized_text(check.final_image_evidence)
        fact = facts_by_id.get(check.fact_id)
        source_evidence = (
            _normalized_text(fact.pure_content_prompt_evidence)
            if fact is not None
            else ""
        )
        if (
            current_evidence.casefold() not in normalized_positive
            and source_evidence
            and source_evidence.casefold() in normalized_positive
        ):
            check = check.model_copy(
                update={"final_image_evidence": source_evidence}
            )
            changed = True
        normalized_checks.append(check)
    if not changed:
        return output
    return output.model_copy(update={"protected_fact_checks": normalized_checks})


def _extract_single_instance_prompt_evidence(
    final_positive_prompt: str,
    identity_display_name: str,
) -> str | None:
    prompt = _normalized_text(final_positive_prompt)
    identity = _normalized_text(identity_display_name)
    if not prompt or not identity:
        return None

    candidates: list[tuple[int, int, str]] = []
    for term in _SINGLE_INSTANCE_TERMS:
        term_pattern = re.escape(term)
        if term.isascii() and any(character.isalnum() for character in term):
            term_pattern = rf"(?<![A-Za-z0-9_]){term_pattern}(?![A-Za-z0-9_])"
        for term_match in re.finditer(term_pattern, prompt, flags=re.IGNORECASE):
            clause_start = max(
                prompt.rfind(delimiter, 0, term_match.start())
                for delimiter in _SINGLE_INSTANCE_CLAUSE_DELIMITERS
            ) + 1
            prefix = prompt[clause_start : term_match.start()].strip().casefold()
            if any(
                prefix.endswith(suffix.casefold())
                for suffix in _SINGLE_INSTANCE_NEGATION_SUFFIXES
            ):
                continue

            identity_match = re.search(
                re.escape(identity),
                prompt[term_match.end() :],
                flags=re.IGNORECASE,
            )
            if identity_match is None:
                continue
            identity_start = term_match.end() + identity_match.start()
            between = prompt[term_match.end() : identity_start]
            if any(
                delimiter in between
                for delimiter in _SINGLE_INSTANCE_CLAUSE_DELIMITERS
            ):
                continue
            identity_end = term_match.end() + identity_match.end()
            evidence = prompt[term_match.start() : identity_end]
            candidates.append((len(evidence), term_match.start(), evidence))

    if not candidates:
        return None
    return min(candidates)[2]


def _contains_term(value: str, term: str) -> bool:
    if term.isascii() and any(character.isalnum() for character in term):
        return re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
            value,
            flags=re.IGNORECASE,
        ) is not None
    return term.casefold() in value.casefold()


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
