import pytest

from pixelle_video.config.schema import PixelleVideoConfig


def test_empty_backends_create_default_profile_from_comfyui_url():
    config = PixelleVideoConfig.model_validate(
        {"comfyui": {"comfyui_url": "http://127.0.0.1:8000"}}
    )

    default = config.comfyui.backends["default"]

    assert default.url == "http://127.0.0.1:8000"
    assert default.data_root.replace("\\", "/").endswith("/pixelle-default")
    assert default.shared_base_path == "E:/ComfyUIData"
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
                        "stop_after_batch": True,
                    },
                    "tts": {
                        "url": "http://127.0.0.1:8002",
                        "stop_after_batch": True,
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
    assert config.comfyui.backends["image"].stop_after_batch is True
    assert config.comfyui.workflow_routing.image == "image"
    assert config.comfyui.workflow_routing.tts == "tts"


def test_implicit_default_profile_clones_explicit_fallback_route():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {
                        "url": "http://127.0.0.1:8001",
                        "custom_node_loading": "allowlist",
                        "allowed_custom_node_folders": ["ComfyUI-GGUF"],
                    },
                    "tts": {"url": "http://127.0.0.1:8002"},
                },
                "workflow_routing": {
                    "image": "image",
                    "tts": "tts",
                    "default": "image",
                },
            }
        }
    )

    fallback = config.comfyui.backends["default"]

    assert fallback.url == "http://127.0.0.1:8001"
    assert fallback.custom_node_loading == "allowlist"
    assert fallback.allowed_custom_node_folders == ["ComfyUI-GGUF"]
    assert fallback.managed is False
    assert fallback.stop_after_batch is False


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


def test_backend_profile_defaults_to_automatic_memory_policy():
    config = PixelleVideoConfig.model_validate({"comfyui": {}})

    profile = config.comfyui.backends["default"]

    assert profile.resource_policy == "auto"
    assert profile.minimum_free_commit_gb is None


@pytest.mark.parametrize("legacy_value", [True, False])
def test_backend_profile_migrates_legacy_restart_setting(legacy_value):
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "default": {"restart_after_batch": legacy_value},
                }
            }
        }
    )

    profile = config.comfyui.backends["default"]
    assert profile.stop_after_batch is legacy_value
    assert "restart_after_batch" not in profile.model_dump()


@pytest.mark.parametrize(
    ("legacy_value", "expected"),
    [("true", True), ("false", False), ("1", True), ("0", False)],
)
def test_backend_profile_migrates_legacy_string_boolean_without_inversion(
    legacy_value,
    expected,
):
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "default": {"restart_after_batch": legacy_value},
                }
            }
        }
    )

    assert config.comfyui.backends["default"].stop_after_batch is expected


def test_backend_profile_explicit_stop_setting_wins_over_legacy_setting():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "default": {
                        "restart_after_batch": False,
                        "stop_after_batch": True,
                    },
                }
            }
        }
    )

    assert config.comfyui.backends["default"].stop_after_batch is True


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
    assert config.comfyui.backends["image"].shared_base_path == "D:/PixelleComfy"


def test_backend_profile_preserves_explicit_shared_base_path():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "default": {
                        "data_root": "D:/PixelleData/runtime",
                        "shared_base_path": "F:/SharedComfy",
                    }
                }
            }
        }
    )

    assert config.comfyui.backends["default"].shared_base_path == "F:/SharedComfy"


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


def test_backend_profile_defaults_to_three_retries_after_initial_attempt():
    config = PixelleVideoConfig.model_validate({"comfyui": {}})

    profile = config.comfyui.backends["default"]

    assert profile.startup_attempts == 4
    assert profile.startup_ready_timeout_seconds == 90
    assert profile.startup_retry_base_delay_seconds == 2


def test_backend_profile_normalizes_custom_node_allowlist():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "tts": {
                        "custom_node_loading": "allowlist",
                        "allowed_custom_node_folders": [
                            " ComfyUI-OmniVoice-TTS ",
                            "ComfyUI-VideoHelperSuite",
                        ],
                    }
                }
            }
        }
    )

    profile = config.comfyui.backends["tts"]

    assert profile.custom_node_loading == "allowlist"
    assert profile.allowed_custom_node_folders == [
        "ComfyUI-OmniVoice-TTS",
        "ComfyUI-VideoHelperSuite",
    ]


@pytest.mark.parametrize(
    "folder",
    (
        "../ComfyUI-nunchaku",
        "ComfyUI/OmniVoice",
        "C:\\ComfyUI\\node",
        ".",
        "",
    ),
)
def test_backend_profile_rejects_custom_node_paths(folder):
    with pytest.raises(ValueError, match="folder names only"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "tts": {
                            "custom_node_loading": "allowlist",
                            "allowed_custom_node_folders": [folder],
                        }
                    }
                }
            }
        )


def test_backend_profile_rejects_case_insensitive_duplicate_custom_nodes():
    with pytest.raises(ValueError, match="duplicate folder"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "tts": {
                            "custom_node_loading": "allowlist",
                            "allowed_custom_node_folders": [
                                "ComfyUI-OmniVoice-TTS",
                                "comfyui-omnivoice-tts",
                            ],
                        }
                    }
                }
            }
        )


