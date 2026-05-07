"""Test IPUsagePlanner presence mode determination for all 6 IPPresenceType values."""

from __future__ import annotations

from typing import Any

from pixelle_video.models.ip_prompt_planning import IPPresenceType
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.ip_usage_planner import IPUsagePlanner


def _make_ip_profile(**overrides: Any) -> Any:
    from pixelle_video.models.asset_bible import IPProfile

    return IPProfile(
        ip_profile_id="ip_test_001",
        workspace_id="ws_test",
        project_id="proj_test",
        name="白兔导游",
        identity_lock=("白色卡通兔子", "长耳朵", "蓝色领带"),
        identity_anchors=("圆脸", "红色腮红"),
        identity_suppression_rules=(),
        semantic_boundary=("不能替代历史人物",),
        negative_constraints=("避免悬浮",),
        color_palette={
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"},
        },
        role_presets=("导游讲解者", "场景参与者"),
        presence_spectrum=("全身出镜", "半身出镜"),
        adaptable_slots=("服装", "道具", "动作姿势"),
        **overrides,
    )


def _make_frame(index: int = 1, **overrides: Any) -> StoryboardPlanFrame:
    defaults: dict[str, Any] = {
        "index": index,
        "source_text": "古城正定是一座千年古城",
        "visual_goal": "展示正定古城的南城门",
        "prompt_intent": "建立古城空间感",
        "frame_id": f"frame_{index:04d}",
        "shot_type": "中远景",
        "shot_purpose": "建立场景",
        "primary_subject": "正定古城南城门",
    }
    defaults.update(overrides)
    return StoryboardPlanFrame(**defaults)


def _make_storyboard_plan(frames: list[StoryboardPlanFrame]) -> StoryboardPlan:
    import hashlib

    source = " ".join(f.source_text for f in frames)
    return StoryboardPlan(
        plan_id="test_plan_01",
        revision=1,
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        resolved_scene_count=len(frames),
        source_text=source,
        source_digest=hashlib.sha256(source.encode()).hexdigest(),
        frames=tuple(frames),
    )


def _plan_frame(frame: StoryboardPlanFrame, **kwargs: Any) -> Any:
    planner = IPUsagePlanner()
    ip_profile = kwargs.pop("ip_profile", _make_ip_profile())
    return planner.plan_frame(frame=frame, ip_profile=ip_profile, **kwargs)


# ── protected subject → LOW_INTRUSION ──────────────────────────────────


