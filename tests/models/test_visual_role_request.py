import pytest

from pixelle_video.models.video_generation_contract import (
    normalize_standard_video_generation_params,
    validate_standard_video_generation_params,
)
from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.models.visual_role_request import (
    VISUAL_ROLE_LEGACY_PIPELINE_VERSION,
    VISUAL_ROLE_PIPELINE_VERSION,
    VisualRoleControlsContract,
    VisualRoleRequest,
    is_supported_visual_role_pipeline_version,
)
from pixelle_video.models.visual_role_strategy import (
    VisualConsistencyMode,
    VisualRoleMode,
    VisualRoleStrategy,
    resolve_effective_role_mode_with_v44_context,
)


def _enabled_params(**overrides):
    payload = {
        "ip_enabled": True,
        "ip_asset_bible_id": "asset_bible_1",
        "ip_profile_id": "rabbit_host",
        "visual_expression_mode": "infographic_layout",
        "visual_structure_mode": "workflow",
        "visual_participation_mode": "operator_demonstrator",
        "visual_role_mode": "supporting_integration",
        "visual_consistency_mode": "supporting_character",
    }
    payload.update(overrides)
    return payload


def test_visual_role_controls_accepts_v4_fields():
    controls = VisualRoleControlsContract.from_mapping(_enabled_params())

    assert controls.enabled is True
    assert controls.asset_bible_id == "asset_bible_1"
    assert controls.profile_id == "rabbit_host"
    assert controls.expression_mode is VisualExpressionMode.INFOGRAPHIC_LAYOUT
    assert controls.structure_mode.value == "workflow"
    assert controls.participation_mode.value == "operator_demonstrator"
    assert controls.strategy.role_mode.value == "supporting_integration"
    assert controls.strategy.consistency_mode.value == "supporting_character"
    assert controls.to_generation_dict() == {
        "visual_expression_mode": "infographic_layout",
        "visual_structure_mode": "workflow",
        "visual_participation_mode": "operator_demonstrator",
        "visual_role_mode": "supporting_integration",
        "visual_consistency_mode": "supporting_character",
        "effective_visual_role_mode": "supporting_integration",
    }


def test_visual_expression_mode_invalid_defaults_auto():
    controls = VisualRoleControlsContract.from_mapping(
        _enabled_params(visual_expression_mode="not_a_mode")
    )

    assert controls.expression_mode is VisualExpressionMode.AUTO


def test_primary_character_forces_subject_replacement():
    request = VisualRoleRequest.from_mapping(
        _enabled_params(
            visual_role_mode="supporting_integration",
            visual_consistency_mode="primary_character",
        )
    )

    assert request.effective_role_mode is VisualRoleMode.SUBJECT_REPLACEMENT
    assert request.strategy.to_dict()["effective_visual_role_mode"] == "subject_replacement"


def test_supporting_character_forces_supporting_integration():
    request = VisualRoleRequest.from_mapping(
        _enabled_params(
            visual_role_mode="subject_replacement",
            visual_consistency_mode="supporting_character",
        )
    )

    assert request.effective_role_mode is VisualRoleMode.SUPPORTING_INTEGRATION
    assert request.strategy.to_dict()["effective_visual_role_mode"] == "supporting_integration"


def test_visual_role_request_disabled_does_not_trigger_v4():
    request = VisualRoleRequest.from_mapping({})

    assert request.enabled is False
    assert request.pipeline_version == VISUAL_ROLE_PIPELINE_VERSION
    assert request.pipeline_version == "v4_2_identity_contract"
    request.validate()


def test_visual_role_pipeline_version_keeps_legacy_route_supported():
    assert is_supported_visual_role_pipeline_version(VISUAL_ROLE_PIPELINE_VERSION)
    assert is_supported_visual_role_pipeline_version(VISUAL_ROLE_LEGACY_PIPELINE_VERSION)


def test_visual_role_request_requires_asset_when_enabled():
    request = VisualRoleRequest.from_mapping(
        {
            "ip_enabled": True,
            "ip_profile_id": "rabbit_host",
        }
    )

    with pytest.raises(ValueError, match="asset_bible_id"):
        request.validate()


def test_visual_role_request_requires_profile_when_enabled():
    request = VisualRoleRequest.from_mapping(
        {
            "ip_enabled": True,
            "ip_asset_bible_id": "asset_bible_1",
        }
    )

    with pytest.raises(ValueError, match="profile_id"):
        request.validate()


def test_normalize_standard_video_generation_params_preserves_v4_fields():
    normalized = normalize_standard_video_generation_params(_enabled_params())

    assert normalized["ip_enabled"] is True
    assert normalized["ip_asset_bible_id"] == "asset_bible_1"
    assert normalized["ip_profile_id"] == "rabbit_host"
    assert normalized["visual_expression_mode"] == "infographic_layout"
    assert normalized["visual_structure_mode"] == "workflow"
    assert normalized["visual_participation_mode"] == "operator_demonstrator"
    assert normalized["visual_role_mode"] == "supporting_integration"
    assert normalized["visual_consistency_mode"] == "supporting_character"
    assert normalized["effective_visual_role_mode"] == "supporting_integration"


