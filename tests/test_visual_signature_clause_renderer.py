from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.services.visual_signature_clause_renderer import (
    render_visual_anchor_plan_clause,
    render_visual_signature_candidate_clause,
)


def test_bookplate_clause_preserves_dynamic_dog_identity_from_metadata():
    plan = VisualAnchorPlacementPlan(
        frame_id="frame-1",
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        anchor_carrier_type=AnchorCarrierType.BOOKPLATE_OR_STAMP,
        anchor_prominence=AnchorProminence.EMBEDDED_MARK,
        placement_zone="inside cover of the book",
        support_anchor="the book 'One Hundred Years of Solitude'",
        scale_ratio="visible but subordinate",
        depth_layer="真实场景元素层",
        contact_relation="physically integrated with the book's inner cover",
        interaction_target="reader",
        occlusion_relation="main subject remains readable",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="在书的内封上有一个带着黑色墨镜的斑点狗作为藏书票。",
        metadata={
            "visual_identity_kernel": ["黑色墨镜", "斑点狗", "带着黑色墨镜的斑点狗"],
        },
    )

    clause = render_visual_anchor_plan_clause(plan)

    assert "斑点狗" in clause
    assert "黑色墨镜" in clause
    assert "清晰可辨" in clause
    assert "频道识别轮廓" not in clause


def test_surface_graphic_clause_preserves_dynamic_identity_from_source_text_fallback():
    clause = render_visual_signature_candidate_clause(
        carrier_type=AnchorCarrierType.SURFACE_GRAPHIC,
        support_anchor="the mirror dividing the two scenes",
        placement="on the mirror surface",
        source_text="在镜子表面有一个带着黑色墨镜的斑点狗作为微妙的图形。",
    )

    assert "斑点狗" in clause
    assert "黑色墨镜" in clause
    assert "清晰可辨" in clause
    assert "频道识别轮廓" not in clause


def test_existing_rabbit_identity_still_gets_specific_label():
    clause = render_visual_signature_candidate_clause(
        carrier_type=AnchorCarrierType.PRINTED_MARK,
        support_anchor="书页",
        source_text="书页角落有蓝领结白兔的图案。",
    )

    assert "蓝领结白兔" in clause
    assert "频道识别轮廓" not in clause
