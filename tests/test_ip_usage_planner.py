import json

import pytest

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.content_world import ContentWorldProfile
from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPPresenceType,
    IPRoleSlot,
)
from pixelle_video.models.scene_cast import SceneCast
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.models.style_resolution import ResolvedStyleSpec
from pixelle_video.services.ip_usage_planner import (
    IPFrameAppearancePlanner,
    IPUsagePlanner,
    _rule_based_role_selection,
)


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


def test_identity_color_terms_reads_workbench_palette_entries():
    from pixelle_video.services.ip_usage_planner import _identity_color_terms

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Guide",
        identity_lock=("white rabbit",),
        color_palette={
            "rule_1": {"hex": "#FFFFFF", "prompt": "white body"},
            "rule_2": {"prompt": "bright blue tie"},
        },
    )

    assert _identity_color_terms(profile) == ("white body", "bright blue tie")


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
    assert "正定长乐门" in package.must_not_replace


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

    assert package.image_text_plan.summary_text == "长乐门"
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
    assert package.presence_mode == "narrative"


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


def test_usage_planner_uses_world_constraints_for_protected_subjects():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="导览员讲述古寺壁画中的宗教故事。",
        visual_goal="表现宗教人物与古寺壁画的庄重感",
        prompt_intent="尊重宗教主体",
        shot_type="全景",
        shot_purpose="历史说明",
        primary_subject="佛像与古寺壁画",
        world_elements=("古寺", "壁画"),
    )
    frame = _plan(frame).frames[0]

    package = IPUsagePlanner().plan_frame(
        frame=frame,
        ip_profile=_profile(),
        generation_world_profile=ContentWorldProfile(
            story_constraints="不能让 IP 替代佛像、宗教人物或历史建筑。",
            ip_integration_guidance="只允许低侵入或不出现。",
        ),
    )

    assert package.ip_presence_type in {
        IPPresenceType.LOW_INTRUSION,
        IPPresenceType.SYMBOLIC_ONLY,
        IPPresenceType.ABSENT,
    }
    assert "佛像与古寺壁画" in package.must_not_replace


def test_usage_planner_world_guidance_does_not_override_scene_cast():
    frame = StoryboardPlanFrame(
        index=1,
        source_text="品牌向导角色出现在古城路线图旁。",
        visual_goal="表现路线图与角色陪伴说明",
        prompt_intent="路线说明",
        primary_subject="正定古城路线图",
    )
    plan = _plan(frame)

    package = IPUsagePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_profile(),
        generation_world_profile={
            "story_constraints": "避免强露出。",
            "ip_integration_guidance": "低侵入陪伴式融入。",
        },
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


# ── IPFrameAppearancePlanner tests ───────────────────────────────────────


def _universal_ip_profile():
    """An IPProfile with the new universal-actor fields populated."""
    return IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="正定向导兔",
        identity_lock=("白色卡通兔子", "蓝色领结", "长耳朵"),
        visual_summary="白色卡通兔子，蓝色领结，长耳朵，圆润脸型。",
        minimal_traits=("蓝色领结一角", "长耳朵轮廓"),
        role_presets=(
            "导游讲解者：温和的讲解者，面向场景做介绍手势",
            "情感陪伴者：安静的陪伴角色，与画面主体自然互动",
            "路人观察者：融入环境背景",
            "画面主角：占据画面主体位置",
            "画外不出镜：不出现在画面中",
        ),
        presence_spectrum=(
            "全身出镜：完整呈现角色形象",
            "半身出镜：展示上半身和表情",
            "局部细节：只露出特征性局部",
            "远景融入：作为场景中的小元素融入背景",
            "完全不出镜：该帧不出现IP角色",
        ),
        adaptable_slots=("服装配饰", "手持道具", "动作姿势"),
    )