@pytest.mark.parametrize("strategy", ["observer_guide", "signature_presence"])
def test_normalize_standard_video_generation_params_constrains_v44_supporting_strategies(
    strategy,
):
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            visual_role_mode="auto",
            visual_consistency_mode="primary_character",
            visual_role_strategy=strategy,
        )
    )

    assert normalized["visual_role_strategy"] == strategy
    assert normalized["visual_consistency_mode"] == "primary_character"
    assert normalized["effective_visual_role_mode"] == "supporting_integration"


def test_normalize_standard_video_generation_params_allows_participant_subject_replacement():
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            visual_role_mode="auto",
            visual_consistency_mode="primary_character",
            visual_role_strategy="participant",
        )
    )

    assert normalized["visual_role_strategy"] == "participant"
    assert normalized["visual_consistency_mode"] == "primary_character"
    assert normalized["effective_visual_role_mode"] == "subject_replacement"


def test_normalize_standard_video_generation_params_does_not_auto_promote_host_explainer():
    normalized = normalize_standard_video_generation_params(
        _enabled_params(
            visual_role_mode="auto",
            visual_consistency_mode="primary_character",
            visual_role_strategy="host_explainer",
        )
    )

    assert normalized["visual_role_strategy"] == "host_explainer"
    assert normalized["visual_consistency_mode"] == "primary_character"
    assert normalized["effective_visual_role_mode"] == "auto"


def test_validate_standard_video_generation_params_accepts_visual_role_controls():
    validate_standard_video_generation_params(_enabled_params())


def test_visual_role_strategy_accepts_known_values():
    assert VisualRoleStrategy.from_value("host_explainer") is VisualRoleStrategy.HOST_EXPLAINER
    assert VisualRoleStrategy.from_value("observer_guide") is VisualRoleStrategy.OBSERVER_GUIDE
    assert VisualRoleStrategy.from_value("not_a_strategy") is VisualRoleStrategy.AUTO


@pytest.mark.parametrize(
    "strategy",
    [
        VisualRoleStrategy.SIGNATURE_PRESENCE,
        VisualRoleStrategy.OBSERVER_GUIDE,
        VisualRoleStrategy.BACKGROUND_SIGNATURE,
    ],
)
def test_v44_context_downgrades_subject_replacement_for_observer_signature_strategies(
    strategy,
):
    assert (
        resolve_effective_role_mode_with_v44_context(
            requested_role_mode=VisualRoleMode.SUBJECT_REPLACEMENT,
            consistency_mode=VisualConsistencyMode.OFF,
            visual_role_strategy=strategy,
            subject_replacement_allowed=False,
        )
        is VisualRoleMode.SUPPORTING_INTEGRATION
    )


def test_v44_context_blocks_explicit_subject_replacement_when_not_allowed():
    assert (
        resolve_effective_role_mode_with_v44_context(
            requested_role_mode=VisualRoleMode.SUBJECT_REPLACEMENT,
            consistency_mode=VisualConsistencyMode.OFF,
            visual_role_strategy=VisualRoleStrategy.HOST_EXPLAINER,
            subject_replacement_allowed=False,
        )
        is VisualRoleMode.SUPPORTING_INTEGRATION
    )


def test_v44_context_primary_character_replacement_requires_participant_strategy():
    assert (
        resolve_effective_role_mode_with_v44_context(
            requested_role_mode=VisualRoleMode.AUTO,
            consistency_mode=VisualConsistencyMode.PRIMARY_CHARACTER,
            visual_role_strategy=VisualRoleStrategy.PARTICIPANT,
            subject_replacement_allowed=True,
        )
        is VisualRoleMode.SUBJECT_REPLACEMENT
    )
    assert (
        resolve_effective_role_mode_with_v44_context(
            requested_role_mode=VisualRoleMode.AUTO,
            consistency_mode=VisualConsistencyMode.PRIMARY_CHARACTER,
            visual_role_strategy=VisualRoleStrategy.PARTICIPANT,
            subject_replacement_allowed=False,
        )
        is VisualRoleMode.SUPPORTING_INTEGRATION
    )
    assert (
        resolve_effective_role_mode_with_v44_context(
            requested_role_mode=VisualRoleMode.AUTO,
            consistency_mode=VisualConsistencyMode.PRIMARY_CHARACTER,
            visual_role_strategy=VisualRoleStrategy.HOST_EXPLAINER,
            subject_replacement_allowed=True,
        )
        is VisualRoleMode.AUTO
    )
