import pytest

from pixelle_video.models.video_generation_contract import (
    normalize_standard_video_generation_params,
    validate_standard_video_generation_params,
)
from pixelle_video.models.visual_expression import VisualExpressionMode
from pixelle_video.models.visual_role_request import (
    VISUAL_ROLE_PIPELINE_VERSION,
    VisualRoleControlsContract,
    VisualRoleRequest,
)
from pixelle_video.models.visual_role_strategy import VisualRoleMode


def _enabled_params(**overrides):
    payload = {
        "ip_enabled": True,
        "ip_asset_bible_id": "asset_bible_1",
        "ip_profile_id": "rabbit_host",
        "visual_expression_mode": "infographic_layout",
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
    assert controls.strategy.role_mode.value == "supporting_integration"
    assert controls.strategy.consistency_mode.value == "supporting_character"
    assert controls.to_generation_dict() == {
        "visual_expression_mode": "infographic_layout",
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


def test_visual_role_request_disabled_does_not_trigger_v4():
    request = VisualRoleRequest.from_mapping({})

    assert request.enabled is False
    assert request.pipeline_version == VISUAL_ROLE_PIPELINE_VERSION
    request.validate()


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
    assert normalized["visual_role_mode"] == "supporting_integration"
    assert normalized["visual_consistency_mode"] == "supporting_character"
    assert normalized["effective_visual_role_mode"] == "supporting_integration"


def test_validate_standard_video_generation_params_accepts_visual_role_controls():
    validate_standard_video_generation_params(_enabled_params())