def _plan_two_frames():
    frames = [
        StoryboardPlanFrame(
            index=1,
            source_text="从长乐门出发，走进正定古城。",
            visual_goal="表现长乐门作为旅程入口的历史感",
            prompt_intent="建立古城空间和导览开篇",
            shot_type="中远景",
            primary_subject="长乐门",
        ),
        StoryboardPlanFrame(
            index=2,
            source_text="街巷里飘来美食的香气，市井生活热闹非凡。",
            visual_goal="表现古城美食街巷的生活气息",
            prompt_intent="美食文化展示",
            shot_type="中景",
            primary_subject="古城美食街巷",
        ),
    ]
    return StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frames[0].source_text + frames[1].source_text,
        frames=frames,
    )


@pytest.mark.asyncio
async def test_appearance_planner_llm_receives_full_actorization_context():
    captured: dict[str, str] = {}

    async def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            [
                {
                    "frame_index": 0,
                    "role_slot": "supporting",
                    "role_label": "scene guide",
                    "presence_level": "half body",
                    "appearance_description": "white rabbit guide blends into the market light",
                    "reason": "supports the travel scene",
                }
            ]
        )

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Market Guide",
        identity_lock=("white rabbit body", "long ears"),
        identity_anchors=("blue necktie",),
        identity_suppression_rules=("do not show mascot logo",),
        visual_summary="white rabbit guide with long ears and a blue necktie",
        minimal_traits=("blue necktie glimpse",),
        semantic_boundary=("must remain a guide character",),
        negative_constraints=("must not replace local vendors",),
        role_presets=("quiet side guide",),
        presence_spectrum=("scene integrated side guide",),
        adaptable_slots=("market basket prop", "walking pose"),
        default_slot_preference="prefer_supporting",
        style_hint="warm travel illustration",
        world_hint="heritage market",
    )
    world = ContentWorldProfile(
        summary="morning travel market",
        story_constraints="do not replace the street vendor",
        ip_integration_guidance="the IP should guide quietly from the side",
    )
    frame = StoryboardPlanFrame(
        index=1,
        frame_id="frame_1",
        source_text="A market route opens.",
        visual_goal="show the travel path",
        prompt_intent="travel opening",
        primary_subject="street vendor",
    )

    await IPFrameAppearancePlanner(llm_client=fake_llm).plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=profile,
        generation_world_profile=world,
        scene_casts_by_frame={"frame_1": {"metadata": {"ip_presence_type": "scene_integrated"}}},
    )

    prompt = captured["prompt"]
    for token in (
        "identity_lock",
        "identity_anchors",
        "visual_summary",
        "minimal_traits",
        "semantic_boundary",
        "negative_constraints",
        "presence_spectrum",
        "adaptable_slots",
        "default_slot_preference",
        "generation_world_profile",
        "story_constraints",
        "ip_integration_guidance",
        "scene_cast_presence",
        "presence_type",
        "presence_mode",
        "semantic_reason",
        "must_not_replace",
        "identity_anchors_visible",
        "identity_anchors_suppressed",
    ):
        assert token in prompt
    for value in (
        "white rabbit body",
        "blue necktie",
        "blue necktie glimpse",
        "must remain a guide character",
        "must not replace local vendors",
        "market basket prop",
        "morning travel market",
        "do not replace the street vendor",
        "the IP should guide quietly from the side",
        "street vendor",
        "do not show mascot logo",
        "scene_integrated",
    ):
        assert value in prompt
    assert '"scene_cast_presence": "scene_integrated"' in prompt


@pytest.mark.asyncio
async def test_appearance_planner_llm_omits_invalid_scene_cast_presence():
    captured: dict[str, str] = {}

    async def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps(
            [
                {
                    "frame_index": 0,
                    "role_slot": "supporting",
                    "role_label": "scene guide",
                    "presence_level": "half body",
                    "appearance_description": "white rabbit guide remains a quiet side character",
                    "reason": "invalid SceneCast directive should not affect planning",
                }
            ]
        )

    frame = StoryboardPlanFrame(
        index=1,
        frame_id="frame_1",
        source_text="A market route opens.",
        visual_goal="show the travel path",
        prompt_intent="travel opening",
        primary_subject="street vendor",
    )

    await IPFrameAppearancePlanner(llm_client=fake_llm).plan_batch(
        storyboard_plan=_plan(frame),
        ip_profile=_universal_ip_profile(),
        scene_casts_by_frame={"frame_1": {"metadata": {"ip_presence_type": "giant_logo_takeover"}}},
    )

    prompt = captured["prompt"]
    assert "giant_logo_takeover" not in prompt
    assert '"scene_cast_presence": null' in prompt


