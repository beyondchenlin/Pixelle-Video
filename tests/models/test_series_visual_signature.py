from __future__ import annotations

import pytest

from pixelle_video.architecture.legacy_signature_field_guard import DEPRECATED_RUNTIME_FIELD_NAMES
from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureContract,
    SeriesVisualSignatureRequest,
    SeriesVisualSignatureRole,
    VisualSignatureProfileSnapshot,
)


def test_request_does_not_derive_enabled_from_article_concretization() -> None:
    request = SeriesVisualSignatureRequest.from_mapping({"article_concretization_enabled": True})

    assert request.enabled is False
    assert request.role is SeriesVisualSignatureRole.NONE


def test_request_rejects_deprecated_runtime_fields() -> None:
    deprecated_profile_key = next(
        key
        for key in DEPRECATED_RUNTIME_FIELD_NAMES
        if key.startswith("ip_") and key.endswith("_id") and "profile" in key
    )
    with pytest.raises(ValueError, match="deprecated visual signature fields"):
        SeriesVisualSignatureRequest.from_mapping({deprecated_profile_key: "dog_1"})


def test_profile_rejects_prompt_paragraph_fields_and_instruction_traits() -> None:
    with pytest.raises(ValueError, match="prompt paragraph fields"):
        VisualSignatureProfileSnapshot.from_mapping(
            {
                "series_visual_signature_profile_id": "dog_1",
                "display_name": "Dog",
                "identity_traits": ["black spots"],
                "positive_prompt": "draw a dog in every scene",
            }
        )

    with pytest.raises(ValueError, match="prompt instruction language"):
        VisualSignatureProfileSnapshot(
            profile_id="dog_1",
            display_name="Dog",
            identity_traits=["always foreground photorealistic dog"],
        )


def test_contract_serializes_new_field_names_only() -> None:
    profile = VisualSignatureProfileSnapshot(
        profile_id="dog_1",
        display_name="Dalmatian",
        identity_traits=("black spots", "black sunglasses"),
    )
    contract = SeriesVisualSignatureContract(
        enabled=True,
        role="guide",
        profile=profile,
        max_area_ratio=0.2,
        participation_rule="Small guide points to the relation line.",
    )

    payload = contract.to_dict()

    assert payload["series_visual_signature_profile_id"] == "dog_1"
    assert "identity_profile_id" not in payload
    assert payload["max_area_ratio"] == pytest.approx(0.2)
