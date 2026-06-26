from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pixelle_video.models.visual_anchor_planning import AnchorCarrierType, VisualAnchorPlacementPlan
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_anchor_policy import is_content_bound_carrier_type, sanitize_provider_anchor_clause
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


_IDENTITY_NOUN_HINTS = (
    "小黑",
    "斑点狗",
    "狗",
    "猫",
    "兔",
    "鸟",
    "雀",
    "人物",
    "角色",
    "机器人",
    "小人",
)
_TRAIT_ONLY_HINTS = ("墨镜", "领结", "帽", "衣", "披风", "眼镜")
_IDENTITY_SUFFIXES = (
    "轮廓",
    "形象",
    "图案",
    "纹样",
    "标志",
    "角色",
    "小人",
    "机器人",
)
_LEGACY_DECORATIVE_CARRIER_TYPES = {
    AnchorCarrierType.BOOKPLATE_OR_STAMP.value,
    AnchorCarrierType.PRINTED_MARK.value,
    AnchorCarrierType.EMBOSSED_MARK.value,
    AnchorCarrierType.ENGRAVED_MARK.value,
    AnchorCarrierType.SURFACE_GRAPHIC.value,
    AnchorCarrierType.DECORATIVE_OBJECT.value,
    AnchorCarrierType.WEARABLE_SYMBOL.value,
    AnchorCarrierType.SMALL_SUPPORTING_PROP.value,
}


def render_visual_signature_candidate_clause(
    *,
    carrier_type: Any,
    support_anchor: str,
    contact_relation: str = "",
    placement: str = "",
    source_text: str = "",
    identity_kernel: Sequence[Any] | None = None,
    policy: VisualSignaturePolicy | None = None,
) -> str:
    policy = policy or load_visual_signature_policy()
    carrier_value = str(getattr(carrier_type, "value", carrier_type) or "").strip()
    support = _clean_fragment(support_anchor)
    contact = _clean_fragment(contact_relation)
    placement_text = _clean_fragment(placement)
    combined = " ".join([support, contact, placement_text, source_text])
    if not support:
        return ""

    if policy.is_content_bound_mandatory:
        if carrier_value in _LEGACY_DECORATIVE_CARRIER_TYPES or not is_content_bound_carrier_type(carrier_value):
            return ""
        if policy.contains_forbidden_overlay_text(combined):
            return ""
        identity = _identity_kernel(source_text, identity_kernel=identity_kernel, policy=policy)
        if not identity:
            return ""
        clause = _content_bound_clause(source_text, identity=identity, policy=policy)
        if policy.contains_forbidden_final_prompt_text(clause):
            return ""
        return clause

    if policy.contains_forbidden_final_prompt_text(combined):
        return ""

    passthrough = _source_text_as_natural_clause(source_text, support=support, policy=policy, carrier_type=carrier_value)
    if passthrough:
        return passthrough

    identity = _identity_kernel(source_text, identity_kernel=identity_kernel, policy=policy)
    if not identity:
        return ""
    if carrier_value in {
        AnchorCarrierType.BOOKPLATE_OR_STAMP.value,
        AnchorCarrierType.PRINTED_MARK.value,
        AnchorCarrierType.EMBOSSED_MARK.value,
    }:
        clause = (
            f"{support}的材质表面有一枚小面积但清晰可辨的{identity}藏书票或浅压印图案，"
            "沿原有纸面或封面纹理呈现，视觉重量低于主体但身份特征可读。"
        )
    elif carrier_value == AnchorCarrierType.ENGRAVED_MARK.value:
        clause = (
            f"{support}的实体表面带有一处小面积但清晰可辨的{identity}雕刻纹样，"
            "顺着原有材质纹理呈现，视觉重量低于主体但身份特征可读。"
        )
    elif carrier_value == AnchorCarrierType.SURFACE_GRAPHIC.value:
        clause = (
            f"{support}上的原有图案中融入一枚小面积但清晰可辨的{identity}装饰纹样，"
            "作为环境表面图形的一部分，身份特征可读但不抢占主体。"
        )
    elif carrier_value == AnchorCarrierType.WEARABLE_SYMBOL.value:
        clause = (
            f"{support}的布料或配饰表面带有一处小面积但清晰可辨的{identity}刺绣纹样，"
            "贴合材质并服务整体造型。"
        )
    elif carrier_value in {
        AnchorCarrierType.DECORATIVE_OBJECT.value,
        AnchorCarrierType.SMALL_SUPPORTING_PROP.value,
    }:
        clause = (
            f"{support}上放置一个小面积但清晰可辨的{identity}小物件，"
            "与支撑面自然接触，尺寸和明度都服从主要画面主体。"
        )
    elif carrier_value == AnchorCarrierType.MINOR_SUPPORTING_CHARACTER.value:
        clause = (
            f"{support}附近有一个小面积但清晰可辨的{identity}小型陪衬形象，"
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
        identity_kernel=_metadata_identity_kernel(visual_anchor_plan.metadata),
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
    if policy.is_content_bound_mandatory:
        if policy.contains_forbidden_overlay_text(combined):
            return ""
        if policy.contains_forbidden_final_prompt_text(clause):
            return ""
    elif policy.contains_forbidden_final_prompt_text(combined):
        return ""
    return clause


def _content_bound_clause(source_text: str, *, identity: str, policy: VisualSignaturePolicy) -> str:
    text = _clean_fragment(source_text)
    if not text:
        return ""
    clause = text.replace("configured recurring identity", identity)
    clause = clause.replace("configured recurring IP", identity).replace("recurring IP", "recurring character")
    return _final_clean(sanitize_provider_anchor_clause(clause), policy=policy, allow_content_bound=True)


def _source_text_as_natural_clause(source_text: str, *, support: str, policy: VisualSignaturePolicy, carrier_type: str = "") -> str:
    text = _clean_fragment(source_text)
    if not text or len(text) < 8:
        return ""
    if policy.contains_forbidden_final_prompt_text(text) and not (policy.is_content_bound_mandatory and is_content_bound_carrier_type(carrier_type)):
        return ""
    if policy.is_content_bound_mandatory and is_content_bound_carrier_type(carrier_type):
        return _final_clean(text, policy=policy, allow_content_bound=True)
    if support not in text and not any(token in text for token in ("纸", "卡片", "书", "桌", "墙", "板", "资料夹", "路径", "按钮", "时间线")):
        return ""
    if not any(token in text for token in ("印", "压", "刻", "画", "站", "接触", "放在", "整理", "指向", "拉", "推", "守", "连接", "观察", "称量", "修复")):
        return ""
    return _final_clean(text, policy=policy)


def _metadata_identity_kernel(metadata: Any) -> tuple[str, ...]:
    if not isinstance(metadata, dict):
        return ()
    raw = metadata.get("visual_identity_kernel") or metadata.get("identity_kernel")
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Sequence):
        return tuple(str(item or "").strip() for item in raw if str(item or "").strip())
    return ()


