import pytest
from pydantic import ValidationError

from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.schema import PixelleVideoConfig


def test_reference_image_and_vision_llm_are_typed_config_sections():
    config = PixelleVideoConfig(
        reference_image={
            "enabled": True,
            "analysis_mode": "auto",
            "workflow_injection_mode": "required",
            "profile_merge_mode": "override",
            "allowed_extensions": [".png"],
            "workflow_param_overrides": {
                "selfhost/image_reference.json": "reference_image",
            },
        },
        vision_llm={
            "enabled": True,
            "model": "qwen-vl-max",
            "force_supports_vision": True,
            "connect_timeout_seconds": 3,
            "read_timeout_seconds": 45,
            "max_retries": 2,
        },
    )

    assert config.reference_image.enabled is True
    assert config.reference_image.analysis_mode == "auto"
    assert config.reference_image.workflow_injection_mode == "required"
    assert config.reference_image.profile_merge_mode == "override"
    assert config.reference_image.allowed_extensions == [".png"]
    assert config.reference_image.workflow_param_overrides == {
        "selfhost/image_reference.json": "reference_image",
    }
    assert config.vision_llm.enabled is True
    assert config.vision_llm.model == "qwen-vl-max"
    assert config.vision_llm.force_supports_vision is True
    assert config.vision_llm.connect_timeout_seconds == 3
    assert config.vision_llm.read_timeout_seconds == 45
    assert config.vision_llm.max_retries == 2

    payload = config.to_dict()
    assert payload["reference_image"]["enabled"] is True
    assert payload["vision_llm"]["model"] == "qwen-vl-max"


def test_reference_image_config_defaults_match_disabled_production_policy():
    payload = PixelleVideoConfig().to_dict()

    assert payload["reference_image"]["enabled"] is False
    assert payload["reference_image"]["web_ui_enabled"] is True
    assert payload["reference_image"]["analysis_mode"] == "off"
    assert payload["reference_image"]["workflow_injection_mode"] == "off"
    assert payload["vision_llm"]["enabled"] is False


def test_config_manager_reads_reference_sections_from_typed_schema():
    manager = object.__new__(ConfigManager)
    manager.raw_config = {
        "reference_image": {"enabled": False},
        "vision_llm": {"model": "raw-model"},
    }
    manager.config = PixelleVideoConfig(
        reference_image={"enabled": True},
        vision_llm={"model": "typed-model"},
    )

    assert manager.get("reference_image")["enabled"] is True
    assert manager.get("vision_llm")["model"] == "typed-model"


def test_reference_image_config_normalizes_extensions_and_rejects_bad_overrides():
    config = PixelleVideoConfig(
        reference_image={
            "allowed_extensions": ["PNG", ".jpg", "png"],
            "workflow_param_overrides": {
                "selfhost/custom.json": {"param_names": "init_image"},
            },
        }
    )

    assert config.reference_image.allowed_extensions == [".png", ".jpg"]
    assert config.reference_image.workflow_param_overrides == {
        "selfhost/custom.json": {"param_names": ["init_image"]},
    }

    with pytest.raises(ValidationError):
        PixelleVideoConfig(reference_image={"workflow_param_overrides": []})

    with pytest.raises(ValidationError):
        PixelleVideoConfig(reference_image={"workflow_param_overrides": {"selfhost/custom.json": 1}})

    with pytest.raises(ValidationError):
        PixelleVideoConfig(reference_image={"workflow_param_overrides": {"selfhost/custom.json": []}})


def test_reference_image_config_rejects_invalid_modes():
    with pytest.raises(ValidationError):
        PixelleVideoConfig(reference_image={"analysis_mode": "always"})

    with pytest.raises(ValidationError):
        PixelleVideoConfig(vision_llm={"unavailable_policy": "ignore"})

    with pytest.raises(ValidationError):
        PixelleVideoConfig(vision_llm={"read_timeout_seconds": 0})

    with pytest.raises(ValidationError):
        PixelleVideoConfig(vision_llm={"max_retries": 6})


def test_direct_media_config_defaults_disabled_and_validates_resource_limits():
    config = PixelleVideoConfig(
        direct_media={
            "enabled": True,
            "openai_image": {
                "enabled": True,
                "api_key": "configured-secret",
                "max_output_size_mb": 32,
                "max_output_pixels": 12_000_000,
            },
        }
    )

    assert PixelleVideoConfig().direct_media.enabled is False
    assert PixelleVideoConfig().direct_media.openai_image.enabled is False
    assert config.direct_media.enabled is True
    assert config.direct_media.openai_image.max_output_size_mb == 32
    assert config.direct_media.openai_image.max_output_pixels == 12_000_000

    with pytest.raises(ValidationError):
        PixelleVideoConfig(direct_media={"openai_image": {"max_output_size_mb": 0}})
    with pytest.raises(ValidationError):
        PixelleVideoConfig(direct_media={"openai_image": {"max_output_pixels": 0}})
