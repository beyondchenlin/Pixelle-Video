"""Test IPImageTextPlan text whitelist and safety rules."""

from __future__ import annotations

from pixelle_video.models.ip_prompt_planning import IPImageTextPlan


def _make_plan(**overrides):
    defaults = {
        "summary_text": "从长乐门出发",
        "scene_text": ("长乐门", "正定古城"),
        "visible_text_whitelist": ("从长乐门出发", "长乐门", "正定古城"),
        "text_safety_rules": (
            "只允许生成白名单中的画面文字",
            "避免额外标语和乱码文字",
        ),
    }
    defaults.update(overrides)
    return IPImageTextPlan(**defaults)


# ── construction and basic access ──────────────────────────────────────


def test_ip_image_text_plan_basic_construction():
    plan = _make_plan()
    assert plan.summary_text == "从长乐门出发"
    assert len(plan.scene_text) == 2
    assert len(plan.visible_text_whitelist) == 3
    assert len(plan.text_safety_rules) == 2


def test_ip_image_text_plan_defaults():
    plan = IPImageTextPlan()
    assert plan.summary_text is None
    assert plan.scene_text == ()
    assert plan.visible_text_whitelist == ()
    assert plan.text_safety_rules == ()


def test_ip_image_text_plan_empty_string_becomes_none():
    plan = IPImageTextPlan(summary_text="  ")
    assert plan.summary_text is None


# ── duplicate removal ──────────────────────────────────────────────────


def test_duplicate_items_are_rejected():
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        IPImageTextPlan(scene_text=("长乐门", "长乐门"))


def test_duplicate_in_whitelist_rejected():
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        IPImageTextPlan(
            visible_text_whitelist=("文字一", "文字一"),
        )


# ── to_dict / from_dict roundtrip ──────────────────────────────────────


def test_to_dict_roundtrip():
    original = _make_plan()
    d = original.to_dict()
    restored = IPImageTextPlan.from_dict(d)
    assert restored.summary_text == original.summary_text
    assert set(restored.scene_text) == set(original.scene_text)
    assert set(restored.visible_text_whitelist) == set(original.visible_text_whitelist)


def test_from_dict_empty():
    plan = IPImageTextPlan.from_dict({})
    assert plan.summary_text is None
    assert plan.scene_text == ()
    assert plan.visible_text_whitelist == ()


def test_from_dict_with_none_fields():
    plan = IPImageTextPlan.from_dict({
        "summary_text": None,
        "scene_text": None,
        "visible_text_whitelist": None,
        "text_safety_rules": None,
    })
    assert plan.summary_text is None


# ── safety rules composition ───────────────────────────────────────────


def test_safety_rules_default_composition():
    plan = IPImageTextPlan(
        text_safety_rules=(
            "不出现英文",
            "不出现色号",
            "不出现水印",
        ),
    )
    assert "不出现英文" in plan.text_safety_rules
    assert "不出现色号" in plan.text_safety_rules
    assert "不出现水印" in plan.text_safety_rules


# ── whitelist validation ───────────────────────────────────────────────


def test_whitelist_preserves_order():
    plan = IPImageTextPlan(
        visible_text_whitelist=("一", "二", "三"),
    )
    assert plan.visible_text_whitelist == ("一", "二", "三")


def test_whitelist_empty_strings_stripped():
    import pytest

    with pytest.raises(ValueError, match="must not be empty"):
        IPImageTextPlan(visible_text_whitelist=("有效", "  "))
