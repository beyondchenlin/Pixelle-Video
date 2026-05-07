"""End-to-end IP pipeline test: AssetBible → IPUsagePlanner → IPFrameAdaptationPackage.

Covers the full chain from IPProfile definition through planning to prompt context injection.
"""

from __future__ import annotations

from typing import Any


def _make_ip_profile(**overrides: Any) -> Any:
    from pixelle_video.models.asset_bible import IPProfile

    defaults: dict[str, Any] = {
        "ip_profile_id": "ip_e2e_001",
        "workspace_id": "ws_e2e",
        "project_id": "proj_e2e",
        "name": "白兔导游",
        "identity_lock": ("白色卡通兔子", "长耳朵", "蓝色领带"),
        "identity_anchors": ("圆脸", "红色腮红"),
        "color_palette": {
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"},
        },
        "adaptable_slots": ("服装", "道具", "动作姿势"),
    }
    defaults.update(overrides)
    return IPProfile(**defaults)


def _make_frame(index: int = 1, **overrides: Any) -> Any:
    from pixelle_video.models.storyboard_plan import StoryboardPlanFrame

    defaults: dict[str, Any] = {
        "index": index,
        "source_text": f"测试场景 {index}",
        "visual_goal": "展示场景",
        "prompt_intent": "建立空间",
        "frame_id": f"frame_{index:04d}",
        "shot_type": "中景",
        "shot_purpose": "叙事",
        "primary_subject": "测试主体",
    }
    defaults.update(overrides)
    return StoryboardPlanFrame(**defaults)


# ── full planning pipeline ────────────────────────────────────────────────


def test_usage_planner_produces_valid_package_for_every_presence_type():
    from pixelle_video.models.ip_prompt_planning import IPPresenceType
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner

    ip_profile = _make_ip_profile()
    planner = IPUsagePlanner()

    scenarios = [
        (IPPresenceType.STRONG_IDENTITY, _make_frame(
            source_text="白兔导游站在古城门前介绍",
            primary_subject="白兔导游",
        )),
        (IPPresenceType.BALANCED_NARRATIVE, _make_frame(
            index=3,
            source_text="导游介绍正定历史",
            primary_subject="古城建筑",
            prompt_intent="叙事铺开",
            shot_purpose="知识讲解",
        )),
        (IPPresenceType.LOW_INTRUSION, _make_frame(
            source_text="佛祖金身法相庄严",
            primary_subject="佛祖金身",
        )),
        (IPPresenceType.SYMBOLIC_ONLY, _make_frame(
            index=3,
            source_text="空镜——远山和河流",
            primary_subject="远山",
            shot_type="远景",
            prompt_intent="风景切换过渡",
            shot_purpose="空镜过渡",
        )),
        (IPPresenceType.ABSENT, (
            _make_frame(index=4, source_text="空镜", primary_subject="天空", shot_purpose="空镜过渡"),
            {"ip_presence_type": "absent"},
        )),
    ]

    for expected_pt, frame_spec in scenarios:
        if isinstance(frame_spec, tuple):
            frame, scene_cast = frame_spec
        else:
            frame, scene_cast = frame_spec, None
        pkg = planner.plan_frame(frame=frame, ip_profile=ip_profile, scene_cast=scene_cast)
        assert pkg.ip_presence_type == expected_pt, f"Expected {expected_pt} for {frame.source_text}"
        assert pkg.frame_id == frame.frame_id
        assert isinstance(pkg.prompt_weight, float)


def test_appearance_planner_enriches_with_domain_fields():
    from pixelle_video.services.ip_usage_planner import (
        IPFrameAppearancePlanner,
        IPUsagePlanner,
    )

    ip_profile = _make_ip_profile()
    deterministic = IPUsagePlanner()
    base_pkg = deterministic.plan_frame(
        frame=_make_frame(source_text="古城导游讲解", primary_subject="城墙"),
        ip_profile=ip_profile,
    )

    appearance_planner = IPFrameAppearancePlanner()
    enriched = appearance_planner.plan_frame_appearance(
        frame=_make_frame(source_text="古城导游讲解", primary_subject="城墙"),
        ip_profile=ip_profile,
        base_package=base_pkg,
        frame_index=0,
        total_frames=5,
    )

    assert enriched.outfit_theme is None
    assert enriched.appearance_description is not None
    assert "白" in enriched.appearance_description or "兔子" in enriched.appearance_description
    assert enriched.role_slot is not None


# ── prompt context injection (e2e) ────────────────────────────────────────


def test_enrich_then_extract_roundtrip():
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    ip_profile = _make_ip_profile()
    frame = _make_frame(source_text="白兔导游站在古城门前讲解", primary_subject="白兔导游")
    planner = IPUsagePlanner()
    pkg = planner.plan_frame(frame=frame, ip_profile=ip_profile)

    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={"style_kind": "文旅纪实"},
    )

    ctx = result.frame_contexts[0]
    assert "ip_scene_description" in ctx
    assert isinstance(ctx["ip_scene_description"], str)
    assert isinstance(ctx["ip_negative_constraints"], list)
    assert isinstance(ctx["ip_image_text_plan"], dict)


def test_batch_plan_to_enrich_flow():
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    ip_profile = _make_ip_profile()
    frames = [
        _make_frame(index=1, source_text="从长乐门出发", primary_subject="古城门"),
        _make_frame(index=2, source_text="导游讲述古城历史", primary_subject="历史遗迹"),
        _make_frame(index=3, source_text="空镜——远山", primary_subject="远山"),
    ]
    import hashlib

    from pixelle_video.models.storyboard_plan import StoryboardPlan

    plan = StoryboardPlan(
        plan_id="test_e2e",
        revision=1,
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        resolved_scene_count=3,
        source_text=" ".join(f.source_text for f in frames),
        source_digest=hashlib.sha256(" ".join(f.source_text for f in frames).encode()).hexdigest(),
        frames=tuple(frames),
    )

    planner = IPUsagePlanner()
    packages = planner.plan_batch(storyboard_plan=plan, ip_profile=ip_profile)
    assert len(packages) == 3

    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=3,
        packages=packages,
        style_context={},
    )

    for i, ctx in enumerate(result.frame_contexts):
        assert "ip_scene_description" in ctx
        assert "ip_negative_constraints" in ctx
        assert isinstance(ctx["ip_negative_constraints"], list)


# ── no hex in prompt path ─────────────────────────────────────────────────


def test_enrich_output_contains_no_hex():
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    ip_profile = _make_ip_profile()
    frame = _make_frame(primary_subject="古城")
    planner = IPUsagePlanner()
    pkg = planner.plan_frame(frame=frame, ip_profile=ip_profile)

    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={},
    )

    scene_desc = result.frame_contexts[0].get("ip_scene_description", "")
    if scene_desc:
        assert "#" not in scene_desc, "Hex found in ip_scene_description"


# ── absent type flow ──────────────────────────────────────────────────────


def test_absent_type_produces_empty_appearance_description():
    from pixelle_video.services.ip_usage_planner import IPUsagePlanner
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    ip_profile = _make_ip_profile()
    frame = _make_frame(
        source_text="空镜",
        primary_subject="天空",
    )
    scene_cast = {"ip_presence_type": "absent"}
    planner = IPUsagePlanner()
    pkg = planner.plan_frame(frame=frame, ip_profile=ip_profile, scene_cast=scene_cast)

    assert pkg.ip_presence_type.value == "absent"

    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={},
    )

    assert result.frame_contexts[0].get("ip_scene_description", "") == ""