def _identity_kernel(
    text: str,
    *,
    identity_kernel: Sequence[Any] | None = None,
    policy: VisualSignaturePolicy | None = None,
) -> str:
    policy = policy or load_visual_signature_policy()
    candidate = _select_identity_candidate(identity_kernel)
    if not candidate:
        candidate = _extract_identity_from_text(text)
    label = _identity_label(candidate, policy=policy)
    return label


def _select_identity_candidate(values: Sequence[Any] | None) -> str:
    candidates = [_clean_identity_text(value) for value in values or ()]
    candidates = [value for value in candidates if value]
    if not candidates:
        return ""

    def score(value: str) -> tuple[int, int]:
        has_noun = any(token in value for token in _IDENTITY_NOUN_HINTS)
        trait_only = any(token in value for token in _TRAIT_ONLY_HINTS) and not has_noun
        return ((100 if has_noun else 0) - (30 if trait_only else 0), len(value))

    return max(candidates, key=score)


def _extract_identity_from_text(text: str) -> str:
    value = str(text or "")
    if "蓝领结白兔" in value:
        return "蓝领结白兔轮廓"
    phrase_patterns = (
        r"(?:带着|戴着|穿着|拿着)[^，。；,.;]{1,24}的[^，。；,.;]{1,18}(?:狗|猫|兔|鸟|雀|角色|机器人|小人)",
        r"(?:小黑|斑点狗|白兔|麻雀|黑猫|小狗|机器人|小人)",
    )
    for pattern in phrase_patterns:
        match = re.search(pattern, value)
        if match:
            return _clean_identity_text(match.group(0))
    if "斑点狗" in value:
        return "戴黑色墨镜的斑点狗" if "黑色墨镜" in value else "斑点狗"
    if "狗" in value:
        return "戴黑色墨镜的小狗" if "黑色墨镜" in value else "小狗"
    if "猫" in value:
        return "戴黑色墨镜的猫" if "黑色墨镜" in value else "猫"
    if "蓝领结白兔" in value:
        return "蓝领结白兔"
    if "兔" in value and ("蓝" in value or "领结" in value):
        return "蓝领结白兔"
    if "兔" in value:
        return "白兔"
    if "麻雀" in value:
        return "红嘴小麻雀" if "红嘴" in value else "麻雀"
    if "小黑" in value:
        return "小黑"
    return ""


def _identity_label(identity: str, *, policy: VisualSignaturePolicy) -> str:
    cleaned = _clean_identity_text(identity)
    if not cleaned:
        return "" if policy.require_concrete_identity else "频道识别轮廓"
    if cleaned.endswith(_IDENTITY_SUFFIXES):
        return cleaned
    if any(token in cleaned for token in _IDENTITY_NOUN_HINTS):
        return f"{cleaned}轮廓"
    return cleaned


def _clean_identity_text(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip(" ，,。;；")
    text = text.replace("Fixed IP identity:", "")
    text = text.replace("fixed identity:", "")
    text = text.replace("required identity traits:", "")
    text = text.replace("required traits:", "")
    return " ".join(text.split()).strip(" ，,。;；")


def _clean_fragment(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    cleaned = cleaned.replace("视觉锚点", "").replace("visual anchor", "")
    cleaned = cleaned.replace("IP角色", "").replace("IP", "")
    return " ".join(cleaned.split()).strip(" ，,。;；")


def _final_clean(text: str, *, policy: VisualSignaturePolicy, allow_content_bound: bool = False) -> str:
    cleaned = _clean_fragment(text)
    if policy.contains_forbidden_overlay_text(cleaned):
        return ""
    if policy.contains_forbidden_final_prompt_text(cleaned) and not allow_content_bound:
        return ""
    if allow_content_bound and policy.contains_forbidden_final_prompt_text(cleaned):
        return ""
    return cleaned


__all__ = ["render_visual_anchor_plan_clause", "render_visual_signature_candidate_clause"]
