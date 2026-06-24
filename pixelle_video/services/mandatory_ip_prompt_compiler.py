from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
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
    """Compile a mandatory, scene-bound IP plan without relying on LLM phrasing.

    This is the repair/fallback path for V1.0. It never returns a suppressed plan.
    It keeps the IP concrete, injects a small content-compatible carrier when needed,
    and emits natural provider-facing visual language only.
    """

    policy = policy or load_visual_signature_policy()
    identity = anchor_identity_from_profile(anchor_profile)
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
        "compiler": "mandatory_ip_prompt_compiler",
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
        return "打开的书页边栏或纸质书签", "injected_book_carrier"
    if any(token in text for token in ("证据", "复盘", "时间线", "调查", "案例", "YouTube", "视频", "事件")):
        return "研究桌上的纸质时间线卡片或资料夹标签", "injected_evidence_carrier"
    if any(token in text for token in ("流程", "机制", "工作流", "方法", "AI", "工具", "系统")):
        return "桌面上的纸质流程卡片或讲解板图例栏", "injected_process_carrier"
    if any(token in text for token in ("情绪", "压力", "拖延", "焦虑", "迷茫", "痛苦")):
        return "前景桌面上的纸质情绪卡片或任务卡", "injected_emotional_carrier"
    if any(token in text for token in ("对比", "冲突", "选择", "判断", "误区")):
        return "左右对比板中间的纸质判断卡", "injected_contrast_carrier"
    return "前景桌面上的纸质分析卡片", "injected_default_carrier"


def _resolve_duty_plan(
    duty_payload: Mapping[str, Any] | IPDutyPlan | None,
    *,
    frame_id: str,
    base_visual_brief: BaseVisualBrief,
) -> IPDutyPlan:
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
