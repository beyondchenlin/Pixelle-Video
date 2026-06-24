import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.ip_duty import IPDutyPreset
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.mandatory_ip_prompt_compiler import compile_mandatory_ip_participation_plan
from pixelle_video.services.provider_prompt_projector import MandatoryIPProjectionError, ProviderPromptProjector


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="ip1",
        workspace_id="w1",
        project_id="p1",
        name="戴黑色墨镜的斑点狗轮廓",
        visual_summary="戴黑色墨镜的斑点狗轮廓",
        identity_lock=("斑点狗轮廓", "黑色墨镜"),
        minimal_traits=("黑色墨镜", "斑点狗"),
    )


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="frame_001",
        core_message="解释拖延背后的情绪压力",
        visual_moment="桌面上有开始按钮、任务卡片和分析卡片",
        main_subjects=("开始按钮", "任务卡片"),
        key_props_symbols=("纸质分析卡片", "开始按钮"),
        anchor_affordances=("桌面上的纸质分析卡片",),
        base_image_prompt="白色桌面上有开始按钮、任务卡片和纸质分析卡片，清晰知识解读画面",
        style_surface="clean explanatory visual",
    )


def test_mandatory_compiler_never_suppresses_and_preserves_identity():
    policy = VisualSignaturePolicy()
    plan = compile_mandatory_ip_participation_plan(
        frame_id="frame_001",
        base_visual_brief=_brief(),
        anchor_profile=_profile(),
        duty_payload={"frame_id": "frame_001", "ip_duty_preset": "operator_demonstrator"},
        policy=policy,
    )
    assert plan.visible
    assert plan.anchor_carrier_type is not AnchorCarrierType.SUPPRESSED
    assert "戴黑色墨镜" in plan.image_prompt_clause
    assert not policy.contains_forbidden_final_prompt_text(plan.image_prompt_clause)
    assert plan.metadata["ip_duty_preset"] == "operator_demonstrator"


def test_projector_fails_when_mandatory_anchor_is_missing():
    with pytest.raises(MandatoryIPProjectionError):
        ProviderPromptProjector().project(
            base_visual_brief=_brief(),
            visual_anchor_plan=None,
            visual_signature_policy=VisualSignaturePolicy(),
        )


def test_projector_keeps_anchor_clause_in_final_prompt():
    policy = VisualSignaturePolicy()
    plan = compile_mandatory_ip_participation_plan(
        frame_id="frame_001",
        base_visual_brief=_brief(),
        anchor_profile=_profile(),
        duty_payload={"frame_id": "frame_001", "ip_duty_preset": IPDutyPreset.BACKGROUND_SIGNATURE.value},
        policy=policy,
    )
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        anchor_profile=_profile(),
        visual_anchor_plan=plan,
        visual_signature_policy=policy,
    )
    assert rendered.prompt_contract.metadata["ip_present"] is True
    assert rendered.prompt_contract.metadata["scene_bound_anchor_gate"] == "passed"
    assert rendered.prompt_contract.metadata["mandatory_ip_final_gate"]["passed"] is True
    assert "戴黑色墨镜的斑点狗轮廓" in rendered.prompt
    assert "纸质分析卡片" in rendered.prompt


def test_manual_plan_with_forbidden_clause_is_rejected():
    forbidden_plan = VisualAnchorPlacementPlan(
        frame_id="frame_001",
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        anchor_carrier_type=AnchorCarrierType.PRINTED_MARK,
        anchor_prominence=AnchorProminence.EMBEDDED_MARK,
        placement_zone="桌面上的纸质分析卡片",
        support_anchor="桌面上的纸质分析卡片",
        scale_ratio="小面积",
        depth_layer="真实场景元素层",
        contact_relation="印在纸面",
        interaction_target="纸质分析卡片",
        occlusion_relation="主体清晰",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="画面角落出现戴黑色墨镜的斑点狗轮廓",
        metadata={"visual_identity_kernel": ["戴黑色墨镜的斑点狗轮廓"]},
    )
    with pytest.raises(MandatoryIPProjectionError):
        ProviderPromptProjector().project(
            base_visual_brief=_brief(),
            visual_anchor_plan=forbidden_plan,
            visual_signature_policy=VisualSignaturePolicy(),
        )
