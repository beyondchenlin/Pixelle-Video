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
from pixelle_video.services.visual_anchor_policy import (
    anchor_identity_from_profile,
    infer_scene_anchor_affordances,
    is_scene_bound_anchor_candidate,
    sanitize_provider_anchor_clause,
)


@dataclass(frozen=True)
class VisualAnchorPlacementPlanner:
    """Deterministic fallback planner that fails closed and never emits canvas-corner anchors."""

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

        support_anchor = _choose_support_anchor(base_visual_brief)
        prominence = _choose_anchor_prominence(
            base_visual_brief=base_visual_brief,
            base_package=base_package,
            support_anchor=support_anchor,
        )
        if prominence is AnchorProminence.HIDDEN:
            return _suppressed_plan(base_visual_brief.frame_id, reason="no safe scene-bound carrier")

        anchor_identity = anchor_identity_from_profile(anchor_profile)
        anchor_function, carrier_type = _function_and_carrier_for_prominence(
            prominence,
            support_anchor=support_anchor,
        )
        placement_zone = _choose_placement_zone(base_visual_brief, support_anchor=support_anchor)
        visual_weight_clause = _visual_weight_clause(prominence)
        contact_relation = _contact_relation_for_prominence(prominence, support_anchor=support_anchor)
        image_prompt_clause = _build_image_prompt_clause(
            anchor_identity=anchor_identity,
            prominence=prominence,
            support_anchor=support_anchor,
            visual_weight_clause=visual_weight_clause,
            contact_relation=contact_relation,
        )
        image_prompt_clause = sanitize_provider_anchor_clause(image_prompt_clause)
        if not is_scene_bound_anchor_candidate(
            image_prompt_clause=image_prompt_clause,
            support_anchor=support_anchor,
            placement=placement_zone,
            contact_relation=contact_relation,
            carrier_type=carrier_type,
        ):
            return _suppressed_plan(base_visual_brief.frame_id, reason="fallback clause rejected by scene-bound policy")

        return VisualAnchorPlacementPlan(
            frame_id=base_visual_brief.frame_id,
            anchor_function=anchor_function,
            anchor_carrier_type=carrier_type,
            anchor_prominence=prominence,
            visual_weight_clause=visual_weight_clause,
            placement_zone=placement_zone,
            support_anchor=support_anchor,
            scale_ratio=visual_weight_clause,
            depth_layer=_depth_layer_for_prominence(prominence, support_anchor=support_anchor),
            contact_relation=contact_relation,
            interaction_target=_choose_interaction_target(base_visual_brief),
            occlusion_relation="主体脸部、关键标志和主要动作区域保持清晰可见",
            style_relation=AnchorStyleRelation.BLENDED if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO} else AnchorStyleRelation.ACCENTED,
            image_prompt_clause=image_prompt_clause,
            metadata={"planner": "VisualAnchorPlacementPlanner", "fallback": True, "policy": "v3_1_scene_bound_no_corner"},
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
        metadata={"reason": reason, "fallback": True, "policy": "v3_1_fail_closed"},
    )


