from __future__ import annotations

import pytest

from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_integration import (
    VisualAnchorIntegrationCandidateResponse,
    VisualAnchorIntegrationPlanResponse,
)
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.provider_prompt_projector import (
    MandatoryIPProjectionError,
    ProviderPromptProjector,
)
from pixelle_video.services.visual_anchor_policy import is_scene_bound_anchor_candidate


FORBIDDEN_ANCHOR_WORDS = (
    "画面角落",
    "画面边角",
    "右上角",
    "左上角",
    "右下角",
    "左下角",
    "角标",
    "水印",
    "贴纸",
    "悬浮",
    "漂浮",
    "corner logo",
    "corner bug",
    "watermark",
    "floating sticker",
)


def _legacy_policy() -> VisualSignaturePolicy:
    return VisualSignaturePolicy(
        version="visual_signature_policy.v1_legacy_visual_mark",
        coverage_mode="sparse",
        suppress_allowed=True,
        fallback_strategy="inject_safe_carrier",
        projection_failure="allow_anchor_free",
        require_concrete_identity=False,
        allowed_visible_carrier_types=(
            "bookplate_or_stamp",
            "printed_mark",
            "embossed_mark",
            "engraved_mark",
            "surface_graphic",
            "decorative_object",
            "wearable_symbol",
            "small_supporting_prop",
            "minor_supporting_character",
        ),
        final_prompt_forbidden_terms=(),
    )


def assert_no_forbidden_anchor_words(text: str) -> None:
    lowered = text.lower()
    for word in FORBIDDEN_ANCHOR_WORDS:
        assert word.lower() not in lowered


def test_scene_bound_policy_rejects_corner_logo_language() -> None:
    assert not is_scene_bound_anchor_candidate(
        image_prompt_clause="画面右下角有一个蓝领结白兔角标。",
        support_anchor="画面角落",
        placement="右下角",
        contact_relation="像水印一样浮在画面上",
        carrier_type=AnchorCarrierType.PRINTED_MARK,
    )


def test_scene_bound_policy_accepts_bookplate_stamp() -> None:
    assert is_scene_bound_anchor_candidate(
        image_prompt_clause="打开的书页纸面上有一个低对比的蓝领结白兔轮廓浅压印纹章，作为纸面纹理细节融入原物体。",
        support_anchor="打开的书页纸面",
        placement="附着在打开的书页纸面",
        contact_relation="作为打开的书页纸面的压印纹理细节",
        carrier_type=AnchorCarrierType.BOOKPLATE_OR_STAMP,
        policy=_legacy_policy(),
    )


def test_integration_plan_filters_selected_overlay_candidate() -> None:
    invalid_overlay = VisualAnchorIntegrationCandidateResponse(
        carrier_type=AnchorCarrierType.PRINTED_MARK,
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        prominence=AnchorProminence.EMBEDDED_MARK,
        style_relation=AnchorStyleRelation.BLENDED,
        placement="画面右下角",
        support_anchor="画面角落",
        contact_relation="像水印一样浮在画面上",
        image_prompt_clause="画面右下角有一个蓝领结白兔角标。",
        scene_coherence_score=10,
        disruption_risk=1,
        identity_preservation_score=10,
    )
    valid_bookplate = VisualAnchorIntegrationCandidateResponse(
        carrier_type=AnchorCarrierType.BOOKPLATE_OR_STAMP,
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        prominence=AnchorProminence.EMBEDDED_MARK,
        style_relation=AnchorStyleRelation.BLENDED,
        placement="附着在打开的书页纸面",
        support_anchor="打开的书页纸面",
        contact_relation="作为打开的书页纸面的压印纹理细节",
        interaction_target="打开的书页",
        occlusion_relation="主体阅读区域保持清晰",
        visual_weight_clause="低对比、低存在感，作为纸面材质细节",
        image_prompt_clause="打开的书页纸面上有一个低对比的蓝领结白兔轮廓浅压印纹章，作为纸面纹理细节融入原物体。",
        scene_coherence_score=9,
        disruption_risk=1,
        identity_preservation_score=8,
    )
    response = VisualAnchorIntegrationPlanResponse(
        frame_id="frame-1",
        candidates=[invalid_overlay, valid_bookplate],
        selected_index=0,
    )

    placement_plan = response.to_placement_plan(policy=_legacy_policy())

    assert placement_plan.visible
    assert placement_plan.support_anchor == "打开的书页纸面"
    assert placement_plan.anchor_carrier_type is AnchorCarrierType.BOOKPLATE_OR_STAMP
    assert_no_forbidden_anchor_words(placement_plan.image_prompt_clause)


def test_provider_projector_rejects_ungated_overlay_anchor() -> None:
    brief = BaseVisualBrief(
        frame_id="frame-1",
        core_message="解释一段历史文本",
        visual_moment="打开的书页中央展示一段历史说明",
        base_image_prompt="打开的书页中央展示一段历史说明",
        readability_constraints=("主体轮廓清楚",),
    )
    invalid_anchor_plan = VisualAnchorPlacementPlan(
        frame_id="frame-1",
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        anchor_carrier_type=AnchorCarrierType.PRINTED_MARK,
        anchor_prominence=AnchorProminence.EMBEDDED_MARK,
        visual_weight_clause="像角落标识一样小",
        placement_zone="画面右下角",
        support_anchor="画面角落",
        scale_ratio="像角落标识一样小",
        depth_layer="画面边缘层",
        contact_relation="像水印一样浮在画面上",
        interaction_target="",
        occlusion_relation="",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="画面右下角有一个蓝领结白兔角标。",
    )

    with pytest.raises(MandatoryIPProjectionError) as exc_info:
        ProviderPromptProjector().project(
            base_visual_brief=brief,
            visual_anchor_plan=invalid_anchor_plan,
            workflow="z_image",
        )

    assert exc_info.value.code == "anchor_clause_rejected"
