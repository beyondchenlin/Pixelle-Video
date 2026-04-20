from pixelle_video.config.workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)


def test_resolve_default_workflow_uses_builtin_image_default_when_config_missing():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow=None,
        )
        == "selfhost/image_z_image_turbo.json"
    )


def test_resolve_default_workflow_prefers_saved_value_when_available():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="runninghub/image_flux.json",
        )
        == "runninghub/image_flux.json"
    )


def test_resolve_default_workflow_falls_back_to_first_available_when_builtin_missing():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="selfhost/missing.json",
        )
        == "runninghub/image_flux.json"
    )


def test_get_configured_default_workflow_normalizes_nested_tts_shape():
    comfyui_config = {
        "tts": {
            "default_workflow": None,
            "comfyui": {"default_workflow": "selfhost/tts_edge.json"},
        }
    }

    assert get_configured_default_workflow(comfyui_config, "tts") == "selfhost/tts_edge.json"
    assert BUILTIN_DEFAULT_WORKFLOWS["image"] == "selfhost/image_z_image_turbo.json"
