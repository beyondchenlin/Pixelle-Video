from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.workflow_defaults import BUILTIN_DEFAULT_WORKFLOWS


def test_tts_defaults_to_comfyui_indextts2_workflow():
    config = PixelleVideoConfig()

    assert config.comfyui.tts.inference_mode == "comfyui"
    assert config.comfyui.tts.comfyui.default_workflow == "selfhost/tts_index2.json"
    assert config.comfyui.tts.default_workflow == "selfhost/tts_index2.json"
    assert BUILTIN_DEFAULT_WORKFLOWS["tts"] == "selfhost/tts_index2.json"


def test_comfyui_config_exposes_nested_tts_settings_for_ui(monkeypatch):
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())

    tts_config = config_manager.get_comfyui_config()["tts"]

    assert tts_config["inference_mode"] == "comfyui"
    assert tts_config["comfyui"]["default_workflow"] == "selfhost/tts_index2.json"
    assert tts_config["default_workflow"] == "selfhost/tts_index2.json"


def test_legacy_tts_default_workflow_config_is_migrated_to_comfyui_section():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "tts": {
                    "default_workflow": "selfhost/tts_longcat.json",
                }
            }
        }
    )

    assert config.comfyui.tts.comfyui.default_workflow == "selfhost/tts_longcat.json"
    assert config.comfyui.tts.default_workflow == "selfhost/tts_longcat.json"


def test_nested_tts_default_workflow_takes_priority_over_legacy_field():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "tts": {
                    "default_workflow": "selfhost/tts_longcat.json",
                    "comfyui": {
                        "default_workflow": "selfhost/tts_voxcpm2_saganaki.json",
                    },
                }
            }
        }
    )

    assert config.comfyui.tts.comfyui.default_workflow == "selfhost/tts_voxcpm2_saganaki.json"
    assert config.comfyui.tts.default_workflow == "selfhost/tts_voxcpm2_saganaki.json"
