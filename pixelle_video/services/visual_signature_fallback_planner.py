from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignatureFallbackMode,
    SeriesVisualSignaturePresentationMode,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_strategy import build_visual_identity_kernel
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.services.mandatory_ip_prompt_compiler import compile_mandatory_ip_participation_plan
from pixelle_video.services.visual_signature_policy_loader import load_visual_signature_policy


@dataclass(frozen=True)
class VisualSignatureFallbackLedgerEntry:
    frame_id: str
    fallback_level: str
    requested_presentation_mode: str
    final_presentation_mode: str
    reason: tuple[str, ...]
    preserved_llm_plan: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "fallback_level": self.fallback_level,
            "requested_presentation_mode": self.requested_presentation_mode,
            "final_presentation_mode": self.final_presentation_mode,
            "reason": list(self.reason),
            "preserved_llm_plan": self.preserved_llm_plan,
        }


@dataclass(frozen=True)
class VisualSignatureFallbackPlanner:
    """Deterministic frame-level fallback for series visual signatures.

    The planner is intentionally used only after LLM integration/repair fails for
    individual frames.  It does not replace successful frames, and it preserves
    the configured identity rather than falling back to a generic channel mark.
    """

    anchor_profile: IPProfile
    presentation_policy: SeriesVisualSignaturePresentationPolicy
    identity_kernel: Sequence[str] = ()

    def plan_failed_frames(
        self,
        *,
        base_visual_briefs: Sequence[BaseVisualBrief],
        failed_frame_ids: Sequence[str],
        failure_reasons_by_frame: Mapping[str, Sequence[str]] | None = None,
    ) -> tuple[VisualAnchorPlacementPlan, ...]:
        failed = {str(frame_id) for frame_id in failed_frame_ids}
        reasons = failure_reasons_by_frame or {}
        return tuple(
            self.plan_frame(
                brief,
                reason=tuple(str(item) for item in reasons.get(brief.frame_id, ())),
            )
            for brief in base_visual_briefs
            if brief.frame_id in failed
        )

    def plan_frame(
        self,
        brief: BaseVisualBrief,
        *,
        reason: Sequence[str] = (),
    ) -> VisualAnchorPlacementPlan:
        policy = load_visual_signature_policy()
        if policy.requires_every_frame_signature and policy.fallback_strategy == "inject_safe_carrier":
            plan = compile_mandatory_ip_participation_plan(
                frame_id=brief.frame_id,
                base_visual_brief=brief,
                anchor_profile=self.anchor_profile,
                failure_reasons=reason,
                policy=policy,
            )
            return replace(
                plan,
                metadata={
                    **dict(plan.metadata or {}),
                    "source": "deterministic_visual_signature_fallback",
                    "fallback_applied": True,
                    "fallback_level": "mandatory_ip_compiler",
                    "requested_presentation_mode": self.presentation_policy.presentation_mode.value,
                    "fallback_mode": self.presentation_policy.fallback_mode.value,
                },
            )
        if policy.requires_every_frame_signature:
            return _suppressed_fallback_plan(
                brief,
                reason=reason,
                presentation_policy=self.presentation_policy,
                policy=policy,
            )

        mode = self.presentation_policy.presentation_mode
        if self.presentation_policy.fallback_mode is SeriesVisualSignatureFallbackMode.DEFAULT_SIGNATURE:
            mode = SeriesVisualSignaturePresentationMode.AUTO

        identity_phrase = _identity_phrase(
            self.identity_kernel or build_visual_identity_kernel(self.anchor_profile),
            self.anchor_profile,
        )
        prompt_context = _brief_context(brief)
        common_metadata = {
            "source": "deterministic_visual_signature_fallback",
            "fallback_applied": True,
            "requested_presentation_mode": self.presentation_policy.presentation_mode.value,
            "fallback_mode": self.presentation_policy.fallback_mode.value,
            "failure_reasons": [str(item) for item in reason],
            "visual_identity_kernel": [str(item) for item in (self.identity_kernel or build_visual_identity_kernel(self.anchor_profile)) if str(item or "").strip()],
            "source_core_message": brief.core_message,
        }

        if mode is SeriesVisualSignaturePresentationMode.PRIMARY_CHARACTER:
            clause = (
                f"让{identity_phrase}成为画面的主视觉行动者，承载原始画面意图：{prompt_context}。"
                "保留原始主题含义，同时让该视觉身份执行核心动作。"
            )
            return VisualAnchorPlacementPlan(
                frame_id=brief.frame_id,
                anchor_function=AnchorFunction.PRIMARY_CARRIER,
                anchor_carrier_type=AnchorCarrierType.LIVING_CHARACTER,
                anchor_prominence=AnchorProminence.PRIMARY_CARRIER,
                placement_zone="主视觉中心",
                support_anchor="主视觉行动位置",
                scale_ratio="主视觉主体",
                depth_layer="主视觉层",
                contact_relation="承担画面核心动作",
                interaction_target=brief.core_message or brief.visual_moment,
                occlusion_relation="不遮挡必要语义元素",
                style_relation=AnchorStyleRelation.BLENDED,
                image_prompt_clause=clause,
                visual_weight_clause="主视觉主体",
                metadata={**common_metadata, "fallback_level": "primary_character"},
            )

        if mode is SeriesVisualSignaturePresentationMode.EMBEDDED_SCENE_MARK or mode is SeriesVisualSignaturePresentationMode.AUTO:
            carrier = _embedded_carrier(brief)
            clause = (
                f"在{carrier}上加入一枚小面积但清晰可辨的{identity_phrase}图案，"
                "作为真实场景内的低调视觉签名；身份特征可读，但不替代主体、不遮挡关键内容。"
            )
            return VisualAnchorPlacementPlan(
                frame_id=brief.frame_id,
                anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
                anchor_carrier_type=AnchorCarrierType.SURFACE_GRAPHIC,
                anchor_prominence=AnchorProminence.EMBEDDED_MARK,
                placement_zone=carrier,
                support_anchor=carrier,
                scale_ratio="小面积但清晰可辨",
                depth_layer="真实场景元素层",
                contact_relation="贴合场景载体表面",
                interaction_target=brief.core_message or brief.visual_moment,
                occlusion_relation="主要主体保持可读",
                style_relation=AnchorStyleRelation.BLENDED,
                image_prompt_clause=clause,
                visual_weight_clause="可见但低于主体",
                metadata={**common_metadata, "fallback_level": "embedded_scene_mark"},
            )

        # Default fallback for visible_supporting_character: a real supporting
        # character, not a watermark or corner badge.  Placement is contextual
        # but deterministic and legal for any scene.
        placement = _supporting_character_location(brief)
        action = _supporting_character_action(brief)
        clause = (
            f"在{placement}出现一只小型{identity_phrase}，作为真实场景中的低存在感陪衬角色；"
            f"它{action}，不替代主体、不遮挡关键内容，体量和视觉重量低于主体，并与场景地面、光线和风格一致。"
        )
        return VisualAnchorPlacementPlan(
            frame_id=brief.frame_id,
            anchor_function=AnchorFunction.CO_PRESENT_SUPPORT,
            anchor_carrier_type=AnchorCarrierType.MINOR_SUPPORTING_CHARACTER,
            anchor_prominence=AnchorProminence.SMALL_SIDE_CHARACTER,
            placement_zone=placement,
            support_anchor=placement,
            scale_ratio="小型陪衬角色",
            depth_layer="前景或中景真实场景层",
            contact_relation="站在、坐在或靠近场景地面/支撑面",
            interaction_target=brief.core_message or brief.visual_moment,
            occlusion_relation="不遮挡主体和关键叙事元素",
            style_relation=AnchorStyleRelation.BLENDED,
            image_prompt_clause=clause,
            visual_weight_clause="可见但服从主体",
            metadata={**common_metadata, "fallback_level": "visible_supporting_character"},
        )


