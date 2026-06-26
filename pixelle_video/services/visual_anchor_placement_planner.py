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
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.visual_anchor_policy import (
    anchor_identity_from_profile,
    infer_scene_anchor_affordances,
    is_scene_bound_anchor_candidate,
    sanitize_provider_anchor_clause,
)
from pixelle_video.services.mandatory_ip_prompt_compiler import (
    MandatoryIPParticipationError,
    compile_mandatory_ip_participation_plan,
)
from pixelle_video.services.visual_signature_clause_renderer import (
    render_visual_signature_candidate_clause,
)
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualAnchorPlacementPlanner:
    """Deterministic planner that fails closed and never emits canvas-corner anchors."""

    policy: VisualSignaturePolicy | None = None

    def plan_batch(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        anchor_profile: IPProfile | None,
        base_packages: Sequence[IPFrameAdaptationPackage] = (),
        frame_contexts: Sequence[Mapping[str, Any]] = (),
        frame_plans: Sequence[Any] = (),
    ) -> tuple[VisualAnchorPlacementPlan, ...]:
        policy = self.policy or load_visual_signature_policy()
        if anchor_profile is None:
            if policy.requires_every_frame_signature:
                raise MandatoryIPParticipationError("mandatory IP participation requires an anchor_profile")
            return tuple(
                _suppressed_plan(brief.frame_id, reason="no anchor profile", policy=policy)
                for brief in base_visual_briefs
            )
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
        policy = self.policy or load_visual_signature_policy()
        if policy.requires_every_frame_signature and policy.fallback_strategy in {"inject_safe_carrier", "rewrite_content_action"}:
            return compile_mandatory_ip_participation_plan(
                frame_id=base_visual_brief.frame_id,
                base_visual_brief=base_visual_brief,
                anchor_profile=anchor_profile,
                duty_payload=_duty_payload_from_frame_inputs(frame_context, frame_plan),
                policy=policy,
            )

        if base_package is not None and base_package.role_slot is IPRoleSlot.ABSENT:
            return _suppressed_plan(base_visual_brief.frame_id, reason="base package absent", policy=policy)

        risk_reason = _high_risk_hidden_reason(base_visual_brief, policy=policy)
        if risk_reason:
            return _suppressed_plan(base_visual_brief.frame_id, reason=risk_reason, policy=policy)

        support_anchor = _choose_support_anchor(base_visual_brief)
        if not support_anchor:
            return _suppressed_plan(
                base_visual_brief.frame_id,
                reason="no safe scene-bound carrier",
                policy=policy,
            )

        prominence = _choose_anchor_prominence(
            base_visual_brief=base_visual_brief,
            base_package=base_package,
            support_anchor=support_anchor,
        )
        if prominence is AnchorProminence.HIDDEN:
            return _suppressed_plan(
                base_visual_brief.frame_id,
                reason="no safe scene-bound carrier",
                policy=policy,
            )

        anchor_identity = anchor_identity_from_profile(anchor_profile)
        anchor_function, carrier_type = _function_and_carrier_for_prominence(
            prominence,
            support_anchor=support_anchor,
        )
        placement_zone = _choose_placement_zone(base_visual_brief, support_anchor=support_anchor)
        visual_weight_clause = _visual_weight_clause(prominence)
        contact_relation = _contact_relation_for_prominence(prominence, support_anchor=support_anchor)
        image_prompt_clause = render_visual_signature_candidate_clause(
            carrier_type=carrier_type,
            support_anchor=support_anchor,
            contact_relation=contact_relation,
            placement=placement_zone,
            source_text=anchor_identity,
            policy=policy,
        )
        image_prompt_clause = sanitize_provider_anchor_clause(image_prompt_clause)
        if not is_scene_bound_anchor_candidate(
            image_prompt_clause=image_prompt_clause,
            support_anchor=support_anchor,
            placement=placement_zone,
            contact_relation=contact_relation,
            carrier_type=carrier_type,
            policy=policy,
        ):
            return _suppressed_plan(
                base_visual_brief.frame_id,
                reason="fallback clause rejected by scene-bound policy",
                policy=policy,
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
            depth_layer=_depth_layer_for_prominence(prominence, support_anchor=support_anchor),
            contact_relation=contact_relation,
            interaction_target=_choose_interaction_target(base_visual_brief),
            occlusion_relation="主体脸部、关键标志和主要动作区域保持清晰可见",
            style_relation=(
                AnchorStyleRelation.BLENDED
                if prominence in {AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO}
                else AnchorStyleRelation.ACCENTED
            ),
            image_prompt_clause=image_prompt_clause,
            metadata={
                "planner": "VisualAnchorPlacementPlanner",
                "fallback": True,
                "policy": policy.version,
                "projection": "deterministic_visual_signature_clause_renderer",
            },
        )


def _duty_payload_from_frame_inputs(
    frame_context: Mapping[str, Any] | None,
    frame_plan: Any,
) -> Mapping[str, Any] | None:
    if isinstance(frame_context, Mapping):
        value = frame_context.get("visual_story_ip_fusion_plan") or frame_context.get("ip_duty_plan")
        if isinstance(value, Mapping):
            return value
    if isinstance(frame_plan, Mapping):
        value = frame_plan.get("visual_story_ip_fusion_plan") or frame_plan.get("ip_duty_plan")
        if isinstance(value, Mapping):
            return value
    value = getattr(frame_plan, "visual_story_ip_fusion_plan", None)
    if isinstance(value, Mapping):
        return value
    if hasattr(frame_plan, "to_dict"):
        try:
            payload = frame_plan.to_dict()
        except Exception:
            payload = None
        if isinstance(payload, Mapping):
            value = payload.get("visual_story_ip_fusion_plan") or payload.get("ip_duty_plan")
            if isinstance(value, Mapping):
                return value
    return None


def _suppressed_plan(
    frame_id: str,
    *,
    reason: str,
    policy: VisualSignaturePolicy,
) -> VisualAnchorPlacementPlan:
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
        metadata={"reason": reason, "fallback": True, "policy": policy.version},
    )


def _high_risk_hidden_reason(
    base_visual_brief: BaseVisualBrief,
    *,
    policy: VisualSignaturePolicy,
) -> str:
    text = " ".join(
        [
            base_visual_brief.base_image_prompt,
            base_visual_brief.core_message,
            base_visual_brief.visual_moment,
            base_visual_brief.setting,
            " ".join(base_visual_brief.main_subjects),
            " ".join(base_visual_brief.subject_identity_anchors),
        ]
    )
    if policy.contains_high_risk_scene_text(text) or policy.contains_high_risk_subject_text(text):
        return "high-risk source subject or scene"
    if (
        policy.suppress_named_subject_count > 0
        and len(base_visual_brief.main_subjects) >= policy.suppress_named_subject_count
    ):
        return "multiple named source subjects"
    return ""


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
        return AnchorProminence.HIDDEN
    if any(word in text for word in ("特写", "近景", "细节", "书页", "卡片", "徽章", "图表", "地图", "迷宫", "文件")):
        return AnchorProminence.EMBEDDED_MARK
    if has_named_subject:
        return AnchorProminence.EMBEDDED_MARK
    if any(word in support_anchor for word in ("桌面", "书签", "小摆件", "徽章")):
        return AnchorProminence.TINY_PROP
    if any(word in text for word in ("城市", "街道", "人群", "广场", "高楼")):
        return AnchorProminence.EMBEDDED_MARK
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


__all__ = ["VisualAnchorPlacementPlanner"]
