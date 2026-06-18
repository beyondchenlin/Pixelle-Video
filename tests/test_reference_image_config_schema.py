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

    payload = config.to_dict()
    assert payload["reference_image"]["enabled"] is True
    assert payload["vision_llm"]["model"] == "qwen-vl-max"


def test_reference_image_config_defaults_match_disabled_production_policy():
    payload = PixelleVideoConfig().to_dict()

    assert payload["reference_image"]["enabled"] is False
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
