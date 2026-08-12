from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureStrategyControls,
)
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.models.visual_signature_policy import VisualSignaturePolicy
from pixelle_video.models.visual_style_contract import (
    VisualLayerTarget,
    VisualRenderingStyle,
    VisualStyleLayer,
    VisualStyleLayerContract,
)
from pixelle_video.services.base_visual_brief_planner import BaseVisualBriefPlanner
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
from pixelle_video.services.series_visual_signature_projection_service import (
    SeriesVisualSignatureProjectionService,
)
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


def _brief() -> BaseVisualBrief:
    return BaseVisualBrief(
        frame_id="f1",
        core_message="英雄对比",
        visual_moment="奥特曼和超人在城市街道中央形成左右对比。",
        main_subjects=("奥特曼", "超人"),
        readability_constraints=(
            "主体轮廓清楚",
            "不要给奥特曼添加红色披风",
            "不要画成奥特曼盔甲",
        ),
        style_surface="history-teaching bird classroom with archive motifs, non-IP background, flat monochrome illustration",
        base_image_prompt="奥特曼和超人在城市街道中央形成左右对比。白色卡通兔子，蓝色领结，长耳朵，站在旁边。",
    )


def _anchor():
    return VisualAnchorPlacementPlan(
        frame_id="frame",
        anchor_function=AnchorFunction.SCENE_BOUND_PROP,
        anchor_carrier_type=AnchorCarrierType.SMALL_SUPPORTING_PROP,
        anchor_prominence=AnchorProminence.TINY_PROP,
        visual_weight_clause="小道具级存在感，低于所有主要主体",
        placement_zone="放置在城市街道地面",
        support_anchor="城市街道地面",
        scale_ratio="小道具级存在感，低于所有主要主体",
        depth_layer="放置在已有支撑面上",
        contact_relation="实体小物件放在城市街道地面上并与地面接触",
        interaction_target="城市街道地面",
        occlusion_relation="奥特曼和超人的脸部、胸前标志和主要动作区域保持清晰可见",
        style_relation=AnchorStyleRelation.ACCENTED,
        image_prompt_clause="城市街道地面上放着一个低存在感的蓝领结白兔轮廓造型小摆件，实体接触地面，视觉优先级低于奥特曼和超人。",
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


def test_provider_prompt_projector_removes_internal_terms_and_raw_style():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert "蓝领结白兔" in rendered.prompt
    assert "visual anchor" not in rendered.prompt
    assert "IP角色" not in rendered.prompt
    assert "history-teaching" not in rendered.prompt
    assert "non-IP" not in rendered.prompt


def test_provider_prompt_projector_removes_duplicate_anchor_from_base_prompt():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert rendered.prompt.count("兔子") <= 1


def test_provider_prompt_projector_converts_negative_subject_rules_to_positive():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert "不要画成" not in rendered.prompt
    assert "不要给" not in rendered.prompt
    assert "奥特曼保持无披风" in rendered.prompt or "超人保持人类男性" in rendered.prompt


def test_provider_prompt_projector_avoids_percent_scale_language_and_overlay_terms():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert "%" not in rendered.prompt
    assert "约为主要主体高度" not in rendered.prompt
    assert (
        "小物件" in rendered.prompt
        or "小摆件" in rendered.prompt
        or "浅压印纹章" in rendered.prompt
        or "装饰纹样" in rendered.prompt
    )
    assert "角落标签" not in rendered.prompt
    assert "角标" not in rendered.prompt
    assert "水印" not in rendered.prompt
    assert "logo" not in rendered.prompt.lower()


def test_visual_prompt_planning_projector_accepts_series_visual_signature_strategy_argument():
    role_strategy = SeriesVisualSignatureStrategyControls.from_mapping(
        {
            "series_visual_signature_mode": "subject_replacement",
            "series_visual_signature_consistency_mode": "primary_character",
        }
    )

    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
        series_visual_signature_strategy=role_strategy,
    )

    assert rendered.prompt
    assert rendered.prompt_contract.metadata["series_visual_signature_strategy"] == role_strategy.to_dict()


