from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from pixelle_video.models.article_concretization import ArticleConcretizationPlan
from pixelle_video.models.final_visual_prompt_contract import (
    V44_TRACE_METADATA_KEYS,
    FinalVisualPromptContract,
    RenderedMediaPrompt,
    join_rendered_negative_prompts,
)
from pixelle_video.models.llm_interaction_trace import LLMTraceContext
from pixelle_video.models.native_prompt import NativePromptHint
from pixelle_video.models.progress import ProgressI18nMessage
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.storyboard_plan import StoryboardPlan
from pixelle_video.models.style_resolution import StyledImagePromptBatch
from pixelle_video.models.text_overlay import (
    build_text_rendering_settings,
    project_prompt_text_rendering_request,
)
from pixelle_video.models.video_generation_contract import (
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS,
    normalize_plan_frame_overrides,
)
from pixelle_video.models.visual_anchor_two_stage import (
    IdentityReferenceCondition,
    ImageWorkflowExecutionContract,
    TargetVisualStyle,
    VisibleTextPolicy,
)
from pixelle_video.prompt_language import (
    CHINESE_PROMPT_LANGUAGE,
    DEFAULT_PROMPT_LANGUAGE,
    PromptLanguage,
)
from pixelle_video.services.article_concretization_pipeline import (
    article_concretization_plans_by_frame,
    article_concretization_snapshot,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.llm_trace_refs import merge_llm_trace_refs
from pixelle_video.services.prompt_plan_service import build_prompt_plan_bundle
from pixelle_video.services.reference_image_visual_context_adapter import (
    current_reference_image_visual_story_context_patch,
    merge_ip_profile_from_reference_patch,
    reference_image_prompt_planning_snapshot,
)
from pixelle_video.services.series_visual_signature_profile_snapshot_builder import (
    SeriesVisualSignatureProfileSnapshotBuilder,
    validate_series_visual_signature_profile_snapshot,
)
from pixelle_video.services.visual_anchor_reference_condition import (
    inspect_image_workflow,
)
from pixelle_video.services.visual_anchor_two_stage_service import (
    VisualAnchorTwoStageService,
    identity_profile_from_snapshot,
)
from pixelle_video.services.visual_profile_registry import resolve_visual_profile
from pixelle_video.services.visual_prompt_profile_projector import apply_visual_profile_to_batch
from pixelle_video.services.visual_quality_gate import VisualQualityGate
from pixelle_video.services.visual_story_prompt_context import attach_visual_story_context
from pixelle_video.utils.content_generators import generate_styled_image_prompt_batch
from pixelle_video.utils.prompt_helper import (
    final_visual_prompt_clause_template_metadata,
    final_visual_prompt_template_metadata,
)
from pixelle_video.utils.style_resolution import (
    resolve_literal_style_spec,
    resolve_style_source,
)
from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities

_CONTENT_FRAME_VISUAL_KEYS = (
    "frame_id",
    "frame_index",
    "source_text",
    "local_claim",
    "visual_task",
    "visual_logic",
    "required_subjects",
    "forbidden_losses",
    "evidence_refs",
    "visible_text_policy",
)
_CONTENT_ROUTE_KEYS = (
    "route_id",
    "route_name",
    "route_type",
    "visual_premise",
    "why_it_fits_article",
    "frame_storytelling_logic",
    "style_family",
    "route_specific_rules",
    "risk_notes",
    "sample_frame_premise",
)
_CONTENT_ARTICLE_KEYS = (
    "input_kind",
    "summary",
    "core_claim",
    "central_problem",
    "tone",
    "key_subjects",
    "cognitive_opportunities",
    "metaphor_opportunities",
    "unsafe_or_sensitive_flags",
    "evidence_spans",
)
@dataclass
class VisualPromptComposer:
    """Canonical visual prompt boundary.

    Historical product controls are normalized before reaching this service.
    When recurring identity is enabled, every frame first receives an
    identity-free content call, then a full identity-fusion rewrite and a
    blocking preflight review before the only image workflow request.
    """

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
        visual_profile_id: Optional[str] = None,
        visual_profile: Optional[Mapping[str, Any]] = None,
        visual_quality_gate_enabled: bool = True,
        visual_quality_gate_strict: bool = False,
        shot_preset_id: Optional[str] = None,
        consistency_strength: str = "standard",
        content_mode: Optional[str] = None,
        role_strategy: Optional[str] = None,
        role_locking_strength: Optional[str] = None,
        shot_strategy: Optional[str] = None,
        frame_overrides: Optional[list[dict[str, Any]]] = None,
        text_rendering: Optional[Mapping[str, Any]] = None,
        native_prompt_hints_by_frame: Optional[Mapping[int, Sequence[NativePromptHint | str]]] = None,
        ip_profile=None,
        series_visual_signature_request: SeriesVisualSignatureRequest | None = None,
        series_visual_signature_profile_snapshot: VisualSignatureProfileSnapshot | None = None,
        article_concretization_plans: Sequence[ArticleConcretizationPlan] = (),
        visual_story_context: Optional[Mapping[str, Any]] = None,
        stage_callback: Optional[Callable[[dict[str, Any]], None]] = None,
        upstream_llm_trace_refs: Optional[Sequence[Mapping[str, str]]] = None,
        trace_context: LLMTraceContext | None = None,
        trace_recorder: LLMInteractionRecorder | None = None,
        task_id: str | None = None,
        random_seeds_by_frame: Mapping[str, int] | None = None,
        media_width: int | None = None,
        media_height: int | None = None,
        visual_anchor_reference_conditioning_enabled: bool | None = None,
        identity_reference_workflow_inspection: Mapping[str, Any] | None = None,
    ) -> StyledImagePromptBatch:
        reference_patch = current_reference_image_visual_story_context_patch()
        ip_profile = merge_ip_profile_from_reference_patch(ip_profile, reference_patch)
        resolved_signature_request = (
            series_visual_signature_request
            if series_visual_signature_request is not None
            else SeriesVisualSignatureRequest.disabled()
        )
        if not isinstance(resolved_signature_request, SeriesVisualSignatureRequest):
            raise TypeError(
                "series_visual_signature_request must be the canonical SeriesVisualSignatureRequest"
            )
        signature_enabled = resolved_signature_request.enabled
        if signature_enabled and media_type != "image":
            raise ValueError(
                "visual signature requires image media prompts"
            )
        if visual_anchor_reference_conditioning_enabled is None:
            visual_anchor_reference_conditioning_enabled = (
                signature_enabled
                and media_type == "image"
                and _workflow_supports_reference_image(
                    media_service=media_service,
                    workflow=workflow,
                )
            )
        if not isinstance(visual_anchor_reference_conditioning_enabled, bool):
            raise TypeError(
                "visual_anchor_reference_conditioning_enabled must be a boolean"
            )
        if visual_anchor_reference_conditioning_enabled and not signature_enabled:
            raise ValueError(
                "reference conditioning requires an enabled visual signature"
            )
        if visual_anchor_reference_conditioning_enabled:
            if media_type != "image":
                raise ValueError(
                    "reference-conditioned visual anchor requires an image workflow"
                )
            if media_service is None:
                raise ValueError(
                    "reference-conditioned visual anchor requires the media service"
                )
            reference_payload = reference_patch.get("reference_image")
            if not isinstance(reference_payload, Mapping) or not reference_payload.get(
                "enabled"
            ):
                raise ValueError(
                    "reference-conditioned visual anchor requires a real reference image"
                )
            if not isinstance(identity_reference_workflow_inspection, Mapping):
                raise ValueError(
                    "reference-conditioned visual anchor requires completed workflow preflight"
                )
        if not signature_enabled and series_visual_signature_profile_snapshot is not None:
            raise ValueError(
                "series_visual_signature_profile_snapshot requires an enabled canonical request"
            )

        profile_snapshot: VisualSignatureProfileSnapshot | None = None
        if signature_enabled:
            profile_snapshot = series_visual_signature_profile_snapshot
            if profile_snapshot is None:
                profile_snapshot = SeriesVisualSignatureProfileSnapshotBuilder().build(
                    request=resolved_signature_request,
                    ip_profile=ip_profile,
                )
            profile_snapshot = validate_series_visual_signature_profile_snapshot(
                profile_snapshot,
                expected_profile_id=resolved_signature_request.profile_id,
            )

        if reference_patch:
            visual_story_context = _merge_visual_story_context_patch(
                visual_story_context,
                reference_patch,
            )
        visual_story_context = _content_only_visual_story_context(
            visual_story_context,
            identity_isolation_enabled=signature_enabled,
        )

        normalized_overrides = normalize_plan_frame_overrides(
            frame_overrides,
            storyboard_plan=storyboard_plan,
        )
        prompt_contexts = _build_prompt_contexts(
            storyboard_plan=storyboard_plan,
            frame_overrides=normalized_overrides,
            article_concretization_plans=article_concretization_plans,
        )
        prompt_contexts = attach_visual_story_context(
            prompt_contexts,
            visual_story_context,
        )
        if signature_enabled:
            batch = _resolve_visual_anchor_style_batch(
                image_config=image_config,
                prompt_prefix=prompt_prefix,
                frame_count=storyboard_plan.resolved_scene_count,
            )
        else:
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
                series_visual_signature_enabled=False,
                ip_profile=None,
                series_visual_signature_expression_mode=None,
                series_visual_signature_structure_mode=None,
                series_visual_signature_participation_mode=None,
                series_visual_signature_request=None,
                series_visual_signature_profile=None,
                series_visual_signature_mode=None,
                series_visual_signature_consistency_mode=None,
                series_visual_signature_presentation_mode=None,
                series_visual_signature_enforcement=None,
                series_visual_signature_fallback_enabled=None,
                series_visual_signature_fallback_mode=None,
                series_visual_signature_min_visibility=None,
                scene_casts_by_frame=None,
                stage_callback=stage_callback,
                upstream_llm_trace_refs=upstream_llm_trace_refs,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
        if len(batch.prompts) != storyboard_plan.resolved_scene_count:
            raise ValueError("visual prompt count must match storyboard frame count")

        resolved_visual_profile = resolve_visual_profile(
            profile_id=visual_profile_id,
            inline_profile=visual_profile,
        )
        visual_profile_snapshot = None
        if resolved_visual_profile is not None and media_type == "image":
            if signature_enabled:
                visual_profile_snapshot = {
                    "profile": resolved_visual_profile.to_dict()
                }
            else:
                batch, visual_profile_snapshot = apply_visual_profile_to_batch(
                    batch=batch,
                    profile=resolved_visual_profile,
                    frame_contexts=prompt_contexts.frame_contexts,
                    quality_gate=VisualQualityGate(
                        enabled=visual_quality_gate_enabled,
                        strict=visual_quality_gate_strict,
                    ),
                )

        planning_snapshot = dict(batch.planning_snapshot or {})
        final_assembly_trace_refs: list[dict[str, str]] = []
        if signature_enabled:
            if profile_snapshot is None:
                raise RuntimeError(
                    "enabled visual signature must have a prevalidated canonical profile snapshot"
                )
            if media_service is None:
                raise ValueError(
                    "visual-anchor two-stage fusion requires the media service"
                )
            resolved_task_id = str(
                task_id or getattr(trace_context, "task_id", "") or ""
            ).strip()
            if not resolved_task_id:
                raise ValueError(
                    "visual-anchor two-stage fusion requires a task id"
                )
            registered_seeds = dict(random_seeds_by_frame or {})
            if set(registered_seeds) != {
                frame.frame_id for frame in storyboard_plan.frames
            }:
                raise ValueError(
                    "visual-anchor random seeds must be registered for every frame"
                )

            workflow_info = media_service._resolve_workflow(
                workflow=workflow,
                workflow_domain="image",
            )
            workflow_capabilities = get_workflow_capabilities(dict(workflow_info))
            reference_condition: IdentityReferenceCondition | None = None
            if visual_anchor_reference_conditioning_enabled:
                inspection_payload = dict(identity_reference_workflow_inspection or {})
                reference_condition = IdentityReferenceCondition.model_validate(
                    inspection_payload.get("condition")
                )
                workflow_key = str(inspection_payload.get("workflow_key") or "").strip()
                workflow_version_sha256 = str(
                    inspection_payload.get("workflow_version_sha256") or ""
                ).strip()
                model_files = list(inspection_payload.get("model_files") or [])
                sampler_defaults = dict(
                    inspection_payload.get("sampler_defaults") or {}
                )
                identity_conditioning_mode = "reference_image"
                identity_condition_summary = (
                    "当前工作流真实支持参考图输入；使用已校验的参考资源和文字身份档案共同保持身份"
                )
                identity_profile = identity_profile_from_snapshot(
                    profile_snapshot,
                    identity_reference_resource_id=(
                        reference_condition.resource_version
                    ),
                )
                planning_snapshot["identity_reference_workflow_inspection"] = (
                    inspection_payload
                )
            else:
                workflow_inspection = inspect_image_workflow(
                    workflow_info=workflow_info,
                    project_root=Path(__file__).resolve().parents[2],
                )
                workflow_key = workflow_inspection.workflow_key
                workflow_version_sha256 = (
                    workflow_inspection.workflow_version_sha256
                )
                model_files = list(workflow_inspection.model_files)
                sampler_defaults = dict(workflow_inspection.sampler_defaults)
                identity_conditioning_mode = "text_profile"
                identity_condition_summary = (
                    "当前工作流不支持参考图输入；仅使用身份档案名称、核心识别特征和禁止变化项作为真实身份条件"
                )
                identity_profile = identity_profile_from_snapshot(profile_snapshot)
                planning_snapshot["image_workflow_inspection"] = (
                    workflow_inspection.to_dict()
                )

            expected_execution = ImageWorkflowExecutionContract(
                width=media_width,
                height=media_height,
                model_files=model_files,
                steps=sampler_defaults.get("steps"),
                cfg=sampler_defaults.get("cfg"),
                sampler_name=sampler_defaults.get("sampler_name"),
                scheduler=sampler_defaults.get("scheduler"),
                denoise=sampler_defaults.get("denoise"),
            )
            target_visual_style = _target_visual_style_contract(
                batch=batch,
                visual_profile_snapshot=visual_profile_snapshot,
                prompt_language=prompt_language,
            )
            visible_text_policy = _visible_text_policy(
                text_rendering,
                prompt_language=prompt_language,
            )
            two_stage_result = await VisualAnchorTwoStageService().run_batch(
                llm_service=llm_service,
                storyboard_plan=storyboard_plan,
                identity_profile=identity_profile,
                identity_reference_condition=reference_condition,
                identity_conditioning_mode=identity_conditioning_mode,
                workflow_identity_condition_summary=identity_condition_summary,
                target_visual_style=target_visual_style,
                visible_text_policy=visible_text_policy,
                target_image_prompt_language=(
                    "中文"
                    if prompt_language == CHINESE_PROMPT_LANGUAGE
                    else "英文"
                ),
                task_id=resolved_task_id,
                workflow_key=workflow_key,
                workflow_version_sha256=workflow_version_sha256,
                expected_execution=expected_execution,
                random_seeds_by_frame=registered_seeds,
                negative_prompt_supported=workflow_capabilities.supports_negative_prompt,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
                stage_callback=stage_callback,
            )
            rendered_prompts = [
                _render_two_stage_prompt(frame_result)
                for frame_result in two_stage_result.frames
            ]
            batch = StyledImagePromptBatch(
                prompts=[item.prompt for item in rendered_prompts],
                negative_prompt=join_rendered_negative_prompts(rendered_prompts),
                resolved_style=batch.resolved_style,
                planning_snapshot=planning_snapshot,
                rendered_prompts=rendered_prompts,
            )
            planning_snapshot["visual_anchor_two_stage"] = two_stage_result.to_dict()
            planning_snapshot["visual_anchor_generation_request_by_frame"] = {
                item.frame_id: item.generation_request.model_dump(mode="json")
                for item in two_stage_result.frames
            }
            planning_snapshot["visual_anchor_two_stage_prompt_policy"] = {
                "schema_version": "visual_anchor_two_stage_prompt_policy.v3",
                "prompt_chain": (
                    "content_stage_then_fusion_rewrite_then_preflight_review"
                ),
                "image_generation_attempts_per_frame": 1,
                "post_generation_model_validation_enabled": False,
                "post_generation_prompt_repair_enabled": False,
                "post_generation_regeneration_enabled": False,
                "identity_conditioning_mode": identity_conditioning_mode,
            }
            planning_snapshot["series_visual_signature_request_audit"] = (
                _series_visual_signature_request_audit(resolved_signature_request)
            )
            planning_snapshot["series_visual_signature_profile_ref"] = (
                identity_profile.model_dump(mode="json")
            )

        reference_snapshot = reference_image_prompt_planning_snapshot(
            reference_patch,
            ip_profile=ip_profile,
        )
        if reference_snapshot:
            planning_snapshot["reference_image_visual_context"] = reference_snapshot
        if visual_profile_snapshot:
            planning_snapshot["visual_profile"] = visual_profile_snapshot["profile"]
            if visual_profile_snapshot.get("quality_gate") is not None:
                planning_snapshot["visual_quality_gate"] = visual_profile_snapshot["quality_gate"]
        llm_trace_refs = merge_llm_trace_refs(
            upstream_llm_trace_refs,
            planning_snapshot.get("llm_trace_refs"),
            final_assembly_trace_refs,
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
        article_concretization_by_frame = article_concretization_snapshot(
            storyboard_plan=storyboard_plan,
            plans=article_concretization_plans,
        )
        if article_concretization_by_frame:
            planning_snapshot["article_concretization_by_frame"] = (
                article_concretization_by_frame
            )
        rendered_prompts_for_plan = batch.rendered_prompts or None
        prompt_plan_bundle = build_prompt_plan_bundle(
            storyboard_plan=storyboard_plan,
            rendered_prompts=rendered_prompts_for_plan,
            image_prompts=batch.prompts if rendered_prompts_for_plan is None else None,
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
            rendered_prompts=batch.rendered_prompts,
        )


def _resolve_visual_anchor_style_batch(
    *,
    image_config: Any,
    prompt_prefix: str | None,
    frame_count: int,
) -> StyledImagePromptBatch:
    """Resolve the user's literal style without an extra style-model call."""

    source = resolve_style_source(
        image_config,
        prompt_prefix_override=prompt_prefix,
    )
    resolved_style = resolve_literal_style_spec(source) if source is not None else None
    return StyledImagePromptBatch(
        prompts=["" for _ in range(frame_count)],
        negative_prompt=(
            resolved_style.negative_prompt if resolved_style is not None else None
        ),
        resolved_style=resolved_style,
        planning_snapshot={},
        rendered_prompts=[],
    )


def _target_visual_style_contract(
    *,
    batch: StyledImagePromptBatch,
    visual_profile_snapshot: Mapping[str, Any] | None,
    prompt_language: PromptLanguage,
) -> TargetVisualStyle:
    resolved_style = batch.resolved_style
    payload: dict[str, Any] = {}
    required_positive: list[str] = []
    required_negative: list[str] = []
    if resolved_style is not None:
        payload["resolved_style"] = {
            "style_kind": resolved_style.style_kind,
            "prompt_template": resolved_style.prompt_template,
            "negative_prompt": resolved_style.negative_prompt,
            "style_profile": dict(resolved_style.style_profile),
            "resolver_version": resolved_style.resolver_version,
            "source_identity": resolved_style.source_identity,
            "raw_content": resolved_style.raw_content,
        }
        required_positive.extend(_style_fragments(resolved_style.raw_content))
        required_negative.extend(_style_fragments(resolved_style.negative_prompt))
        profile_negative = str(
            resolved_style.style_profile.get("negative_rules") or ""
        ).strip()
        required_negative.extend(_style_fragments(profile_negative))
        if "builtin_line_art_emotion_minimal" in resolved_style.source_identity:
            if prompt_language == CHINESE_PROMPT_LANGUAGE:
                required_positive = [
                    "极简线稿",
                    "二维表达",
                    "单色或严格受控配色",
                    "大面积留白",
                    "简洁轮廓",
                    "细微情绪",
                    "禁止摄影写实",
                    "禁止三维渲染",
                    "禁止复杂彩色背景",
                ]
                required_negative = [
                    "摄影写实",
                    "三维渲染",
                    "复杂彩色背景",
                ]
            else:
                required_positive = [
                    "minimal line art",
                    "two-dimensional expression",
                    "monochrome or strictly controlled palette",
                    "large areas of negative space",
                    "clean concise contours",
                    "subtle emotion",
                    "no photorealism",
                    "no 3D rendering",
                    "no complex colorful background",
                ]
                required_negative = [
                    "photorealism",
                    "3D rendering",
                    "complex colorful background",
                ]
    if visual_profile_snapshot:
        payload["visual_profile"] = dict(visual_profile_snapshot)
    description = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if payload
        else "未选择额外全局风格；保持纯内容阶段建立的统一视觉表达"
    )
    return TargetVisualStyle(
        description=description,
        required_final_prompt_fragments=_dedupe_fragments(required_positive),
        required_negative_prompt_fragments=_dedupe_fragments(required_negative),
    )


