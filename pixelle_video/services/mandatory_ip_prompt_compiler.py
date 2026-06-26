from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.content_bound_ip import (
    ContentBoundIPPresencePlan,
    IPParticipationMechanism,
    image_prompt_clause_from_presence_plan,
)
from pixelle_video.models.ip_duty import (
    IPDutyPlan,
    IPDutyPreset,
    IPPresentationForm,
    build_default_ip_duty_plan,
)
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.content_bound_ip_planner import ContentBoundIPPlanner
from pixelle_video.services.visual_anchor_policy import anchor_identity_from_profile
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


class MandatoryIPParticipationError(ValueError):
    """Raised when mandatory IP participation cannot be projected safely."""


_ACTION_BASED_DUTIES = {
    IPDutyPreset.HOST_EXPLAINER,
    IPDutyPreset.GUIDE_EXPLAINER,
    IPDutyPreset.OPERATOR_DEMONSTRATOR,
    IPDutyPreset.POINTER_ANNOTATOR,
    IPDutyPreset.EVIDENCE_CURATOR,
    IPDutyPreset.CONTRAST_JUDGE,
    IPDutyPreset.EMOTIONAL_PROXY,
    IPDutyPreset.METAPHOR_SYMBOL,
    IPDutyPreset.STRUCTURE_CARRIER,
    IPDutyPreset.RELATIONSHIP_MEDIATOR,
    IPDutyPreset.NAVIGATOR_PATHFINDER,
    IPDutyPreset.MECHANIC_REPAIRER,
    IPDutyPreset.THRESHOLD_GUARDIAN,
    IPDutyPreset.COMIC_COUNTERPOINT,
}

_BACKGROUND_DUTIES = {
    IPDutyPreset.BACKGROUND_SIGNATURE,
    IPDutyPreset.COMPANION_WITNESS,
}


def compile_mandatory_ip_participation_plan(
    *,
    frame_id: str,
    anchor_profile: IPProfile,
    base_visual_brief: BaseVisualBrief,
    duty_payload: Mapping[str, Any] | IPDutyPlan | None = None,
    failure_reasons: Sequence[str] = (),
    policy: VisualSignaturePolicy | None = None,
) -> VisualAnchorPlacementPlan:
    """Compile a mandatory IP plan.

    v2 defaults to content-bound IP presence: the IP appears as a visible actor,
    system component, scale reference, or explanation director.  It never falls
    back to bookplates, labels, bookmarks, surface marks, stickers, or cards.
    Legacy carrier behavior is retained only for explicit legacy policies.
    """

    policy = policy or load_visual_signature_policy()
    identity = anchor_identity_from_profile(anchor_profile)
    if policy.is_content_bound_mandatory:
        return _compile_content_bound_ip_plan(
            frame_id=frame_id,
            identity=identity,
            base_visual_brief=base_visual_brief,
            duty_payload=duty_payload,
            failure_reasons=failure_reasons,
            policy=policy,
            anchor_profile=anchor_profile,
        )
    return _compile_legacy_anchor_plan(
        frame_id=frame_id,
        identity=identity,
        base_visual_brief=base_visual_brief,
        duty_payload=duty_payload,
        failure_reasons=failure_reasons,
        policy=policy,
    )


