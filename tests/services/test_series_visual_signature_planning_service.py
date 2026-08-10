from __future__ import annotations

from pixelle_video.models.series_visual_signature import SeriesVisualSignatureRole
from pixelle_video.services.series_visual_signature_planning_service import (
    SeriesVisualSignaturePlanningService,
)


def _service() -> SeriesVisualSignaturePlanningService:
    return SeriesVisualSignaturePlanningService(
        profile_resolver=lambda profile_id: {
            "series_visual_signature_profile_id": profile_id,
            "display_name": "Dalmatian",
            "identity_traits": ["black spots", "black sunglasses"],
        }
    )


def test_planning_service_is_global_not_article_concretization_owned() -> None:
    contract = _service().build_contract(
        video_params={
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "guide",
            "article_concretization_enabled": False,
        }
    )

    assert contract.enabled is True
    assert contract.profile is not None
    assert contract.profile.profile_id == "dog_1"
    assert contract.role is SeriesVisualSignatureRole.GUIDE


def test_planning_service_resolves_auto_role_from_request_context() -> None:
    contract = _service().build_contract(
        video_params={
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "auto",
            "cognitive_anchor_kind": "causal_mechanism",
            "explanation_diagram_grammar": "process_flow",
        }
    )

    assert contract.role is SeriesVisualSignatureRole.OPERATOR
