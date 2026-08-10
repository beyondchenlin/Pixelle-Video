from __future__ import annotations

import pytest

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.series_visual_signature_final_prompt_gate import (
    SeriesVisualSignatureFinalPromptGateError,
    assert_series_visual_signature_final_prompt,
)


def _signature(*, trait: str = "black spots") -> SeriesVisualSignatureContract:
    return SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name="Dalmatian",
            identity_traits=(trait,),
        ),
        max_area_ratio=0.2,
        participation_rule="Guide the viewer without replacing source subjects.",
    )


def test_missing_subject_error_does_not_echo_subject_text() -> None:
    protected_subject = "private-subject-918273"

    with pytest.raises(SeriesVisualSignatureFinalPromptGateError) as exc_info:
        assert_series_visual_signature_final_prompt(
            positive_prompt="Dalmatian with black spots",
            negative_prompt=(
                "sticker, logo, watermark, duplicate recurring visual signature, readable text"
            ),
            required_subjects=(protected_subject,),
            signature=_signature(),
            visible_text_policy="no_visible_text",
        )

    message = str(exc_info.value)
    assert "required subject missing" in message
    assert "index 0" in message
    assert protected_subject not in message


def test_missing_identity_trait_error_does_not_echo_trait_text() -> None:
    protected_trait = "private fur pattern"

    with pytest.raises(SeriesVisualSignatureFinalPromptGateError) as exc_info:
        assert_series_visual_signature_final_prompt(
            positive_prompt="worker beside Dalmatian",
            negative_prompt=(
                "sticker, logo, watermark, duplicate recurring visual signature, readable text"
            ),
            required_subjects=("worker",),
            signature=_signature(trait=protected_trait),
            visible_text_policy="no_visible_text",
        )

    message = str(exc_info.value)
    assert "identity trait missing" in message
    assert "index 0" in message
    assert protected_trait not in message