def _compile_content_bound_ip_plan(
    *,
    frame_id: str,
    identity: str,
    anchor_profile: IPProfile,
    base_visual_brief: BaseVisualBrief,
    duty_payload: Mapping[str, Any] | IPDutyPlan | None,
    failure_reasons: Sequence[str],
    policy: VisualSignaturePolicy,
) -> VisualAnchorPlacementPlan:
    metadata = dict(base_visual_brief.metadata or {})
    fusion_payload = _mapping_from(duty_payload) or _mapping_from(metadata.get("visual_story_ip_fusion_plan")) or _mapping_from(metadata.get("ip_duty_plan"))

    if fusion_payload and isinstance(fusion_payload.get("content_bound_ip_presence_plan"), Mapping):
        presence = ContentBoundIPPresencePlan.from_mapping(
            fusion_payload.get("content_bound_ip_presence_plan"),
            frame_id=frame_id,
        )
    elif fusion_payload:
        presence = ContentBoundIPPresencePlan.from_mapping(fusion_payload, frame_id=frame_id)
    else:
        visual_payload = _visual_payload_from_brief(base_visual_brief)
        selected_route = _mapping_from(metadata.get("selected_visual_route"))
        ip_profile_payload = _ip_profile_payload(anchor_profile)
        fusion_payload = ContentBoundIPPlanner().plan_for_frame(
            visual_payload,
            selected_visual_route=selected_route,
            style_harmonization=_mapping_from(metadata.get("style_harmonization")),
            article_summary=_mapping_from(metadata.get("article_summary")),
            ip_profile=ip_profile_payload,
            force_rewrite=bool(failure_reasons),
            rewrite_reason="; ".join(str(item) for item in failure_reasons),
        )
        presence = ContentBoundIPPresencePlan.from_mapping(
            fusion_payload.get("content_bound_ip_presence_plan") or fusion_payload,
            frame_id=frame_id,
        )

    if presence.rewrite_required:
        # The fallback compiler consumes rewrite_required by using the deterministic
        # content-bound plan itself.  Downstream never sees a pending rewrite flag.
        presence = ContentBoundIPPresencePlan.from_mapping(
            {**presence.to_dict(), "rewrite_required": False, "rewrite_instruction": ""},
            frame_id=frame_id,
        )

    carrier_type = _carrier_for_mechanism(presence.participation_mechanism)
    clause = image_prompt_clause_from_presence_plan(presence, identity_phrase=identity)
    metadata_payload = {
        "compiler": "mandatory_ip_prompt_compiler.v2_content_bound",
        "mandatory_ip_participation": True,
        "policy": policy.version,
        "fallback_strategy": policy.fallback_strategy,
        "content_bound_ip_presence_plan": presence.to_dict(),
        "ip_participation_mechanism": presence.participation_mechanism.value,
        "content_relation_type": "content_bound",
        "semantic_removal_test": presence.semantic_removal_test,
        "channel_identity_removal_test": "removing the recurring character removes the series identity while keeping article subjects intact",
        "failure_reasons": [str(item) for item in failure_reasons],
        "visual_identity_kernel": [identity],
    }
    return VisualAnchorPlacementPlan(
        frame_id=frame_id,
        anchor_function=AnchorFunction.CONTENT_BOUND_PARTICIPANT,
        anchor_carrier_type=carrier_type,
        anchor_prominence=AnchorProminence.CONTENT_PARTICIPANT,
        visual_weight_clause=presence.scale_role,
        placement_zone=presence.scene_arena,
        support_anchor=presence.scene_arena,
        scale_ratio=presence.scale_role,
        depth_layer="content action layer",
        contact_relation=presence.scene_binding,
        interaction_target=presence.interaction_target,
        occlusion_relation=presence.relation_to_article_subject,
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause=clause,
        metadata=metadata_payload,
        version="visual_anchor_placement_plan.v4_content_bound_ip",
    )


