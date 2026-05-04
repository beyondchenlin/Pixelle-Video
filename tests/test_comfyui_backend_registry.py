from pathlib import Path

import pytest

from pixelle_video.config import config_manager
from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.comfyui_backend_registry import ComfyUIBackendRegistry


def make_registry() -> ComfyUIBackendRegistry:
    config = ComfyUIConfig.model_validate(
        {
            "comfyui_url": "http://127.0.0.1:8000",
            "executor_type": None,
            "runninghub_api_key": "rh",
            "runninghub_instance_type": "plus",
            "backends": {
                "image": {"url": "http://127.0.0.1:8001"},
                "tts": {"url": "http://127.0.0.1:8002"},
            },
            "workflow_routing": {"image": "image", "tts": "tts"},
        }
    )
    return ComfyUIBackendRegistry(config, repo_root=Path.cwd())


def test_registry_resolves_media_and_tts_roles():
    registry = make_registry()

    assert registry.resolve_role_for_media("selfhost/image_z.json", "image") == "image"
    assert registry.resolve_role_for_media("selfhost/video_wan.json", "image") == "default"
    assert registry.resolve_role_for_tts("selfhost/tts_index2.json") == "tts"
    assert registry.resolve_role_for_workflow("selfhost/video_wan.json") == "default"
    assert registry.resolve_role_for_workflow("runninghub/image.json") == "default"


def test_registry_builds_role_specific_comfykit_config():
    registry = make_registry()

    config = registry.get_comfykit_config("image")

    assert config["comfyui_url"] == "http://127.0.0.1:8001"
    assert config["executor_type"] == "http"
    assert config["runninghub_api_key"] == "rh"
    assert config["runninghub_instance_type"] == "plus"


def test_registry_reports_dedicated_backend():
    registry = make_registry()

    assert registry.is_dedicated_backend("image") is True
    assert registry.is_dedicated_backend("tts") is True
    assert registry.is_dedicated_backend("default") is False


def test_registry_unknown_profile_error_includes_role():
    registry = make_registry()

    with pytest.raises(ValueError, match="missing-role"):
        registry.profile("missing-role")


def test_core_backend_registry_uses_latest_comfyui_config(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "backends": {"image": {"url": "http://127.0.0.1:8001"}},
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()

    first_registry = core._get_comfyui_backend_registry()

    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:9000",
                    "backends": {"image": {"url": "http://127.0.0.1:9001"}},
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    latest_registry = core._get_comfyui_backend_registry()

    assert first_registry.profile("image").url == "http://127.0.0.1:8001"
    assert latest_registry.profile("image").url == "http://127.0.0.1:9001"
