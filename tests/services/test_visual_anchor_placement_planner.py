from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_planning import AnchorCarrierType, AnchorFunction
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


def _profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )


def test_visual_anchor_placement_uses_content_bound_participant_for_named_comparison_subjects():
    brief = BaseVisualBrief(
        frame_id="f1",
        core_message="英雄对比",
        visual_moment="奥特曼和超人在城市街道中央形成左右对比，前景有街道路面。",
        main_subjects=("奥特曼", "超人"),
        base_image_prompt="奥特曼和超人在城市街道中央形成左右对比，前景有街道路面。",
    )
    plan = VisualAnchorPlacementPlanner().plan_frame(
        base_visual_brief=brief,
        anchor_profile=_profile(),
    )

    assert plan.visible
    assert plan.anchor_function is AnchorFunction.CONTENT_BOUND_PARTICIPANT
    assert plan.anchor_carrier_type is AnchorCarrierType.CONTENT_BOUND_IP_ACTOR
    assert plan.metadata["content_relation_type"] == "content_bound"


def test_visual_anchor_placement_outputs_content_bound_action_for_safe_book_surface():
    brief = BaseVisualBrief(
        frame_id="f1",
        core_message="书籍介绍",
        visual_moment="一本打开的书页展示家族故事。",
        main_subjects=("打开的书页",),
        anchor_affordances=("打开的书页纸面",),
        base_image_prompt="一本打开的书页展示家族故事。",
    )
    plan = VisualAnchorPlacementPlanner().plan_frame(
        base_visual_brief=brief,
        anchor_profile=_profile(),
    )

    assert plan.visible
    assert "蓝色领结" in plan.image_prompt_clause
    assert plan.anchor_function is AnchorFunction.CONTENT_BOUND_PARTICIPANT
    assert plan.anchor_carrier_type.value.startswith("content_bound_")
    assert "可见参与者" in plan.image_prompt_clause
    assert "视觉锚点" not in plan.image_prompt_clause
    assert "IP角色" not in plan.image_prompt_clause
    assert "%" not in plan.image_prompt_clause
    assert "右下角" not in plan.image_prompt_clause
    assert "角标" not in plan.image_prompt_clause
