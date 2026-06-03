import pytest

from pixelle_video.models.series_visual_signature_request import (
    SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION,
    SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION,
    SeriesVisualSignatureControlsContract,
    SeriesVisualSignatureRequest,
    is_supported_series_visual_signature_pipeline_version,
)
from pixelle_video.models.series_visual_signature_strategy import (
    SeriesVisualSignatureConsistencyMode,
    SeriesVisualSignatureMode,
    SeriesVisualSignatureStrategy,
    resolve_effective_signature_mode_with_v44_context,
)
from pixelle_video.models.video_generation_contract import (
    normalize_standard_video_generation_params,
    validate_standard_video_generation_params,
)
from pixelle_video.models.visual_expression import VisualExpressionMode


def _enabled_params(**overrides):
    payload = {
        "series_visual_signature_enabled": True,
        "series_visual_signature_asset_bible_id": "asset_bible_1",
        "series_visual_signature_profile_id": "rabbit_host",
        "series_visual_signature_expression_mode": "infographic_layout",
        "series_visual_signature_structure_mode": "workflow",
        "series_visual_signature_participation_mode": "operator_demonstrator",
        "series_visual_signature_mode": "supporting_integration",
        "series_visual_signature_consistency_mode": "supporting_character",
    }
    payload.update(overrides)
    return payload


def test_series_visual_signature_controls_accepts_v4_fields():
    controls = SeriesVisualSignatureControlsContract.from_mapping(_enabled_params())

    assert controls.enabled is True
    assert controls.asset_bible_id == "asset_bible_1"
    assert controls.profile_id == "rabbit_host"
    assert controls.expression_mode is VisualExpressionMode.INFOGRAPHIC_LAYOUT
    assert controls.structure_mode.value == "workflow"
    assert controls.participation_mode.value == "operator_demonstrator"
    assert controls.strategy.signature_mode.value == "supporting_integration"
    assert controls.strategy.consistency_mode.value == "supporting_character"
    assert controls.to_generation_dict() == {
        "series_visual_signature_expression_mode": "infographic_layout",
        "series_visual_signature_structure_mode": "workflow",
        "series_visual_signature_participation_mode": "operator_demonstrator",
        "series_visual_signature_mode": "supporting_integration",
        "series_visual_signature_consistency_mode": "supporting_character",
        "effective_series_visual_signature_mode": "supporting_integration",
    }


def test_series_visual_signature_expression_mode_invalid_defaults_auto():
    controls = SeriesVisualSignatureControlsContract.from_mapping(
        _enabled_params(series_visual_signature_expression_mode="not_a_mode")
    )

    assert controls.expression_mode is VisualExpressionMode.AUTO


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("series_visual_signature_mode", "not_a_signature_mode"),
        ("series_visual_signature_mode", False),
        ("series_visual_signature_consistency_mode", "not_a_consistency_mode"),
        ("series_visual_signature_consistency_mode", 0),
    ],
)
def test_series_visual_signature_controls_reject_invalid_strategy_facts(field_name, bad_value):
    with pytest.raises(ValueError, match=field_name):
        SeriesVisualSignatureControlsContract.from_mapping(_enabled_params(**{field_name: bad_value}))


def test_primary_character_forces_subject_replacement():
    request = SeriesVisualSignatureRequest.from_mapping(
        _enabled_params(
            series_visual_signature_mode="supporting_integration",
            series_visual_signature_consistency_mode="primary_character",
        )
    )

    assert request.effective_signature_mode is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    assert request.strategy.to_dict()["effective_series_visual_signature_mode"] == "subject_replacement"


def test_supporting_character_forces_supporting_integration():
    request = SeriesVisualSignatureRequest.from_mapping(
        _enabled_params(
            series_visual_signature_mode="subject_replacement",
            series_visual_signature_consistency_mode="supporting_character",
        )
    )

    assert request.effective_signature_mode is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    assert request.strategy.to_dict()["effective_series_visual_signature_mode"] == "supporting_integration"


def test_series_visual_signature_request_disabled_does_not_trigger_v4():
    request = SeriesVisualSignatureRequest.from_mapping({})

    assert request.enabled is False
    assert request.pipeline_version == SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION
    assert request.pipeline_version == "v4_2_identity_contract"
    request.validate()


def test_series_visual_signature_pipeline_version_keeps_legacy_route_supported():
    assert is_supported_series_visual_signature_pipeline_version(SERIES_VISUAL_SIGNATURE_PIPELINE_VERSION)
    assert is_supported_series_visual_signature_pipeline_version(SERIES_VISUAL_SIGNATURE_LEGACY_PIPELINE_VERSION)


