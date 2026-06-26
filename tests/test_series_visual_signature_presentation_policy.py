from pixelle_video.models.series_visual_signature_presentation import (
    SeriesVisualSignatureFallbackMode,
    SeriesVisualSignaturePresentationMode,
    SeriesVisualSignaturePresentationPolicy,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureConsistencyMode,
    SeriesVisualSignatureMode,
)


def test_visible_supporting_character_maps_to_supporting_strategy():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {
            "series_visual_signature_presentation_mode": "visible_supporting_character",
            "series_visual_signature_mode": "auto",
            "series_visual_signature_consistency_mode": "off",
        }
    )

    strategy = policy.strategy_controls()
    assert policy.presentation_mode is SeriesVisualSignaturePresentationMode.VISIBLE_SUPPORTING_CHARACTER
    assert strategy.signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    assert strategy.consistency_mode is SeriesVisualSignatureConsistencyMode.SUPPORTING_CHARACTER
    assert "series_visual_signature_mode" in policy.overridden_advanced_fields
    assert "series_visual_signature_consistency_mode" in policy.overridden_advanced_fields


def test_embedded_scene_mark_maps_to_low_disruption_strategy():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {"series_visual_signature_presentation_mode": "embedded_scene_mark"}
    )

    strategy = policy.strategy_controls()
    assert strategy.signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    assert strategy.consistency_mode is SeriesVisualSignatureConsistencyMode.OFF


def test_fallback_mode_can_request_default_signature():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {
            "series_visual_signature_presentation_mode": "visible_supporting_character",
            "series_visual_signature_fallback_mode": "default_signature",
        }
    )

    assert policy.fallback_mode is SeriesVisualSignatureFallbackMode.DEFAULT_SIGNATURE
    assert policy.fallback_enabled is True


def test_fallback_enabled_false_normalizes_mode_to_disabled():
    policy = SeriesVisualSignaturePresentationPolicy.from_mapping(
        {
            "series_visual_signature_presentation_mode": "content_bound_mandatory_ip",
            "series_visual_signature_fallback_enabled": "false",
        }
    )

    assert policy.fallback_enabled is False
    assert policy.fallback_mode is SeriesVisualSignatureFallbackMode.DISABLED
    assert policy.to_generation_dict()["series_visual_signature_fallback_mode"] == "disabled"
