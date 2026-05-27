from pixelle_video.models.asset_bible import IPProfile, IPRenderingStyle
from pixelle_video.models.base_visual_brief import BaseVisualBrief
from pixelle_video.models.visual_anchor_planning import AnchorProminence
from pixelle_video.services.visual_anchor_placement_planner import VisualAnchorPlacementPlanner


def test_visual_anchor_placement_outputs_low_prominence_signature_clause():
    profile = IPProfile(
        ip_profile_id="rabbit",
        workspace_id="ws",
        project_id="prj",
        name="科技兔子",
        rendering_style=IPRenderingStyle.STYLIZED_CHARACTER,
        visual_summary="一只白色科技兔子，蓝色领结，长耳朵，圆润脸型",
    )
    brief = BaseVisualBrief(
        frame_id="f1",
        core_message="英雄对比",
        visual_moment="奥特曼和超人在城市街道中央形成左右对比，前景有街道路面。",
        main_subjects=("奥特曼", "超人"),
        base_image_prompt="奥特曼和超人在城市街道中央形成左右对比，前景有街道路面。",
    )
    plan = VisualAnchorPlacementPlanner().plan_frame(
        base_visual_brief=brief,
        anchor_profile=profile,
    )

    assert plan.visible
    assert plan.anchor_prominence in {
        AnchorProminence.EMBEDDED_MARK,
        AnchorProminence.TINY_PROP,
        AnchorProminence.MICRO_CAMEO,
    }
    assert "蓝领结白兔" in plan.image_prompt_clause or "白兔" in plan.image_prompt_clause
    assert "视觉锚点" not in plan.image_prompt_clause
    assert "IP角色" not in plan.image_prompt_clause
    assert "%" not in plan.image_prompt_clause
    assert "约为主要主体高度" not in plan.image_prompt_clause
