from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_planning import (
    AnchorCarrierType,
    AnchorFunction,
    AnchorProminence,
    AnchorStyleRelation,
    VisualAnchorPlacementPlan,
)
from pixelle_video.services.provider_prompt_projector import ProviderPromptProjector
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


def test_provider_prompt_projector_removes_internal_terms_and_raw_style():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
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
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert rendered.prompt.count("兔子") <= 1


def test_provider_prompt_projector_converts_negative_subject_rules_to_positive():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert "不要画成" not in rendered.prompt
    assert "不要给" not in rendered.prompt
    assert "奥特曼保持无披风" in rendered.prompt or "超人保持人类男性" in rendered.prompt


def test_provider_prompt_projector_avoids_percent_scale_language():
    rendered = ProviderPromptProjector().project(
        base_visual_brief=_brief(),
        visual_anchor_plan=_anchor(),
        workflow="selfhost/image_z_image_turbo_gguf.json",
    )
    assert "%" not in rendered.prompt
    assert "约为主要主体高度" not in rendered.prompt
    assert "小摆件" in rendered.prompt or "浅压印纹章" in rendered.prompt or "墙绘或纹章细节" in rendered.prompt
    assert "角落标签" not in rendered.prompt
    assert "角标" not in rendered.prompt


def test_planner_defaults_named_subjects_to_low_prominence():
    profile = IPProfile(
        ip_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )
    plan = VisualAnchorPlacementPlanner().plan_frame(base_visual_brief=_brief(), anchor_profile=profile)
    assert plan.anchor_prominence in {AnchorProminence.TINY_PROP, AnchorProminence.EMBEDDED_MARK, AnchorProminence.MICRO_CAMEO}
    assert "%" not in plan.image_prompt_clause