def merge_visual_anchor_plans_by_frame(
    *,
    frame_ids: Sequence[str],
    accepted_plans: Mapping[str, VisualAnchorPlacementPlan],
    fallback_plans: Sequence[VisualAnchorPlacementPlan],
) -> tuple[VisualAnchorPlacementPlan, ...]:
    fallback_by_frame = {plan.frame_id: plan for plan in fallback_plans}
    result: list[VisualAnchorPlacementPlan] = []
    for frame_id in frame_ids:
        if frame_id in accepted_plans:
            result.append(accepted_plans[frame_id])
        elif frame_id in fallback_by_frame:
            result.append(fallback_by_frame[frame_id])
    return tuple(result)


def _suppressed_fallback_plan(
    brief: BaseVisualBrief,
    *,
    reason: Sequence[str],
    presentation_policy: SeriesVisualSignaturePresentationPolicy,
    policy: Any,
) -> VisualAnchorPlacementPlan:
    return VisualAnchorPlacementPlan(
        frame_id=brief.frame_id,
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
        metadata={
            "source": "deterministic_visual_signature_fallback",
            "fallback_applied": True,
            "fallback_level": "suppressed_by_policy",
            "requested_presentation_mode": presentation_policy.presentation_mode.value,
            "fallback_mode": presentation_policy.fallback_mode.value,
            "failure_reasons": [str(item) for item in reason],
            "visual_signature_policy": getattr(policy, "version", ""),
        },
    )


