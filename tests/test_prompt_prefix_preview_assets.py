from pathlib import Path

from pixelle_video.config import PixelleVideoConfig
from pixelle_video.config.prompt_prefix_library import (
    BUILTIN_PROMPT_PREFIXES,
    DEFAULT_PROMPT_PREFIX_PLACEHOLDER,
    get_prompt_prefix_preview_asset,
)


def test_builtin_prompt_prefix_defaults_include_preview_asset_paths():
    config = PixelleVideoConfig()
    items = config.comfyui.image.prompt_prefix_library.items

    assert items
    assert all(item.preview_asset_path for item in items)


def test_builtin_prompt_prefix_preview_assets_exist_on_disk():
    for item in BUILTIN_PROMPT_PREFIXES:
        assert item.preview_asset_path
        assert Path(item.preview_asset_path).exists()


def test_prompt_prefix_preview_placeholder_exists():
    assert Path(DEFAULT_PROMPT_PREFIX_PLACEHOLDER).exists()


def test_get_prompt_prefix_preview_asset_falls_back_to_placeholder_for_missing_file():
    asset_path = get_prompt_prefix_preview_asset({"preview_asset_path": "resources/prompt_prefix_previews/missing.svg"})

    assert asset_path == DEFAULT_PROMPT_PREFIX_PLACEHOLDER
