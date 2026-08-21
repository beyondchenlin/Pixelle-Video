from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Optional, Sequence

from pixelle_video.models.article_concretization import ArticleConcretizationPlan
from pixelle_video.models.final_visual_prompt_contract import (
    V44_TRACE_METADATA_KEYS,
    FinalVisualPromptContract,
    RenderedMediaPrompt,
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
from pixelle_video.models.text_overlay import project_prompt_text_rendering_request
from pixelle_video.models.video_generation_contract import (
    PLAN_FRAME_OVERRIDE_VALUE_FIELDS,
    normalize_plan_frame_overrides,
)
from pixelle_video.prompt_language import DEFAULT_PROMPT_LANGUAGE, PromptLanguage
from pixelle_video.services.article_concretization_pipeline import (
    article_concretization_plans_by_frame,
    article_concretization_snapshot,
)
from pixelle_video.services.final_visual_prompt_llm_assembler import (
    FinalVisualPromptLLMAssembler,
    deterministic_prompt_assembly_result,
)
from pixelle_video.services.llm_interaction_recorder import LLMInteractionRecorder
from pixelle_video.services.llm_trace_refs import (
    LLMTraceCollector,
    llm_trace_refs_from_records,
    merge_llm_trace_refs,
)
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
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
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
_CONTENT_REFERENCE_IMAGE_KEYS = (
    "enabled",
    "asset_sha256",
    "style_summary",
    "color_atmosphere",
    "composition_summary",
    "style_anchors",
    "confidence",
    "limitations",
    "merge_mode",
)


@dataclass
class VisualPromptComposer:
    """Canonical visual prompt boundary.

    This core service accepts one recurring-identity request type only. Historical
    product controls are normalized by ``ImagePromptComposer`` before reaching
    this service. When recurring identity is enabled, raw Asset Bible identity is
    first validated into one canonical runtime snapshot. Identity facts are kept
    out of the content-prompt LLM boundary, every legacy signature-generator
    control remains hard-disabled, and canonical V4.5 projection is the sole owner
    of the final subject/identity contract.
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
        # Legacy identity-generator controls remain hard-disabled. The LLM owns
        # content composition only; recurring identity is projected exactly once
        # after the base batch returns.
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
            briefs = dict(
                planning_snapshot.get("base_visual_briefs_by_frame") or {}
            )
            base_negative_prompts = _base_negative_prompts(
                batch=batch,
                frame_count=storyboard_plan.resolved_scene_count,
            )
            projection = SeriesVisualSignatureProjectionService().project_batch(
                base_prompts=batch.prompts,
                frame_ids=[frame.frame_id for frame in storyboard_plan.frames],
                frame_contexts=prompt_contexts.frame_contexts,
                request=resolved_signature_request,
                profile=profile_snapshot,
                article_concretization_plans=article_concretization_plans,
                base_visual_briefs_by_frame=briefs,
                base_negative_prompts=base_negative_prompts,
            )
            if resolved_signature_request.llm_prompt_assembly_enabled:
                assembly_trace_collector = (
                    LLMTraceCollector(trace_recorder)
                    if trace_recorder is not None
                    else None
                )
                assembly_result = await FinalVisualPromptLLMAssembler().assemble_batch(
                    llm_service=llm_service,
                    batch=projection,
                    trace_context=trace_context,
                    trace_recorder=assembly_trace_collector,
                    max_concurrency=max_concurrency,
                )
                if assembly_trace_collector is not None:
                    final_assembly_trace_refs = llm_trace_refs_from_records(
                        assembly_trace_collector.records
                    )
            else:
                assembly_result = deterministic_prompt_assembly_result(projection)
            projection = assembly_result.batch
            planning_snapshot["series_visual_signature_prompt_assembly"] = dict(
                assembly_result.audit
            )
            bundle_metadata_by_frame = {
                frame.frame_id: frame.bundle.to_dict()["metadata"]
                for frame in projection.frames
            }
            rendered_prompts = _project_rendered_prompts(
                batch.rendered_prompts,
                projection.frames,
                bundle_metadata_by_frame=bundle_metadata_by_frame,
            )
            batch = StyledImagePromptBatch(
                prompts=projection.prompts,
                negative_prompt=_projection_negative_prompt(
                    projection.frames,
                    rendered_prompts,
                ),
                resolved_style=batch.resolved_style,
                planning_snapshot=planning_snapshot,
                rendered_prompts=rendered_prompts,
            )
            planning_snapshot["series_visual_signature_request_audit"] = (
                projection.audit_policy.request_audit_dict(
                    resolved_signature_request
                )
            )
            planning_snapshot["series_visual_signature_profile_ref"] = (
                projection.audit_policy.profile_reference_dict(profile_snapshot)
            )
            planning_snapshot["series_visual_signature_projection_audit"] = (
                projection.audit_dict()
            )
            planning_snapshot["series_visual_signature_contract_by_frame"] = {
                frame.frame_id: {
                    "contract_id": frame.contract.contract_id,
                    "role": frame.signature.role.value,
                    "max_area_ratio": frame.signature.max_area_ratio,
                    "relative_size": frame.signature.relative_size.value,
                    "required_subject_count": len(frame.required_subjects),
                    "identity_content_sha256": (
                        frame.signature.profile.identity_content_sha256
                        if frame.signature.profile is not None
                        else ""
                    ),
                    "contract_content_sha256": frame.contract.contract_content_sha256,
                    "contract_version": frame.contract.contract_version,
                    "prompt_budget": dict(
                        bundle_metadata_by_frame[frame.frame_id].get("prompt_budget")
                        or {}
                    ),
                    "prompt_assembly": dict(
                        bundle_metadata_by_frame[frame.frame_id].get(
                            "prompt_assembly"
                        )
                        or {}
                    ),
                }
                for frame in projection.frames
            }
            planning_snapshot["series_visual_signature_trace_by_frame"] = {
                frame.frame_id: {
                    "contract": frame.contract.to_dict(),
                    "final_positive_prompt": frame.bundle.positive_prompt,
                    "final_negative_prompt": frame.bundle.negative_prompt,
                    "identity_content_sha256": (
                        frame.signature.profile.identity_content_sha256
                        if frame.signature.profile is not None
                        else ""
                    ),
                    "contract_content_sha256": frame.contract.contract_content_sha256,
                    "contract_version": frame.contract.contract_version,
                    "prompt_budget": dict(
                        bundle_metadata_by_frame[frame.frame_id].get("prompt_budget")
                        or {}
                    ),
                    "prompt_assembly": dict(
                        bundle_metadata_by_frame[frame.frame_id].get(
                            "prompt_assembly"
                        )
                        or {}
                    ),
                }
                for frame in projection.frames
            }

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
    if isinstance(reference_image, Mapping):
        result["reference_image"] = (
            _mapping_projection(reference_image, _CONTENT_REFERENCE_IMAGE_KEYS)
            if identity_isolation_enabled
            else dict(reference_image)
        )

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


def _base_negative_prompts(
    *,
    batch: StyledImagePromptBatch,
    frame_count: int,
) -> tuple[str | None, ...]:
    rendered = tuple(batch.rendered_prompts or ())
    if rendered:
        if len(rendered) != frame_count:
            raise ValueError(
                "rendered prompt count must match frame count before visual signature projection"
            )
        return tuple(item.negative_prompt for item in rendered)
    return tuple(batch.negative_prompt for _ in range(frame_count))


def _project_rendered_prompts(
    rendered_prompts: Sequence[RenderedMediaPrompt],
    projection_frames: Sequence[Any],
    *,
    bundle_metadata_by_frame: Mapping[str, Mapping[str, Any]],
) -> list[RenderedMediaPrompt]:
    rendered = tuple(rendered_prompts or ())
    if rendered and len(rendered) != len(projection_frames):
        raise ValueError(
            "rendered prompt count must match projection frame count"
        )
    result: list[RenderedMediaPrompt] = []
    for index, projection in enumerate(projection_frames):
        base_rendered = rendered[index] if rendered else None
        metadata = (
            base_rendered.metadata_to_dict() if base_rendered is not None else {}
        )
        for reserved_key in (*V44_TRACE_METADATA_KEYS, "v44_contract"):
            metadata.pop(reserved_key, None)
        bundle_metadata = dict(bundle_metadata_by_frame.get(projection.frame_id) or {})
        if not bundle_metadata:
            raise ValueError(
                "projection bundle metadata must exist for every projected frame"
            )
        prompt_sections = dict(bundle_metadata.get("prompt_sections") or {})
        prompt_budget = dict(bundle_metadata.get("prompt_budget") or {})
        metadata["series_visual_signature_v45"] = {
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
                prompt_contract=_projected_prompt_contract(
                    projection=projection,
                    prompt_sections=prompt_sections,
                ),
                renderer_id=(
                    base_rendered.renderer_id
                    if base_rendered is not None
                    else "final_visual_prompt_compiler"
                ),
                renderer_version=(
                    base_rendered.renderer_version
                    if base_rendered is not None
                    else "v4.5"
                ),
                metadata=metadata,
            )
        )
    return result


def _projected_prompt_contract(
    *,
    projection: Any,
    prompt_sections: Mapping[str, str],
) -> FinalVisualPromptContract:
    required_keys = (
        "main_content",
        "fixed_identity",
        "role",
        "placement",
        "scene_fusion",
        "style",
        "subject_protection",
    )
    missing = [key for key in required_keys if not str(prompt_sections.get(key) or "").strip()]
    if missing:
        raise ValueError(
            "projected V4.5 prompt sections are incomplete: " + ", ".join(missing)
        )
    return FinalVisualPromptContract(
        scene=prompt_sections["main_content"],
        composition=prompt_sections["placement"],
        style_assignment=prompt_sections["style"],
        character_layer_style=prompt_sections["fixed_identity"],
        world_layer_style=prompt_sections["scene_fusion"],
        integration_priority=(
            prompt_sections["role"] + ". " + prompt_sections["subject_protection"]
        ),
        negative_rules=tuple(
            part.strip()
            for part in projection.bundle.negative_prompt.split(",")
            if part.strip()
        ),
        metadata={
            "series_visual_signature_contract_v45": projection.contract.to_dict()
        },
        version=projection.contract.contract_version,
    )


def _projection_negative_prompt(
    projection_frames: Sequence[Any],
    rendered_prompts: Sequence[RenderedMediaPrompt],
) -> str | None:
    if rendered_prompts:
        values = [item.negative_prompt for item in rendered_prompts if item.negative_prompt]
    else:
        values = [
            frame.bundle.negative_prompt
            for frame in projection_frames
            if frame.bundle.negative_prompt
        ]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in str(value).split(","):
            text = " ".join(part.strip().split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
    return ", ".join(result) or None


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
