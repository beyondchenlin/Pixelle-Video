from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_prompt_planning import IPFrameAdaptationPackage, IPRoleSlot
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)


@dataclass(frozen=True)
class VisualAnchorPlacementPlanner:
    """Plan recurring visual anchors using a prominence budget instead of numeric size ratios."""

    def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        anchor_profile: IPProfile | None,
        base_packages: Sequence[IPFrameAdaptationPackage] = (),
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        frame_plans: Sequence[Any] = (),
    ) -> tuple[VisualAnchorPlacementPlan, ...]:
        if anchor_profile is None:
            return tuple(_suppressed_plan(brief.frame_id, reason="no anchor profile") for brief in base_visual_briefs)
        return tuple(
            self.plan_frame(
                base_visual_brief=brief,
                anchor_profile=anchor_profile,
                base_package=base_packages[index] if index < len(base_packages) else None,
                frame_context=frame_contexts[index] if index < len(frame_contexts) else {},
                frame_plan=frame_plans[index] if index < len(frame_plans) else None,
            )
            for index, brief in enumerate(base_visual_briefs)
        )

    def plan_frame(
        self,
        *,
        base_visual_brief: BaseVisualBrief,
        anchor_profile: IPProfile,
        base_package: IPFrameAdaptationPackage | None = None,
        frame_context: Mapping[str, Any] | None = None,
        frame_plan: Any = None,
    ) -> VisualAnchorPlacementPlan:
        if base_package is not None and base_package.role_slot is IPRoleSlot.ABSENT:
            return _suppressed_plan(base_visual_brief.frame_id, reason="base package absent")
        anchor_identity = _anchor_identity(anchor_profile)
        prominence = _choose_anchor_prominence(base_visual_brief=base_visual_brief, base_package=base_package)
        anchor_function, carrier_type = _function_and_carrier_for_prominence(prominence, base_visual_brief=base_visual_brief)
        if prominence is AnchorProminence.HIDDEN or anchor_function is AnchorFunction.SUPPRESSED:
            return _suppressed_plan(base_visual_brief.frame_id, reason="hidden by prominence budget")
        placement_zone = _choose_placement_zone(base_visual_brief, prominence=prominence)
        support_anchor = _choose_support_anchor(base_visual_brief, prominence=prominence)
        visual_weight_clause = _visual_weight_clause(prominence)
        depth_layer = _choose_depth_layer(placement_zone, prominence=prominence)
        interaction_target = _choose_interaction_target(base_visual_brief)
        contact_relation = _contact_relation_for_support(support_anchor, prominence=prominence)
        occlusion_relation = _occlusion_relation(base_visual_brief, prominence=prominence)
        style_relation = _choose_style_relation(anchor_profile, prominence)
        image_prompt_clause = _build_image_prompt_clause(
            anchor_identity=anchor_identity,
            anchor_prominence=prominence,
            carrier_type=carrier_type,
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            visual_weight_clause=visual_weight_clause,
            depth_layer=depth_layer,
            contact_relation=contact_relation,
            interaction_target=interaction_target,
            occlusion_relation=occlusion_relation,
            style_relation=style_relation,
        )
        return VisualAnchorPlacementPlan(
            frame_id=base_visual_brief.frame_id,
            anchor_function=anchor_function,
            anchor_carrier_type=carrier_type,
            anchor_prominence=prominence,
            visual_weight_clause=visual_weight_clause,
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            scale_ratio=visual_weight_clause,
            depth_layer=depth_layer,
            contact_relation=contact_relation,
            interaction_target=interaction_target,
            occlusion_relation=occlusion_relation,
            style_relation=style_relation,
            image_prompt_clause=image_prompt_clause,
            metadata={"planner": "VisualAnchorPlacementPlanner", "anchor_profile_id": anchor_profile.ip_profile_id},
        )


def _suppressed_plan(frame_id: str, *, reason: str) -> VisualAnchorPlacementPlan:
    return VisualAnchorPlacementPlan(
        frame_id=frame_id,
        anchor_function=AnchorFunction.SUPPRESSED,
        anchor_carrier_type=AnchorCarrierType.SUPPRESSED,
        anchor_prominence=AnchorProminence.HIDDEN,
        visual_weight_clause="",
        placement_zone="",
        support_anchor="",
        scale_ratio="",
        depth_layer="",
        contact_relation="",
        interaction_target="",
        occlusion_relation="",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="",
        metadata={"reason": reason},
    )


