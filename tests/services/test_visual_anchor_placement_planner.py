from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


def _profile() -> IPProfile:
    return IPProfile(
        ip_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )


def test_visual_anchor_placement_suppresses_named_comparison_subjects():
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

    assert not plan.visible
    assert plan.metadata["reason"] in {"multiple named source subjects", "high-risk source subject or scene"}


def test_visual_anchor_placement_outputs_material_signature_for_safe_book_surface():
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
    assert "蓝领结白兔" in plan.image_prompt_clause
    assert "压印" in plan.image_prompt_clause
    assert "视觉锚点" not in plan.image_prompt_clause
    assert "IP角色" not in plan.image_prompt_clause
    assert "%" not in plan.image_prompt_clause
    assert "右下角" not in plan.image_prompt_clause
    assert "角标" not in plan.image_prompt_clause
