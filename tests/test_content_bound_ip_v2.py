from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_request import SeriesVisualSignatureRequest
from pixelle_video.models.video_generation_contract import IPControlsContract
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.services.mandatory_ip_prompt_compiler import (
    compile_mandatory_ip_participation_plan,
)
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
from pixelle_video.services.visual_anchor_projection_gate import validate_visual_anchor_projection
from pixelle_video.services.visual_signature_clause_renderer import render_visual_anchor_plan_clause
from pixelle_video.services.visual_signature_policy_resolver import policy_for_presentation_mode


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="pixelle-rabbit",
        workspace_id="workspace",
        project_id="project",
        name="Pixelle 小白兔",
        visual_summary="白色科技兔子，蓝色领结，圆润长耳朵轮廓",
        identity_lock=("白色科技兔子", "蓝色领结", "圆润长耳朵"),
        minimal_traits=("白色身体", "蓝色领结", "圆润长耳朵"),
        identity_anchors=("白色科技兔子", "蓝色领结"),
    )


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="frame_001",
        core_message="AI 工作流会筛选高价值信息",
        visual_moment="筛选机器把混乱输入变成三路输出",
        base_image_prompt="白色解释空间里，一台低科技筛选机器把混乱输入变成三路输出。",
        subject_identity_anchors=("筛选机器", "三路输出"),
        key_props_symbols=("筛选机器", "输入输出通道"),
        spatial_layout="机器居中，角色在侧面操作把手",
        camera_plan="中景",
        style_surface="干净二维解释插画",
        readability_constraints=("不要覆盖主流程",),
        metadata={"selected_visual_route": {"route_type": "cognitive_explainer", "route_name": "AI workflow explainer"}},
    )


def test_content_bound_compiler_projects_visible_action_actor() -> None:
    policy = VisualSignaturePolicy()
    plan = compile_mandatory_ip_participation_plan(
        frame_id="frame_001",
        anchor_profile=_profile(),
        base_visual_brief=_brief(),
        policy=policy,
    )
    assert plan.anchor_carrier_type.value.startswith("content_bound_")
    assert "卡片" not in plan.image_prompt_clause
    assert "书签" not in plan.image_prompt_clause
    assert "贴纸" not in plan.image_prompt_clause

    gate = validate_visual_anchor_projection(plan, policy=policy)
    assert gate.passed, gate.reason
    assert "IP" not in gate.anchor_clause
    assert "卡片" not in gate.anchor_clause
    assert "书签" not in gate.anchor_clause


def test_content_bound_policy_rejects_legacy_mark_carriers() -> None:
    policy = VisualSignaturePolicy()
    legacy_like = VisualAnchorPlacementPlan(
        frame_id="frame_001",
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        anchor_carrier_type=AnchorCarrierType.BOOKPLATE_OR_STAMP,
        anchor_prominence=AnchorProminence.EMBEDDED_MARK,
        visual_weight_clause="small",
        placement_zone="桌面",
        support_anchor="桌面资料夹",
        scale_ratio="small",
        depth_layer="foreground",
        contact_relation="printed on surface",
        interaction_target="folder",
        occlusion_relation="none",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="桌面资料夹上有白色科技兔子藏书票",
        metadata={"visual_identity_kernel": ["白色科技兔子"]},
    )
    assert not validate_visual_anchor_projection(legacy_like, policy=policy).passed
    assert render_visual_anchor_plan_clause(legacy_like, policy=policy) == ""


def test_content_bound_policy_rejects_old_minor_supporting_character_contract() -> None:
    policy = VisualSignaturePolicy()
    old_contract = VisualAnchorPlacementPlan(
        frame_id="frame_001",
        anchor_function=AnchorFunction.CONTENT_BOUND_PARTICIPANT,
        anchor_carrier_type=AnchorCarrierType.MINOR_SUPPORTING_CHARACTER,
        anchor_prominence=AnchorProminence.CONTENT_PARTICIPANT,
        visual_weight_clause="small",
        placement_zone="解释空间",
        support_anchor="解释空间",
        scale_ratio="small",
        depth_layer="foreground",
        contact_relation="角色操作机器",
        interaction_target="机器",
        occlusion_relation="none",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="解释空间里白色科技兔子操作机器把手",
        metadata={"visual_identity_kernel": ["白色科技兔子"]},
    )
    assert not validate_visual_anchor_projection(old_contract, policy=policy).passed


