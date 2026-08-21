from __future__ import annotations

import pytest

from pixelle_video.models.series_visual_signature import (
    SeriesVisualSignatureRole,
    VisualSignatureProfileSnapshot,
)
from pixelle_video.services.series_visual_signature_contract_builder import (
    SeriesVisualSignatureContractBuilder,
)


def _profile(profile_id: str = "dog_1") -> dict:
    return {
        "series_visual_signature_profile_id": profile_id,
        "display_name": "Dalmatian",
        "identity_traits": ["black spots", "black sunglasses"],
    }


def _enabled_request(**overrides) -> dict:
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_profile_id": "dog_1",
        "series_visual_signature_role": "auto",
    }
    payload.update(overrides)
    return payload


def test_builder_returns_disabled_contract_when_request_disabled() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(request={})

    assert contract.enabled is False
    assert contract.role is SeriesVisualSignatureRole.NONE
    assert contract.profile is None


def test_builder_requires_semantic_area_instead_of_using_role_cap() -> None:
    with pytest.raises(ValueError, match="semantic area ratio"):
        SeriesVisualSignatureContractBuilder().build(
            request=_enabled_request(),
            profile=_profile(),
        )


def test_builder_auto_role_uses_operator_for_process_flow() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(
        request=_enabled_request(),
        profile=_profile(),
        role_context={"explanation_diagram_grammar": "process_flow"},
        suggested_area_ratio=0.36,
    )

    assert contract.role is SeriesVisualSignatureRole.OPERATOR
    assert contract.max_area_ratio == pytest.approx(0.36)


def test_builder_auto_role_uses_guide_for_relationship_map() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(
        request=_enabled_request(),
        profile=_profile(),
        role_context={"explanation_diagram_grammar": "relationship_map"},
        suggested_area_ratio=0.24,
    )

    assert contract.role is SeriesVisualSignatureRole.GUIDE
    assert contract.max_area_ratio == pytest.approx(0.24)


def test_builder_explicit_role_wins_over_context() -> None:
    with pytest.raises(ValueError, match="container"):
        SeriesVisualSignatureContractBuilder().build(
            request=_enabled_request(series_visual_signature_role="container"),
            profile=_profile(),
            role_context={"explanation_diagram_grammar": "process_flow"},
        )


def test_builder_accepts_smaller_user_area_than_role_limit() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(
        request=_enabled_request(
            series_visual_signature_role="guide",
            series_visual_signature_max_area_ratio=0.12,
        ),
        profile=_profile(),
    )

    assert contract.max_area_ratio == pytest.approx(0.12)


def test_builder_accepts_full_frame_user_area_without_legacy_role_cap() -> None:
    contract = SeriesVisualSignatureContractBuilder().build(
        request=_enabled_request(
            series_visual_signature_role="guide",
            series_visual_signature_max_area_ratio=0.8,
        ),
        profile=_profile(),
    )

    assert contract.max_area_ratio == pytest.approx(0.8)
    assert contract.relative_size.value == "full_frame"


def test_builder_requires_profile_id_when_enabled() -> None:
    with pytest.raises(ValueError, match="requires series_visual_signature_profile_id"):
        SeriesVisualSignatureContractBuilder().build(
            request={
                "series_visual_signature_enabled": True,
                "series_visual_signature_role": "guide",
            },
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


def test_builder_revalidates_typed_profile_instead_of_trusting_object_identity() -> None:
    profile = VisualSignatureProfileSnapshot.from_mapping(_profile())
    object.__setattr__(profile, "display_name", "Tampered Dalmatian")

    with pytest.raises(ValueError, match="canonical_identity_clause"):
        SeriesVisualSignatureContractBuilder().build(
            request=_enabled_request(series_visual_signature_role="guide"),
            profile=profile,
        )
