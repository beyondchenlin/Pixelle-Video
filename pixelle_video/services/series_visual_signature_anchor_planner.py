from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from httpx import NetworkError, TimeoutException
from loguru import logger
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_duty import IPDutyPlan, IPDutyPreset
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
from pixelle_video.models.mandatory_visual_anchor_integration import (
    MandatoryVisualAnchorIntegrationResponse,
)
from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignatureEnforcementMode,
    SeriesVisualSignaturePresentationMode,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureStrategyControls,
    build_visual_identity_kernel,
)
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.prompts.visual_anchor_integration import render_visual_anchor_integration_prompt
from pixelle_video.services.visual_anchor_policy import contains_forbidden_overlay_language
from pixelle_video.services.visual_anchor_projection_gate import validate_visual_anchor_projection
from pixelle_video.services.visual_signature_fallback_planner import (
    VisualSignatureFallbackPlanner,
    merge_visual_anchor_plans_by_frame,
)
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy
from pixelle_video.services.visual_signature_policy_resolver import (
    policy_for_presentation_mode,
)
from pixelle_video.services.visual_story_context_budget import compact_visual_anchor_contexts


@dataclass(frozen=True)
class VisualAnchorIntegrationPlanner:
    """Resilient series-visual-signature integration planner.

    LLM integration remains the primary path.  If only some frames fail validation,
    accepted frames are preserved and failed frames receive deterministic fallback
    in soft mode.  Strict mode keeps the old fail-closed behavior for CI and
    contract testing.
    """

    llm_service: Any | None = None
    policy: VisualSignaturePolicy | None = None
    series_visual_signature_strategy: SeriesVisualSignatureStrategyControls | None = None
    presentation_policy: SeriesVisualSignaturePresentationPolicy | None = None
    max_repair_attempts: int = 2

    async def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        anchor_profile: IPProfile | None,
        base_packages: Sequence[IPFrameAdaptationPackage] = (),
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        frame_plans: Sequence[Any] = (),
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[VisualAnchorPlacementPlan, ...]:
        del base_packages
        briefs = tuple(base_visual_briefs)
        compact_visual_story_context = compact_visual_anchor_contexts(
            frame_contexts=frame_contexts,
            max_total_chars=9000,
        )
        normalized_frame_contexts = compact_visual_story_context["frame_contexts"]
        selected_visual_route = compact_visual_story_context["selected_visual_route"]
        visual_story_frame_plans = compact_visual_story_context["visual_story_frame_plans"]
        visual_story_ip_fusion_plans = compact_visual_story_context["visual_story_ip_fusion_plans"]
        if not briefs:
            return ()
        if anchor_profile is None:
            raise ValueError("series visual signature integration requires anchor_profile")
        if self.llm_service is None:
            raise ValueError("series visual signature integration requires llm_service")
        if not callable(self.llm_service):
            raise ValueError("series visual signature integration requires callable llm_service")

        policy = self.policy or load_visual_signature_policy()
        presentation_policy = self.presentation_policy or SeriesVisualSignaturePresentationPolicy.from_strategy(
            self.series_visual_signature_strategy,
        )
        policy = policy_for_presentation_mode(policy, presentation_policy)
        role_strategy = presentation_policy.strategy_controls()
        identity_kernel = build_visual_identity_kernel(anchor_profile)
        frame_ids = [brief.frame_id for brief in briefs]
        repair_context: dict[str, Any] = {}
        accepted_by_frame: dict[str, VisualAnchorPlacementPlan] = {}
        last_errors_by_frame: dict[str, list[str]] = {}

        for attempt in range(max(1, self.max_repair_attempts + 1)):
            rendered_prompt = render_visual_anchor_integration_prompt(
                base_visual_briefs_json=[brief.to_dict() for brief in briefs],
                anchor_profile_json=_anchor_profile_payload(
                    anchor_profile,
                    policy=policy,
                    identity_kernel=identity_kernel,
                    presentation_policy=presentation_policy,
                ),
                visual_signature_policy_json=policy.to_dict(),
                cadence_plan_json=[],
                series_visual_signature_strategy_json=role_strategy.to_dict(),
                presentation_policy_json=presentation_policy.to_prompt_policy(),
                visual_identity_kernel_json=list(identity_kernel),
                repair_context_json=repair_context,
                frame_contexts_json=normalized_frame_contexts,
                selected_visual_route_json=selected_visual_route,
                visual_story_frame_plans_json=visual_story_frame_plans,
                visual_story_ip_fusion_plans_json=visual_story_ip_fusion_plans,
            )
            try:
                raw_response = await self.llm_service(
                    prompt=rendered_prompt.text,
                    response_type=MandatoryVisualAnchorIntegrationResponse,
                    temperature=0.2,
                    max_tokens=5000,
                    trace_context=trace_context,
                    trace_recorder=trace_recorder,
                )
            except (ValidationError, ValueError) as exc:
                errors = [f"LLM response failed integration schema validation: {_exception_summary(exc)}"]
                last_errors_by_frame = {frame_id: list(errors) for frame_id in frame_ids if frame_id not in accepted_by_frame}
                repair_context = _repair_context(
                    attempt=attempt + 1,
                    errors=errors,
                    presentation_policy=presentation_policy,
                    instruction="Return one flat visible plan object per frame. Use presentation_policy. Do not output candidates arrays, hidden/suppressed/fallback.",
                )
                logger.warning(
                    "series visual signature integration rejected attempt {}: {}",
                    attempt + 1,
                    errors[0],
                )
                continue
            except Exception as exc:
                if not _is_recoverable_llm_call_error(exc):
                    raise
                errors = [f"LLM call failed during integration planning: {_exception_summary(exc)}"]
                last_errors_by_frame = {
                    frame_id: list(errors)
                    for frame_id in frame_ids
                    if frame_id not in accepted_by_frame
                }
                logger.warning(
                    "series visual signature integration LLM call failed; using deterministic fallback: {}",
                    errors[0],
                )
                break
            plans, errors = _placement_plans_from_payload(
                raw_response,
                frame_ids=frame_ids,
                role_strategy=role_strategy,
                identity_kernel=identity_kernel,
                policy=policy,
                presentation_policy=presentation_policy,
                visual_story_ip_fusion_plans=visual_story_ip_fusion_plans,
            )
            for plan in plans:
                accepted_by_frame[plan.frame_id] = plan
            if not errors and set(accepted_by_frame) >= set(frame_ids):
                return tuple(accepted_by_frame[frame_id] for frame_id in frame_ids)
            last_errors_by_frame = _errors_by_frame(errors, frame_ids)
            repair_context = _repair_context(
                attempt=attempt + 1,
                errors=errors[:24],
                presentation_policy=presentation_policy,
                instruction=(
                    "Rewrite every failed frame as one flat visible content-bound plan object. Use action_executor, reader_proxy, observation_gateway, system_component, conflict_participant, scale_reference, explanation_director, or transformation_medium. Do not use cards, labels, bookmarks, stickers, stamps, bookplates, surface marks, or small carrier props."
                    if policy.is_content_bound_mandatory
                    else "Rewrite every failed frame as one flat visible plan object. Preserve accepted frames. For visible_supporting_character, use a real small supporting character on ground/floor/roadside/beside the main subject."
                ),
            )
            logger.warning(
                "series visual signature integration rejected attempt {}: {}",
                attempt + 1,
                "; ".join(errors[:8]) if errors else "missing frame coverage",
            )

        missing_frame_ids = [frame_id for frame_id in frame_ids if frame_id not in accepted_by_frame]
        if not missing_frame_ids:
            return tuple(accepted_by_frame[frame_id] for frame_id in frame_ids)

        if presentation_policy.enforcement is SeriesVisualSignatureEnforcementMode.STRICT or not presentation_policy.fallback_enabled:
            raise ValueError(
                "series visual signature integration failed after repair attempts: "
                + "; ".join(_flatten_errors(last_errors_by_frame, missing_frame_ids)[:12])
            )

        fallback_plans = VisualSignatureFallbackPlanner(
            anchor_profile=anchor_profile,
            presentation_policy=presentation_policy,
            identity_kernel=identity_kernel,
            visual_signature_policy=policy,
        ).plan_failed_frames(
            base_visual_briefs=briefs,
            failed_frame_ids=missing_frame_ids,
            failure_reasons_by_frame=last_errors_by_frame,
        )
        logger.warning(
            "series visual signature integration applied deterministic fallback for {} frame(s): {}",
            len(fallback_plans),
            ", ".join(plan.frame_id for plan in fallback_plans),
        )
        return merge_visual_anchor_plans_by_frame(
            frame_ids=frame_ids,
            accepted_plans=accepted_by_frame,
            fallback_plans=fallback_plans,
        )



