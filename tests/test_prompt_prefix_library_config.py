from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.prompt_prefix_library import (
    BUILTIN_PROMPT_PREFIXES,
    get_effective_image_prompt_prefix,
    get_prompt_prefix_category_options,
)
from pixelle_video.config.schema import PixelleVideoConfig


def test_image_config_exposes_builtin_prompt_prefix_library_defaults():
    config = PixelleVideoConfig()

    library = config.comfyui.image.prompt_prefix_library

    assert library.active_prefix_id
    assert library.items
    assert library.items[0].style_category_id
    assert library.items[0].scene_category_id
    assert library.items[0].id in {item.id for item in library.items}


def test_builtin_prompt_prefix_defaults_match_schema_defaults():
    config = PixelleVideoConfig()

    assert len(BUILTIN_PROMPT_PREFIXES) == len(config.comfyui.image.prompt_prefix_library.items)
    assert config.comfyui.image.prompt_prefix_library.active_prefix_id == BUILTIN_PROMPT_PREFIXES[0].id


def test_get_effective_image_prompt_prefix_prefers_active_library_item():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "legacy prefix",
                    "prompt_prefix_library": {
                        "active_prefix_id": "custom-flat",
                        "items": [
                            {
                                "id": "custom-flat",
                                "name": "Flat",
                                "content": "flat illustration, simple shapes",
                                "style_category_id": "flat_illustration",
                                "scene_category_id": "knowledge_sharing",
                                "source": "manual",
                                "is_builtin": False,
                            }
                        ],
                    },
                }
            }
        }
    )

    assert get_effective_image_prompt_prefix(config.comfyui.image) == "flat illustration, simple shapes"


def test_get_effective_image_prompt_prefix_falls_back_to_legacy_prefix_when_library_has_no_active_item():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "legacy prefix",
                    "prompt_prefix_library": {
                        "active_prefix_id": None,
                        "items": [],
                    },
                }
            }
        }
    )

    assert get_effective_image_prompt_prefix(config.comfyui.image) == "legacy prefix"


def test_image_config_with_legacy_prompt_prefix_and_no_library_keeps_legacy_prefix_active():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "legacy custom prefix",
                }
            }
        }
    )

    assert config.comfyui.image.prompt_prefix_library.active_prefix_id is None
    assert config.comfyui.image.prompt_prefix_library.items
    assert get_effective_image_prompt_prefix(config.comfyui.image) == "legacy custom prefix"


def test_get_prompt_prefix_category_options_return_stable_ids():
    style_options, scene_options = get_prompt_prefix_category_options()

    assert "storybook" in style_options
    assert "childrens_story" in scene_options


def test_get_comfyui_config_includes_image_prompt_prefix_library(monkeypatch):
    manager = ConfigManager.__new__(ConfigManager)
    manager.config_path = None
    manager.config = PixelleVideoConfig()
    manager._initialized = True

    comfyui_config = manager.get_comfyui_config()

    assert "prompt_prefix_library" in comfyui_config["image"]
    assert comfyui_config["video"]["prompt_prefix"]