def test_series_visual_signature_request_requires_asset_when_enabled():
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_profile_id": "rabbit_host",
        }
    )

    with pytest.raises(ValueError, match="asset_bible_id"):
        request.validate()


def test_series_visual_signature_request_requires_profile_when_enabled():
    request = SeriesVisualSignatureRequest.from_mapping(
        {
            "series_visual_signature_enabled": True,
            "series_visual_signature_asset_bible_id": "asset_bible_1",
        }
    )

    with pytest.raises(ValueError, match="profile_id"):
        request.validate()


def test_normalize_standard_video_generation_params_preserves_v4_fields():
    normalized = normalize_standard_video_generation_params(_enabled_params())

    assert normalized["series_visual_signature_enabled"] is True
    assert normalized["series_visual_signature_asset_bible_id"] == "asset_bible_1"
    assert normalized["series_visual_signature_profile_id"] == "rabbit_host"
    assert normalized["series_visual_signature_expression_mode"] == "infographic_layout"
    assert normalized["series_visual_signature_structure_mode"] == "workflow"
    assert normalized["series_visual_signature_participation_mode"] == "operator_demonstrator"
    assert normalized["series_visual_signature_mode"] == "supporting_integration"
    assert normalized["series_visual_signature_consistency_mode"] == "supporting_character"
    assert normalized["effective_series_visual_signature_mode"] == "supporting_integration"


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("series_visual_signature_mode", "not_a_signature_mode"),
        ("series_visual_signature_mode", False),
        ("series_visual_signature_consistency_mode", "not_a_consistency_mode"),
        ("series_visual_signature_consistency_mode", 0),
    ],
)
def test_normalize_standard_video_generation_params_rejects_invalid_series_visual_signature_facts(
    field_name,
    bad_value,
):
    with pytest.raises(ValueError, match=field_name):
        normalize_standard_video_generation_params(_enabled_params(**{field_name: bad_value}))


@pytest.mark.parametrize("strategy", ["observer_guide", "signature_presence"])
def test_normalize_standard_video_generation_params_constrains_v44_supporting_strategies(
    strategy,
):
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            series_visual_signature_mode="auto",
            series_visual_signature_consistency_mode="primary_character",
            series_visual_signature_strategy=strategy,
        )
    )

    assert normalized["series_visual_signature_strategy"] == strategy
    assert normalized["series_visual_signature_consistency_mode"] == "primary_character"
    assert normalized["effective_series_visual_signature_mode"] == "supporting_integration"


def test_normalize_standard_video_generation_params_allows_participant_subject_replacement():
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            series_visual_signature_mode="auto",
            series_visual_signature_consistency_mode="primary_character",
            series_visual_signature_strategy="participant",
        )
    )

    assert normalized["series_visual_signature_strategy"] == "participant"
    assert normalized["series_visual_signature_consistency_mode"] == "primary_character"
    assert normalized["effective_series_visual_signature_mode"] == "subject_replacement"


def test_normalize_standard_video_generation_params_does_not_auto_promote_host_explainer():
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            series_visual_signature_mode="auto",
            series_visual_signature_consistency_mode="primary_character",
            series_visual_signature_strategy="host_explainer",
        )
    )

    assert normalized["series_visual_signature_strategy"] == "host_explainer"
    assert normalized["series_visual_signature_consistency_mode"] == "primary_character"
    assert normalized["effective_series_visual_signature_mode"] == "auto"


def test_validate_standard_video_generation_params_accepts_series_visual_signature_controls():
    validate_standard_video_generation_params(_enabled_params())


def test_series_visual_signature_strategy_accepts_known_values():
    assert SeriesVisualSignatureStrategy.from_value("host_explainer") is SeriesVisualSignatureStrategy.HOST_EXPLAINER
    assert SeriesVisualSignatureStrategy.from_value("observer_guide") is SeriesVisualSignatureStrategy.OBSERVER_GUIDE
    assert SeriesVisualSignatureStrategy.from_value(None) is SeriesVisualSignatureStrategy.AUTO


def test_series_visual_signature_strategy_rejects_unknown_values():
    with pytest.raises(ValueError, match="series_visual_signature_strategy"):
        SeriesVisualSignatureStrategy.from_value("not_a_strategy")


@pytest.mark.parametrize("value", [False, 0, [], object()])
def test_series_visual_signature_strategy_rejects_non_string_default_like_values(value):
    with pytest.raises(ValueError, match="series_visual_signature_strategy"):
        SeriesVisualSignatureStrategy.from_value(value)


