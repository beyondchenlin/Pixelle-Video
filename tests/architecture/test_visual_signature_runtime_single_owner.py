from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRequest,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.utils.content_generators import (
    _resolve_visual_signature_prompt_ownership,
)


ROOT = Path(__file__).resolve().parents[2]


def _composer_generator_call() -> ast.Call:
    source = (ROOT / "pixelle_video/services/visual_prompt_composer.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "generate_styled_image_prompt_batch":
            return node
    raise AssertionError("generate_styled_image_prompt_batch call not found")


def _request(*, enabled: bool) -> SeriesVisualSignatureRequest:
    if not enabled:
        return SeriesVisualSignatureRequest.disabled()
    return SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "guide",
        }
    )


def _snapshot() -> VisualSignatureProfileSnapshot:
    return VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=("black spots", "red collar"),
    )


def test_canonical_prompt_routing_enables_llm_identity_without_legacy_projection() -> None:
    llm_enabled, legacy_enabled = _resolve_visual_signature_prompt_ownership(
        legacy_request=_request(enabled=False),
        canonical_request=_request(enabled=True),
        canonical_profile_snapshot=_snapshot(),
    )

    assert llm_enabled is True
    assert legacy_enabled is False


def test_legacy_prompt_routing_remains_compatible() -> None:
    llm_enabled, legacy_enabled = _resolve_visual_signature_prompt_ownership(
        legacy_request=_request(enabled=True),
        canonical_request=_request(enabled=False),
        canonical_profile_snapshot=None,
    )

    assert llm_enabled is True
    assert legacy_enabled is True


def test_prompt_routing_rejects_dual_ownership() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _resolve_visual_signature_prompt_ownership(
            legacy_request=_request(enabled=True),
            canonical_request=_request(enabled=True),
            canonical_profile_snapshot=_snapshot(),
        )


def test_canonical_prompt_routing_requires_matching_validated_snapshot() -> None:
    wrong_snapshot = VisualSignatureProfileSnapshot(
        profile_id="other",
        display_name="Dalmatian",
        identity_traits=("black spots",),
    )
    with pytest.raises(ValueError, match="match request profile_id"):
        _resolve_visual_signature_prompt_ownership(
            legacy_request=_request(enabled=False),
            canonical_request=_request(enabled=True),
            canonical_profile_snapshot=wrong_snapshot,
        )


def test_composer_uses_canonical_context_while_hard_disabling_legacy_inputs() -> None:
    call = _composer_generator_call()
    keywords = {item.arg: item.value for item in call.keywords if item.arg}

    expected_legacy_constants = {
        "series_visual_signature_enabled": False,
        "ip_profile": None,
        "series_visual_signature_expression_mode": None,
        "series_visual_signature_structure_mode": None,
        "series_visual_signature_participation_mode": None,
        "series_visual_signature_request": None,
        "series_visual_signature_profile": None,
        "series_visual_signature_mode": None,
        "series_visual_signature_consistency_mode": None,
        "series_visual_signature_presentation_mode": None,
        "series_visual_signature_enforcement": None,
        "series_visual_signature_fallback_enabled": None,
        "series_visual_signature_fallback_mode": None,
        "series_visual_signature_min_visibility": None,
        "scene_casts_by_frame": None,
    }
    for name, expected in expected_legacy_constants.items():
        assert name in keywords
        assert isinstance(keywords[name], ast.Constant)
        assert keywords[name].value is expected

    assert ast.unparse(keywords["canonical_series_visual_signature_request"]) == (
        "resolved_signature_request if signature_enabled else None"
    )
    assert ast.unparse(
        keywords["canonical_series_visual_signature_profile_snapshot"]
    ) == "profile_snapshot if signature_enabled else None"
