"""Test hex color (#RRGGBB) never leaks into prompt text fields."""

from __future__ import annotations

import pytest

from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPImageTextPlan,
    IPPresenceType,
    IPRoleSlot,
)


def _make_package(**overrides):
    defaults = {
        "frame_id": "frame_0001",
        "ip_presence_type": IPPresenceType.STRONG_IDENTITY,
        "presence_mode": "hero",
        "semantic_reason": "test frame",
        "identity_anchors_visible": ("白色卡通兔子", "长耳朵"),
        "identity_color_terms": ("纯白色身体", "宝蓝色领带"),
        "appearance_description": "白色卡通兔子作为画面主角占据前景",
        "role_slot": IPRoleSlot.PROTAGONIST,
        "prompt_weight": 0.9,
        "negative_constraints": ("避免角色悬浮",),
    }
    defaults.update(overrides)
    return IPFrameAdaptationPackage(**defaults)


# ── hex rejection in string fields ─────────────────────────────────────


def test_appearance_description_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(appearance_description="白色兔子 #FFFFFF 占据前景")


def test_semantic_reason_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(semantic_reason="color #FF0000 is used")


def test_outfit_theme_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(outfit_theme="#0000FF 服装")


def test_action_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(action="#FFFFFF move")


def test_identity_color_terms_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(identity_color_terms=("#FFFFFF body",))


def test_negative_constraints_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        _make_package(negative_constraints=("avoid #FF0000",))


# ── IPImageTextPlan hex rejection ──────────────────────────────────────


def test_image_text_plan_summary_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        IPImageTextPlan(summary_text="#5A2A12 深棕色标题")


def test_image_text_plan_scene_text_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        IPImageTextPlan(scene_text=("长乐门 #AA0000",))


def test_image_text_plan_whitelist_rejects_hex_color():
    with pytest.raises(ValueError, match="hex"):
        IPImageTextPlan(visible_text_whitelist=("#FFFFFF",))


# ── natural language colors are accepted ───────────────────────────────


def test_natural_language_colors_accepted():
    pkg = _make_package(
        appearance_description="纯白色卡通兔子，蓝色领带，柔和粉色耳朵",
        identity_color_terms=("纯白色身体", "宝蓝色领带"),
    )
    assert "纯白色卡通兔子" in pkg.appearance_description


def test_image_text_plan_accepts_natural_colors():
    plan = IPImageTextPlan(
        summary_text="深棕色墨迹标题",
        scene_text=("旧金色匾额字",),
        visible_text_whitelist=("深墨色手写字",),
    )
    assert plan.summary_text == "深棕色墨迹标题"
    assert "旧金色匾额字" in plan.scene_text


# ── color palette hex is allowed (not prompt-facing) ───────────────────


def test_color_palette_hex_allowed_in_model():
    from pixelle_video.models.asset_bible import IPProfile

    profile = IPProfile(
        series_visual_signature_profile_id="ip_hex_test",
        workspace_id="ws_test",
        project_id="proj_test",
        name="测试角色",
        identity_lock=("白色猫",),
        identity_anchors=("蓝眼睛",),
        color_palette={
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "宝蓝色领带"},
        },
    )
    assert profile.color_palette["body"]["hex"] == "#FFFFFF"
    assert profile.color_palette["body"]["prompt"] == "纯白色身体"


# ── to_dict output contains no hex in prompt fields ────────────────────


def test_to_dict_has_no_hex_in_prompt_fields():
    pkg = _make_package(
        appearance_description="白色卡通兔子，纯白色身体",
    )
    d = pkg.to_dict()
    assert "#" not in d["appearance_description"]
    for term in d["identity_color_terms"]:
        assert "#" not in term


# ── from_dict rejects hex ──────────────────────────────────────────────


def test_from_dict_rejects_hex_in_appearance():
    with pytest.raises(ValueError, match="hex"):
        IPFrameAdaptationPackage.from_dict({
            "frame_id": "frame_0001",
            "ip_presence_type": "strong_identity",
            "appearance_description": "white #FFFFFF rabbit",
        })


# ── IPRoleSlot enum prevents hex ───────────────────────────────────────


def test_role_slot_string_maps_correctly():
    pkg = _make_package(role_slot="protagonist")
    assert pkg.role_slot == IPRoleSlot.PROTAGONIST


def test_invalid_role_slot_string_raises():
    with pytest.raises(ValueError):
        _make_package(role_slot="invalid_role")