def _compile_legacy_anchor_plan(
    *,
    frame_id: str,
    identity: str,
    base_visual_brief: BaseVisualBrief,
    duty_payload: Mapping[str, Any] | IPDutyPlan | None,
    failure_reasons: Sequence[str],
    policy: VisualSignaturePolicy,
) -> VisualAnchorPlacementPlan:
    duty = _resolve_duty_plan(duty_payload, frame_id=frame_id, base_visual_brief=base_visual_brief)
    if duty.duty_preset is IPDutyPreset.NONE:
        raise MandatoryIPParticipationError(f"{frame_id}: mandatory IP duty cannot be none")

    support_anchor, carrier_origin = choose_mandatory_support_anchor(base_visual_brief, duty=duty)
    if duty.duty_preset in _BACKGROUND_DUTIES or duty.presentation_form in {IPPresentationForm.BACKGROUND_SIGNATURE, IPPresentationForm.EMBEDDED_MARK}:
        carrier_type = _embedded_carrier_type(support_anchor)
        anchor_function = AnchorFunction.MATERIAL_SIGNATURE
        prominence = AnchorProminence.EMBEDDED_MARK
        clause = _background_signature_clause(identity=identity, support_anchor=support_anchor)
        contact_relation = f"印刷、压印或刻写在{support_anchor}的真实材质表面"
        visual_weight = "小面积清晰可辨，视觉重量低于主体"
    elif duty.presentation_form is IPPresentationForm.SMALL_SUPPORTING_PROP:
        carrier_type = AnchorCarrierType.SMALL_SUPPORTING_PROP
        anchor_function = AnchorFunction.SCENE_BOUND_PROP
        prominence = AnchorProminence.TINY_PROP
        clause = _small_prop_clause(identity=identity, duty=duty, support_anchor=support_anchor)
        contact_relation = f"小物件放在{support_anchor}上并与支撑面接触"
        visual_weight = "小道具级存在感，服从主体叙事"
    else:
        carrier_type = AnchorCarrierType.MINOR_SUPPORTING_CHARACTER
        anchor_function = _anchor_function_for_duty(duty.duty_preset)
        prominence = AnchorProminence.SMALL_SIDE_CHARACTER
        clause = _functional_actor_clause(identity=identity, duty=duty, support_anchor=support_anchor)
        contact_relation = f"小型角色站在或靠近{support_anchor}，身体或爪子接触交互对象"
        visual_weight = "可见但明显低于主要主体"

    metadata = {
        "compiler": "mandatory_ip_prompt_compiler.legacy",
        "mandatory_ip_participation": True,
        "policy": policy.version,
        "carrier_origin": carrier_origin,
        "ip_duty_preset": duty.duty_preset.value,
        "presentation_form": duty.presentation_form.value,
        "fallback_presentation": duty.fallback_presentation.value,
        "action_verb": duty.action_verb,
        "interaction_target": duty.interaction_target,
        "scene_binding": duty.scene_binding,
        "semantic_removal_test": duty.semantic_removal_test,
        "channel_identity_removal_test": duty.channel_identity_removal_test,
        "failure_reasons": [str(item) for item in failure_reasons],
        "visual_identity_kernel": [identity],
    }
    return VisualAnchorPlacementPlan(
        frame_id=frame_id,
        anchor_function=anchor_function,
        anchor_carrier_type=carrier_type,
        anchor_prominence=prominence,
        visual_weight_clause=visual_weight,
        placement_zone=f"绑定在{support_anchor}",
        support_anchor=support_anchor,
        scale_ratio=visual_weight,
        depth_layer="真实场景元素层",
        contact_relation=contact_relation,
        interaction_target=duty.interaction_target,
        occlusion_relation="主要主体、关键资料和人物面部保持清晰",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause=clause,
        metadata=metadata,
    )


def choose_mandatory_support_anchor(base_visual_brief: BaseVisualBrief, *, duty: IPDutyPlan) -> tuple[str, str]:
    """Legacy-only carrier selection.

    Content-bound v2 never calls this helper.  It remains for explicit legacy
    policies so old projects can be replayed with the former semantics.
    """

    existing = [str(item or "").strip() for item in base_visual_brief.anchor_affordances if str(item or "").strip()]
    safe_existing = [item for item in existing if not _unsafe_support(item)]
    if safe_existing:
        return safe_existing[0], "existing"

    text = " ".join(
        [
            base_visual_brief.base_image_prompt,
            base_visual_brief.core_message,
            base_visual_brief.visual_moment,
            base_visual_brief.setting,
            " ".join(base_visual_brief.key_props_symbols),
            " ".join(base_visual_brief.main_subjects),
            duty.duty_goal,
        ]
    )
    if any(token in text for token in ("书", "章节", "阅读", "作者", "书籍")):
        return "打开的书页边栏或纸质书签", "legacy_injected_book_carrier"
    if any(token in text for token in ("证据", "复盘", "时间线", "调查", "案例", "YouTube", "视频", "事件")):
        return "研究桌上的纸质时间线卡片或资料夹标签", "legacy_injected_evidence_carrier"
    if any(token in text for token in ("流程", "机制", "工作流", "方法", "AI", "工具", "系统")):
        return "桌面上的纸质流程卡片或讲解板图例栏", "legacy_injected_process_carrier"
    if any(token in text for token in ("情绪", "压力", "拖延", "焦虑", "迷茫", "痛苦")):
        return "前景桌面上的纸质情绪卡片或任务卡", "legacy_injected_emotional_carrier"
    if any(token in text for token in ("对比", "冲突", "选择", "判断", "误区")):
        return "左右对比板中间的纸质判断卡", "legacy_injected_contrast_carrier"
    return "前景桌面上的纸质分析卡片", "legacy_injected_default_carrier"


