from __future__ import annotations

import pytest

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRole
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)


def test_builder_returns_disabled_contract_when_request_disabled() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(request={})

    assert contract.enabled is False
    assert contract.role is SeriesVisualSignatureRole.NONE
    assert contract.profile is None


def test_builder_resolves_auto_role_to_guide_without_old_runtime() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(
        request={
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
        },
        profile={
            "series_visual_signature_profile_id": "dog_1",
            "display_name": "Dalmatian",
            "identity_traits": ["black spots", "black sunglasses"],
        },
    )

    assert contract.enabled is True
    assert contract.role is SeriesVisualSignatureRole.GUIDE
    assert contract.max_area_ratio == pytest.approx(0.2)
    assert "photorealistic" in " ".join(contract.forbidden_behaviors)


def test_builder_requires_profile_id_when_enabled() -> None:
    with pytest.raises(ValueError, match="requires series_visual_signature_profile_id"):
        SeriesVisualSignatureContractBuilder().build(
            request={"series_visual_signature_enabled": True, "series_visual_signature_role": "guide"},
            strict_user_mode=True,
        )


def test_builder_does_not_fabricate_profile_from_profile_id() -> None:
    with pytest.raises(ValueError, match="profile could not be resolved: dog_1"):
        SeriesVisualSignatureContractBuilder().build(
            request={
                "series_visual_signature_enabled": True,
                "series_visual_signature_profile_id": "dog_1",
                "series_visual_signature_role": "guide",
            },
            profile=None,
        )


def test_builder_rejects_resolved_profile_id_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match request profile_id"):
        SeriesVisualSignatureContractBuilder().build(
            request={
                "series_visual_signature_enabled": True,
                "series_visual_signature_profile_id": "dog_1",
                "series_visual_signature_role": "guide",
            },
            profile={
                "series_visual_signature_profile_id": "dog_2",
                "display_name": "Other Dog",
                "identity_traits": ["white coat", "red collar"],
            },
        )
