from pixelle_video.config import config_manager
from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore


def test_get_comfykit_config_defaults_to_websocket_executor(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
            )
        ),
    )

    core = PixelleVideoCore()

    assert core._get_comfykit_config() == {
        "comfyui_url": "http://127.0.0.1:8000",
        "executor_type": "websocket",
    }


def test_get_comfykit_config_uses_explicit_executor_type(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                executor_type="http",
            )
        ),
    )

    core = PixelleVideoCore()

    assert core._get_comfykit_config()["executor_type"] == "http"