def _carrier_for_mechanism(mechanism: IPParticipationMechanism | str) -> AnchorCarrierType:
    mechanism = IPParticipationMechanism.from_value(mechanism)
    if mechanism is IPParticipationMechanism.SYSTEM_COMPONENT:
        return AnchorCarrierType.CONTENT_BOUND_SYSTEM_COMPONENT
    if mechanism is IPParticipationMechanism.SCALE_REFERENCE:
        return AnchorCarrierType.CONTENT_BOUND_SCALE_REFERENCE
    if mechanism in {IPParticipationMechanism.EXPLANATION_DIRECTOR, IPParticipationMechanism.OBSERVATION_GATEWAY}:
        return AnchorCarrierType.CONTENT_BOUND_EXPLANATION_DIRECTOR
    return AnchorCarrierType.CONTENT_BOUND_IP_ACTOR


def _visual_payload_from_brief(base_visual_brief: BaseVisualBrief) -> dict[str, Any]:
    metadata = dict(base_visual_brief.metadata or {})
    frame_plan = _mapping_from(metadata.get("visual_story_frame_plan"))
    return {
        **frame_plan,
        "frame_id": base_visual_brief.frame_id,
        "local_claim": frame_plan.get("local_claim") or base_visual_brief.core_message,
        "visual_task": frame_plan.get("visual_task") or base_visual_brief.visual_moment or base_visual_brief.base_image_prompt,
        "visual_logic": frame_plan.get("visual_logic") or base_visual_brief.spatial_layout,
        "cognitive_anchor": frame_plan.get("cognitive_anchor") or metadata.get("cognitive_anchor") or "",
        "physical_metaphor": frame_plan.get("physical_metaphor") or metadata.get("physical_metaphor") or "",
        "scene_arena": frame_plan.get("scene_arena") or base_visual_brief.setting or "中性解释空间",
        "ip_action_affordance": frame_plan.get("ip_action_affordance") or "; ".join(base_visual_brief.anchor_affordances),
    }


def _ip_profile_payload(anchor_profile: IPProfile) -> dict[str, Any]:
    return {
        "canonical_identity_name": getattr(anchor_profile, "canonical_identity_name", ""),
        "fixed_identity_clause": getattr(anchor_profile, "fixed_identity_clause", ""),
        "visual_summary": getattr(anchor_profile, "visual_summary", ""),
        "minimal_traits": list(getattr(anchor_profile, "minimal_traits", ()) or ()),
    }


def _mapping_from(value: Any) -> dict[str, Any]:
    if isinstance(value, IPDutyPlan):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _resolve_duty_plan(duty_payload: Mapping[str, Any] | IPDutyPlan | None, *, frame_id: str, base_visual_brief: BaseVisualBrief) -> IPDutyPlan:
    if isinstance(duty_payload, IPDutyPlan):
        return duty_payload
    if isinstance(duty_payload, Mapping) and duty_payload:
        return IPDutyPlan.from_mapping(duty_payload, frame_id=frame_id)

    metadata = dict(base_visual_brief.metadata or {})
    for key in ("visual_story_ip_fusion_plan", "ip_duty_plan"):
        value = metadata.get(key)
        if isinstance(value, Mapping) and value:
            return IPDutyPlan.from_mapping(value, frame_id=frame_id)

    selected_route = metadata.get("selected_visual_route")
    route_type = ""
    legacy_role = ""
    if isinstance(selected_route, Mapping):
        route_type = str(selected_route.get("route_type") or selected_route.get("route_id") or "")
        legacy_role = str(selected_route.get("recommended_ip_role") or selected_route.get("ip_role") or "")

    return build_default_ip_duty_plan(
        frame_id=frame_id,
        route_type=route_type,
        legacy_role=legacy_role,
        local_claim=base_visual_brief.core_message,
        visual_task=base_visual_brief.visual_moment or base_visual_brief.base_image_prompt,
        risk_text=_risk_text(base_visual_brief),
    )