def _style_fragments(value: str) -> list[str]:
    normalized = str(value or "").replace("；", ",").replace(";", ",")
    return [" ".join(part.split()) for part in normalized.split(",") if part.strip()]


def _dedupe_fragments(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _visible_text_policy(
    text_rendering: Mapping[str, Any] | None,
    *,
    prompt_language: PromptLanguage,
) -> VisibleTextPolicy:
    settings = build_text_rendering_settings(text_rendering)
    if not settings.image_text.suppress_embedded_text:
        return VisibleTextPolicy()
    if prompt_language == CHINESE_PROMPT_LANGUAGE:
        canonical_positive = "画面中禁止出现任何可见文字、标题、水印或乱码"
        canonical_negative = "文字，水印，标题，乱码"
    else:
        canonical_positive = (
            "no visible text, no title, no watermark, no garbled text"
        )
        canonical_negative = "text, watermark, title, garbled text"
    image_text_request = (
        dict(text_rendering.get("image_text") or {})
        if isinstance(text_rendering, Mapping)
        else {}
    )
    custom_positive = str(image_text_request.get("positive_prompt") or "").strip()
    custom_negative = str(image_text_request.get("negative_prompt") or "").strip()
    return VisibleTextPolicy(
        suppress_visible_text=True,
        required_positive_prompt_fragment=(
            f"{custom_positive}；{canonical_positive}"
            if custom_positive and canonical_positive not in custom_positive
            else custom_positive or canonical_positive
        ),
        required_negative_prompt_fragment=(
            f"{custom_negative}，{canonical_negative}"
            if custom_negative and canonical_negative not in custom_negative
            else custom_negative or canonical_negative
        ),
    )


def _series_visual_signature_request_audit(
    request: SeriesVisualSignatureRequest,
) -> dict[str, Any]:
    """Persist request shape and presence flags without retaining user text."""

    return {
        "schema_version": "visual_anchor_request_audit.v2",
        "enabled": request.enabled,
        "pipeline_version": request.pipeline_version,
        "profile_id": request.profile_id,
        "asset_bible_id": request.asset_bible_id,
        "role": request.role.value,
        "role_was_explicit": request.role_was_explicit,
        "contains_user_hint": bool(request.user_hint),
        "contains_generation_world_hint": bool(request.generation_world_hint),
        "compatibility_option_keys": sorted(
            str(key) for key in request.compatibility_options
        ),
    }


def _render_two_stage_prompt(frame_result: Any) -> RenderedMediaPrompt:
    fusion = frame_result.fusion_stage_output
    request = frame_result.generation_request
    negative_prompt = request.final_negative_prompt or None
    identity_condition = (
        "唯一身份实例使用已绑定首次工作流的真实参考资源保持身份"
        if request.identity_conditioning_mode == "reference_image"
        else "唯一身份实例使用身份档案的名称、核心识别特征和禁止变化项保持身份"
    )
    contract = FinalVisualPromptContract(
        scene=request.final_positive_prompt,
        composition=fusion.selected_fusion_method,
        style_assignment="融合结果服从用户选择的全局风格、材质、光照和空间关系",
        character_layer_style=identity_condition,
        world_layer_style=fusion.spatial_contact_and_lighting_relation,
        integration_priority="先保护真正主体与全部文案事实，再保持唯一视觉锚点和场景协调",
        negative_rules=(request.final_negative_prompt,)
        if request.final_negative_prompt
        else (),
        metadata={
            "visual_anchor_two_stage": frame_result.model_dump(mode="json"),
        },
        version="visual_anchor_two_stage_contract.v3",
    )
    return RenderedMediaPrompt(
        prompt=request.final_positive_prompt,
        negative_prompt=negative_prompt,
        prompt_contract=contract,
        renderer_id="visual_anchor_two_stage_renderer",
        renderer_version="v3",
        metadata={
            "visual_anchor_two_stage": frame_result.model_dump(mode="json"),
            "generation_request": request.model_dump(mode="json"),
        },
    )


def _workflow_supports_reference_image(
    *,
    media_service: Any,
    workflow: str | None,
) -> bool:
    resolver = getattr(media_service, "_resolve_workflow", None)
    if not callable(resolver):
        return False
    workflow_info = resolver(
        workflow=workflow,
        workflow_domain="image",
    )
    return get_workflow_capabilities(
        dict(workflow_info)
    ).supports_reference_image


def _content_only_visual_story_context(
    visual_story_context: Optional[Mapping[str, Any]],
    *,
    identity_isolation_enabled: bool = False,
) -> dict[str, Any]:
    """Project visual-story context onto content facts only.

    This boundary is whitelist-based so compatibility-only identity fields can
    never leak into the signature-free base prompt.
    """

    source = dict(visual_story_context or {})
    result: dict[str, Any] = {}
    reference_image = source.get("reference_image")
    if isinstance(reference_image, Mapping) and not identity_isolation_enabled:
        result["reference_image"] = dict(reference_image)

    route_source = source.get("selected_visual_route")
    if not isinstance(route_source, Mapping):
        engine_source = source.get("visual_story_engine")
        if isinstance(engine_source, Mapping):
            route_source = engine_source.get("selected_visual_route")
    route = _content_only_route(route_source)
    if route:
        result["selected_visual_route"] = route

    frame_visuals = source.get("frame_visual_plans")
    if isinstance(frame_visuals, Sequence) and not isinstance(frame_visuals, (str, bytes)):
        sanitized = [
            _content_only_frame_visual_plan(item)
            for item in frame_visuals
            if isinstance(item, Mapping)
        ]
        sanitized = [item for item in sanitized if item]
        if sanitized:
            result["frame_visual_plans"] = sanitized

    engine_source = source.get("visual_story_engine")
    if isinstance(engine_source, Mapping):
        engine: dict[str, Any] = {}
        plan_id = engine_source.get("plan_id")
        article = engine_source.get("article")
        if plan_id:
            engine["plan_id"] = plan_id
        if isinstance(article, Mapping):
            engine["article"] = (
                _mapping_projection(article, _CONTENT_ARTICLE_KEYS)
                if identity_isolation_enabled
                else dict(article)
            )
        if route:
            engine["selected_visual_route"] = route
        if engine:
            result["visual_story_engine"] = engine
    return result


def _content_only_route(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _mapping_projection(value, _CONTENT_ROUTE_KEYS)


def _content_only_frame_visual_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping_projection(value, _CONTENT_FRAME_VISUAL_KEYS)


def _mapping_projection(
    value: Mapping[str, Any],
    allowed_keys: Sequence[str],
) -> dict[str, Any]:
    return {
        key: value[key]
        for key in allowed_keys
        if key in value and value[key] is not None
    }


def _project_rendered_prompts(
    rendered_prompts: Sequence[RenderedMediaPrompt],
    projection_frames: Sequence[Any],
    *,
    bundle_metadata_by_frame: Mapping[str, Mapping[str, Any]],
) -> list[RenderedMediaPrompt]:
    """Preserve the legacy projection helper used by its isolated contract tests."""

    rendered = tuple(rendered_prompts or ())
    if rendered and len(rendered) != len(projection_frames):
        raise ValueError("rendered prompt count must match projection frame count")
    result: list[RenderedMediaPrompt] = []
    for index, projection in enumerate(projection_frames):
        base_rendered = rendered[index] if rendered else None
        metadata = (
            base_rendered.metadata_to_dict() if base_rendered is not None else {}
        )
        for reserved_key in (*V44_TRACE_METADATA_KEYS, "v44_contract"):
            metadata.pop(reserved_key, None)
        bundle_metadata = dict(
            bundle_metadata_by_frame.get(projection.frame_id) or {}
        )
        if not bundle_metadata:
            raise ValueError(
                "projection bundle metadata must exist for every projected frame"
            )
        prompt_sections = dict(bundle_metadata.get("prompt_sections") or {})
        prompt_budget = dict(bundle_metadata.get("prompt_budget") or {})
        metadata["series_visual_signature_v46"] = {
            "contract_id": projection.contract.contract_id,
            "role": projection.signature.role.value,
            "max_area_ratio": projection.signature.max_area_ratio,
            "relative_size": projection.signature.relative_size.value,
            "identity_content_sha256": (
                projection.signature.profile.identity_content_sha256
                if projection.signature.profile is not None
                else ""
            ),
            "contract_content_sha256": projection.contract.contract_content_sha256,
            "contract_version": projection.contract.contract_version,
            "entity_placement": projection.contract.entity_placement.to_dict(),
            "scene_fusion": projection.contract.scene_fusion.to_dict(),
            "prompt_sections": prompt_sections,
            "prompt_budget": prompt_budget,
            "audit": projection.audit_dict(),
        }
        result.append(
            RenderedMediaPrompt(
                prompt=projection.bundle.positive_prompt,
                negative_prompt=projection.bundle.negative_prompt or None,
                prompt_contract=projection.contract,
                renderer_id=(
                    base_rendered.renderer_id
                    if base_rendered is not None
                    else "final_visual_prompt_compiler"
                ),
                renderer_version=(
                    base_rendered.renderer_version
                    if base_rendered is not None
                    else "v4.6"
                ),
                metadata=metadata,
            )
        )
    return result


def _merge_visual_story_context_patch(
    visual_story_context: Optional[Mapping[str, Any]],
    reference_patch: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(visual_story_context or {})
    merged.update(dict(reference_patch or {}))
    return merged


def _build_prompt_contexts(
    *,
    storyboard_plan: StoryboardPlan,
    frame_overrides: list[dict[str, Any]],
    article_concretization_plans: Sequence[ArticleConcretizationPlan],
) -> PromptContextEnvelope:
    overrides_by_frame_id = {
        override["frame_id"]: override for override in frame_overrides
    }
    article_plans_by_frame_id = article_concretization_plans_by_frame(
        storyboard_plan=storyboard_plan,
        plans=article_concretization_plans,
    )
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
        article_plan = article_plans_by_frame_id.get(frame.frame_id)
        if article_plan is not None:
            context["article_concretization_plan"] = article_plan.to_dict()
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


__all__ = ["VisualPromptComposer"]
