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
    """Deterministic fallback planner using low-prominence anchor defaults."""

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
        anchor_function, carrier_type = _function_and_carrier_for_prominence(prominence)
        if prominence is AnchorProminence.HIDDEN:
            return _suppressed_plan(base_visual_brief.frame_id, reason="hidden by prominence budget")
        placement_zone = _choose_placement_zone(base_visual_brief, prominence=prominence)
        support_anchor = _choose_support_anchor(base_visual_brief, prominence=prominence)
        visual_weight_clause = _visual_weight_clause(prominence)
        image_prompt_clause = _build_image_prompt_clause(
            anchor_identity=anchor_identity,
            prominence=prominence,
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            visual_weight_clause=visual_weight_clause,
            interaction_target=_choose_interaction_target(base_visual_brief),
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
            depth_layer=_depth_layer_for_prominence(prominence),
            contact_relation=_contact_relation_for_prominence(prominence),
            interaction_target=_choose_interaction_target(base_visual_brief),
            occlusion_relation="不遮挡主体脸部、标志、关键动作或阅读重点",
            style_relation=AnchorStyleRelation.BLENDED if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO} else AnchorStyleRelation.ACCENTED,
            image_prompt_clause=image_prompt_clause,
            metadata={"planner": "VisualAnchorPlacementPlanner", "fallback": True},
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
        metadata={"reason": reason, "fallback": True},
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
    if any(word in text for word in ("特写", "近景", "细节", "书页", "卡片", "徽章", "图表", "地图", "迷宫")):
        return AnchorProminence.EMBEDDED_MARK
    if has_named_subject and len(base_visual_brief.main_subjects) >= 2:
        return AnchorProminence.EMBEDDED_MARK
    if any(word in text for word in ("课堂", "教室", "讲解板", "电视", "孩子", "观看", "学习", "桌")):
        return AnchorProminence.TINY_PROP
    if any(word in text for word in ("城市", "街道", "战斗", "对峙", "人群", "广场", "高楼")):
        return AnchorProminence.MICRO_CAMEO
    if not has_named_subject and any(word in text for word in ("勇气", "选择", "成长", "孤独", "责任", "梦想")):
        return AnchorProminence.PRIMARY_CARRIER
    return AnchorProminence.EMBEDDED_MARK


def _function_and_carrier_for_prominence(prominence: AnchorProminence) -> tuple[AnchorFunction, AnchorCarrierType]:
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
    return AnchorFunction.EMBEDDED_MARK, AnchorCarrierType.EMBEDDED_MARK


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
        return "蓝领结白兔剪影"
    if "麻雀" in raw:
        return "红嘴小麻雀剪影"
    return "频道签名小标记"


def _choose_placement_zone(brief: BaseVisualBrief, *, prominence: AnchorProminence) -> str:
    text = brief.base_image_prompt
    if prominence is AnchorProminence.EMBEDDED_MARK:
        if any(word in text for word in ("书页", "卡片", "地图", "迷宫")):
            return "纸面右下角"
        if any(word in text for word in ("屏幕", "电视")):
            return "屏幕边角"
        if any(word in text for word in ("讲解板", "黑板", "图表")):
            return "讲解板边角"
        return "画面角落"
    if prominence is AnchorProminence.TINY_PROP:
        return "前景侧边或已有道具旁"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return "画面边缘、人群边缘或窗边背景处"
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return "画面视觉中心"
    return "画面边缘"


def _choose_support_anchor(brief: BaseVisualBrief, *, prominence: AnchorProminence) -> str:
    text = brief.base_image_prompt
    if prominence is AnchorProminence.EMBEDDED_MARK:
        if "书页" in text:
            return "书页角落"
        if "地图" in text or "迷宫" in text:
            return "地图或迷宫图角落"
        if "屏幕" in text or "电视" in text:
            return "屏幕边框"
        if "讲解板" in text or "黑板" in text:
            return "讲解板边框"
        return "已有平面边角"
    if "桌" in text:
        return "桌面边缘"
    if "电视" in text:
        return "电视柜边缘"
    if "街道" in text or "城市" in text:
        return "街道路面边缘"
    return "已有物体边缘"


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


def _depth_layer_for_prominence(prominence: AnchorProminence) -> str:
    if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO}:
        return "画面边缘层"
    if prominence is AnchorProminence.TINY_PROP:
        return "前景低位"
    return "主体层"


def _contact_relation_for_prominence(prominence: AnchorProminence) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return "贴合已有平面或边框"
    if prominence is AnchorProminence.TINY_PROP:
        return "与已有道具或支撑面接触"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return "与边缘环境相邻"
    return "与场景空间自然接触"


def _choose_interaction_target(brief: BaseVisualBrief) -> str:
    if brief.key_props_symbols:
        return brief.key_props_symbols[0]
    if brief.main_subjects:
        return "、".join(brief.main_subjects[:2])
    return "最近的场景道具"


def _build_image_prompt_clause(
    *,
    anchor_identity: str,
    prominence: AnchorProminence,
    placement_zone: str,
    support_anchor: str,
    visual_weight_clause: str,
    interaction_target: str,
) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return f"{support_anchor}印着一个极小的{anchor_identity}角标，{visual_weight_clause}，贴合画面材质，不影响主体内容。"
    if prominence is AnchorProminence.TINY_PROP:
        return f"{placement_zone}的{support_anchor}放着一个很小的{anchor_identity}摆件，{visual_weight_clause}，不遮挡主体内容。"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return f"{placement_zone}有一个很小的{anchor_identity}轮廓，{visual_weight_clause}，不参与主要叙事。"
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return f"一个{anchor_identity}位于{placement_zone}，作为画面核心承载主题。"
    return ""


__all__ = ["VisualAnchorPlacementPlanner"]