def _risk_text(base_visual_brief: BaseVisualBrief) -> str:
    metadata = dict(base_visual_brief.metadata or {})
    parts: list[str] = [
        base_visual_brief.base_image_prompt,
        base_visual_brief.core_message,
        base_visual_brief.visual_moment,
        base_visual_brief.setting,
        " ".join(base_visual_brief.main_subjects),
        " ".join(base_visual_brief.subject_identity_anchors),
        " ".join(base_visual_brief.readability_constraints),
    ]
    for key in ("visual_story_frame_plan", "visual_story_ip_fusion_plan", "source_text"):
        value = metadata.get(key)
        if value:
            parts.append(str(value))
    return " ".join(str(part or "") for part in parts)


def _background_signature_clause(*, identity: str, support_anchor: str) -> str:
    return (
        f"{support_anchor}的真实材质表面带有一枚小面积但清晰可辨的{identity}，"
        "以纸面印刷、浅压印或细小刻写的方式贴合材质纹理，视觉重量低于当前帧主体。"
    )


def _small_prop_clause(*, identity: str, duty: IPDutyPlan, support_anchor: str) -> str:
    return (
        f"{support_anchor}上放着一个小型{identity}实体小物件，"
        f"它靠近{duty.interaction_target}并承担“{duty.duty_goal}”的画面职责，"
        "与支撑面自然接触，尺寸低于主体。"
    )


def _functional_actor_clause(*, identity: str, duty: IPDutyPlan, support_anchor: str) -> str:
    action = _natural_action(duty)
    return (
        f"一个小型{identity}在{support_anchor}旁执行{action}，"
        f"身体或爪子与{duty.interaction_target}发生清晰接触，"
        f"用于表达“{duty.duty_goal}”，同时服从当前帧主体和构图。"
    )


def _natural_action(duty: IPDutyPlan) -> str:
    verb = str(duty.action_verb or "").strip()
    target = str(duty.interaction_target or "").strip()
    if not verb:
        return f"与{target}互动"
    if any(token in verb for token in ("整理", "标记", "指向", "操作", "引导", "守", "修", "称", "观察", "连接", "承载", "推", "拉")):
        return f"“{verb}{target}”的动作"
    return f"与{target}相关的{verb}动作"


def _embedded_carrier_type(support_anchor: str) -> AnchorCarrierType:
    if any(token in support_anchor for token in ("书页", "书签", "纸", "卡片", "资料夹", "标签")):
        return AnchorCarrierType.BOOKPLATE_OR_STAMP
    if any(token in support_anchor for token in ("木", "桌", "相框", "牌")):
        return AnchorCarrierType.ENGRAVED_MARK
    return AnchorCarrierType.SURFACE_GRAPHIC


def _anchor_function_for_duty(duty: IPDutyPreset) -> AnchorFunction:
    if duty in {IPDutyPreset.POINTER_ANNOTATOR, IPDutyPreset.HOST_EXPLAINER, IPDutyPreset.GUIDE_EXPLAINER}:
        return AnchorFunction.EXPLAINER_POINTER
    if duty in _ACTION_BASED_DUTIES:
        return AnchorFunction.CO_PRESENT_SUPPORT
    return AnchorFunction.MATERIAL_SIGNATURE


def _unsafe_support(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("画面", "画布", "角落", "corner", "canvas", "overlay"))


__all__ = [
    "MandatoryIPParticipationError",
    "choose_mandatory_support_anchor",
    "compile_mandatory_ip_participation_plan",
]