@pytest.mark.parametrize(
    "strategy",
    [
        SeriesVisualSignatureStrategy.SIGNATURE_PRESENCE,
        SeriesVisualSignatureStrategy.OBSERVER_GUIDE,
        SeriesVisualSignatureStrategy.BACKGROUND_SIGNATURE,
    ],
)
def test_v44_context_downgrades_subject_replacement_for_observer_signature_strategies(
    strategy,
):
    assert (
        resolve_effective_signature_mode_with_v44_context(
            requested_signature_mode=SeriesVisualSignatureMode.SUBJECT_REPLACEMENT,
            consistency_mode=SeriesVisualSignatureConsistencyMode.OFF,
            series_visual_signature_strategy=strategy,
            subject_replacement_allowed=False,
        )
        is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    )


def test_v44_context_blocks_explicit_subject_replacement_when_not_allowed():
    assert (
        resolve_effective_signature_mode_with_v44_context(
            requested_signature_mode=SeriesVisualSignatureMode.SUBJECT_REPLACEMENT,
            consistency_mode=SeriesVisualSignatureConsistencyMode.OFF,
            series_visual_signature_strategy=SeriesVisualSignatureStrategy.HOST_EXPLAINER,
            subject_replacement_allowed=False,
        )
        is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    )


def test_v44_context_primary_character_replacement_requires_participant_strategy():
    assert (
        resolve_effective_signature_mode_with_v44_context(
            requested_signature_mode=SeriesVisualSignatureMode.AUTO,
            consistency_mode=SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER,
            series_visual_signature_strategy=SeriesVisualSignatureStrategy.PARTICIPANT,
            subject_replacement_allowed=True,
        )
        is SeriesVisualSignatureMode.SUBJECT_REPLACEMENT
    )
    assert (
        resolve_effective_signature_mode_with_v44_context(
            requested_signature_mode=SeriesVisualSignatureMode.AUTO,
            consistency_mode=SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER,
            series_visual_signature_strategy=SeriesVisualSignatureStrategy.PARTICIPANT,
            subject_replacement_allowed=False,
        )
        is SeriesVisualSignatureMode.SUPPORTING_INTEGRATION
    )
    assert (
        resolve_effective_signature_mode_with_v44_context(
            requested_signature_mode=SeriesVisualSignatureMode.AUTO,
            consistency_mode=SeriesVisualSignatureConsistencyMode.PRIMARY_CHARACTER,
            series_visual_signature_strategy=SeriesVisualSignatureStrategy.HOST_EXPLAINER,
            subject_replacement_allowed=True,
        )
        is SeriesVisualSignatureMode.AUTO
    )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        (
            "requested_signature_mode",
            {
                "requested_signature_mode": "not_a_signature_mode",
                "consistency_mode": SeriesVisualSignatureConsistencyMode.OFF,
                "series_visual_signature_strategy": SeriesVisualSignatureStrategy.AUTO,
            },
        ),
        (
            "consistency_mode",
            {
                "requested_signature_mode": SeriesVisualSignatureMode.AUTO,
                "consistency_mode": "not_a_consistency_mode",
                "series_visual_signature_strategy": SeriesVisualSignatureStrategy.AUTO,
            },
        ),
        (
            "series_visual_signature_strategy",
            {
                "requested_signature_mode": SeriesVisualSignatureMode.AUTO,
                "consistency_mode": SeriesVisualSignatureConsistencyMode.OFF,
                "series_visual_signature_strategy": "not_a_strategy",
            },
        ),
    ],
)
def test_v44_context_rejects_invalid_mode_resolution_facts(field_name, kwargs):
    with pytest.raises(ValueError, match=field_name):
        resolve_effective_signature_mode_with_v44_context(
            **kwargs,
            subject_replacement_allowed=False,
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        (
            "requested_signature_mode",
            {
                "requested_signature_mode": False,
                "consistency_mode": SeriesVisualSignatureConsistencyMode.OFF,
                "series_visual_signature_strategy": SeriesVisualSignatureStrategy.AUTO,
            },
        ),
        (
            "consistency_mode",
            {
                "requested_signature_mode": SeriesVisualSignatureMode.AUTO,
                "consistency_mode": 0,
                "series_visual_signature_strategy": SeriesVisualSignatureStrategy.AUTO,
            },
        ),
        (
            "series_visual_signature_strategy",
            {
                "requested_signature_mode": SeriesVisualSignatureMode.AUTO,
                "consistency_mode": SeriesVisualSignatureConsistencyMode.OFF,
                "series_visual_signature_strategy": [],
            },
        ),
    ],
)
def test_v44_context_rejects_non_string_default_like_mode_resolution_facts(
    field_name,
    kwargs,
):
    with pytest.raises(ValueError, match=field_name):
        resolve_effective_signature_mode_with_v44_context(
            **kwargs,
            subject_replacement_allowed=False,
        )