def _compact_visual_story_frame_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the frame-level fields needed by visual anchor integration.

    The upstream prompt context can include full article text, full base prompts,
    long storyboard fields, and route plans. Passing all of it to the visual
    anchor LLM easily exceeds provider input limits. This compact form preserves
    the selected route and per-frame IP/visual-story decision while trimming the
    rest.
    """
    source = dict(context)
    keep_keys = (
        "frame_id",
        "frame_index",
        "source_text",
        "frame_source_text",
        "visual_goal",
        "prompt_intent",
        "primary_subject",
        "secondary_subjects",
        "continuity_anchors",
        "selected_visual_route",
        "visual_story_frame_plan",
        "visual_story_ip_fusion_plan",
    )
    compact: dict[str, Any] = {}
    for key in keep_keys:
        if key in source:
            compact[key] = _compact_visual_story_value(source[key])
    return compact


def _compact_visual_story_value(value: Any, *, max_text: int = 520, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        return text if len(text) <= max_text else f"{text[:max_text].rstrip()}..."
    if isinstance(value, Mapping):
        if depth >= 2:
            return _compact_visual_story_value(str(dict(value)), max_text=max_text)
        preferred_keys = (
            "route_id",
            "route_name",
            "route_type",
            "visual_premise",
            "frame_storytelling_logic",
            "style_family",
            "recommended_ip_role",
            "scores",
            "frame_id",
            "frame_index",
            "local_claim",
            "visual_task",
            "visual_logic",
            "required_subjects",
            "forbidden_losses",
            "ip_role",
            "ip_visibility",
            "placement_logic",
            "action_or_function",
            "relation_to_article_subject",
            "positive_prompt_clause",
            "negative_constraints",
        )
        result: dict[str, Any] = {}
        for key in preferred_keys:
            if key in value:
                result[key] = _compact_visual_story_value(value[key], max_text=max_text, depth=depth + 1)
        if result:
            return result
        for index, (key, item) in enumerate(value.items()):
            if index >= 8:
                break
            result[str(key)] = _compact_visual_story_value(item, max_text=max_text, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_compact_visual_story_value(item, max_text=max_text, depth=depth + 1) for item in list(value)[:8]]
    text = str(value).strip()
    return text if len(text) <= max_text else f"{text[:max_text].rstrip()}..."


def _selected_visual_route_from_contexts(
    frame_contexts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    for context in frame_contexts:
        value = context.get("selected_visual_route")
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _visual_story_frame_plans_from_contexts(
    frame_contexts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for context in frame_contexts:
        value = context.get("visual_story_frame_plan")
        if isinstance(value, Mapping):
            result.append(dict(value))
    return result


def _visual_story_ip_fusion_plans_from_contexts(
    frame_contexts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for context in frame_contexts:
        value = context.get("visual_story_ip_fusion_plan")
        if isinstance(value, Mapping):
            result.append(dict(value))
    return result


def _exception_summary(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        details = []
        for error in exc.errors()[:8]:
            field = ".".join(str(part) for part in error.get("loc", ()))
            message = str(error.get("msg", ""))
            details.append(f"{field}: {message}" if field else message)
        return "; ".join(details) or str(exc)
    return str(exc)


def _is_recoverable_llm_call_error(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, TimeoutException, NetworkError)):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    recoverable_markers = (
        "timeout",
        "timed out",
        "connection",
        "rate_limit",
        "ratelimit",
        "temporarily unavailable",
    )
    return any(marker in text for marker in recoverable_markers)


def _anchor_profile_payload(
    anchor_profile: IPProfile,
    *,
    policy: VisualSignaturePolicy,
    identity_kernel: Sequence[str],
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
) -> dict[str, Any]:
    return {
        "name": anchor_profile.name,
        "visual_summary": anchor_profile.visual_summary,
        "identity_kernel": list(identity_kernel),
        "identity_lock": list(anchor_profile.identity_lock),
        "minimal_traits": list(anchor_profile.minimal_traits),
        "identity_anchors": list(anchor_profile.identity_anchors),
        "style_hint": anchor_profile.style_hint,
        "negative_constraints": list(anchor_profile.negative_constraints),
        "policy_version": policy.version,
        "presentation_policy": presentation_policy.to_prompt_policy(),
        "guidance": (
            [
                "The identity must appear visibly in the final prompt as a content participant.",
                "Use the frame-level content_bound_ip_presence_plan as the source of truth.",
                "If no natural action slot exists, rewrite the scene around the frame physical metaphor; never add a card, label, bookmark, sticker, stamp, logo, bookplate, or surface mark.",
                "Use only provider-facing positive visual language in the final integrated prompt.",
            ]
            if policy.is_content_bound_mandatory
            else [
                "The identity must appear visibly in the final prompt.",
                "Prefer the frame-level IP duty and presentation_policy over lower-level strategy conflicts.",
                "If no natural carrier exists, add a small content-compatible real scene carrier.",
                "Use only natural visual language in the final integrated prompt; do not echo internal policy or forbidden-form labels.",
            ]
        ),
    }


def _placement_plans_from_payload(
    payload: Any,
    *,
    frame_ids: Sequence[str],
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str],
    policy: VisualSignaturePolicy,
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    visual_story_ip_fusion_plans: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[VisualAnchorPlacementPlan], list[str]]:
    if isinstance(payload, MandatoryVisualAnchorIntegrationResponse):
        payload = {
            "visual_anchor_integration_plans": [
                plan.to_plan_payload()
                for plan in payload.visual_anchor_integration_plans
            ]
        }
    elif hasattr(payload, "model_dump"):
        try:
            payload = payload.model_dump(mode="json")
        except TypeError:
            payload = payload.model_dump()
    elif hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    raw_plans = []
    if isinstance(payload, Mapping):
        raw_plans = payload.get("visual_anchor_integration_plans") or payload.get("plans") or payload.get("frames") or []
    elif _is_sequence(payload):
        raw_plans = list(payload)
    if isinstance(raw_plans, Mapping):
        raw_plans = list(raw_plans.values())
    if not _is_sequence(raw_plans):
        raw_plans = []

    by_frame: dict[str, Mapping[str, Any]] = {}
    for index, raw_plan in enumerate(raw_plans):
        if not isinstance(raw_plan, Mapping):
            continue
        frame_id = _first_text(raw_plan.get("frame_id"), raw_plan.get("id"))
        if not frame_id and index < len(frame_ids):
            frame_id = frame_ids[index]
        if frame_id:
            by_frame[frame_id] = raw_plan

    duty_by_frame = _ip_duty_by_frame(visual_story_ip_fusion_plans, frame_ids=frame_ids)

    result: list[VisualAnchorPlacementPlan] = []
    errors: list[str] = []
    for frame_id in frame_ids:
        raw_plan = by_frame.get(frame_id)
        if raw_plan is None:
            errors.append(f"{frame_id}: missing plan")
            continue
        plan, plan_errors = _placement_plan_from_raw_plan(
            raw_plan,
            frame_id=frame_id,
            role_strategy=role_strategy,
            identity_kernel=identity_kernel,
            policy=policy,
            presentation_policy=presentation_policy,
            ip_duty_plan=duty_by_frame.get(frame_id),
        )
        if plan_errors:
            errors.extend(plan_errors)
            continue
        result.append(plan)
    return result, errors


def _placement_plan_from_raw_plan(
    raw_plan: Mapping[str, Any],
    *,
    frame_id: str,
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str],
    policy: VisualSignaturePolicy,
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    ip_duty_plan: Mapping[str, Any] | None = None,
) -> tuple[VisualAnchorPlacementPlan | None, list[str]]:
    if "candidates" in raw_plan or "selected_index" in raw_plan:
        return None, [f"{frame_id}: candidates arrays are not allowed for flat integration"]
    if not _has_flat_candidate_fields(raw_plan):
        return None, [f"{frame_id}: flat visible plan fields are required"]

    errors = _candidate_errors(
        raw_plan,
        frame_id=frame_id,
        role_strategy=role_strategy,
        identity_kernel=identity_kernel,
        policy=policy,
        presentation_policy=presentation_policy,
        ip_duty_plan=ip_duty_plan,
    )
    if errors:
        return None, errors
    plan = _candidate_to_plan(
        raw_plan,
        frame_id=frame_id,
        role_strategy=role_strategy,
        identity_kernel=identity_kernel,
        presentation_policy=presentation_policy,
        ip_duty_plan=ip_duty_plan,
        policy=policy,
    )
    projection_gate = validate_visual_anchor_projection(plan, policy=policy)
    if not projection_gate.passed:
        return None, [
            f"{frame_id}: provider projection gate rejected plan "
            f"({projection_gate.code}: {projection_gate.reason})"
        ]
    return plan, []


def _candidate_to_plan(
    candidate: Mapping[str, Any],
    *,
    frame_id: str,
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str] = (),
    presentation_policy: SeriesVisualSignaturePresentationPolicy | None = None,
    ip_duty_plan: Mapping[str, Any] | None = None,
    policy: VisualSignaturePolicy | None = None,
) -> VisualAnchorPlacementPlan:
    prompt = _prompt_text(candidate)
    duty_plan = _resolved_ip_duty_for_candidate(candidate, ip_duty_plan, frame_id=frame_id)
    carrier_type = _enum_value(candidate.get("carrier_type"), AnchorCarrierType, AnchorCarrierType.BOOKPLATE_OR_STAMP)
    anchor_function = _enum_value(candidate.get("anchor_function"), AnchorFunction, AnchorFunction.MATERIAL_SIGNATURE)
    prominence = _enum_value(candidate.get("prominence"), AnchorProminence, AnchorProminence.EMBEDDED_MARK)
    if policy is not None and policy.is_content_bound_mandatory:
        mechanism = _first_text(candidate.get("ip_participation_mechanism"), candidate.get("participation_mechanism"))
        if mechanism in {"system_component", "transformation_medium"}:
            carrier_type = AnchorCarrierType.CONTENT_BOUND_SYSTEM_COMPONENT
        elif mechanism == "scale_reference":
            carrier_type = AnchorCarrierType.CONTENT_BOUND_SCALE_REFERENCE
        elif mechanism in {"explanation_director", "observation_gateway"}:
            carrier_type = AnchorCarrierType.CONTENT_BOUND_EXPLANATION_DIRECTOR
        else:
            carrier_type = AnchorCarrierType.CONTENT_BOUND_IP_ACTOR
        anchor_function = AnchorFunction.CONTENT_BOUND_PARTICIPANT
        prominence = AnchorProminence.CONTENT_PARTICIPANT
    elif role_strategy.requires_subject_replacement:
        carrier_type = AnchorCarrierType.LIVING_CHARACTER
        anchor_function = AnchorFunction.PRIMARY_CARRIER
        prominence = AnchorProminence.PRIMARY_CARRIER
    elif (
        presentation_policy is not None
        and presentation_policy.presentation_mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER
    ):
        if carrier_type in {AnchorCarrierType.BOOKPLATE_OR_STAMP, AnchorCarrierType.PRINTED_MARK, AnchorCarrierType.SURFACE_GRAPHIC, AnchorCarrierType.EMBOSSED_MARK}:
            carrier_type = AnchorCarrierType.MINOR_SUPPORTING_CHARACTER
            anchor_function = AnchorFunction.CO_PRESENT_SUPPORT
            prominence = AnchorProminence.SMALL_SIDE_CHARACTER

    return VisualAnchorPlacementPlan(
        frame_id=frame_id,
        anchor_function=anchor_function,
        anchor_carrier_type=carrier_type,
        anchor_prominence=prominence,
        visual_weight_clause=_first_text(candidate.get("visual_weight_clause")) or ("主视觉主体" if role_strategy.requires_subject_replacement else "可见但服从主体"),
        placement_zone=_first_text(candidate.get("placement"), _manifestation_value(candidate, "location")),
        support_anchor=_first_text(candidate.get("support_anchor"), _manifestation_value(candidate, "carrier")),
        scale_ratio=_first_text(candidate.get("visual_weight_clause")) or "",
        depth_layer="主视觉层" if role_strategy.requires_subject_replacement else "真实场景元素层",
        contact_relation=_first_text(candidate.get("contact_relation"), _manifestation_value(candidate, "relationship")),
        interaction_target=_first_text(candidate.get("interaction_target")),
        occlusion_relation=_first_text(candidate.get("occlusion_relation")),
        style_relation=_enum_value(candidate.get("style_relation"), AnchorStyleRelation, AnchorStyleRelation.BLENDED),
        image_prompt_clause=prompt,
        metadata={
            "source": "llm_mandatory_series_visual_signature_integration",
            "projection": "llm_integrated_prompt",
            "mandatory_integration": True,
            "series_visual_signature_strategy": role_strategy.to_dict(),
            "presentation_policy": presentation_policy.to_dict() if presentation_policy is not None else {},
            "integration_strategy": _first_text(candidate.get("integration_strategy")),
            "anchor_manifestation": dict(candidate.get("anchor_manifestation") or {}) if isinstance(candidate.get("anchor_manifestation"), Mapping) else {},
            "ip_duty_preset": duty_plan.duty_preset.value,
            "duty_goal": duty_plan.duty_goal,
            "action_verb": duty_plan.action_verb,
            "interaction_target": duty_plan.interaction_target,
            "scene_binding": duty_plan.scene_binding,
            "presentation_form": duty_plan.presentation_form.value,
            "fallback_presentation": duty_plan.fallback_presentation.value,
            "semantic_removal_test": duty_plan.semantic_removal_test,
            "channel_identity_removal_test": duty_plan.channel_identity_removal_test,
            "visual_identity_kernel": [str(item) for item in identity_kernel if str(item or "").strip()],
        },
    )


def _candidate_errors(
    candidate: Mapping[str, Any],
    *,
    frame_id: str,
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str],
    policy: VisualSignaturePolicy,
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    ip_duty_plan: Mapping[str, Any] | None = None,
) -> list[str]:
    prompt = _prompt_text(candidate)
    combined = " ".join([prompt, _first_text(candidate.get("placement")), _first_text(candidate.get("support_anchor")), _first_text(candidate.get("contact_relation")), _first_text(candidate.get("manifestation_location")), _first_text(candidate.get("manifestation_relationship")), str(candidate.get("anchor_manifestation") or "")])
    errors: list[str] = []
    if not prompt:
        errors.append(f"{frame_id}: integrated_scene_prompt is required")
    if any(_first_text(candidate.get(key)).lower() in {"suppressed", "hidden", "absent", "not_present"} for key in ("carrier_type", "anchor_function", "prominence")):
        errors.append(f"{frame_id}: hidden/suppressed candidate is not allowed")
    if policy.contains_forbidden_final_prompt_text(prompt) or contains_forbidden_overlay_language(combined, policy=policy):
        errors.append(f"{frame_id}: prompt contains forbidden overlay/corner/watermark language")
    if not _has_identity_signal(combined, identity_kernel):
        errors.append(f"{frame_id}: prompt does not contain configured visual identity kernel")
    if role_strategy.requires_subject_replacement and not _looks_primary(candidate, combined):
        errors.append(f"{frame_id}: subject_replacement requires primary subject manifestation")
    if policy.is_content_bound_mandatory:
        if _has_content_free_carrier_language(combined):
            errors.append(f"{frame_id}: content-bound IP cannot use cards, labels, bookmarks, stickers, stamps, bookplates, surface marks, or decorative carriers")
        if not _has_content_bound_action(candidate, combined):
            errors.append(f"{frame_id}: content-bound IP requires a visible semantic action bound to the frame metaphor")
    elif role_strategy.requires_supporting_integration:
        if _looks_primary(candidate, combined) and not _looks_small_supporting_character(candidate, combined):
            errors.append(f"{frame_id}: supporting_integration must not replace source subject")
        if not _has_supporting_carrier(candidate, combined, presentation_policy=presentation_policy):
            errors.append(f"{frame_id}: supporting_integration requires a concrete in-scene carrier")
    if policy.requires_every_frame_signature:
        duty_plan = _resolved_ip_duty_for_candidate(candidate, ip_duty_plan, frame_id=frame_id)
        if duty_plan.duty_preset is IPDutyPreset.NONE:
            errors.append(f"{frame_id}: mandatory integration requires ip_duty_preset")
        if not duty_plan.action_verb:
            errors.append(f"{frame_id}: mandatory integration requires action_verb")
        if not duty_plan.interaction_target:
            errors.append(f"{frame_id}: mandatory integration requires interaction_target")
        if not duty_plan.scene_binding:
            errors.append(f"{frame_id}: mandatory integration requires scene_binding")
    return errors


def _ip_duty_by_frame(
    plans: Sequence[Mapping[str, Any]],
    *,
    frame_ids: Sequence[str],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, plan in enumerate(plans or ()):
        if not isinstance(plan, Mapping):
            continue
        frame_id = _first_text(plan.get("frame_id"), plan.get("id"))
        if not frame_id and index < len(frame_ids):
            frame_id = frame_ids[index]
        if frame_id:
            result[frame_id] = dict(plan)
    return result


def _resolved_ip_duty_for_candidate(
    candidate: Mapping[str, Any],
    ip_duty_plan: Mapping[str, Any] | None,
    *,
    frame_id: str,
) -> IPDutyPlan:
    payload: dict[str, Any] = {}
    if isinstance(ip_duty_plan, Mapping):
        payload.update(ip_duty_plan)
    for key in (
        "ip_duty_preset",
        "duty_preset",
        "duty_goal",
        "action_verb",
        "interaction_target",
        "scene_binding",
        "presentation_form",
        "fallback_presentation",
        "semantic_removal_test",
        "channel_identity_removal_test",
        "route_type",
        "visual_route_type",
    ):
        value = candidate.get(key)
        if _first_text(value):
            payload[key] = value
    if not _first_text(payload.get("interaction_target")):
        payload["interaction_target"] = _first_text(candidate.get("interaction_target"), _manifestation_value(candidate, "carrier"))
    if not _first_text(payload.get("scene_binding")):
        payload["scene_binding"] = _first_text(
            candidate.get("scene_binding"),
            candidate.get("contact_relation"),
            candidate.get("support_anchor"),
            _manifestation_value(candidate, "relationship"),
        )
    return IPDutyPlan.from_mapping(payload, frame_id=frame_id)


def _prompt_text(candidate: Mapping[str, Any]) -> str:
    return _first_text(candidate.get("integrated_scene_prompt"), candidate.get("final_integrated_prompt"), candidate.get("final_prompt"), candidate.get("image_prompt_clause"))


def _manifestation_value(candidate: Mapping[str, Any], key: str) -> str:
    manifest = candidate.get("anchor_manifestation")
    if isinstance(manifest, Mapping):
        return _first_text(manifest.get(key))
    return ""


def _has_identity_signal(text: str, identity_kernel: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(token or "").strip().lower() in lowered for token in identity_kernel if len(str(token or "").strip()) >= 2)


def _looks_primary(candidate: Mapping[str, Any], text: str) -> bool:
    values = " ".join([_first_text(candidate.get("carrier_type")), _first_text(candidate.get("anchor_function")), _first_text(candidate.get("prominence")), text]).lower()
    return any(token in values for token in ("primary_carrier", "主角", "主要主体", "protagonist", "main subject", "primary subject"))


def _looks_small_supporting_character(candidate: Mapping[str, Any], text: str) -> bool:
    values = " ".join([_first_text(candidate.get("carrier_type")), _first_text(candidate.get("anchor_function")), _first_text(candidate.get("prominence")), text]).lower()
    return any(token in values for token in ("minor_supporting_character", "small_side_character", "co_present_support", "陪衬", "小型", "旁边", "身旁", "foreground", "beside", "near"))


def _has_supporting_carrier(
    candidate: Mapping[str, Any],
    text: str,
    *,
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
) -> bool:
    carrier_type = _first_text(candidate.get("carrier_type")).lower()
    if carrier_type in {"minor_supporting_character", "small_supporting_prop", "decorative_object"}:
        return True
    lowered = str(text or "").lower()
    tokens = (
        "墙", "桌", "书", "纸", "地图", "相框", "照片", "摆件", "展板", "投影", "屏幕", "电视", "海报", "徽章", "胸针",
        "地面", "前景", "空地", "路边", "草地", "房间角落", "角落", "画面一侧", "主体旁边", "身旁", "桌边", "镜旁", "边缘", "道路", "街道",
        "display", "screen", "projection", "poster", "framed", "prop", "wall", "desk", "book", "foreground", "ground", "floor", "beside", "next to", "near", "corner", "edge", "side", "roadside", "street", "path", "grass", "room corner",
    )
    if any(token in lowered for token in tokens):
        return True
    if presentation_policy.presentation_mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER and _looks_small_supporting_character(candidate, lowered):
        return True
    return False


def _has_content_free_carrier_language(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in (
        "贴纸", "标签", "卡片", "书签", "藏书票", "印章", "表面图案", "压印", "雕刻",
        "sticker", "label", "card", "bookmark", "bookplate", "stamp", "surface graphic", "printed mark", "badge",
    ))


def _has_content_bound_action(candidate: Mapping[str, Any], text: str) -> bool:
    combined = " ".join([
        text,
        _first_text(candidate.get("action_verb")),
        _first_text(candidate.get("interaction_target")),
        _first_text(candidate.get("scene_binding")),
        _first_text(candidate.get("contact_relation")),
    ]).lower()
    return any(token in combined for token in (
        "操作", "拉动", "推动", "连接", "承受", "支撑", "衡量", "整理", "排列", "搭建", "修复", "转化", "过滤", "观察",
        "operate", "pull", "push", "connect", "carry", "weigh", "arrange", "repair", "transform", "filter", "observe",
    ))


def _has_flat_candidate_fields(plan: Mapping[str, Any]) -> bool:
    return any(key in plan for key in ("integrated_scene_prompt", "final_integrated_prompt", "image_prompt_clause", "carrier_type"))


def _enum_value(value: Any, enum_cls: Any, default: Any) -> Any:
    text = _first_text(value)
    if not text:
        return default
    try:
        return enum_cls(text)
    except Exception:
        return default


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _repair_context(
    *,
    attempt: int,
    errors: Sequence[str],
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    instruction: str,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "errors": list(errors),
        "presentation_policy": presentation_policy.to_prompt_policy(),
        "instruction": instruction,
    }


def _errors_by_frame(errors: Sequence[str], frame_ids: Sequence[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {frame_id: [] for frame_id in frame_ids}
    for error in errors:
        text = str(error)
        frame_id = text.split(":", 1)[0].strip()
        if frame_id not in result:
            continue
        result[frame_id].append(text)
    for frame_id in list(result):
        if not result[frame_id]:
            result.pop(frame_id)
    return result


def _flatten_errors(errors_by_frame: Mapping[str, Sequence[str]], frame_ids: Sequence[str]) -> list[str]:
    result: list[str] = []
    for frame_id in frame_ids:
        result.extend(str(item) for item in errors_by_frame.get(frame_id, ()))
    return result


__all__ = ["VisualAnchorIntegrationPlanner"]
