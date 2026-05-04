from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.ip_prompt_planning import IPPresenceType
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.ip_usage_planner import IPUsagePlanner


def _profile():
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "长耳朵"),
        identity_anchors=("蓝色领带",),
        variable_slots=("动作", "表情", "服装", "道具", "站位"),
        semantic_boundary=("不能替代历史建筑", "不能替代宗教人物"),
        color_palette={"tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"}},
    )


def _plan(frame):
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frame.source_text,
        frames=[frame],
    )


def test_usage_planner_marks_establishing_frame_as_scene_integrated_by_default():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="从长乐门出发，这是正定的南大门。",
        visual_goal="表现正定长乐门作为古城入口的历史感和出发感",
        prompt_intent="建立古城空间和旅程开篇",
        shot_type="中远景",
        shot_purpose="建立场景",
        primary_subject="正定长乐门、青砖城墙",
        world_elements=("青砖城墙", "城楼", "晨光"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type is IPPresenceType.SCENE_INTEGRATED
    assert package.presence_mode in {"support", "ambient"}
    assert "长乐门" in package.must_not_replace


def test_usage_planner_marks_historical_subject_as_low_intrusion_or_absent():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古寺中讲述佛祖故事，香火与壁画静静铺开。",
        visual_goal="表现古寺宗教叙事的庄重感",
        prompt_intent="严肃历史宗教场景",
        shot_type="全景",
        shot_purpose="历史说明",
        primary_subject="佛祖故事与古寺壁画",
        world_elements=("古寺", "香火", "壁画"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }
    assert "不能替代" in " ".join(package.negative_constraints)


def test_usage_planner_generates_summary_and_scene_text_plan():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="从长乐门出发，走进正定古城的七处印记。",
        visual_goal="表现第一站与旅行手账感",
        prompt_intent="文旅开篇",
        primary_subject="长乐门",
        world_elements=("地图", "手账", "古城路线"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.image_text_plan.summary_text in {"从长乐门出发", "正定古城"}
    assert "长乐门" in package.image_text_plan.visible_text_whitelist