def fallback_ledger_from_plans(
    plans: Sequence[VisualAnchorPlacementPlan],
) -> dict[str, Any]:
    entries = []
    for plan in plans:
        metadata = dict(plan.metadata or {})
        if metadata.get("fallback_applied"):
            entries.append(
                {
                    "frame_id": plan.frame_id,
                    "fallback_level": metadata.get("fallback_level"),
                    "requested_presentation_mode": metadata.get("requested_presentation_mode"),
                    "fallback_mode": metadata.get("fallback_mode"),
                    "failure_reasons": list(metadata.get("failure_reasons") or []),
                    "final_clause": plan.image_prompt_clause,
                }
            )
    return {
        "fallback_applied": bool(entries),
        "fallback_count": len(entries),
        "entries": entries,
    }


def _identity_phrase(identity_kernel: Sequence[str], anchor_profile: IPProfile) -> str:
    values = [str(item or "").strip() for item in identity_kernel if str(item or "").strip()]
    values.extend(
        str(item or "").strip()
        for item in (
            anchor_profile.visual_summary,
            anchor_profile.name,
            *anchor_profile.identity_lock,
            *anchor_profile.identity_anchors,
            *anchor_profile.minimal_traits,
        )
        if str(item or "").strip()
    )
    noun_hints = ("斑点狗", "狗", "猫", "兔", "小黑", "机器人", "小人", "麻雀", "鸟")
    trait_hints = ("墨镜", "领结", "帽", "眼镜")

    def score(value: str) -> tuple[int, int]:
        has_noun = any(token in value for token in noun_hints)
        has_trait = any(token in value for token in trait_hints)
        return (100 if has_noun else 0) + (20 if has_trait else 0), len(value)

    candidates = [value for value in values if len(value) <= 80]
    return max(candidates, key=score) if candidates else "频道视觉签名角色"


def _brief_context(brief: BaseVisualBrief) -> str:
    return brief.core_message or brief.visual_moment or brief.base_image_prompt or "当前画面主题"


def _supporting_character_location(brief: BaseVisualBrief) -> str:
    text = " ".join(
        [
            brief.setting,
            brief.spatial_layout,
            brief.base_image_prompt,
            " ".join(brief.key_props_symbols),
        ]
    )
    if any(token in text for token in ("街", "路", "道路", "城市", "巷", "广场")):
        return "画面一侧的路边或前景地面"
    if any(token in text for token in ("草", "森林", "山", "户外", "田野", "公园")):
        return "主体旁边的草地或前景地面"
    if any(token in text for token in ("桌", "书", "纸", "房间", "教室", "室内", "镜子")):
        return "主体旁边的地面、桌边或房间角落"
    return "主体旁边或画面一侧的前景空白区"


def _supporting_character_action(brief: BaseVisualBrief) -> str:
    text = " ".join([brief.core_message, brief.visual_moment, brief.base_image_prompt])
    if any(token in text for token in ("阅读", "书", "看", "镜", "观察")):
        return "安静旁观或跟随主体的视线"
    if any(token in text for token in ("走", "路", "旅行", "穿越", "移动")):
        return "跟随主体缓慢行走或站在路边旁观"
    if any(token in text for token in ("冲突", "对比", "拉扯", "分裂")):
        return "站在画面边缘旁观主要冲突"
    return "自然站立、坐下或轻微参与场景"


def _embedded_carrier(brief: BaseVisualBrief) -> str:
    props = list(brief.key_props_symbols)
    for prop in props:
        if any(token in prop for token in ("书", "纸", "墙", "屏幕", "镜", "桌", "海报", "地图", "门", "窗")):
            return prop
    text = " ".join([brief.setting, brief.spatial_layout, brief.base_image_prompt])
    if "书" in text:
        return "书页或书封表面"
    if "镜" in text:
        return "镜面边缘或镜框表面"
    if any(token in text for token in ("房间", "室内", "教室")):
        return "墙面、桌面或房间内道具表面"
    return "画面中的真实道具或背景表面"


__all__ = [
    "VisualSignatureFallbackLedgerEntry",
    "VisualSignatureFallbackPlanner",
    "fallback_ledger_from_plans",
    "merge_visual_anchor_plans_by_frame",
]