@pytest.mark.asyncio
async def test_appearance_planner_populates_appearance_description():
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )

    assert len(packages) == 2
    for pkg in packages:
        assert isinstance(pkg.appearance_description, str)
        assert len(pkg.appearance_description) >= 20
        assert "白色卡通兔子" in pkg.appearance_description
        assert isinstance(pkg.visual_identity, str)
        assert len(pkg.visual_identity) > 0
        assert "古城文旅向导" not in pkg.visual_identity


@pytest.mark.asyncio
async def test_appearance_planner_fields_delegated_to_llm_are_none():
    """outfit/accessories/action/expression/pose are delegated to the LLM image prompt layer."""
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )

    for pkg in packages:
        assert pkg.outfit_theme is None
        assert pkg.accessories == ()
        assert pkg.action is None
        assert pkg.expression is None
        assert pkg.pose is None


@pytest.mark.asyncio
async def test_appearance_planner_produces_valid_descriptions_for_all_frames():
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )

    for pkg in packages:
        assert isinstance(pkg.appearance_description, str)
        assert len(pkg.appearance_description) > 0
        assert "白色卡通兔子" in pkg.appearance_description


@pytest.mark.asyncio
async def test_appearance_planner_uses_role_presets_from_ip_profile():
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )

    pkg0 = packages[0]
    assert pkg0.role_slot is not None
    assert "白色卡通兔子" in pkg0.appearance_description
    assert "蓝色领结" in pkg0.appearance_description


@pytest.mark.asyncio
async def test_appearance_planner_tracks_continuity_between_frames():
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )

    assert packages[0].continuity_from_previous is None
    assert isinstance(packages[1].continuity_from_previous, str)
    assert "上一帧" in packages[1].continuity_from_previous


@pytest.mark.asyncio
async def test_appearance_planner_different_frames_preserve_role_and_visual_identity():
    travel_frame = StoryboardPlanFrame(
        index=1,
        source_text="古城墙下游人如织，导游讲述历史。",
        visual_goal="古城文旅",
        prompt_intent="文旅展示",
        primary_subject="古城墙",
    )
    food_frame = StoryboardPlanFrame(
        index=1,
        source_text="餐厅里火锅沸腾，美食的香气弥漫。",
        visual_goal="美食展示",
        prompt_intent="美食内容",
        primary_subject="火锅",
    )
    tech_frame = StoryboardPlanFrame(
        index=1,
        source_text="数据中心的屏幕上，代码飞速滚动。",
        visual_goal="科技展示",
        prompt_intent="科技内容",
        primary_subject="数据屏幕",
    )

    planner = IPFrameAppearancePlanner()
    profile = _universal_ip_profile()

    def _make_plan(frame):
        return StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text=frame.source_text,
            frames=[frame],
        )

    travel_pkg = (await planner.plan_batch(storyboard_plan=_make_plan(travel_frame), ip_profile=profile))[0]
    food_pkg = (await planner.plan_batch(storyboard_plan=_make_plan(food_frame), ip_profile=profile))[0]
    tech_pkg = (await planner.plan_batch(storyboard_plan=_make_plan(tech_frame), ip_profile=profile))[0]

    for pkg in (travel_pkg, food_pkg, tech_pkg):
        assert pkg.role_slot is not None
        assert "白色卡通兔子" in pkg.appearance_description
        assert pkg.outfit_theme is None