def _choose_anchor_prominence(
    *,
    base_visual_brief: BaseVisualBrief,
    base_package: IPFrameAdaptationPackage | None,
) -> AnchorProminence:
    text = " ".join(
        [
            base_visual_brief.base_image_prompt,
            base_visual_brief.camera_plan,
            base_visual_brief.composition_rules,
            base_visual_brief.core_message,
            " ".join(base_visual_brief.main_subjects),
        ]
    )
    has_named_subject = bool(base_visual_brief.main_subjects)
    if base_package is not None and base_package.role_slot is IPRoleSlot.PROTAGONIST and not has_named_subject:
        return AnchorProminence.PRIMARY_CARRIER

    if any(word in text for word in ("严肃", "纪实", "宗教", "真实人物", "悼念", "灾难")):
        return AnchorProminence.EMBEDDED_MARK

    if any(word in text for word in ("特写", "近景", "细节", "书页", "卡片", "徽章", "图表")):
        return AnchorProminence.EMBEDDED_MARK

    if has_named_subject and len(base_visual_brief.main_subjects) >= 2:
        return AnchorProminence.TINY_PROP

    if any(word in text for word in ("课堂", "教室", "讲解板", "电视", "孩子", "观看", "学习")):
        return AnchorProminence.TINY_PROP

    if any(word in text for word in ("城市", "街道", "战斗", "对峙", "人群", "广场", "高楼")):
        return AnchorProminence.MICRO_CAMEO

    if not has_named_subject and any(word in text for word in ("勇气", "选择", "成长", "孤独", "责任", "梦想")):
        return AnchorProminence.PRIMARY_CARRIER

    return AnchorProminence.TINY_PROP


def _function_and_carrier_for_prominence(
    prominence: AnchorProminence,
    *,
    base_visual_brief: BaseVisualBrief,
) -> tuple[AnchorFunction, AnchorCarrierType]:
    if prominence is AnchorProminence.HIDDEN:
        return AnchorFunction.SUPPRESSED, AnchorCarrierType.SUPPRESSED
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return AnchorFunction.EMBEDDED_MARK, AnchorCarrierType.EMBEDDED_MARK
    if prominence is AnchorProminence.TINY_PROP:
        return AnchorFunction.ENVIRONMENTAL_SIGNATURE, AnchorCarrierType.FIGURINE
    if prominence is AnchorProminence.MICRO_CAMEO:
        return AnchorFunction.MICRO_CAMEO, AnchorCarrierType.BACKGROUND_EXTRA
    if prominence is AnchorProminence.SMALL_SIDE_CHARACTER:
        return AnchorFunction.CO_PRESENT_SUPPORT, AnchorCarrierType.LIVING_CHARACTER
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return AnchorFunction.PRIMARY_CARRIER, AnchorCarrierType.LIVING_CHARACTER
    return AnchorFunction.ENVIRONMENTAL_SIGNATURE, AnchorCarrierType.FIGURINE


def _anchor_identity(anchor_profile: IPProfile) -> str:
    raw_parts = [
        anchor_profile.name,
        anchor_profile.visual_summary,
        *anchor_profile.identity_lock,
        *anchor_profile.minimal_traits,
        *anchor_profile.identity_anchors,
    ]
    raw = "，".join(str(part or "").strip() for part in raw_parts if str(part or "").strip())

    if "兔" in raw:
        traits = ["白色科技兔子" if "科技" in raw else "白色卡通兔子"]
        if "白" in raw:
            traits.append("白色身体")
        if "蓝色领结" in raw or "领结" in raw:
            traits.append("蓝色领结")
        if "长耳" in raw:
            traits.append("长耳朵")
        if "粉" in raw and "耳" in raw:
            traits.append("浅粉色耳朵内侧")
        if "圆润" in raw or "圆脸" in raw:
            traits.append("圆润脸型")
        return "，".join(_dedupe(traits))

    if "麻雀" in raw:
        traits = ["小麻雀"]
        if "红嘴" in raw:
            traits.append("红嘴")
        return "，".join(_dedupe(traits))

    return "，".join(_dedupe(str(part).strip() for part in raw_parts if str(part or "").strip())) or anchor_profile.name


def _visual_weight_clause(prominence: AnchorProminence) -> str:
    labels = {
        AnchorProminence.HIDDEN: "",
        AnchorProminence.EMBEDDED_MARK: "像角落标签一样小，只作为识别细节",
        AnchorProminence.TINY_PROP: "小摆件大小，观众仔细看才会注意到",
        AnchorProminence.MICRO_CAMEO: "画面边缘的小细节，远小于主角，不吸引第一眼注意",
        AnchorProminence.SMALL_SIDE_CHARACTER: "明显小于主角，存在感低于主要配角",
        AnchorProminence.PRIMARY_CARRIER: "作为本帧主要视觉载体",
    }
    return labels[prominence]


def _choose_placement_zone(brief: BaseVisualBrief, *, prominence: AnchorProminence) -> str:
    text = brief.base_image_prompt
    if prominence is AnchorProminence.EMBEDDED_MARK:
        if any(word in text for word in ("书页", "卡片")):
            return "书页或卡片右下角"
        if any(word in text for word in ("屏幕", "电视")):
            return "屏幕边角或电视柜小标签位置"
        if any(word in text for word in ("讲解板", "黑板", "图表")):
            return "讲解板或图表边角"
        return "画面边角的标记位置"
    if prominence is AnchorProminence.TINY_PROP:
        return "前景侧边或已有道具旁"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return "画面边缘、人群边缘或窗边背景处"
    if prominence is AnchorProminence.SMALL_SIDE_CHARACTER:
        return "主体旁边但不遮挡主体的低位区域"
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return "画面视觉中心"
    return "画面边缘"


