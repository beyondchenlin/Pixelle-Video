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
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)


@dataclass(frozen=True)
class VisualAnchorPlacementPlanner:
    """Plan how a recurring visual anchor is inserted after the base image scene exists."""

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
        anchor_function, carrier_type = _choose_anchor_function_and_carrier(base_visual_brief=base_visual_brief, base_package=base_package)
        if anchor_function is AnchorFunction.SUPPRESSED:
            return _suppressed_plan(base_visual_brief.frame_id, reason="suppressed by placement policy")
        placement_zone = _choose_placement_zone(base_visual_brief)
        support_anchor = _choose_support_anchor(base_visual_brief)
        scale_ratio = _choose_scale_ratio(anchor_function, base_visual_brief)
        depth_layer = _choose_depth_layer(placement_zone)
        interaction_target = _choose_interaction_target(base_visual_brief)
        contact_relation = _contact_relation_for_support(support_anchor)
        occlusion_relation = _occlusion_relation(base_visual_brief)
        style_relation = _choose_style_relation(anchor_profile, anchor_function)
        image_prompt_clause = _build_image_prompt_clause(
            anchor_identity=anchor_identity,
            anchor_function=anchor_function,
            carrier_type=carrier_type,
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            scale_ratio=scale_ratio,
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
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            scale_ratio=scale_ratio,
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


def _anchor_identity(anchor_profile: IPProfile) -> str:
    parts = [anchor_profile.visual_summary, *anchor_profile.identity_lock, *anchor_profile.minimal_traits, *anchor_profile.identity_anchors]
    return "，".join(_dedupe(str(part).strip() for part in parts if str(part or "").strip())) or anchor_profile.name


def _choose_anchor_function_and_carrier(*, base_visual_brief: BaseVisualBrief, base_package: IPFrameAdaptationPackage | None) -> tuple[AnchorFunction, AnchorCarrierType]:
    text = " ".join([base_visual_brief.base_image_prompt, base_visual_brief.camera_plan, base_visual_brief.composition_rules, base_visual_brief.core_message])
    if base_package is not None and base_package.role_slot is IPRoleSlot.PROTAGONIST and not base_visual_brief.main_subjects:
        return AnchorFunction.PRIMARY_CARRIER, AnchorCarrierType.LIVING_CHARACTER
    if any(word in text for word in ("特写", "近景", "细节", "书页", "卡片", "徽章")):
        return AnchorFunction.EMBEDDED_MARK, AnchorCarrierType.EMBEDDED_MARK
    if any(word in text for word in ("讲解板", "黑板", "图表", "对比图", "屏幕")):
        return AnchorFunction.EXPLAINER_POINTER, AnchorCarrierType.LIVING_CHARACTER
    if any(word in text for word in ("严肃", "纪实", "宗教", "真实人物")):
        return AnchorFunction.MICRO_CAMEO, AnchorCarrierType.PROP_OBJECT
    return AnchorFunction.CO_PRESENT_SUPPORT, AnchorCarrierType.LIVING_CHARACTER


def _choose_placement_zone(brief: BaseVisualBrief) -> str:
    text = brief.base_image_prompt
    if "左侧" in text and "右侧" in text:
        return "前景下方靠边位置"
    if any(word in text for word in ("特写", "近景", "书页", "卡片")):
        return "画面边角或道具边缘"
    if any(word in text for word in ("天空", "飞", "高空")):
        return "前景下方或建筑边缘"
    return "前景低位或主体旁边的非遮挡区域"


def _choose_support_anchor(brief: BaseVisualBrief) -> str:
    text = brief.base_image_prompt
    candidates = (
        ("电视", "电视柜、屏幕边缘或观看区地面"),
        ("书页", "书页角落或桌面边缘"),
        ("讲解板", "讲解板旁边的地面或板框边缘"),
        ("黑板", "黑板旁边的地面或板框边缘"),
        ("城市", "街道路面、车辆旁或建筑边缘"),
        ("街道", "街道路面、路边或车辆旁"),
        ("楼", "楼顶边缘、窗台后方或建筑底部"),
        ("桌", "桌面、桌边或桌脚旁"),
        ("人群", "人群边缘的地面"),
        ("车", "车辆旁、车顶边缘或车轮旁地面"),
        ("海", "岸边地面、礁石或船舷边缘"),
        ("森林", "树根旁、树枝或地面草丛边缘"),
    )
    for keyword, support in candidates:
        if keyword in text:
            return support
    return "已有场景中的地面、物体边缘、墙面角落或前景支撑面"


def _choose_scale_ratio(anchor_function: AnchorFunction, brief: BaseVisualBrief) -> str:
    if anchor_function is AnchorFunction.EMBEDDED_MARK:
        return "约占画面宽度的3%到6%"
    if anchor_function is AnchorFunction.MICRO_CAMEO:
        return "约占画面高度的5%到10%"
    if len(brief.main_subjects) >= 2:
        return "约为主要主体高度的10%到18%"
    return "明显小于主体，约占主体高度的15%到25%"


def _choose_depth_layer(placement_zone: str) -> str:
    if "前景" in placement_zone:
        return "前景"
    if "边角" in placement_zone:
        return "画面边缘层"
    return "中景边缘"


def _choose_interaction_target(brief: BaseVisualBrief) -> str:
    if brief.main_subjects:
        return brief.main_subjects[0]
    if brief.key_props_symbols:
        return brief.key_props_symbols[0]
    return "画面主体或最近的场景道具"


def _contact_relation_for_support(support_anchor: str) -> str:
    if any(word in support_anchor for word in ("墙", "板框", "屏幕", "书页")):
        return "与支撑面相邻或贴附在边缘"
    if any(word in support_anchor for word in ("地面", "路面", "桌面", "楼顶", "车顶", "岸边", "树枝")):
        return "身体或底部与支撑面有可见接触，并带有轻微投影"
    return "与已有物体有接触、遮挡或邻接关系"


def _occlusion_relation(brief: BaseVisualBrief) -> str:
    if len(brief.main_subjects) >= 2:
        return "不遮挡任何主要主体的脸部、标志、轮廓或关键动作"
    return "不遮挡主体面部、关键标志或画面阅读重点"


def _choose_style_relation(anchor_profile: IPProfile, anchor_function: AnchorFunction) -> AnchorStyleRelation:
    if anchor_function in {AnchorFunction.EMBEDDED_MARK, AnchorFunction.MICRO_CAMEO}:
        return AnchorStyleRelation.BLENDED
    if anchor_profile.style_hint and any(word in anchor_profile.style_hint.lower() for word in ("3d", "realistic", "真人", "独立")):
        return AnchorStyleRelation.ACCENTED
    return AnchorStyleRelation.ACCENTED


def _build_image_prompt_clause(
    *,
    anchor_identity: str,
    anchor_function: AnchorFunction,
    carrier_type: AnchorCarrierType,
    placement_zone: str,
    support_anchor: str,
    scale_ratio: str,
    depth_layer: str,
    contact_relation: str,
    interaction_target: str,
    occlusion_relation: str,
    style_relation: AnchorStyleRelation,
) -> str:
    if anchor_function is AnchorFunction.EMBEDDED_MARK:
        return f"{anchor_identity}以小型图标或标记形式出现在{support_anchor}，{scale_ratio}，{contact_relation}，{occlusion_relation}。"
    if carrier_type in {AnchorCarrierType.PROP_OBJECT, AnchorCarrierType.FIGURINE}:
        return f"{anchor_identity}作为小型摆件或道具放在{placement_zone}的{support_anchor}，{scale_ratio}，{contact_relation}，{occlusion_relation}。"
    style_clause = "轮廓清晰但不抢占主体" if style_relation is AnchorStyleRelation.ACCENTED else "造型和线条与画面风格协调"
    return (
        f"{anchor_identity}位于{placement_zone}，依托{support_anchor}，{scale_ratio}，"
        f"处在{depth_layer}，{contact_relation}，面向或关联{interaction_target}，"
        f"{occlusion_relation}，{style_clause}。"
    )


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
