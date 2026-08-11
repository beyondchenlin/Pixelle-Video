from pixelle_video.config import config_manager
from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore


def test_get_comfykit_config_defaults_to_http_executor(monkeypatch):
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
        "executor_type": "http",
    }


def test_get_comfykit_config_defaults_to_http_with_comfyui_api_key(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "comfyui_api_key": "secret-token",
                    "executor_type": None,
                }
            }
        ),
    )

    core = PixelleVideoCore()

    assert core._get_comfykit_config()["executor_type"] == "http"


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


def test_get_comfykit_config_respects_explicit_websocket_override(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret-token",
                executor_type="websocket",
            )
        ),
    )

    core = PixelleVideoCore()

    assert core._get_comfykit_config()["executor_type"] == "websocket"


def test_comfyui_backend_management_defaults_to_external_desktop_mode():
    config = PixelleVideoConfig()

    assert config.comfyui.comfyui_url == "http://127.0.0.1:8188"
    assert config.comfyui.backend_management_mode == "disabled"
    assert config.comfyui.backends["default"].managed is True
    assert config.comfyui.backends["default"].restart_after_batch is False


def test_comfyui_headless_management_remains_an_explicit_supported_mode():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backend_management_mode": "auto",
                "backends": {
                    "default": {
                        "managed": True,
                        "restart_after_batch": True,
                    }
                },
            }
        }
    )

    assert config.comfyui.backend_management_mode == "auto"
    assert config.comfyui.backends["default"].managed is True
    assert config.comfyui.backends["default"].restart_after_batch is True


def test_service_backend_management_fallback_is_fail_safe():
    core = PixelleVideoCore()

    assert core._get_comfyui_backend_management_mode({}) == "disabled"
    assert (
        core._get_comfyui_backend_management_mode(
            {"backend_management_mode": "unsupported"}
        )
        == "disabled"
    )


def test_comfyui_legacy_gguf_cleanup_strategy_is_retired():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"gguf_cleanup_strategy": "process_restart"}}
    )

    assert not hasattr(config.comfyui, "gguf_cleanup_strategy")
    assert "gguf_cleanup_strategy" not in config.comfyui.model_dump()


def test_comfyui_config_exposes_backend_management_mode(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                backend_management_mode="required",
            )
        ),
    )

    assert config_manager.get_comfyui_config()["backend_management_mode"] == "required"


def test_comfyui_config_does_not_expose_retired_gguf_cleanup_strategy(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(comfyui=ComfyUIConfig(comfyui_url="http://127.0.0.1:8000")),
    )

    assert "gguf_cleanup_strategy" not in config_manager.get_comfyui_config()


def test_legacy_post_generation_cleanup_fields_are_not_exposed(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "post_generation_cleanup_mode": "idle",
                    "post_generation_cleanup_intensity": "low",
                }
            }
        ),
    )

    comfyui_config = config_manager.get_comfyui_config()

    assert "post_generation_cleanup_mode" not in comfyui_config
    assert "post_generation_cleanup_intensity" not in comfyui_config


def test_comfyui_config_exposes_backends_and_workflow_routing(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )

    comfyui_config = config_manager.get_comfyui_config()

    assert comfyui_config["backends"]["image"]["url"] == "http://127.0.0.1:8001"
    assert comfyui_config["backends"]["tts"]["url"] == "http://127.0.0.1:8002"
    assert comfyui_config["workflow_routing"]["image"] == "image"
    assert comfyui_config["workflow_routing"]["tts"] == "tts"


def test_set_comfyui_config_accepts_backends_and_workflow_routing(monkeypatch):
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())

    config_manager.set_comfyui_config(
        backends={
            "image": {"url": "http://127.0.0.1:8001"},
            "tts": {"url": "http://127.0.0.1:8002"},
        },
        workflow_routing={"image": "image", "tts": "tts"},
    )

    assert config_manager.config.comfyui.backends["image"].url == "http://127.0.0.1:8001"
    assert config_manager.config.comfyui.backends["tts"].url == "http://127.0.0.1:8002"
    assert config_manager.config.comfyui.workflow_routing.image == "image"
    assert config_manager.config.comfyui.workflow_routing.tts == "tts"


def test_set_comfyui_config_replaces_backends_instead_of_merging(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )

    config_manager.set_comfyui_config(
        backends={"image": {"url": "http://127.0.0.1:9001"}},
        workflow_routing={"image": "image", "tts": "default"},
    )

    assert set(config_manager.config.comfyui.backends) == {"default", "image"}
    assert "tts" not in config_manager.config.comfyui.backends
    assert config_manager.config.comfyui.backends["image"].url == "http://127.0.0.1:9001"
    assert config_manager.config.comfyui.workflow_routing.tts == "default"


def test_set_comfyui_config_updates_default_backend_url_with_legacy_url(monkeypatch):
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())

    config_manager.set_comfyui_config(comfyui_url="http://127.0.0.1:9000")

    assert config_manager.config.comfyui.comfyui_url == "http://127.0.0.1:9000"
    assert config_manager.config.comfyui.backends["default"].url == "http://127.0.0.1:9000"


def test_set_comfyui_config_syncs_legacy_url_from_default_backend(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
        ),
    )

    config_manager.set_comfyui_config(
        backends={"default": {"url": "http://127.0.0.1:9000"}}
    )

    assert config_manager.config.comfyui.comfyui_url == "http://127.0.0.1:9000"
    assert config_manager.config.comfyui.backends["default"].url == "http://127.0.0.1:9000"


def test_set_comfyui_config_prefers_structured_default_backend_url_over_legacy_url(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
        ),
    )

    config_manager.set_comfyui_config(
        comfyui_url="http://127.0.0.1:8000",
        backends={"default": {"url": "http://127.0.0.1:9000"}},
    )

    assert config_manager.config.comfyui.comfyui_url == "http://127.0.0.1:9000"
    assert config_manager.config.comfyui.backends["default"].url == "http://127.0.0.1:9000"


def test_set_comfyui_config_replaces_workflow_routing_instead_of_merging(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )

    config_manager.set_comfyui_config(workflow_routing={})

    assert config_manager.config.comfyui.workflow_routing.image == "default"
    assert config_manager.config.comfyui.workflow_routing.tts == "default"
    assert config_manager.config.comfyui.workflow_routing.default == "default"


def test_set_comfyui_config_accepts_none_workflow_routing_as_default(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                        "tts": {"url": "http://127.0.0.1:8002"},
                    },
                    "workflow_routing": {"image": "image", "tts": "tts"},
                }
            }
        ),
    )

    config_manager.set_comfyui_config(workflow_routing=None)

    assert config_manager.config.comfyui.workflow_routing.image == "default"
    assert config_manager.config.comfyui.workflow_routing.tts == "default"
    assert config_manager.config.comfyui.workflow_routing.default == "default"