def test_protected_subject_buddha_yields_low_intrusion():
    frame = _make_frame(
        source_text="大佛寺的佛祖金身庄严无比",
        primary_subject="佛祖金身",
        visual_goal="表现佛祖金身的庄严感",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.LOW_INTRUSION
    assert pkg.prompt_weight == 0.3
    assert pkg.presence_mode == "ambient"


def test_protected_subject_historical_building_yields_low_intrusion():
    frame = _make_frame(
        index=3,
        primary_subject="历史建筑",
        source_text="这座历史建筑已经列入严肃历史保护名录",
        shot_purpose="知识讲解",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.LOW_INTRUSION
    assert "不能替代历史人物" in pkg.negative_constraints


# ── pure landscape → SYMBOLIC_ONLY ─────────────────────────────────────


def test_pure_landscape_frame_yields_symbolic_only():
    frame = _make_frame(
        source_text="空镜——远山和河流",
        visual_goal="展示纯风景",
        primary_subject="远山河流",
        shot_type="远景",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.SYMBOLIC_ONLY
    assert pkg.prompt_weight == 0.2
    assert pkg.presence_mode == "symbolic"
    # Only 1 anchor visible for symbolic mode
    assert len(pkg.identity_anchors_visible) <= 1


# ── ip hero frame → STRONG_IDENTITY ────────────────────────────────────


def test_ip_hero_frame_yields_strong_identity():
    frame = _make_frame(
        source_text="此刻白兔导游站在古城门前面向观众介绍",
        primary_subject="白兔导游、古城南城门",
        visual_goal="IP主角强露出，面向观众介绍古城",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.STRONG_IDENTITY
    assert pkg.prompt_weight == 0.9
    assert pkg.presence_mode == "hero"
    assert len(pkg.identity_anchors_visible) >= 3


def test_ip_name_in_text_yields_strong_identity():
    frame = _make_frame(
        source_text="白兔导游站在古城门前面向观众介绍",
        visual_goal="IP主角强露出",
        primary_subject="白兔导游、古城南城门",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.STRONG_IDENTITY


# ── opening / establishing frame → SCENE_INTEGRATED ────────────────────


def test_opening_frame_yields_scene_integrated():
    frame = _make_frame(
        index=1,
        source_text="从长乐门出发，这是正定的南大门",
        visual_goal="建立古城空间和旅程开篇",
        primary_subject="正定长乐门、青砖城墙",
        shot_type="中远景",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.SCENE_INTEGRATED
    assert pkg.prompt_weight == 0.6
    assert pkg.presence_mode == "support"


# ── narrative frame → BALANCED_NARRATIVE ───────────────────────────────


def test_narrative_frame_yields_balanced_narrative():
    frame = _make_frame(
        source_text="导游开始介绍正定的七处历史印记",
        visual_goal="讲述第一处印记的历史故事",
        primary_subject="古城建筑细节",
        shot_purpose="知识讲解",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.BALANCED_NARRATIVE
    assert pkg.prompt_weight == 0.7
    assert pkg.presence_mode == "narrative"


# ── default fallback → BALANCED_NARRATIVE ──────────────────────────────


def test_default_frame_yields_balanced_narrative():
    frame = _make_frame(
        index=3,
        source_text="一般场景描述",
        visual_goal="展示古城风貌",
        primary_subject="古城街景",
        shot_purpose="叙事",
    )
    pkg = _plan_frame(frame)
    assert pkg.ip_presence_type == IPPresenceType.BALANCED_NARRATIVE


# ── scene_cast override ────────────────────────────────────────────────


def test_scene_cast_overrides_presence_type():
    frame = _make_frame(
        source_text="空镜——远山和河流",
        visual_goal="展示纯风景",
        primary_subject="远山河流",
    )
    scene_cast = {"ip_presence_type": "strong_identity"}
    pkg = _plan_frame(frame, scene_cast=scene_cast)
    assert pkg.ip_presence_type == IPPresenceType.STRONG_IDENTITY


def test_scene_cast_metadata_overrides_presence_type():
    frame = _make_frame(
        source_text="空镜——远山和河流",
        primary_subject="远山河流",
    )
    scene_cast = {"metadata": {"ip_presence_type": "absent"}}
    pkg = _plan_frame(frame, scene_cast=scene_cast)
    assert pkg.ip_presence_type == IPPresenceType.ABSENT


# ── batch planning ─────────────────────────────────────────────────────


def test_batch_plan_returns_correct_count():
    frames = [
        _make_frame(index=1, source_text="从长乐门出发", primary_subject="古城门"),
        _make_frame(index=2, source_text="导游讲述古城历史", primary_subject="历史遗迹"),
        _make_frame(index=3, source_text="空镜——远山", primary_subject="远山"),
    ]
    plan = _make_storyboard_plan(frames)
    ip_profile = _make_ip_profile()
    planner = IPUsagePlanner()
    packages = planner.plan_batch(storyboard_plan=plan, ip_profile=ip_profile)
    assert len(packages) == 3
    assert all(pkg.frame_id == f"frame_{i+1:04d}" for i, pkg in enumerate(packages))


# ── identity color terms extraction ────────────────────────────────────


def test_identity_color_terms_extracted_from_palette():
    frame = _make_frame()
    pkg = _plan_frame(frame)
    assert "纯白色身体" in pkg.identity_color_terms
    assert "鲜明宝蓝色领带" in pkg.identity_color_terms


# ── image text plan ────────────────────────────────────────────────────


def test_image_text_plan_present_for_non_absent_frames():
    frame = _make_frame()
    pkg = _plan_frame(frame)
    assert pkg.image_text_plan is not None
    assert len(pkg.image_text_plan.text_safety_rules) == 0


def test_image_text_plan_includes_whitelist():
    ip_profile = _make_ip_profile(visible_text_whitelist=("正定古城", "长乐门"))
    frame = _make_frame(
        source_text="从长乐门出发",
        primary_subject="正定古城",
    )
    pkg = _plan_frame(frame, ip_profile=ip_profile)
    assert pkg.image_text_plan is not None
    assert "正定古城" in pkg.image_text_plan.visible_text_whitelist
    assert "长乐门" in pkg.image_text_plan.visible_text_whitelist


# ── world_profile_text → LOW_INTRUSION ──────────────────────────────────


def test_world_profile_protected_subject_yields_low_intrusion():
    from pixelle_video.models.content_world import ContentWorldProfile

    frame = _make_frame(index=3, source_text="普通场景", primary_subject="古城")
    world = ContentWorldProfile(story_constraints="本场景涉及严肃历史内容")
    pkg = _plan_frame(frame, generation_world_profile=world)
    assert pkg.ip_presence_type == IPPresenceType.LOW_INTRUSION


def test_world_profile_low_intrusion_guidance_yields_low_intrusion():
    from pixelle_video.models.content_world import ContentWorldProfile

    frame = _make_frame(index=3, source_text="普通场景", primary_subject="古城")
    world = ContentWorldProfile(ip_integration_guidance="本场景需低侵入处理，IP只允许象征性出现")
    pkg = _plan_frame(frame, generation_world_profile=world)
    assert pkg.ip_presence_type == IPPresenceType.LOW_INTRUSION


# ── serious documentary style → LOW_INTRUSION ────────────────────────────


def test_serious_documentary_style_yields_low_intrusion():
    from pixelle_video.models.style_resolution import ResolvedStyleSpec

    frame = _make_frame(index=3, source_text="普通场景", primary_subject="古城")
    style = ResolvedStyleSpec(style_kind="visual_only", prompt_template="严肃纪实纪录片风格")
    pkg = _plan_frame(frame, resolved_style=style)
    assert pkg.ip_presence_type == IPPresenceType.LOW_INTRUSION


# ── negative constraints ───────────────────────────────────────────────


def test_negative_constraints_include_ip_profile_constraints():
    frame = _make_frame()
    pkg = _plan_frame(frame)
    assert "避免悬浮" in pkg.negative_constraints
    assert "不能替代历史人物" in pkg.negative_constraints
