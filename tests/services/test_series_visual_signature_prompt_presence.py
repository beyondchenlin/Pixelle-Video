from __future__ import annotations

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureContract
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    SeriesVisualSignatureFinalPromptGateError,
    assert_series_visual_signature_final_prompt,
)
from pixelle_video.services.series_visual_signature_prompt_presence import (
    prompt_contains_term,
    prompt_presence_map,
)


def test_ascii_protected_term_requires_token_boundary() -> None:
    assert prompt_contains_term("AI system beside a chair", "AI") is True
    assert prompt_contains_term("a wooden chair", "AI") is False
    assert prompt_presence_map("a wooden chair", ["AI"])["AI"] is False


def test_multiword_ascii_phrase_matches_as_complete_phrase() -> None:
    assert prompt_contains_term("factory owner beside assembly line", "factory owner") is True
    assert prompt_contains_term("factory ownership chart", "factory owner") is False


def test_non_ascii_term_uses_normalized_phrase_presence() -> None:
    assert prompt_contains_term("工人正在操作装配机器", "装配机器") is True
    assert prompt_contains_term("工人正在休息", "装配机器") is False


def test_final_gate_does_not_accept_ai_inside_chair() -> None:
    with pytest.raises(SeriesVisualSignatureFinalPromptGateError, match="required subject missing"):
        assert_series_visual_signature_final_prompt(
            positive_prompt="a wooden chair in a quiet room",
            negative_prompt="",
            required_subjects=("AI",),
            signature=SeriesVisualSignatureContract.disabled(),
            visible_text_policy="free_text_allowed",
        )
