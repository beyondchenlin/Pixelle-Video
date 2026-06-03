from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_identity import (
    SeriesVisualSignatureParticipationMode,
    SeriesVisualSignatureStructureMode,
)
from pixelle_video.models.series_visual_signature_planning import (
    SeriesVisualSignatureIntegratedPromptPlan,
)
from pixelle_video.models.series_visual_signature_profile import SeriesVisualSignatureProfile
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.series_visual_signature_strategy import SeriesVisualSignatureMode
from pixelle_video.models.visual_expression import VisualExpressionDecision, VisualExpressionMode
from pixelle_video.services.series_visual_signature_primary_contract import (
    has_non_primary_subject_signal,
    has_primary_subject_signal,
    repair_primary_subject_negations,
)


class SeriesVisualSignaturePlanningError(ValueError):
    pass


@dataclass(frozen=True)
class SeriesVisualSignatureScenePlanner:
    llm_service: Any | None = None

    async def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        series_visual_signature_request: SeriesVisualSignatureRequest,
        series_visual_signature_profile: SeriesVisualSignatureProfile,
        expression_decisions: Sequence[VisualExpressionDecision],
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        repair_context_by_frame: Mapping[str, Any] | None = None,
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> tuple[SeriesVisualSignatureIntegratedPromptPlan, ...]:
        plans: list[SeriesVisualSignatureIntegratedPromptPlan] = []
        for index, brief in enumerate(base_visual_briefs):
            decision = (
                expression_decisions[index]
                if index < len(expression_decisions)
                else VisualExpressionDecision(
                    frame_id=brief.frame_id,
                    expression_mode=series_visual_signature_request.expression_mode,
                    reason="fallback to request expression mode",
                )
            )
            frame_context = frame_contexts[index] if index < len(frame_contexts) else {}
            repair_context = (repair_context_by_frame or {}).get(brief.frame_id)
            if self.llm_service is not None:
                plans.append(
                    await self._plan_frame_with_llm(
                        base_visual_brief=brief,
                        series_visual_signature_request=series_visual_signature_request,
                        series_visual_signature_profile=series_visual_signature_profile,
                        expression_decision=decision,
                        frame_context=frame_context,
                        repair_context=repair_context,
                        trace_context=trace_context,
                        trace_recorder=trace_recorder,
                    )
                )
            else:
                plans.append(
                    self.plan_frame_rule(
                        base_visual_brief=brief,
                        series_visual_signature_request=series_visual_signature_request,
                        series_visual_signature_profile=series_visual_signature_profile,
                        expression_decision=decision,
                        frame_context=frame_context,
                        repair_context=repair_context,
                    )
                )
        return tuple(plans)

    async def _plan_frame_with_llm(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        series_visual_signature_request: SeriesVisualSignatureRequest,
        series_visual_signature_profile: SeriesVisualSignatureProfile,
        expression_decision: VisualExpressionDecision,
        frame_context: Mapping[str, Any] | None = None,
        repair_context: Any = None,
        trace_context: Any = None,
        trace_recorder: Any = None,
    ) -> SeriesVisualSignatureIntegratedPromptPlan:
        prompt = _render_planner_prompt(
            base_visual_brief=base_visual_brief,
            series_visual_signature_request=series_visual_signature_request,
            series_visual_signature_profile=series_visual_signature_profile,
            expression_decision=expression_decision,
            frame_context=frame_context,
            repair_context=repair_context,
        )
        response = await self.llm_service(
            prompt=prompt,
            response_type=dict,
            temperature=0.2,
            max_tokens=2500,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        return _plan_from_payload(
            response,
            base_visual_brief=base_visual_brief,
            series_visual_signature_request=series_visual_signature_request,
            series_visual_signature_profile=series_visual_signature_profile,
            expression_decision=expression_decision,
            frame_context=frame_context,
            repair_context=repair_context,
            planner_source="llm",
            require_integrated_prompt=True,
        )

    def plan_frame_rule(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        series_visual_signature_request: SeriesVisualSignatureRequest,
        series_visual_signature_profile: SeriesVisualSignatureProfile,
        expression_decision: VisualExpressionDecision,
        frame_context: Mapping[str, Any] | None = None,
        repair_context: Any = None,
    ) -> SeriesVisualSignatureIntegratedPromptPlan:
        return _plan_from_payload(
            {},
            base_visual_brief=base_visual_brief,
            series_visual_signature_request=series_visual_signature_request,
            series_visual_signature_profile=series_visual_signature_profile,
            expression_decision=expression_decision,
            frame_context=frame_context,
            repair_context=repair_context,
            planner_source="rule",
            require_integrated_prompt=False,
        )


def _plan_from_payload(
    payload: Mapping[str, Any],
    *,
    base_visual_brief: BaseVisualBrief,
    series_visual_signature_request: SeriesVisualSignatureRequest,
    series_visual_signature_profile: SeriesVisualSignatureProfile,
    expression_decision: VisualExpressionDecision,
    frame_context: Mapping[str, Any] | None,
    repair_context: Any,
    planner_source: str,
    require_integrated_prompt: bool,
) -> SeriesVisualSignatureIntegratedPromptPlan:
    if not isinstance(payload, Mapping):
        raise SeriesVisualSignaturePlanningError("series visual signature planner response must be a mapping")
    signature_mode = _effective_signature_mode(series_visual_signature_request)
    identity = series_visual_signature_profile.display_name
    original_intent = _original_intent(base_visual_brief, frame_context)
    role_action = _text(payload.get("role_action")) or _select_action(series_visual_signature_profile, signature_mode=signature_mode)
    role_manifestation = _text(payload.get("role_manifestation")) or _select_manifestation(series_visual_signature_profile, signature_mode=signature_mode)
    retained_intent = _retained_intent(base_visual_brief)
    role_location = _text(payload.get("role_location")) or _role_location(expression_decision.expression_mode, signature_mode)
    scene_rewrite_level = _text(payload.get("scene_rewrite_level")) or (
        "recompose_subject" if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT else "supporting_in_scene_rewrite"
    )
    integration_strategy = _text(payload.get("integration_strategy")) or _integration_strategy(expression_decision.expression_mode, signature_mode)
    structure_mode = series_visual_signature_request.structure_mode
    participation_mode = series_visual_signature_request.participation_mode
    structure_decision = _text(payload.get("structure_decision")) or _structure_decision(
        structure_mode,
        expression_decision.expression_mode,
        base_visual_brief,
    )
    participation_decision = _text(payload.get("participation_decision")) or _participation_decision(
        participation_mode,
        signature_mode,
        series_visual_signature_profile,
    )

    integrated_prompt = _text(payload.get("integrated_scene_prompt"))
    if require_integrated_prompt and not integrated_prompt:
        raise SeriesVisualSignaturePlanningError("LLM series visual signature planner must return integrated_scene_prompt")
    if not integrated_prompt:
        integrated_prompt = _rule_integrated_prompt(
            signature_mode=signature_mode,
            identity=identity,
            original_intent=original_intent,
            role_action=role_action,
            role_manifestation=role_manifestation,
            role_location=role_location,
            structure_decision=structure_decision,
            participation_decision=participation_decision,
            base_visual_brief=base_visual_brief,
        )
    integrated_prompt = _ensure_identity_presence_in_prompt(
        integrated_prompt,
        series_visual_signature_profile,
    )

    role_assignment = _text(payload.get("role_assignment")) or (
        "primary series visual signature" if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT else "supporting series visual signature"
    )
    subject_replacement_primary_contract_enforced = False
    if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        (
            role_assignment,
            role_action,
            role_manifestation,
            role_location,
            integrated_prompt,
            subject_replacement_primary_contract_enforced,
        ) = _normalize_subject_replacement_primary_contract(
            identity=identity,
            original_intent=original_intent,
            role_assignment=role_assignment,
            role_action=role_action,
            role_manifestation=role_manifestation,
            role_location=role_location,
            integrated_prompt=integrated_prompt,
        )
        integrated_prompt = _ensure_identity_presence_in_prompt(
            integrated_prompt,
            series_visual_signature_profile,
        )
    metadata = {
        "planner": "SeriesVisualSignatureScenePlanner",
        "planner_version": "v4_2_identity_contract",
        "planner_source": planner_source,
        "expression_decision": expression_decision.to_dict(),
        "series_visual_signature_request": series_visual_signature_request.to_dict(),
    }
    if subject_replacement_primary_contract_enforced:
        metadata["subject_replacement_primary_contract_enforced"] = True
    if repair_context:
        metadata["repair_context"] = repair_context

    return SeriesVisualSignatureIntegratedPromptPlan(
        frame_id=base_visual_brief.frame_id,
        expression_mode=expression_decision.expression_mode,
        signature_mode=signature_mode,
        consistency_mode=series_visual_signature_request.strategy.consistency_mode,
        role_assignment=role_assignment,
        scene_rewrite_level=scene_rewrite_level,
        integration_strategy=integration_strategy,
        original_intent_summary=original_intent,
        retained_intent=retained_intent,
        transformed_scene_logic=_text(payload.get("transformed_scene_logic"))
        or "将基础视觉意图转化为视觉签名参与表达的完整画面，而不是后置添加装饰。",
        role_action=role_action,
        role_manifestation=role_manifestation,
        role_location=role_location,
        integrated_scene_prompt=integrated_prompt,
        structure_mode=structure_mode,
        participation_mode=participation_mode,
        structure_decision=structure_decision,
        participation_decision=participation_decision,
        quality_notes=_normalize_text_tuple(payload.get("quality_notes"))
        or (
            "视觉签名必须参与表达",
            "禁止角标、水印、贴纸、logo、overlay",
            "最终 prompt 来自 integrated_scene_prompt",
        ),
        metadata=metadata,
    )


def _render_planner_prompt(
    *,
    base_visual_brief: BaseVisualBrief,
    series_visual_signature_request: SeriesVisualSignatureRequest,
    series_visual_signature_profile: SeriesVisualSignatureProfile,
    expression_decision: VisualExpressionDecision,
    frame_context: Mapping[str, Any] | None,
    repair_context: Any,
) -> str:
    payload = {
        "task": "Rewrite base visual intent into a complete integrated_scene_prompt where the series visual signature participates in expression.",
        "hard_rules": [
            "Return valid JSON only.",
            "integrated_scene_prompt is mandatory and must be non-empty.",
            "Do not output hidden, suppressed, fallback, watermark, sticker, logo, corner badge, or overlay as success.",
            "Preserve the original visual intent, topic, main subjects, information focus, and mood.",
            "The series visual signature must carry an action or scene responsibility, not meaningless decoration.",
            "If signature_mode is subject_replacement, the series visual signature must be the primary subject.",
            "If signature_mode is supporting_integration, keep the original subjects and integrate the series visual signature as an in-scene support role.",
            "Repair context is instruction only; never copy issue text into integrated_scene_prompt.",
        ],
        "expected_json_keys": [
            "role_assignment",
            "scene_rewrite_level",
            "integration_strategy",
            "original_intent_summary",
            "retained_intent",
            "transformed_scene_logic",
            "role_action",
            "role_manifestation",
            "role_location",
            "structure_decision",
            "participation_decision",
            "integrated_scene_prompt",
            "quality_notes",
        ],
        "base_visual_brief": base_visual_brief.to_dict(),
        "series_visual_signature_request": series_visual_signature_request.to_dict(),
        "series_visual_signature_profile": series_visual_signature_profile.to_dict(),
        "expression_decision": expression_decision.to_dict(),
        "frame_context": dict(frame_context or {}),
        "repair_context": repair_context or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _rule_integrated_prompt(
    *,
    signature_mode: SeriesVisualSignatureMode,
    identity: str,
    original_intent: str,
    role_action: str,
    role_manifestation: str,
    role_location: str,
    structure_decision: str,
    participation_decision: str,
    base_visual_brief: BaseVisualBrief,
) -> str:
    if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return (
            f"以{identity}作为画面核心主体和主要行动者，{role_action}当前主题；"
            f"保留原始意图：{original_intent}；"
            f"画面构图围绕{identity}展开，{role_manifestation}，位置：{role_location}；"
            f"结构决策：{structure_decision}；参与决策：{participation_decision}；"
            "风格与原始画面保持一致，画面清晰统一。"
        )
    main_subjects = "、".join(base_visual_brief.main_subjects) or "原始画面主体"
    return (
        f"保留原始主体：{main_subjects}；保留原始意图：{original_intent}；"
        f"让{identity}作为真实场景内的辅助视觉签名出现，承担{role_action}职责，"
        f"{role_manifestation}，位置：{role_location}；"
        f"结构决策：{structure_decision}；参与决策：{participation_decision}；"
        f"{identity}必须以真实场景内角色或载体参与画面表达，具有明确动作和场景职责。"
    )


def _effective_signature_mode(request: SeriesVisualSignatureRequest) -> SeriesVisualSignatureMode:
    if request.strategy.effective_signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    if request.strategy.effective_signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION:
        return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    return SeriesVisualSignatureMode.SUPPORTING_INTEGRATION


def _ensure_identity_presence_in_prompt(
    prompt: str,
    profile: SeriesVisualSignatureProfile,
) -> str:
    missing_required = _missing_terms(
        prompt,
        profile.identity_contract.required_identity_traits,
    )
    identity_kernel_present = _contains_any(prompt, profile.identity_kernel)
    if not missing_required and identity_kernel_present:
        return prompt

    identity_clause = _identity_presence_scene_clause(
        profile,
        missing_required=missing_required,
        include_identity_kernel=not identity_kernel_present,
    )
    if not identity_clause:
        return prompt
    if prompt.endswith((".", "。", "!", "！", "?", "？")):
        return f"{prompt} {identity_clause}"
    return f"{prompt}. {identity_clause}"


def _normalize_subject_replacement_primary_contract(
    *,
    identity: str,
    original_intent: str,
    role_assignment: str,
    role_action: str,
    role_manifestation: str,
    role_location: str,
    integrated_prompt: str,
) -> tuple[str, str, str, str, str, bool]:
    changed = False
    role_action, repaired = _repair_primary_subject_negations(role_action)
    changed = changed or repaired
    role_manifestation, repaired = _repair_primary_subject_negations(role_manifestation)
    changed = changed or repaired
    role_location, repaired = _repair_primary_subject_negations(role_location)
    changed = changed or repaired
    integrated_prompt, repaired = _repair_primary_subject_negations(integrated_prompt)
    changed = changed or repaired
    if not has_primary_subject_signal(role_assignment) or has_non_primary_subject_signal(role_assignment):
        role_assignment = f"{identity} as primary protagonist and central visual subject"
        changed = True
    if not has_primary_subject_signal(role_manifestation) or has_non_primary_subject_signal(role_manifestation):
        role_manifestation = "primary in-scene protagonist"
        changed = True
    if not has_primary_subject_signal(role_location) or has_non_primary_subject_signal(role_location):
        role_location = "primary focus area"
        changed = True
    if not has_primary_subject_signal(role_action) or has_non_primary_subject_signal(role_action):
        role_action = "carries the primary scene action"
        changed = True
    if has_non_primary_subject_signal(integrated_prompt):
        integrated_prompt = _subject_replacement_primary_prompt(
            identity=identity,
            original_intent=original_intent,
            role_action=role_action,
            role_manifestation=role_manifestation,
            role_location=role_location,
        )
        changed = True
    elif not has_primary_subject_signal(integrated_prompt):
        primary_clause = (
            f"{identity} is the primary protagonist and central visual subject of the frame, "
            "carrying the main scene action while preserving the source intent."
        )
        integrated_prompt = _join_sentence_prefix(primary_clause, integrated_prompt)
        changed = True
    return (
        role_assignment,
        role_action,
        role_manifestation,
        role_location,
        integrated_prompt,
        changed,
    )


def _join_sentence_prefix(prefix: str, body: str) -> str:
    prefix_text = _text(prefix)
    body_text = _text(body)
    if not prefix_text:
        return body_text
    if not body_text:
        return prefix_text
    if prefix_text.endswith((".", "。", "!", "！", "?", "？")):
        return f"{prefix_text} {body_text}"
    return f"{prefix_text}. {body_text}"


def _subject_replacement_primary_prompt(
    *,
    identity: str,
    original_intent: str,
    role_action: str,
    role_manifestation: str,
    role_location: str,
) -> str:
    return (
        f"{identity} is the primary protagonist and central visual subject of the frame, "
        f"{role_action}. The composition is built around {identity} in the {role_location}; "
        f"{role_manifestation}. Preserve the source intent: {original_intent}."
    )


def _repair_primary_subject_negations(value: str) -> tuple[str, bool]:
    original = _text(value)
    repaired = repair_primary_subject_negations(original)
    return repaired, repaired != original


def _identity_presence_scene_clause(
    profile: SeriesVisualSignatureProfile,
    *,
    missing_required: Sequence[str],
    include_identity_kernel: bool,
) -> str:
    parts = [profile.display_name]
    if include_identity_kernel:
        identity_kernel = ", ".join(_dedupe(profile.identity_kernel))
        if identity_kernel:
            parts.append(identity_kernel)
    parts.extend(_dedupe(missing_required))
    visible_traits = "、".join(_dedupe(parts))
    if not visible_traits:
        return ""
    return f"{visible_traits}作为真实场景内角色出现，身份特征通过可见动作和场景互动自然呈现。"


def _missing_terms(prompt: str, required_terms: Sequence[str]) -> tuple[str, ...]:
    lowered = prompt.lower()
    missing: list[str] = []
    for term in required_terms:
        text = str(term or "").strip()
        if text and text.lower() not in lowered:
            missing.append(text)
    return tuple(missing)


def _contains_any(prompt: str, terms: Sequence[str]) -> bool:
    lowered = prompt.lower()
    return any(term and term.lower() in lowered for term in terms)


def _original_intent(brief: BaseVisualBrief, frame_context: Mapping[str, Any] | None) -> str:
    context_text = ""
    if frame_context:
        context_text = str(frame_context.get("visual_goal") or frame_context.get("prompt_intent") or frame_context.get("source_text") or frame_context.get("frame_source_text") or "").strip()
    return context_text or brief.visual_moment or brief.base_image_prompt or brief.core_message or "清晰表达当前分镜主题"


def _retained_intent(brief: BaseVisualBrief) -> tuple[str, ...]:
    return tuple(_dedupe([brief.core_message, brief.visual_moment, brief.subject_relationship, brief.setting, *brief.main_subjects, *brief.key_props_symbols])) or ("保留原始用户意图",)


def _select_action(profile: SeriesVisualSignatureProfile, *, signature_mode: SeriesVisualSignatureMode) -> str:
    if profile.action_affordances:
        return profile.action_affordances[0]
    return "作为核心主体行动" if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT else "讲解和引导视线"


def _select_manifestation(profile: SeriesVisualSignatureProfile, *, signature_mode: SeriesVisualSignatureMode) -> str:
    if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return profile.primary_role_affordances[0] if profile.primary_role_affordances else "画面主角"
    return profile.supporting_role_affordances[0] if profile.supporting_role_affordances else "场景内辅助角色"


def _role_location(expression_mode: VisualExpressionMode, signature_mode: SeriesVisualSignatureMode) -> str:
    if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT:
        return "画面中心或主要视觉焦点区域"
    mapping = {
        VisualExpressionMode.EXPLANATORY_DIAGRAM: "图解结构旁的真实讲解位置",
        VisualExpressionMode.INFOGRAPHIC_LAYOUT: "信息层级中的指示区域",
        VisualExpressionMode.COGNITIVE_METAPHOR: "隐喻场景中的可见职责位置",
        VisualExpressionMode.ENVIRONMENT_BRANDING: "环境空间中的品牌化装置位置",
    }
    return mapping.get(expression_mode, "主体附近的真实场景位置")


def _structure_decision(
    mode: SeriesVisualSignatureStructureMode,
    expression_mode: VisualExpressionMode,
    brief: BaseVisualBrief,
) -> str:
    if mode is SeriesVisualSignatureStructureMode.AUTO:
        return (
            f"Use the {expression_mode.value} structure that best preserves "
            f"the frame intent: {brief.core_message or brief.visual_moment}."
        )
    return f"Use the configured {mode.value} visual structure for this frame."


def _participation_decision(
    mode: SeriesVisualSignatureParticipationMode,
    signature_mode: SeriesVisualSignatureMode,
    profile: SeriesVisualSignatureProfile,
) -> str:
    if mode is SeriesVisualSignatureParticipationMode.AUTO:
        return (
            f"Let {profile.display_name} participate as {signature_mode.value} "
            "with a visible in-scene responsibility."
        )
    return f"Let {profile.display_name} participate through {mode.value}."


def _integration_strategy(expression_mode: VisualExpressionMode, signature_mode: SeriesVisualSignatureMode) -> str:
    return f"{expression_mode.value}: {'subject replacement' if signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT else 'supporting integration'}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_text(value),) if _text(value) else ()
    if isinstance(value, Sequence):
        return tuple(_dedupe(str(item or "").strip() for item in value if str(item or "").strip()))
    return ()


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


__all__ = ["SeriesVisualSignaturePlanningError", "SeriesVisualSignatureScenePlanner"]
