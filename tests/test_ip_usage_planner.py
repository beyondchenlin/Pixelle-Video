from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.ip_prompt_planning import IPPresenceType
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec
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


def test_usage_planner_marks_explanation_frame_as_balanced_narrative():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古城街巷的生活记忆。",
        visual_goal="表现轻松的文化讲解氛围",
        prompt_intent="讲解地方文化",
        shot_type="中景",
        shot_purpose="叙事说明",
        primary_subject="古城街巷与生活细节",
        world_elements=("街巷", "摊位", "行人"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE
    assert package.presence_mode == "guide"


def test_usage_planner_marks_explicit_ip_hero_frame_as_strong_identity():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="正定向导兔作为品牌主角面向镜头开场。",
        visual_goal="表现IP主角强露出的欢迎画面",
        prompt_intent="品牌主画面",
        shot_type="近景",
        shot_purpose="IP主画面",
        primary_subject="正定向导兔",
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY
    assert package.presence_mode == "hero"


def test_usage_planner_allows_scene_cast_to_request_strong_identity():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古城路线从地图上展开。",
        visual_goal="表现路线总览",
        prompt_intent="旅行路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={
            plan.frames[0].frame_id: {"presence_type": "strong_identity"},
        },
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY


def test_usage_planner_uses_serious_documentary_style_as_low_intrusion_signal():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="镜头缓慢扫过城墙纹理。",
        visual_goal="表现朴素、克制的记录感",
        prompt_intent="空间质感说明",
        shot_type="全景",
        shot_purpose="说明环境",
        primary_subject="城墙纹理",
        world_elements=("砖石", "阴影", "墙面"),
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style={"style_kind": "严肃纪实纪录片"},
    )[0]

    assert package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }


def test_usage_planner_reads_scene_cast_metadata_ip_presence_type_override():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古城路线从地图上展开。",
        visual_goal="表现路线总览",
        prompt_intent="旅行路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={
            plan.frames[0].frame_id: {
                "metadata": {"ip_presence_type": "strong_identity"},
            },
        },
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY


def test_usage_planner_reads_scene_cast_metadata_presence_type_override():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古城路线从地图上展开。",
        visual_goal="表现路线总览",
        prompt_intent="旅行路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={
            plan.frames[0].frame_id: {
                "metadata": {"presence_type": "strong_identity"},
            },
        },
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY


def test_usage_planner_treats_uppercase_english_documentary_style_as_low_intrusion():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="镜头缓慢扫过城墙纹理。",
        visual_goal="表现朴素、克制的记录感",
        prompt_intent="空间质感说明",
        shot_type="全景",
        shot_purpose="说明环境",
        primary_subject="城墙纹理",
        world_elements=("砖石", "阴影", "墙面"),
    )

    documentary_package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style={"style_kind": "Documentary"},
    )[0]
    serious_package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style={"style_kind": "SERIOUS DOCUMENTARY"},
    )[0]

    assert documentary_package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }
    assert serious_package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }


def test_usage_planner_reads_resolved_style_spec_positive_documentary_signals():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="镜头缓慢扫过城墙纹理。",
        visual_goal="表现朴素、克制的记录感",
        prompt_intent="空间质感说明",
        shot_type="全景",
        shot_purpose="说明环境",
        primary_subject="城墙纹理",
        world_elements=("砖石", "阴影", "墙面"),
    )
    documentary_style = ResolvedStyleSpec(
        style_kind="visual_only",
        prompt_template="Documentary visual language, restrained composition, {prompt}",
    )
    serious_style = ResolvedStyleSpec(
        style_kind="visual_only",
        style_profile={"shape_language": "SERIOUS DOCUMENTARY camera language"},
    )

    documentary_package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=documentary_style,
    )[0]
    serious_package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=serious_style,
    )[0]

    assert documentary_package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }
    assert serious_package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }


def test_usage_planner_ignores_resolved_style_spec_negative_documentary_signals():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古城街巷的生活记忆。",
        visual_goal="表现轻松的文化讲解氛围",
        prompt_intent="讲解地方文化",
        shot_type="中景",
        shot_purpose="叙事说明",
        primary_subject="古城街巷与生活细节",
        world_elements=("街巷", "摊位", "行人"),
    )
    style = ResolvedStyleSpec(
        style_kind="visual_only",
        prompt_template="bright travel illustration, {prompt}",
        negative_prompt="avoid Documentary style",
        style_profile={
            "shape_language": "friendly rounded cartoon language",
            "negative_rules": "avoid SERIOUS DOCUMENTARY tone",
        },
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=style,
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE


def test_usage_planner_ignores_resolved_style_spec_raw_content_documentary_signal():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古城街巷的生活记忆。",
        visual_goal="表现轻松的文化讲解氛围",
        prompt_intent="讲解地方文化",
        shot_type="中景",
        shot_purpose="叙事说明",
        primary_subject="古城街巷与生活细节",
        world_elements=("街巷", "摊位", "行人"),
    )
    style = ResolvedStyleSpec(
        style_kind="visual_only",
        prompt_template="bright travel illustration, {prompt}",
        negative_prompt="avoid documentary style",
        style_profile={
            "shape_language": "friendly rounded cartoon language",
            "negative_rules": "avoid serious documentary tone",
        },
        raw_content="bright travel illustration, avoid documentary style",
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=style,
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE


def test_usage_planner_ignores_nested_negative_rules_in_mapping_resolved_style():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古城街巷的生活记忆。",
        visual_goal="表现轻松的文化讲解氛围",
        prompt_intent="讲解地方文化",
        shot_type="中景",
        shot_purpose="叙事说明",
        primary_subject="古城街巷与生活细节",
        world_elements=("街巷", "摊位", "行人"),
    )
    style = {
        "style_kind": "visual_only",
        "prompt_template": "bright travel illustration, {prompt}",
        "style_profile": {
            "shape_language": "friendly rounded cartoon language",
            "negative_rules": "avoid SERIOUS DOCUMENTARY tone",
        },
    }

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=style,
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE


def test_usage_planner_ignores_raw_content_in_mapping_resolved_style():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古城街巷的生活记忆。",
        visual_goal="表现轻松的文化讲解氛围",
        prompt_intent="讲解地方文化",
        shot_type="中景",
        shot_purpose="叙事说明",
        primary_subject="古城街巷与生活细节",
        world_elements=("街巷", "摊位", "行人"),
    )
    style = {
        "style_kind": "visual_only",
        "prompt_template": "bright travel illustration, {prompt}",
        "style_profile": {
            "shape_language": "friendly rounded cartoon language",
            "negative_rules": "avoid serious documentary tone",
        },
        "raw_content": "bright travel illustration, avoid documentary style",
    }

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_profile(),
        resolved_style=style,
    )[0]

    assert package.ip_presence_type is IPPresenceType.BALANCED_NARRATIVE


def test_usage_planner_reads_real_scene_cast_to_dict_metadata_ip_presence_type():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古城路线从地图上展开。",
        visual_goal="表现路线总览",
        prompt_intent="旅行路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)
    scene_cast = SceneCast(
        scene_cast_id="cast_1",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id=plan.plan_id,
        frame_id=plan.frames[0].frame_id,
        asset_bible_id="asset_bible_1",
        metadata={"ip_presence_type": "strong_identity"},
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={plan.frames[0].frame_id: scene_cast.to_dict()},
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY


def test_usage_planner_reads_real_scene_cast_to_dict_metadata_presence_type():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="古城路线从地图上展开。",
        visual_goal="表现路线总览",
        prompt_intent="旅行路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)
    scene_cast = SceneCast(
        scene_cast_id="cast_1",
        workspace_id="workspace_1",
        project_id="project_1",
        storyboard_plan_id=plan.plan_id,
        frame_id=plan.frames[0].frame_id,
        asset_bible_id="asset_bible_1",
        metadata={"presence_type": "strong_identity"},
    )

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        scene_casts_by_frame={plan.frames[0].frame_id: scene_cast.to_dict()},
    )[0]

    assert package.ip_presence_type is IPPresenceType.STRONG_IDENTITY