def test_provider_prompt_assembly_keeps_rules_once_and_avoids_mid_clause_truncation():
    base_prompt = (
        "一幅充满未来感的城市景象，融合了现实与梦想。"
        "画面中可见特斯拉汽车穿梭在街道上，远处有一枚火箭正在升空。"
        "整个场景以简洁的线条和轮廓勾勒，使用单色调表达梦幻与现实交织的感觉。"
    )
    style_rules = (
        "Clean, simple lines with a focus on contour and silhouette, using negative space effectively.",
        "Implied through line work, no explicit material textures or details.",
        "Monochrome, with subtle variations in tone to convey emotion and depth.",
        "Subtle and consistent, enhancing the emotional tone without overpowering the design.",
        "Minimalist, with a focus on the subject and its immediate surroundings, avoiding clutter.",
        "Maintain a consistent use of line weight, spacing, and tonal values to ensure uniformity.",
    )
    style_contract = VisualStyleLayerContract(
        layers=(
            VisualStyleLayer(
                layer_id="latest_video_line_art",
                targets=(
                    VisualLayerTarget.NON_IP_WORLD,
                    VisualLayerTarget.ALL_NON_HUMAN,
                ),
                rendering_style=VisualRenderingStyle.STYLE_INHERITED,
                positive_rules=style_rules,
            ),
        )
    )
    brief = BaseVisualBriefPlanner().plan_frame(
        base_prompt=base_prompt,
        frame_context={"frame_id": "frame-1"},
        visual_style_contract=style_contract,
    )

    # The explicit contract already carries monochrome line-art semantics, so the
    # planner must not append a second hard-coded Chinese version of the same style.
    assert "黑白灰扁平插画，线条简洁，二维无纹理" not in brief.style_surface

    rendered = ProviderPromptProjector().project(
        base_visual_brief=brief,
        negative_rules=(
            "Avoid excessive detail",
            "color",
            "and complex backgrounds; maintain simplicity and clarity.",
        ),
        visual_signature_policy=_legacy_policy(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )

    for rule in style_rules:
        assert rendered.prompt.count(rule) == 1
    assert "使用克制且一致的配色" in rendered.prompt
    assert "背景简洁、低细节" in rendered.prompt
    assert "构图简洁清晰" in rendered.prompt
    assert "complex backgrounds" not in rendered.prompt

    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        }
    )
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="斑点狗",
        identity_traits=("黑色墨镜", "斑点花纹"),
    )
    final_prompt = (
        SeriesVisualSignatureProjectionService()
        .project_batch(
            base_prompts=[rendered.prompt],
            frame_ids=["frame-1"],
            frame_contexts=[{}],
            request=request,
            profile=profile,
        )
        .prompts[0]
    )

    assert len(final_prompt) < 1200
    assert "…" not in final_prompt
    assert "Preserve the base scene action, composition, and subject hierarchy" in final_prompt
    assert "Preserve the base scene visual style, camera, lighting, and surface treatment" not in final_prompt
    assert "斑点狗" in final_prompt
    assert "黑色墨镜" in final_prompt
    assert "斑点花纹" in final_prompt
    for rule in style_rules:
        assert final_prompt.count(rule) == 1


def test_planner_uses_content_bound_participant_for_named_comparison_subjects_by_default():
    profile = IPProfile(
        series_visual_signature_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )
    plan = VisualAnchorPlacementPlanner().plan_frame(base_visual_brief=_brief(), anchor_profile=profile)
    assert plan.visible
    assert plan.anchor_function is AnchorFunction.CONTENT_BOUND_PARTICIPANT
    assert plan.anchor_carrier_type is AnchorCarrierType.CONTENT_BOUND_IP_ACTOR
    assert plan.metadata["content_relation_type"] == "content_bound"