def test_backend_profile_rejects_allowlist_values_in_all_mode():
    with pytest.raises(ValueError, match="only be set"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "default": {
                            "custom_node_loading": "all",
                            "allowed_custom_node_folders": ["ComfyUI-GGUF"],
                        }
                    }
                }
            }
        )


@pytest.mark.parametrize(
    ("field_name", "shared_value"),
    (
        ("url", "http://127.0.0.1:8001"),
        ("data_root", "E:/ComfyUIData/shared"),
        ("runtime_dir", "_runtime/comfyui/shared"),
        ("logs_dir", "logs/comfyui/shared"),
        ("database_url", "sqlite:///E:/ComfyUIData/shared/user/comfyui.db"),
    ),
)
def test_distinct_routed_profiles_reject_shared_process_identity(
    field_name,
    shared_value,
):
    image = {
        "url": "http://127.0.0.1:8001",
        "data_root": "E:/ComfyUIData/image",
        "runtime_dir": "_runtime/comfyui/image",
        "logs_dir": "logs/comfyui/image",
        "database_url": "sqlite:///E:/ComfyUIData/image/user/comfyui.db",
    }
    tts = {
        "url": "http://127.0.0.1:8002",
        "data_root": "E:/ComfyUIData/tts",
        "runtime_dir": "_runtime/comfyui/tts",
        "logs_dir": "logs/comfyui/tts",
        "database_url": "sqlite:///E:/ComfyUIData/tts/user/comfyui.db",
    }
    image[field_name] = shared_value
    tts[field_name] = shared_value

    with pytest.raises(ValueError, match=field_name):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {"image": image, "tts": tts},
                    "workflow_routing": {
                        "image": "image",
                        "tts": "tts",
                        "default": "image",
                    },
                }
            }
        )


def test_shared_routed_profile_remains_backward_compatible():
    config = PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "shared": {"url": "http://127.0.0.1:8000"},
                },
                "workflow_routing": {
                    "image": "shared",
                    "tts": "shared",
                    "default": "shared",
                },
            }
        }
    )

    assert config.comfyui.workflow_routing.image == "shared"
    assert config.comfyui.workflow_routing.tts == "shared"


@pytest.mark.parametrize(
    ("image_url", "tts_url"),
    (
        ("http://localhost:8001", "http://127.0.0.1:8001"),
        ("http://127.0.0.1:8001/api", "http://127.0.0.1:8001/"),
    ),
)
def test_distinct_routed_profiles_reject_equivalent_listener_endpoints(
    image_url,
    tts_url,
):
    with pytest.raises(ValueError, match="url"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": image_url},
                        "tts": {"url": tts_url},
                    },
                    "workflow_routing": {
                        "image": "image",
                        "tts": "tts",
                        "default": "image",
                    },
                }
            }
        )


@pytest.mark.parametrize(
    ("field_name", "image_value", "tts_value"),
    (
        (
            "data_root",
            "E:/ComfyUIData/shared",
            "E:/ComfyUIData/image/../shared",
        ),
        (
            "runtime_dir",
            "_runtime/comfyui/shared",
            "_runtime/comfyui/tts/../shared",
        ),
        (
            "logs_dir",
            "logs/comfyui/shared",
            "logs/comfyui/tts/../shared",
        ),
        (
            "database_url",
            "sqlite:///E:/ComfyUIData/shared/user/comfyui.db",
            "sqlite:///E:/ComfyUIData/image/../shared/user/comfyui.db?timeout=30",
        ),
    ),
)
def test_distinct_routed_profiles_reject_equivalent_filesystem_identities(
    field_name,
    image_value,
    tts_value,
):
    image = {"url": "http://127.0.0.1:8001", field_name: image_value}
    tts = {"url": "http://127.0.0.1:8002", field_name: tts_value}

    with pytest.raises(ValueError, match=field_name):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {"image": image, "tts": tts},
                    "workflow_routing": {
                        "image": "image",
                        "tts": "tts",
                        "default": "image",
                    },
                }
            }
        )


@pytest.mark.parametrize(
    "url",
    (
        "https://127.0.0.1:8001",
        "http://192.168.1.10:8001",
        "http://user:password@127.0.0.1:8001",
        "http://127.0.0.1:8001/api",
        "http://127.0.0.1:8001?token=value",
        "http://127.0.0.1:8188",
        "http://127.0.0.1:0",
    ),
)
def test_required_management_rejects_urls_the_launcher_cannot_own(url):
    with pytest.raises(ValueError, match="backend_management_mode=required"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backend_management_mode": "required",
                    "backends": {"image": {"url": url}},
                    "workflow_routing": {
                        "image": "image",
                        "tts": "image",
                        "default": "image",
                    },
                }
            }
        )


def test_required_management_rejects_routed_profile_without_ownership():
    with pytest.raises(ValueError, match="managed=true"):
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backend_management_mode": "required",
                    "backends": {
                        "image": {
                            "url": "http://127.0.0.1:8001",
                            "managed": False,
                        }
                    },
                    "workflow_routing": {
                        "image": "image",
                        "tts": "image",
                        "default": "image",
                    },
                }
            }
        )
