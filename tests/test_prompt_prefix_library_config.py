import pytest
from pydantic import ValidationError

from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.prompt_prefix_library import (
    BUILTIN_PROMPT_PREFIXES,
    get_effective_image_prompt_prefix,
    get_prompt_prefix_category_options,
    image_prompt_prefix_revision,
)
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.models.image_style_selection import normalize_image_style_selection


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


def test_versioned_image_style_selection_is_one_atomic_contract():
    revision = image_prompt_prefix_revision("flat illustration")

    selection = normalize_image_style_selection("flat-style", revision)

    assert selection is not None
    assert selection.style_id == "flat-style"
    assert selection.revision == revision


@pytest.mark.parametrize(
    "style_id, revision, prompt_prefix",
    [
        ("flat-style", None, None),
        (None, "a" * 64, None),
        ("flat-style", "a" * 64, "raw style"),
    ],
)
def test_versioned_image_style_selection_rejects_partial_or_conflicting_state(
    style_id,
    revision,
    prompt_prefix,
):
    with pytest.raises(ValueError):
        normalize_image_style_selection(
            style_id,
            revision,
            prompt_prefix=prompt_prefix,
        )


def test_get_effective_image_prompt_prefix_prefers_active_library_item():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "retired config value",
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


def test_get_effective_image_prompt_prefix_returns_empty_when_library_has_no_active_item():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix": "retired config value",
                    "prompt_prefix_library": {
                        "active_prefix_id": None,
                        "items": [],
                    },
                }
            }
        }
    )

    assert get_effective_image_prompt_prefix(config.comfyui.image) == ""


def test_image_config_with_legacy_prompt_prefix_and_no_library_does_not_activate_legacy_prefix():
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
    assert get_effective_image_prompt_prefix(config.comfyui.image) == ""


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


def test_prompt_prefix_library_config_rejects_legacy_workflow_preview_asset_strings():
    with pytest.raises(ValidationError):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix_library": {
                            "active_prefix_id": "manual-test",
                            "items": [
                                {
                                    "id": "manual-test",
                                    "name": "Manual Test",
                                    "content": "flat illustration",
                                    "style_category_id": "flat_illustration",
                                    "scene_category_id": "knowledge_sharing",
                                    "workflow_preview_assets": {
                                        "selfhost/image_z_image_turbo.json": (
                                            "resources/prompt_prefix_previews/custom/manual-test.webp"
                                        )
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        )


def test_prompt_prefix_library_config_preserves_workflow_preview_metadata_fields():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "image": {
                    "prompt_prefix_library": {
                        "active_prefix_id": "manual-test",
                        "items": [
                            {
                                "id": "manual-test",
                                "name": "Manual Test",
                                "content": "flat illustration",
                                "style_category_id": "flat_illustration",
                                "scene_category_id": "knowledge_sharing",
                                "workflow_preview_assets": {
                                    " selfhost/image_z_image_turbo.json ": {
                                        "asset_path": " resources/prompt_prefix_previews/custom/manual-test.webp ",
                                        "reference_prompt": " storybook cover ",
                                        "generated_at": " 2026-04-22T12:34:56Z ",
                                        "status": " ready ",
                                    }
                                },
                            }
                        ],
                    }
                }
            }
        }
    )

    preview = config.comfyui.image.prompt_prefix_library.items[0].workflow_preview_assets[
        "selfhost/image_z_image_turbo.json"
    ]

    assert preview.asset_path == "resources/prompt_prefix_previews/custom/manual-test.webp"
    assert preview.reference_prompt == "storybook cover"
    assert preview.generated_at == "2026-04-22T12:34:56Z"
    assert preview.status == "ready"


def _style_item(item_id: str = "manual-test") -> dict:
    return {
        "id": item_id,
        "name": "Manual Test",
        "content": "flat illustration",
        "style_category_id": "flat_illustration",
        "scene_category_id": "knowledge_sharing",
    }


@pytest.mark.parametrize("item_id", ["", " spaced ", "../style", "style/one"])
def test_prompt_prefix_library_rejects_invalid_item_ids(item_id):
    with pytest.raises(ValidationError, match="image style id"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix_library": {
                            "active_prefix_id": None,
                            "items": [_style_item(item_id)],
                        }
                    }
                }
            }
        )


def test_prompt_prefix_library_rejects_duplicate_item_ids():
    with pytest.raises(ValidationError, match="must be unique"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix_library": {
                            "active_prefix_id": "manual-test",
                            "items": [_style_item(), _style_item()],
                        }
                    }
                }
            }
        )


def test_prompt_prefix_library_rejects_dangling_active_id():
    with pytest.raises(ValidationError, match="must reference an existing"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "image": {
                        "prompt_prefix_library": {
                            "active_prefix_id": "missing-style",
                            "items": [_style_item()],
                        }
                    }
                }
            }
        )


def test_prompt_prefix_revision_uses_canonical_effective_content():
    assert image_prompt_prefix_revision("  flat illustration  ") == (
        image_prompt_prefix_revision("flat illustration")
    )
    assert len(image_prompt_prefix_revision("flat illustration")) == 64
