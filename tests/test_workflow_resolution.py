import pytest

from pixelle_video.config.workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.media import MediaService
from web.utils.workflow_defaults import resolve_selectbox_default_index


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


def _workflow_info(key: str) -> dict:
    source, name = key.split("/", 1)
    return {
        "name": name,
        "display_name": f"{name} - {source.title()}",
        "source": source,
        "path": f"workflows/{key}",
        "key": key,
    }


class DummyImageService(ComfyBaseService):
    WORKFLOW_PREFIX = "image_"


def test_base_service_uses_builtin_default_when_config_is_unset(monkeypatch):
    service = DummyImageService(
        {"comfyui": {"image": {"default_workflow": None}}},
        service_name="image",
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            _workflow_info("runninghub/image_flux.json"),
            _workflow_info("selfhost/image_z_image_turbo.json"),
        ],
    )

    assert service._resolve_workflow()["key"] == "selfhost/image_z_image_turbo.json"


def test_media_service_uses_video_domain_default_for_video_requests(monkeypatch):
    service = MediaService(
        {
            "comfyui": {
                "image": {"default_workflow": None},
                "video": {"default_workflow": None},
            }
        },
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            _workflow_info("selfhost/image_z_image_turbo.json"),
            _workflow_info("runninghub/video_wan2.1_fusionx.json"),
        ],
    )

    assert (
        service._resolve_workflow(workflow=None, workflow_domain="video")["key"]
        == "runninghub/video_wan2.1_fusionx.json"
    )


def test_base_service_still_raises_for_explicit_missing_workflow(monkeypatch):
    service = DummyImageService(
        {"comfyui": {"image": {"default_workflow": None}}},
        service_name="image",
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [_workflow_info("selfhost/image_z_image_turbo.json")],
    )

    with pytest.raises(ValueError, match="Workflow 'selfhost/missing.json' not found"):
        service._resolve_workflow(workflow="selfhost/missing.json")


def test_resolve_selectbox_default_index_uses_shared_image_default():
    workflow_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo.json",
    ]

    assert (
        resolve_selectbox_default_index(
            domain="image",
            workflow_keys=workflow_keys,
            configured_workflow=None,
        )
        == 1
    )


def test_resolve_selectbox_default_index_returns_zero_when_no_workflows_exist():
    assert (
        resolve_selectbox_default_index(
            domain="image",
            workflow_keys=[],
            configured_workflow=None,
        )
        == 0
    )
