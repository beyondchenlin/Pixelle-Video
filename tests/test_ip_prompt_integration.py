"""Test IP prompt context enrichment and identity terms extraction.

Covers:
- _enrich_prompt_contexts_with_ip()  injects ip_adaptation into frame contexts
- _ip_identity_prompt_terms_from_context()  gate: role_slot, prompt_weight, fallback
- _strip_ip_prompt_context_fields()  removes ip_adaptation / ip_presence_options
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


def test_enrich_injects_ip_adaptation_into_frame_contexts():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
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
    assert "ip_adaptation" in result.frame_contexts[0]
    assert result.frame_contexts[0]["ip_adaptation"]["frame_id"] == "frame_0001"


def test_enrich_injects_ip_presence_options():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
        _enrich_prompt_contexts_with_ip,
    )

    pkg = _make_pkg()
    result = _enrich_prompt_contexts_with_ip(
        prompt_contexts=None,
        expected_count=1,
        packages=[pkg],
        style_context={},
    )
    options = result.frame_contexts[0].get("ip_presence_options")
    assert isinstance(options, list)
    assert len(options) == 6
    for opt in options:
        assert isinstance(opt, str)
    assert "strong_identity" in options
    assert "absent" in options


def test_enrich_injects_style_context():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
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
    assert "ip_adaptation" in result.frame_contexts[0]


def test_enrich_mismatched_count_raises():
    from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip

    with pytest.raises(ValueError, match="must match"):
        _enrich_prompt_contexts_with_ip(
            prompt_contexts=None,
            expected_count=2,
            packages=[_make_pkg()],
            style_context={},
        )


# ── _ip_identity_prompt_terms_from_context ───────────────────────────────


def test_absent_role_slot_skips():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    ctx = {
        "ip_adaptation": _make_pkg(role_slot=IPRoleSlot.ABSENT).to_dict(),
    }
    assert _ip_identity_prompt_terms_from_context(ctx) == ()


def test_low_weight_skips():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    ctx = {
        "ip_adaptation": _make_pkg(prompt_weight=0.3, role_slot=IPRoleSlot.PASSERBY).to_dict(),
    }
    assert _ip_identity_prompt_terms_from_context(ctx) == ()


def test_high_weight_returns_appearance_description():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    ctx = {
        "ip_adaptation": _make_pkg(prompt_weight=0.9).to_dict(),
    }
    result = _ip_identity_prompt_terms_from_context(ctx)
    assert len(result) == 1
    assert "白色卡通兔子" in result[0]


def test_no_adaptation_returns_empty():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    assert _ip_identity_prompt_terms_from_context({}) == ()


def test_non_mapping_adaptation_returns_empty():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    assert _ip_identity_prompt_terms_from_context({"ip_adaptation": "not_a_mapping"}) == ()


def test_fallback_when_no_appearance_description():
    from pixelle_video.utils.content_generators import _ip_identity_prompt_terms_from_context

    ctx = {
        "ip_adaptation": _make_pkg(
            prompt_weight=0.9,
            appearance_description=None,
            identity_anchors_visible=("白色卡通兔子", "长耳朵"),
            identity_color_terms=("纯白色身体",),
        ).to_dict(),
    }
    result = _ip_identity_prompt_terms_from_context(ctx)
    assert len(result) >= 1
    assert any("白色卡通兔子" in term for term in result)


# ── _strip_ip_prompt_context_fields ──────────────────────────────────────


def test_strip_removes_ip_fields():
    from pixelle_video.utils.content_generators import (
        PromptContextEnvelope,
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
    assert "ip_presence_options" not in stripped.frame_contexts[0]


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