def _choose_anchor_prominence(
    *,
    base_visual_brief: BaseVisualBrief,
    base_package: IPFrameAdaptationPackage | None,
    support_anchor: str,
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

    if not support_anchor:
        return AnchorProminence.HIDDEN

    if any(word in text for word in ("严肃", "纪实", "宗教", "真实人物", "悼念", "灾难")):
        return AnchorProminence.EMBEDDED_MARK
    if any(word in text for word in ("特写", "近景", "细节", "书页", "卡片", "徽章", "图表", "地图", "迷宫", "文件")):
        return AnchorProminence.EMBEDDED_MARK
    if has_named_subject and len(base_visual_brief.main_subjects) >= 2:
        return AnchorProminence.EMBEDDED_MARK
    if any(word in support_anchor for word in ("桌面", "书签", "小摆件", "徽章")):
        return AnchorProminence.TINY_PROP
    if any(word in text for word in ("城市", "街道", "人群", "广场", "高楼")):
        return AnchorProminence.MICRO_CAMEO
    if not has_named_subject and any(word in text for word in ("勇气", "选择", "成长", "孤独", "责任", "梦想")):
        return AnchorProminence.TINY_PROP
    return AnchorProminence.EMBEDDED_MARK


def _function_and_carrier_for_prominence(
    prominence: AnchorProminence,
    *,
    support_anchor: str,
) -> tuple[AnchorFunction, AnchorCarrierType]:
    if prominence is AnchorProminence.HIDDEN:
        return AnchorFunction.SUPPRESSED, AnchorCarrierType.SUPPRESSED
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return AnchorFunction.PRIMARY_CARRIER, AnchorCarrierType.LIVING_CHARACTER
    if prominence is AnchorProminence.TINY_PROP:
        return AnchorFunction.SCENE_BOUND_PROP, AnchorCarrierType.SMALL_SUPPORTING_PROP
    if prominence is AnchorProminence.MICRO_CAMEO:
        return AnchorFunction.MATERIAL_SIGNATURE, AnchorCarrierType.SURFACE_GRAPHIC
    if any(word in support_anchor for word in ("书页", "书封", "书签", "藏书票", "纸面", "卡片", "文件")):
        return AnchorFunction.MATERIAL_SIGNATURE, AnchorCarrierType.BOOKPLATE_OR_STAMP
    if any(word in support_anchor for word in ("木", "长椅", "相框", "桌面")):
        return AnchorFunction.MATERIAL_SIGNATURE, AnchorCarrierType.ENGRAVED_MARK
    if any(word in support_anchor for word in ("墙", "海报", "路牌", "招牌", "讲解板", "黑板")):
        return AnchorFunction.MATERIAL_SIGNATURE, AnchorCarrierType.SURFACE_GRAPHIC
    return AnchorFunction.MATERIAL_SIGNATURE, AnchorCarrierType.PRINTED_MARK


def _choose_placement_zone(brief: BaseVisualBrief, *, support_anchor: str) -> str:
    if support_anchor:
        return f"附着在{support_anchor}"
    return "本帧隐藏"


def _choose_support_anchor(brief: BaseVisualBrief) -> str:
    affordances = tuple(getattr(brief, "anchor_affordances", ()) or ())
    if not affordances:
        inferred = infer_scene_anchor_affordances(
            base_prompt=brief.base_image_prompt,
            main_subjects=brief.main_subjects,
            key_props=brief.key_props_symbols,
        )
        affordances = inferred.carriers
    return affordances[0] if affordances else ""


def _visual_weight_clause(prominence: AnchorProminence) -> str:
    labels = {
        AnchorProminence.HIDDEN: "",
        AnchorProminence.EMBEDDED_MARK: "低对比、低存在感，作为材质细节融入原物体",
        AnchorProminence.TINY_PROP: "小道具级存在感，低于所有主要主体",
        AnchorProminence.MICRO_CAMEO: "背景环境细节级存在感，只服务系列识别",
        AnchorProminence.SMALL_SIDE_CHARACTER: "明显低于主要配角，作为弱存在感陪衬",
        AnchorProminence.PRIMARY_CARRIER: "作为本帧主要视觉载体",
    }
    return labels[prominence]


def _depth_layer_for_prominence(prominence: AnchorProminence, *, support_anchor: str) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return "附着在已有物体表面"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return "附着在背景环境表面"
    if prominence is AnchorProminence.TINY_PROP:
        return "放置在已有支撑面上"
    return "主体层"


def _contact_relation_for_prominence(prominence: AnchorProminence, *, support_anchor: str) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return f"作为{support_anchor}的印刷、压印、雕刻或纹理细节"
    if prominence is AnchorProminence.TINY_PROP:
        return f"实体小物件放在{support_anchor}上并与支撑面接触"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return f"作为{support_anchor}的一部分融入背景材质"
    return "与场景空间自然接触"


def _choose_interaction_target(brief: BaseVisualBrief) -> str:
    if brief.key_props_symbols:
        return brief.key_props_symbols[0]
    if brief.main_subjects:
        return "、".join(brief.main_subjects[:2])
    if brief.anchor_affordances:
        return brief.anchor_affordances[0]
    return "最近的场景道具"


def _build_image_prompt_clause(
    *,
    anchor_identity: str,
    prominence: AnchorProminence,
    support_anchor: str,
    visual_weight_clause: str,
    contact_relation: str,
) -> str:
    if prominence is AnchorProminence.EMBEDDED_MARK:
        return f"{support_anchor}上有一个低对比的{anchor_identity}浅压印纹章，{contact_relation}，{visual_weight_clause}。"
    if prominence is AnchorProminence.TINY_PROP:
        return f"{support_anchor}呈现为一个低存在感的{anchor_identity}造型小道具，实体接触支撑面，{visual_weight_clause}。"
    if prominence is AnchorProminence.MICRO_CAMEO:
        return f"{support_anchor}中融入一个低对比的{anchor_identity}墙绘或纹章细节，{contact_relation}，{visual_weight_clause}。"
    if prominence is AnchorProminence.PRIMARY_CARRIER:
        return f"一个{anchor_identity}位于主体层，作为画面核心承载主题。"
    return ""


__all__ = ["VisualAnchorPlacementPlanner"]
