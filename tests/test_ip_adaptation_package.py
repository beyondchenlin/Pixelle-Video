"""Test IPFrameAdaptationPackage creation, validation, and roundtrip."""

from __future__ import annotations

import pytest

from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
    IPRoleSlot,
)


def _make_pkg(**overrides):
    defaults = {
        "frame_id": "frame_0001",
        "ip_presence_type": IPPresenceType.BALANCED_NARRATIVE,
        "presence_mode": "guide",
        "semantic_reason": "narrative frame benefits from IP guide",
        "must_not_replace": ("正定古城",),
        "identity_anchors_visible": ("白色卡通兔子", "长耳朵", "蓝色领带"),
        "identity_anchors_suppressed": (),
        "identity_color_terms": ("纯白色身体", "宝蓝色领带"),
        "outfit_theme": "轻便文旅休闲装",
        "outfit_condition": None,
        "accessories": ("导览旗",),
        "action": "自然陪伴并指向场景重点",
        "expression": "温和好奇",
        "pose": "侧身站立",
        "camera_relationship": "mid-ground guide subject",
        "depth_layer": "middle",
        "interaction_target": "正定古城",
        "continuity_from_previous": None,
        "appearance_description": "白色卡通兔子替换画面配角位置",
        "role_slot": IPRoleSlot.SUPPORTING,
        "shot_fit_notes": "IP should support the scene",
        "image_text_plan": IPImageTextPlan(
            summary_text="正定古城",
            visible_text_whitelist=("正定古城",),
        ),
        "prompt_weight": 0.7,
        "negative_constraints": ("避免角色悬浮", "不能替代画面中的历史建筑"),
    }
    defaults.update(overrides)
    return IPFrameAdaptationPackage(**defaults)


# ── construction ───────────────────────────────────────────────────────


def test_full_construction_succeeds():
    pkg = _make_pkg()
    assert pkg.frame_id == "frame_0001"
    assert pkg.ip_presence_type == IPPresenceType.BALANCED_NARRATIVE
    assert pkg.appearance_description is not None


def test_minimal_construction_succeeds():
    pkg = IPFrameAdaptationPackage(
        frame_id="frame_min",
        ip_presence_type=IPPresenceType.ABSENT,
    )
    assert pkg.frame_id == "frame_min"
    assert pkg.ip_presence_type == IPPresenceType.ABSENT
    assert pkg.presence_mode is None
    assert pkg.must_not_replace == ()


def test_frame_id_must_not_be_empty():
    with pytest.raises(ValueError):
        IPFrameAdaptationPackage(
            frame_id="",
            ip_presence_type=IPPresenceType.ABSENT,
        )


def test_frame_id_must_not_be_whitespace():
    with pytest.raises(ValueError):
        IPFrameAdaptationPackage(
            frame_id="   ",
            ip_presence_type=IPPresenceType.ABSENT,
        )


# ── all presence types accepted ────────────────────────────────────────


def test_all_presence_types_accepted():
    for pt in IPPresenceType:
        pkg = IPFrameAdaptationPackage(
            frame_id="frame_test",
            ip_presence_type=pt,
        )
        assert pkg.ip_presence_type == pt


# ── prompt_weight validation ───────────────────────────────────────────


def test_prompt_weight_accepts_finite_number():
    pkg = _make_pkg(prompt_weight=0.5)
    assert pkg.prompt_weight == 0.5


def test_prompt_weight_rejects_string():
    with pytest.raises(ValueError):
        _make_pkg(prompt_weight="0.5")


def test_prompt_weight_rejects_infinity():
    with pytest.raises(ValueError):
        _make_pkg(prompt_weight=float("inf"))


def test_prompt_weight_rejects_nan():
    with pytest.raises(ValueError):
        _make_pkg(prompt_weight=float("nan"))


# ── role_slot validation ───────────────────────────────────────────────


def test_role_slot_from_string():
    pkg = _make_pkg(role_slot="protagonist")
    assert pkg.role_slot == IPRoleSlot.PROTAGONIST


def test_role_slot_none_allowed():
    pkg = _make_pkg(role_slot=None)
    assert pkg.role_slot is None


def test_role_slot_invalid_string_raises():
    with pytest.raises(ValueError):
        _make_pkg(role_slot="not_a_valid_role")


# ── empty string fields become None ────────────────────────────────────


def test_empty_string_fields_become_none():
    pkg = IPFrameAdaptationPackage(
        frame_id="frame_x",
        ip_presence_type=IPPresenceType.ABSENT,
        appearance_description="  ",
        action="",
        outfit_theme="   ",
    )
    assert pkg.appearance_description is None
    assert pkg.action is None
    assert pkg.outfit_theme is None


# ── to_dict / from_dict roundtrip ──────────────────────────────────────


def test_full_roundtrip():
    original = _make_pkg()
    d = original.to_dict()
    restored = IPFrameAdaptationPackage.from_dict(d)
    assert restored.frame_id == original.frame_id
    assert restored.ip_presence_type == original.ip_presence_type
    assert restored.presence_mode == original.presence_mode
    assert restored.prompt_weight == original.prompt_weight
    assert set(restored.identity_anchors_visible) == set(original.identity_anchors_visible)
    assert set(restored.identity_color_terms) == set(original.identity_color_terms)
    assert restored.role_slot == original.role_slot
    assert restored.image_text_plan is not None


def test_minimal_roundtrip():
    original = IPFrameAdaptationPackage(
        frame_id="frame_min",
        ip_presence_type=IPPresenceType.ABSENT,
    )
    d = original.to_dict()
    restored = IPFrameAdaptationPackage.from_dict(d)
    assert restored.frame_id == "frame_min"
    assert restored.ip_presence_type == IPPresenceType.ABSENT


def test_to_dict_includes_all_keys():
    pkg = _make_pkg()
    d = pkg.to_dict()
    for key in (
        "frame_id", "ip_presence_type", "presence_mode", "semantic_reason",
        "identity_anchors_visible", "identity_color_terms", "appearance_description",
        "role_slot", "prompt_weight", "negative_constraints",
    ):
        assert key in d


# ── identity_anchors_visible for absent type ───────────────────────────


def test_absent_type_has_empty_visible_anchors():
    pkg = IPFrameAdaptationPackage(
        frame_id="frame_absent",
        ip_presence_type=IPPresenceType.ABSENT,
    )
    assert pkg.identity_anchors_visible == ()


# ── image_text_plan integration ────────────────────────────────────────


def test_image_text_plan_roundtrip():
    itp = IPImageTextPlan(
        summary_text="测试标题",
        scene_text=("场景文字",),
        visible_text_whitelist=("测试标题", "场景文字"),
    )
    pkg = _make_pkg(image_text_plan=itp)
    assert pkg.image_text_plan is not None
    assert pkg.image_text_plan.summary_text == "测试标题"

    d = pkg.to_dict()
    restored = IPFrameAdaptationPackage.from_dict(d)
    assert restored.image_text_plan is not None
    assert restored.image_text_plan.summary_text == "测试标题"


def test_invalid_image_text_plan_type_raises():
    with pytest.raises(ValueError, match="image_text_plan"):
        _make_pkg(image_text_plan={"not": "valid"})
