from __future__ import annotations

from typing import Any

from pixelle_video.models.visual_anchor_planning import AnchorCarrierType, VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


def render_visual_signature_candidate_clause(
    *,
    carrier_type: Any,
    support_anchor: str,
    contact_relation: str = "",
    placement: str = "",
    source_text: str = "",
    policy: VisualSignaturePolicy | None = None,
) -> str:
    policy = policy or load_visual_signature_policy()
    carrier_value = str(getattr(carrier_type, "value", carrier_type) or "").strip()
    support = _clean_fragment(support_anchor)
    contact = _clean_fragment(contact_relation)
    placement_text = _clean_fragment(placement)
    combined = " ".join([support, contact, placement_text, source_text])
    if not support or policy.contains_forbidden_final_prompt_text(combined):
        return ""

    identity = _identity_kernel(source_text)
    if carrier_value in {
        AnchorCarrierType.BOOKPLATE_OR_STAMP.value,
        AnchorCarrierType.PRINTED_MARK.value,
        AnchorCarrierType.EMBOSSED_MARK.value,
    }:
        clause = (
            f"{support}的材质表面融入一枚低对比的{identity}浅压印纹章，"
            "沿原有纸面或封面纹理呈现，作为安静的场景细节。"
        )
    elif carrier_value == AnchorCarrierType.ENGRAVED_MARK.value:
        clause = (
            f"{support}的实体表面带有一处细浅的{identity}雕刻纹样，"
            "顺着原有材质纹理呈现，视觉重量低于主体。"
        )
    elif carrier_value == AnchorCarrierType.SURFACE_GRAPHIC.value:
        clause = (
            f"{support}上的原有图案中融入一枚低对比的{identity}装饰纹样，"
            "作为环境表面图形的一部分。"
        )
    elif carrier_value == AnchorCarrierType.WEARABLE_SYMBOL.value:
        clause = (
            f"{support}的布料或配饰表面带有一处细小的{identity}刺绣纹样，"
            "贴合材质并服务整体造型。"
        )
    elif carrier_value in {
        AnchorCarrierType.DECORATIVE_OBJECT.value,
        AnchorCarrierType.SMALL_SUPPORTING_PROP.value,
    }:
        clause = (
            f"{support}上放置一个低存在感的{identity}小物件，"
            "与支撑面自然接触，尺寸和明度都服从主要画面主体。"
        )
    elif carrier_value == AnchorCarrierType.MINOR_SUPPORTING_CHARACTER.value:
        clause = (
            f"{support}附近有一个低存在感的{identity}小型陪衬形象，"
            "与场景地面和光线一致，只承担系列识别细节。"
        )
    else:
        return ""

    return _final_clean(clause, policy=policy)


def render_visual_anchor_plan_clause(
    visual_anchor_plan: VisualAnchorPlacementPlan | None,
    *,
    policy: VisualSignaturePolicy | None = None,
) -> str:
    policy = policy or load_visual_signature_policy()
    if not visual_anchor_plan or not visual_anchor_plan.visible:
        return ""
    clause = render_visual_signature_candidate_clause(
        carrier_type=visual_anchor_plan.anchor_carrier_type,
        support_anchor=visual_anchor_plan.support_anchor,
        contact_relation=visual_anchor_plan.contact_relation,
        placement=visual_anchor_plan.placement_zone,
        source_text=visual_anchor_plan.image_prompt_clause,
        policy=policy,
    )
    if not clause:
        return ""
    combined = " ".join(
        [
            clause,
            visual_anchor_plan.support_anchor,
            visual_anchor_plan.placement_zone,
            visual_anchor_plan.contact_relation,
        ]
    )
    if policy.contains_forbidden_final_prompt_text(combined):
        return ""
    return clause


def _identity_kernel(text: str) -> str:
    value = str(text or "")
    if "蓝领结白兔" in value:
        return "蓝领结白兔轮廓"
    if "兔" in value and ("蓝" in value or "领结" in value):
        return "蓝领结白兔轮廓"
    if "兔" in value:
        return "白兔轮廓"
    if "麻雀" in value:
        return "红嘴小麻雀轮廓"
    return "频道识别轮廓"


def _clean_fragment(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    cleaned = cleaned.replace("视觉锚点", "").replace("visual anchor", "")
    cleaned = cleaned.replace("IP角色", "").replace("IP", "")
    return " ".join(cleaned.split()).strip(" ，,。;；")


def _final_clean(text: str, *, policy: VisualSignaturePolicy) -> str:
    cleaned = _clean_fragment(text)
    if policy.contains_forbidden_final_prompt_text(cleaned):
        return ""
    return cleaned


__all__ = ["render_visual_anchor_plan_clause", "render_visual_signature_candidate_clause"]
