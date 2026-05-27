from pixelle_video.services.base_visual_brief_planner import BaseVisualBriefPlanner


def test_base_visual_brief_preserves_base_prompt_without_anchor():
    brief = BaseVisualBriefPlanner().plan_frame(
        base_prompt="奥特曼和超人在城市街道中央形成左右对比。",
        frame_context={
            "frame_id": "f1",
            "primary_subject": "奥特曼",
            "secondary_subjects": ["超人"],
            "shot_type": "中景",
            "shot_purpose": "展示对比",
        },
    )
    assert brief.frame_id == "f1"
    assert "奥特曼" in brief.base_image_prompt
    assert "超人" in brief.base_image_prompt
    assert "兔子" not in brief.base_image_prompt