@pytest.mark.asyncio
async def test_appearance_planner_handles_skeletal_ip_profile():
    skeletal = IPProfile(
        ip_profile_id="ip_min",
        workspace_id="workspace_1",
        project_id="project_1",
        name="Minimal",
        identity_lock=("白色卡通兔子",),
    )
    frame = StoryboardPlanFrame(
        index=1,
        source_text="日常散步场景。",
        visual_goal="日常",
        prompt_intent="日常",
        primary_subject="公园",
    )
    plan = StoryboardPlan.build(
        mode="sentence",
        count_mode="auto",
        requested_scene_count=None,
        source_text=frame.source_text,
        frames=[frame],
    )

    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=skeletal,
    )

    assert len(packages) == 1
    assert len(packages[0].appearance_description) > 0


# ── IPRoleSlot and replacement semantics tests ──────────────────────────


def test_role_slot_enum_values():
    assert IPRoleSlot.PROTAGONIST == "protagonist"
    assert IPRoleSlot.SUPPORTING == "supporting"
    assert IPRoleSlot.PASSERBY == "passerby"
    assert IPRoleSlot.ABSENT == "absent"


def test_rule_based_role_selection_returns_role_slot_tuple():
    profile = _universal_ip_profile()
    from pixelle_video.models.ip_prompt_planning import IPPresenceType as PT

    # STRONG_IDENTITY → protagonist
    slot, label, desc = _rule_based_role_selection(profile, PT.STRONG_IDENTITY)
    assert slot is IPRoleSlot.PROTAGONIST
    assert isinstance(label, str) and len(label) > 0
    assert isinstance(desc, str) and len(desc) > 0

    # BALANCED_NARRATIVE → supporting
    slot, label, desc = _rule_based_role_selection(profile, PT.BALANCED_NARRATIVE)
    assert slot is IPRoleSlot.SUPPORTING

    # LOW_INTRUSION → passerby
    slot, label, desc = _rule_based_role_selection(profile, PT.LOW_INTRUSION)
    assert slot is IPRoleSlot.PASSERBY

    # ABSENT → absent
    slot, label, desc = _rule_based_role_selection(profile, PT.ABSENT)
    assert slot is IPRoleSlot.ABSENT
    assert label == "画外不出镜"
    assert desc == "完全不出镜"

    # SYMBOLIC_ONLY → passerby
    slot, label, desc = _rule_based_role_selection(profile, PT.SYMBOLIC_ONLY)
    assert slot is IPRoleSlot.PASSERBY


def test_build_appearance_description_returns_visual_identity():
    """_build_appearance_description returns pure visual identity from IPProfile."""
    from pixelle_video.services.ip_usage_planner import _build_appearance_description

    profile = _universal_ip_profile()
    desc = _build_appearance_description(
        ip_profile=profile,
        role_slot=IPRoleSlot.SUPPORTING,
    )
    assert "白色卡通兔子" in desc
    assert "蓝色领结" in desc


def test_build_appearance_description_absent_returns_empty():
    from pixelle_video.services.ip_usage_planner import _build_appearance_description

    profile = _universal_ip_profile()
    desc = _build_appearance_description(
        ip_profile=profile,
        role_slot=IPRoleSlot.ABSENT,
    )
    assert desc == ""


def test_build_appearance_description_uses_visual_summary_when_available():
    from pixelle_video.services.ip_usage_planner import _build_appearance_description

    profile = _universal_ip_profile()
    desc = _build_appearance_description(
        ip_profile=profile,
        role_slot=IPRoleSlot.PROTAGONIST,
    )
    assert "圆润脸型" in desc


def test_ipframe_adaptation_package_serialization_preserves_role_slot():
    pkg = IPFrameAdaptationPackage(
        frame_id="frame_1",
        ip_presence_type=IPPresenceType.BALANCED_NARRATIVE,
        appearance_description="白色卡通兔子替换画面配角位置",
        role_slot=IPRoleSlot.SUPPORTING,
    )
    payload = pkg.to_dict()
    assert payload["role_slot"] == "supporting"
    restored = IPFrameAdaptationPackage.from_dict(payload)
    assert restored.role_slot is IPRoleSlot.SUPPORTING


