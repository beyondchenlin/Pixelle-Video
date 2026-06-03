from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage
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
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualAnchorIntegrationPlanner:
    """Mandatory series-visual-signature integration planner.

    The second stage is a task: every frame must receive a visible integrated prompt.
    There is no successful hidden/suppressed/fallback result. Bad LLM output enters a
    repair loop; repeated failure raises a clear error.
    """

    llm_service: Any | None = None
    policy: VisualSignaturePolicy | None = None
    series_visual_signature_strategy: SeriesVisualSignatureStrategyControls | None = None
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
        briefs = tuple(base_visual_briefs)
        if not briefs:
            return ()
        if anchor_profile is None:
            raise ValueError("mandatory series visual signature integration requires anchor_profile")
        if self.llm_service is None:
            raise ValueError("mandatory series visual signature integration requires llm_service")
        if not callable(self.llm_service):
            raise ValueError("mandatory series visual signature integration requires callable llm_service")

        policy = self.policy or load_visual_signature_policy()
        role_strategy = self.series_visual_signature_strategy or SeriesVisualSignatureStrategyControls()
        identity_kernel = build_visual_identity_kernel(anchor_profile)
        frame_ids = [brief.frame_id for brief in briefs]
        repair_context: dict[str, Any] = {}

        for attempt in range(max(1, self.max_repair_attempts + 1)):
            rendered_prompt = render_visual_anchor_integration_prompt(
                base_visual_briefs_json=[brief.to_dict() for brief in briefs],
                anchor_profile_json=_anchor_profile_payload(anchor_profile, policy=policy, identity_kernel=identity_kernel),
                visual_signature_policy_json=policy.to_dict(),
                cadence_plan_json=[],
                series_visual_signature_strategy_json=role_strategy.to_dict(),
                visual_identity_kernel_json=list(identity_kernel),
                repair_context_json=repair_context,
            )
            raw_response = await self.llm_service(
                prompt=rendered_prompt.text,
                response_type=dict,
                temperature=0.2,
                max_tokens=5000,
                trace_context=trace_context,
                trace_recorder=trace_recorder,
            )
            plans, errors = _placement_plans_from_payload(
                raw_response,
                frame_ids=frame_ids,
                role_strategy=role_strategy,
                identity_kernel=identity_kernel,
                policy=policy,
            )
            if not errors:
                return tuple(plans)
            repair_context = {
                "attempt": attempt + 1,
                "errors": errors[:24],
                "instruction": "Rewrite every failed frame. Do not output hidden/suppressed/fallback.",
            }
            logger.warning(
                "mandatory series visual signature integration rejected attempt {}: {}",
                attempt + 1,
                "; ".join(errors[:8]),
            )

        raise ValueError(
            "mandatory series visual signature integration failed after repair attempts: "
            + "; ".join(repair_context.get("errors", [])[:12])
        )


def _anchor_profile_payload(anchor_profile: IPProfile, *, policy: VisualSignaturePolicy, identity_kernel: Sequence[str]) -> dict[str, Any]:
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
        "guidance": [
            "This is mandatory series-visual-signature integration.",
            "The identity must appear visibly in the final prompt.",
            "If no natural carrier exists, create one by recomposition: TV, projection, frame, exhibit, desk, wall, book, poster, or prop.",
            "Do not output hidden, suppressed, absent, fallback, watermark, sticker, corner badge, or UI overlay.",
        ],
    }


def _placement_plans_from_payload(
    payload: Any,
    *,
    frame_ids: Sequence[str],
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str],
    policy: VisualSignaturePolicy,
) -> tuple[list[VisualAnchorPlacementPlan], list[str]]:
    if hasattr(payload, "model_dump"):
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
) -> tuple[VisualAnchorPlacementPlan | None, list[str]]:
    raw_candidates = raw_plan.get("candidates")
    if isinstance(raw_candidates, Mapping):
        candidates = [raw_candidates]
    elif _is_sequence(raw_candidates):
        candidates = [candidate for candidate in raw_candidates if isinstance(candidate, Mapping)]
    elif _has_flat_candidate_fields(raw_plan):
        candidates = [raw_plan]
    else:
        return None, [f"{frame_id}: candidates must be an array of visible candidate objects"]

    candidate_errors: list[str] = []
    for candidate in candidates:
        errors = _candidate_errors(candidate, frame_id=frame_id, role_strategy=role_strategy, identity_kernel=identity_kernel, policy=policy)
        if errors:
            candidate_errors.extend(errors)
            continue
        return _candidate_to_plan(candidate, frame_id=frame_id, role_strategy=role_strategy), []
    return None, candidate_errors or [f"{frame_id}: no visible candidate accepted"]


def _candidate_to_plan(
    candidate: Mapping[str, Any],
    *,
    frame_id: str,
    role_strategy: SeriesVisualSignatureStrategyControls,
) -> VisualAnchorPlacementPlan:
    prompt = _prompt_text(candidate)
    carrier_type = _enum_value(candidate.get("carrier_type"), AnchorCarrierType, AnchorCarrierType.BOOKPLATE_OR_STAMP)
    anchor_function = _enum_value(candidate.get("anchor_function"), AnchorFunction, AnchorFunction.MATERIAL_SIGNATURE)
    prominence = _enum_value(candidate.get("prominence"), AnchorProminence, AnchorProminence.EMBEDDED_MARK)
    if role_strategy.requires_subject_replacement:
        carrier_type = AnchorCarrierType.LIVING_CHARACTER
        anchor_function = AnchorFunction.PRIMARY_CARRIER
        prominence = AnchorProminence.PRIMARY_CARRIER

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
            "integration_strategy": _first_text(candidate.get("integration_strategy")),
            "anchor_manifestation": dict(candidate.get("anchor_manifestation") or {}) if isinstance(candidate.get("anchor_manifestation"), Mapping) else {},
        },
    )


def _candidate_errors(
    candidate: Mapping[str, Any],
    *,
    frame_id: str,
    role_strategy: SeriesVisualSignatureStrategyControls,
    identity_kernel: Sequence[str],
    policy: VisualSignaturePolicy,
) -> list[str]:
    prompt = _prompt_text(candidate)
    combined = " ".join([prompt, _first_text(candidate.get("placement")), _first_text(candidate.get("support_anchor")), _first_text(candidate.get("contact_relation")), str(candidate.get("anchor_manifestation") or "")])
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
    if role_strategy.requires_supporting_integration:
        if _looks_primary(candidate, combined):
            errors.append(f"{frame_id}: supporting_integration must not replace source subject")
        if not _has_supporting_carrier(combined):
            errors.append(f"{frame_id}: supporting_integration requires a concrete in-scene carrier")
    return errors


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
    return any(token in values for token in ("living_character", "primary_carrier", "主角", "主要主体", "protagonist", "main subject", "primary subject"))


def _has_supporting_carrier(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("墙", "桌", "书", "纸", "地图", "相框", "照片", "摆件", "展板", "投影", "屏幕", "电视", "海报", "徽章", "胸针", "display", "screen", "projection", "poster", "framed", "prop", "wall", "desk", "book"))


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


__all__ = ["VisualAnchorIntegrationPlanner"]