def _choose_support_anchor(brief: BaseVisualBrief, *, prominence: AnchorProminence) -> str:
    text = brief.base_image_prompt
    if prominence is AnchorProminence.EMBEDDED_MARK:
        if "书页" in text:
            return "书页角落"
        if "屏幕" in text or "电视" in text:
            return "屏幕边框或电视柜角落"
        if "讲解板" in text or "黑板" in text:
            return "讲解板边框"
        return "画面角落的已有平面"
    candidates = (
        ("电视", "电视柜边缘"),
        ("书页", "书页角落"),
        ("讲解板", "讲解板下方边缘"),
        ("黑板", "黑板下方边缘"),
        ("城市", "街道路面边缘"),
        ("街道", "街道路面边缘"),
        ("楼", "建筑边缘或窗边"),
        ("桌", "桌面边缘或桌脚旁"),
        ("人群", "人群边缘"),
        ("车", "车辆旁边"),
        ("海", "岸边或礁石旁"),
        ("森林", "树根旁或草丛边缘"),
    )
    for keyword, support in candidates:
        if keyword in text:
            return support
    return "前景已有物体或地面边缘"


def _choose_depth_layer(placement_zone: str, *, prominence: AnchorProminence) -> str:
    if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO}:
        return "画面边缘层"
    if "前景" in placement_zone:
        return "前景低位"
    return "中景边缘"


def _choose_interaction_target(brief: BaseVisualBrief) -> str:
    if brief.key_props_symbols:
        return brief.key_props_symbols[0]
    if brief.main_subjects:
        return "、".join(brief.main_subjects[:2])
    return "最近的场景道具"


def _contact_relation_for_support(support_anchor: str, *, prominence: AnchorProminence) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return "贴附在已有平面或边框上"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return "与边缘环境相邻，形成背景小细节"
    if any(word in support_anchor for word in ("地面", "路面", "桌面", "边缘", "旁")):
        return "与支撑面有可见接触或贴近关系"
    return "与已有物体有接触、遮挡或邻接关系"


def _occlusion_relation(brief: BaseVisualBrief, *, prominence: AnchorProminence) -> str:
    if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.TINY_PROP, AnchorProminence.MICRO_CAMEO}:
        return "不参与主要叙事，不遮挡任何主体脸部、标志或关键动作"
    if len(brief.main_subjects) >= 2:
        return "不遮挡任何主要主体的脸部、标志、轮廓或关键动作"
    return "不遮挡主体面部、关键标志或画面阅读重点"


def _choose_style_relation(anchor_profile: IPProfile, prominence: AnchorProminence) -> AnchorStyleRelation:
    if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO}:
        return AnchorStyleRelation.BLENDED
    if anchor_profile.style_hint and any(word in anchor_profile.style_hint.lower() for word in ("3d", "realistic", "真人", "独立")):
        return AnchorStyleRelation.ACCENTED
    return AnchorStyleRelation.ACCENTED


def _build_image_prompt_clause(
    *,
    anchor_identity: str,
    anchor_prominence: AnchorProminence,
    carrier_type: AnchorCarrierType,
    placement_zone: str,
    support_anchor: str,
    visual_weight_clause: str,
    depth_layer: str,
    contact_relation: str,
    interaction_target: str,
    occlusion_relation: str,
    style_relation: AnchorStyleRelation,
) -> str:
    if anchor_prominence is AnchorProminence.EMBEDDED_MARK:
        return f"{support_anchor}有一个很小的{anchor_identity}徽记，{visual_weight_clause}，{contact_relation}，{occlusion_relation}。"
    if anchor_prominence is AnchorProminence.TINY_PROP:
        return f"{placement_zone}的{support_anchor}放着一个很小的{anchor_identity}摆件，{visual_weight_clause}，{contact_relation}，{occlusion_relation}。"
    if anchor_prominence is AnchorProminence.MICRO_CAMEO:
        return f"{placement_zone}有一个很小的{anchor_identity}轮廓，{visual_weight_clause}，{contact_relation}，{occlusion_relation}。"
    if anchor_prominence is AnchorProminence.SMALL_SIDE_CHARACTER:
        return f"一只小型{anchor_identity}位于{placement_zone}，依托{support_anchor}，{visual_weight_clause}，{contact_relation}，面向或关联{interaction_target}，{occlusion_relation}。"
    if anchor_prominence is AnchorProminence.PRIMARY_CARRIER:
        return f"一只{anchor_identity}位于{placement_zone}，{visual_weight_clause}，作为画面核心承载主题。"
    return ""


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


__all__ = ["VisualAnchorPlacementPlanner"]
