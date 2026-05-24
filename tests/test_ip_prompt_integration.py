"""Test IP prompt context enrichment.

Covers:
- _enrich_prompt_contexts_with_ip()  injects ip_scene_description into frame contexts
- _strip_ip_prompt_context_fields()  removes IP-related fields from contexts
"""

from __future__ import annotations

from typing import Any

import pytest

from pixelle_video.models.ip_prompt_planning import (
    IPFrameAdaptationPackage,
    IPPresenceType,
    IPRoleSlot,
)


def _make_pkg(frame_id: str = "frame_0001", **overrides: Any) -> IPFrameAdaptationPackage:
    defaults: dict[str, Any] = {
        "frame_id": frame_id,
        "ip_presence_type": IPPresenceType.BALANCED_NARRATIVE,
        "presence_mode": "guide",
        "identity_anchors_visible": ("白色卡通兔子", "长耳朵", "蓝色领带"),
        "identity_color_terms": ("纯白色身体", "宝蓝色领带"),
        "appearance_description": "白色卡通兔子替换画面配角位置，中景融入场景",
        "role_slot": IPRoleSlot.SUPPORTING,
        "prompt_weight": 0.7,
    }
    defaults.update(overrides)
    return IPFrameAdaptationPackage(**defaults)


# ── _enrich_prompt_contexts_with_ip ──────────────────────────────────────


def test_enrich_injects_ip_scene_description():
    from pixelle_video.utils.content_generators import (
        _enrich_prompt_contexts_with_ip,
    )

    pkg = _make_pkg()
    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={"style_kind": "文旅纪实"},
    )
    assert len(result.frame_contexts) == 1
    assert "ip_scene_description" in result.frame_contexts[0]
    assert "白色卡通兔子" in result.frame_contexts[0]["ip_scene_description"]


def test_enrich_injects_style_context():
    from pixelle_video.utils.content_generators import (
        _enrich_prompt_contexts_with_ip,
    )

    pkg = _make_pkg()
    style = {"style_kind": "文旅纪实", "prompt_template": "test"}
    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context=style,
    )
    assert result.frame_contexts[0].get("style_context") == style


def test_enrich_with_existing_prompt_contexts():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
        _enrich_prompt_contexts_with_ip,
    )

    existing = PromptContextEnvelope(
        plan_context={"source_text": "test"},
        frame_contexts=[{"frame_id": "frame_0001", "visual_goal": "展示古城"}],
    )
    pkg = _make_pkg()
    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=existing,
        expected_count=1,
        packages=[pkg],
        style_context={},
    )
    assert result.frame_contexts[0]["frame_id"] == "frame_0001"
    assert result.frame_contexts[0]["visual_goal"] == "展示古城"
    assert "ip_scene_description" in result.frame_contexts[0]


def test_enrich_prompt_contexts_with_ip_adds_structured_ip_adaptation():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
        _enrich_prompt_contexts_with_ip,
    )

    pkg = _make_pkg()
    result = _enrich_prompt_contexts_with_ip(
        PromptContextEnvelope(plan_context={}, frame_contexts=({},)),
        expected_count=1,
        packages=(pkg,),
        style_context={"style_kind": "visual_only"},
    )

    context = result.frame_contexts[0]
    assert context["ip_scene_description"] == pkg.appearance_description
    assert context["ip_adaptation"]["frame_id"] == pkg.frame_id
    assert context["ip_adaptation"]["ip_presence_type"] == pkg.ip_presence_type.value


def test_enrich_mismatched_count_raises():
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    with pytest.raises(ValueError, match="must match"):
        _enrich_prompt_contexts_with_ip(
            prompt_contexts=None,
            expected_count=2,
            packages=[_make_pkg()],
            style_context={},
        )


# ── _strip_ip_prompt_context_fields ──────────────────────────────────────


def test_strip_removes_ip_fields():
    from pixelle_video.utils.content_generators import (
        _enrich_prompt_contexts_with_ip,
        _strip_ip_prompt_context_fields,
    )

    pkg = _make_pkg()
    enriched = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={},
    )
    stripped = _strip_ip_prompt_context_fields(enriched)
    assert stripped is not None
    assert "ip_adaptation" not in stripped.frame_contexts[0]
    assert "ip_scene_description" not in stripped.frame_contexts[0]
    assert "ip_negative_constraints" not in stripped.frame_contexts[0]
    assert "ip_image_text_plan" not in stripped.frame_contexts[0]


def test_strip_none_returns_none():
    from pixelle_video.utils.content_generators import _strip_ip_prompt_context_fields

    assert _strip_ip_prompt_context_fields(None) is None


# ── PromptContextEnvelope ─────────────────────────────────────────────────


def test_envelope_construction():
    from pixelle_video.utils.content_generators import PromptContextEnvelope

    envelope = PromptContextEnvelope(
        plan_context={"source": "test"},
        frame_contexts=[{"frame_id": "f1"}],
    )
    assert envelope.plan_context["source"] == "test"
    assert envelope.frame_contexts[0]["frame_id"] == "f1"


def test_envelope_defaults():
    from pixelle_video.utils.content_generators import PromptContextEnvelope

    envelope = PromptContextEnvelope()
    assert envelope.plan_context == {}
    assert envelope.frame_contexts == ()
