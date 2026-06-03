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


def test_builder_strict_mode_requires_profile() -> None:
    with pytest.raises(ValueError, match="requires series_visual_signature_profile_id"):
        SeriesVisualSignatureContractBuilder().build(
            request={"series_visual_signature_enabled": True, "series_visual_signature_role": "guide"},
            strict_user_mode=True,
        )