def test_provider_prompt_stays_image_facing() -> None:
    policy = VisualSignaturePolicy()
    profile = _profile()
    brief = _brief()
    plan = compile_mandatory_ip_participation_plan(
        frame_id="frame_001",
        anchor_profile=profile,
        base_visual_brief=brief,
        policy=policy,
    )
    rendered = ProviderPromptProjector().project(
        base_visual_brief=brief,
        anchor_profile=profile,
        visual_anchor_plan=plan,
        visual_signature_policy=policy,
        workflow="z_image",
    )
    for forbidden in ("IP", "must", "do not", "forbidden", "policy", "不要", "禁止", "不能", "卡片", "书签", "贴纸", "水印"):
        assert forbidden not in rendered.prompt


def test_provider_prompt_drops_do_not_rules_without_inverting_them() -> None:
    policy = VisualSignaturePolicy(
        version="visual_signature_policy.v1_legacy_visual_mark",
        coverage_mode="sparse",
        suppress_allowed=True,
        fallback_strategy="inject_safe_carrier",
        projection_failure="allow_anchor_free",
        require_concrete_identity=False,
        final_prompt_forbidden_terms=(),
    )
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        negative_rules=("Do not use stickers or corner badges.",),
        visual_signature_policy=policy,
        workflow="z_image",
    )

    assert "Do not" not in rendered.prompt
    assert "use stickers" not in rendered.prompt
    assert "corner badges" not in rendered.prompt


def test_content_bound_prompt_keeps_safe_style_constraints_only() -> None:
    policy = VisualSignaturePolicy()
    profile = _profile()
    plan = compile_mandatory_ip_participation_plan(
        frame_id="frame_001",
        anchor_profile=profile,
        base_visual_brief=_brief(),
        policy=policy,
    )

    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        anchor_profile=profile,
        visual_anchor_plan=plan,
        negative_rules=("photo realism, realistic fur", "Do not use stickers or corner badges."),
        visual_signature_policy=policy,
        workflow="z_image",
    )

    assert "photo realism" in rendered.prompt
    assert "realistic fur" in rendered.prompt
    assert "stickers" not in rendered.prompt
    assert "corner badges" not in rendered.prompt


def test_disabled_content_bound_policy_keeps_positive_only_negative_rules() -> None:
    policy = VisualSignaturePolicy(
        coverage_mode="sparse",
        suppress_allowed=True,
        projection_failure="allow_anchor_free",
        require_concrete_identity=False,
    )
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        negative_rules=("no visible text",),
        visual_signature_policy=policy,
        workflow="z_image",
    )

    assert rendered.negative_prompt is None
    assert "画面通过物体、构图和符号表达内容" in rendered.prompt


def test_string_false_does_not_enable_visual_signature() -> None:
    assert not SeriesVisualSignatureRequest.from_mapping({"series_visual_signature_enabled": "false"}).enabled
    assert not IPControlsContract.from_mapping({"series_visual_signature_enabled": "false"}).series_visual_signature_enabled


def test_explicit_legacy_mode_allows_legacy_mark_projection() -> None:
    policy = policy_for_presentation_mode(
        VisualSignaturePolicy(),
        SeriesVisualSignaturePresentationPolicy.from_mapping(
            {"series_visual_signature_presentation_mode": "legacy_visual_mark"}
        ),
    )
    legacy_mark = VisualAnchorPlacementPlan(
        frame_id="frame_001",
        anchor_function=AnchorFunction.MATERIAL_SIGNATURE,
        anchor_carrier_type=AnchorCarrierType.BOOKPLATE_OR_STAMP,
        anchor_prominence=AnchorProminence.EMBEDDED_MARK,
        visual_weight_clause="small",
        placement_zone="桌面资料夹",
        support_anchor="桌面资料夹",
        scale_ratio="small",
        depth_layer="foreground",
        contact_relation="printed on folder surface",
        interaction_target="folder",
        occlusion_relation="none",
        style_relation=AnchorStyleRelation.BLENDED,
        image_prompt_clause="桌面资料夹上有白色科技兔子藏书票",
        metadata={"visual_identity_kernel": ["白色科技兔子"]},
    )

    gate = validate_visual_anchor_projection(legacy_mark, policy=policy)
    assert gate.passed, gate.reason
