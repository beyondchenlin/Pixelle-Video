import pytest

from pixelle_video.config.schema import PixelleVideoConfig


def test_empty_backends_create_default_profile_from_comfyui_url():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
    )

    default = config.comfyui.backends["default"]

    assert default.url == "http://127.0.0.1:8000"
    assert default.data_root.replace("\\", "/").endswith("/pixelle-default")
    assert default.runtime_dir.replace("\\", "/").endswith("_runtime/comfyui/default")
    assert default.logs_dir.replace("\\", "/").endswith("logs/comfyui/default")
    assert default.database_url.replace("\\", "/").endswith(
        "/pixelle-default/user/comfyui.db"
    )


def test_config_keeps_structured_profiles_and_routing():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "backends": {
                    "image": {
                        "url": "http://127.0.0.1:8001",
                        "restart_after_batch": True,
                    },
                    "tts": {
                        "url": "http://127.0.0.1:8002",
                        "restart_after_batch": True,
                    },
                },
                "workflow_routing": {
                    "image": "image",
                    "tts": "tts",
                    "default": "default",
                },
            }
        }
    )

    assert set(config.comfyui.backends) == {"default", "image", "tts"}
    assert config.comfyui.backends["image"].url == "http://127.0.0.1:8001"
    assert config.comfyui.backends["image"].restart_after_batch is True
    assert config.comfyui.workflow_routing.image == "image"
    assert config.comfyui.workflow_routing.tts == "tts"


def test_backend_profile_keeps_optional_runtime_paths():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {
                        "python_exe": "D:/Python/python.exe",
                        "comfyui_root": "D:/ComfyUI",
                        "frontend_root": "D:/ComfyUI/web",
                        "extra_models_config": "D:/ComfyUI/extra_model_paths.yaml",
                    },
                },
            }
        }
    )

    profile = config.comfyui.backends["image"]

    assert profile.python_exe == "D:/Python/python.exe"
    assert profile.comfyui_root == "D:/ComfyUI"
    assert profile.frontend_root == "D:/ComfyUI/web"
    assert profile.extra_models_config == "D:/ComfyUI/extra_model_paths.yaml"


def test_backend_profile_database_url_defaults_to_profile_data_root():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {
                        "data_root": "D:/PixelleComfy/image",
                    },
                },
            }
        }
    )

    assert config.comfyui.backends["image"].database_url == (
        "sqlite:///D:/PixelleComfy/image/user/comfyui.db"
    )


def test_backend_profile_database_url_uses_normalized_data_root():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {
                        "data_root": "D:/PixelleComfy/image/",
                    },
                },
            }
        }
    )

    assert config.comfyui.backends["image"].database_url == (
        "sqlite:///D:/PixelleComfy/image/user/comfyui.db"
    )


def test_backend_profile_accepts_null_database_url_and_generates_default():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {
                        "url": "http://127.0.0.1:8001",
                        "data_root": "D:/PixelleComfy/image/",
                        "database_url": None,
                    }
                }
            }
        }
    )

    assert config.comfyui.backends["image"].database_url == (
        "sqlite:///D:/PixelleComfy/image/user/comfyui.db"
    )


def test_backend_profile_accepts_null_core_paths_and_generates_defaults():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "backends": {
                    "image": {
                        "url": None,
                        "data_root": None,
                        "runtime_dir": None,
                        "logs_dir": None,
                    }
                },
            }
        }
    )

    profile = config.comfyui.backends["image"]

    assert profile.url == "http://127.0.0.1:8000"
    assert profile.data_root == "E:/ComfyUIData/pixelle-image"
    assert profile.runtime_dir == "_runtime/comfyui/image"
    assert profile.logs_dir == "logs/comfyui/image"
    assert profile.database_url == "sqlite:///E:/ComfyUIData/pixelle-image/user/comfyui.db"


def test_null_backend_containers_create_default_profile_and_routing():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "backends": None,
                "workflow_routing": None,
            }
        }
    )

    assert set(config.comfyui.backends) == {"default"}
    assert config.comfyui.backends["default"].url == "http://127.0.0.1:8000"
    assert config.comfyui.workflow_routing.image == "default"
    assert config.comfyui.workflow_routing.tts == "default"
    assert config.comfyui.workflow_routing.default == "default"


def test_null_backend_entry_defaults_by_profile_name():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "backends": {
                    "image": None,
                },
            }
        }
    )

    profile = config.comfyui.backends["image"]

    assert profile.url == "http://127.0.0.1:8000"
    assert profile.data_root == "E:/ComfyUIData/pixelle-image"
    assert profile.runtime_dir == "_runtime/comfyui/image"
    assert profile.logs_dir == "logs/comfyui/image"


@pytest.mark.parametrize("bad_name", ["Image", "../image", "image role", "tts.role"])
def test_backend_profile_names_are_restricted(bad_name):
    with pytest.raises(ValueError, match="backend profile name"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        bad_name: {"url": "http://127.0.0.1:8001"},
                    }
                }
            }
        )


def test_workflow_routing_must_reference_existing_profile():
    with pytest.raises(ValueError, match="workflow_routing.image"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                    },
                    "workflow_routing": {
                        "image": "missing",
                    },
                }
            }
        )
