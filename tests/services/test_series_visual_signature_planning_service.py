from __future__ import annotations

from pixelle_video.services.series_visual_signature_planning_service import (
    SeriesVisualSignaturePlanningService,
)


def test_planning_service_is_global_not_article_concretization_owned() -> None:
    service = SeriesVisualSignaturePlanningService(
        profile_resolver=lambda profile_id: {
            "series_visual_signature_profile_id": profile_id,
            "display_name": "Dalmatian",
            "identity_traits": ["black spots", "black sunglasses"],
        }
    )

    contract = service.build_contract(
        video_params={
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "dog_1",
            "series_visual_signature_role": "guide",
            "article_concretization_enabled": False,
        }
    )

    assert contract.enabled is True
    assert contract.profile.profile_id == "dog_1"