def test_ipframe_adaptation_package_role_slot_none_by_default():
    pkg = IPFrameAdaptationPackage(
        frame_id="frame_1",
        ip_presence_type=IPPresenceType.ABSENT,
    )
    assert pkg.role_slot is None
    payload = pkg.to_dict()
    assert payload["role_slot"] is None
    restored = IPFrameAdaptationPackage.from_dict(payload)
    assert restored.role_slot is None


@pytest.mark.asyncio
async def test_appearance_planner_passes_role_slot_to_packages():
    plan = _plan_two_frames()
    packages = await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=plan,
        ip_profile=_universal_ip_profile(),
    )
    for pkg in packages:
        assert pkg.role_slot is not None
        assert isinstance(pkg.role_slot, IPRoleSlot)
    # Frame 1 (文旅 opening) should be SUPPORTING
    assert packages[0].role_slot is IPRoleSlot.SUPPORTING
    # Frame 2 (美食) with BALANCED_NARRATIVE → SUPPORTING
    assert packages[1].role_slot is IPRoleSlot.SUPPORTING


@pytest.mark.asyncio
async def test_appearance_planner_role_slot_matches_presence_type():
    """STRONG_IDENTITY → PROTAGONIST, ABSENT → ABSENT."""
    profile = _universal_ip_profile()

    hero_frame = StoryboardPlanFrame(
        index=1,
        source_text="正定向导兔引导观众探索古城。",
        visual_goal="IP英雄镜头",
        prompt_intent="强IP露出",
        primary_subject="正定向导兔",
    )
    absent_frame = StoryboardPlanFrame(
        index=1,
        source_text="纯风景空镜。",
        visual_goal="空镜",
        prompt_intent="风景",
        primary_subject="天空",
    )

    def _make_plan(frame):
        return StoryboardPlan.build(
            mode="sentence",
            count_mode="auto",
            requested_scene_count=None,
            source_text=frame.source_text,
            frames=[frame],
        )

    hero_pkg = (await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=_make_plan(hero_frame), ip_profile=profile
    ))[0]
    assert hero_pkg.role_slot is IPRoleSlot.PROTAGONIST
    assert "白色卡通兔子" in hero_pkg.appearance_description

    absent_pkg = (await IPFrameAppearancePlanner().plan_batch(
        storyboard_plan=_make_plan(absent_frame), ip_profile=profile
    ))[0]
    # Pure landscape → SYMBOLIC_ONLY → PASSERBY
    assert absent_pkg.role_slot is IPRoleSlot.PASSERBY
    assert absent_pkg.appearance_description != ""


def test_visible_anchors_excludes_identity_anchors_role_labels():
    """identity_anchors_visible 只含 identity_lock 纯视觉特征，不含 identity_anchors 中的角色标签。"""
    from pixelle_video.services.ip_usage_planner import _visible_anchors

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="TestIP",
        identity_lock=("白色卡通兔子", "蓝色领结"),
        identity_anchors=("古城文旅向导", "温和陪伴式讲解者"),
    )
    result = _visible_anchors(IPPresenceType.BALANCED_NARRATIVE, profile)
    assert "白色卡通兔子" in result
    assert "蓝色领结" in result
    assert "古城文旅向导" not in result
    assert "温和陪伴式讲解者" not in result


def test_build_visual_identity_excludes_role_labels():
    """_build_visual_identity 只返回纯视觉特征，不含角色标签。"""
    from pixelle_video.services.ip_usage_planner import _build_visual_identity

    profile = IPProfile(
        ip_profile_id="ip_main",
        workspace_id="workspace_1",
        project_id="project_1",
        name="TestIP",
        identity_lock=("白色卡通兔子", "蓝色领结"),
        identity_anchors=("古城文旅向导",),
        visual_summary=None,
    )
    result = _build_visual_identity(profile)
    assert "白色卡通兔子" in result
    assert "蓝色领结" in result
    assert "古城文旅向导" not in result


