import pytest

from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.media import MediaService
from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities
from web.utils.workflow_defaults import resolve_selectbox_default_index


def test_resolve_default_workflow_uses_builtin_image_default_when_config_missing():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo_gguf.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow=None,
        )
        == "selfhost/image_z_image_turbo_gguf.json"
    )


def test_resolve_default_workflow_prefers_saved_value_when_available():
    available_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo_gguf.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="runninghub/image_flux.json",
        )
        == "runninghub/image_flux.json"
    )


def test_resolve_default_workflow_ignores_incompatible_saved_value_for_domain():
    available_keys = [
        "runninghub/video_wan2.1_fusionx.json",
        "selfhost/image_qwen.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="runninghub/video_wan2.1_fusionx.json",
        )
        == "selfhost/image_qwen.json"
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


def test_resolve_default_workflow_falls_back_to_first_compatible_workflow():
    available_keys = [
        "runninghub/video_wan2.1_fusionx.json",
        "selfhost/image_qwen.json",
    ]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow="selfhost/missing.json",
        )
        == "selfhost/image_qwen.json"
    )


def test_resolve_default_workflow_returns_none_when_no_compatible_workflow_exists():
    available_keys = ["runninghub/video_wan2.1_fusionx.json"]

    assert (
        resolve_default_workflow(
            domain="image",
            available_keys=available_keys,
            configured_workflow=None,
        )
        is None
    )


def test_get_configured_default_workflow_normalizes_nested_tts_shape():
    comfyui_config = {
        "tts": {
            "default_workflow": None,
            "comfyui": {"default_workflow": "selfhost/tts_edge.json"},
        }
    }

    assert get_configured_default_workflow(comfyui_config, "tts") == "selfhost/tts_edge.json"
    assert BUILTIN_DEFAULT_WORKFLOWS["image"] == "selfhost/image_z_image_turbo_gguf.json"


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
            _workflow_info("selfhost/image_z_image_turbo_gguf.json"),
        ],
    )

    assert service._resolve_workflow()["key"] == "selfhost/image_z_image_turbo_gguf.json"


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
            _workflow_info("selfhost/image_z_image_turbo_gguf.json"),
            _workflow_info("runninghub/video_wan2.1_fusionx.json"),
        ],
    )

    assert (
        service._resolve_workflow(workflow=None, workflow_domain="video")["key"]
        == "runninghub/video_wan2.1_fusionx.json"
    )


def test_media_service_raises_when_requested_domain_has_no_compatible_workflow(monkeypatch):
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
        lambda: [_workflow_info("runninghub/video_wan2.1_fusionx.json")],
    )

    with pytest.raises(ValueError, match="No compatible workflows available for image"):
        service._resolve_workflow(workflow=None, workflow_domain="image")


def test_media_service_raises_for_explicit_incompatible_workflow(monkeypatch):
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
            _workflow_info("selfhost/image_z_image_turbo_gguf.json"),
            _workflow_info("runninghub/video_wan2.1_fusionx.json"),
        ],
    )

    with pytest.raises(ValueError, match="is not compatible with domain 'image'"):
        service._resolve_workflow(
            workflow="runninghub/video_wan2.1_fusionx.json",
            workflow_domain="image",
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
        lambda: [_workflow_info("selfhost/image_z_image_turbo_gguf.json")],
    )

    with pytest.raises(ValueError, match="Workflow 'selfhost/missing.json' not found"):
        service._resolve_workflow(workflow="selfhost/missing.json")


def test_resolve_selectbox_default_index_uses_shared_image_default():
    workflow_keys = [
        "runninghub/image_flux.json",
        "selfhost/image_z_image_turbo_gguf.json",
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


def test_schema_bootstrap_defaults_match_the_new_image_workflow():
    config = PixelleVideoConfig()

    assert config.comfyui.image.default_workflow == "selfhost/image_z_image_turbo_gguf.json"
    assert config.comfyui.video.default_workflow == "runninghub/video_wan2.1_fusionx.json"


def test_workflow_capabilities_mark_gguf_loaders_as_high_memory():
    capabilities = get_workflow_capabilities(
        _workflow_info("selfhost/image_z_image_turbo_gguf.json")
    )

    assert capabilities.uses_gguf_loaders is True
    assert capabilities.local_memory_profile == "high"
    assert capabilities.prefers_isolated_local_execution is True


def test_workflow_capabilities_keep_standard_selfhost_image_workflows_batchable():
    capabilities = get_workflow_capabilities(
        _workflow_info("selfhost/image_z_image_turbo.json")
    )

    assert capabilities.uses_gguf_loaders is False
    assert capabilities.local_memory_profile == "standard"
    assert capabilities.prefers_isolated_local_execution is False


@pytest.mark.asyncio
async def test_media_service_surfaces_actionable_oom_guidance(monkeypatch):
    class _FailedResult:
        status = "failed"
        msg = (
            "[enforce fail at alloc_cpu.cpp:117] data. "
            "DefaultCPUAllocator: not enough memory: you tried to allocate 911360 bytes."
        )

    class _FakeKit:
        async def execute(self, workflow_input, workflow_params):
            return _FailedResult()

    class _FakeCore:
        async def _get_or_create_comfykit(self):
            return _FakeKit()

    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=_FakeCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: _workflow_info(
            "selfhost/image_z_image_turbo_gguf.json"
        ),
    )

    with pytest.raises(RuntimeError, match="ran out of memory"):
        await service(prompt="a cat", media_type="image")


@pytest.mark.asyncio
async def test_media_service_formats_direct_execute_oom_exceptions(monkeypatch):
    class _ExplodingKit:
        async def execute(self, workflow_input, workflow_params):
            raise RuntimeError(
                "[enforce fail at alloc_cpu.cpp:117] data. "
                "DefaultCPUAllocator: not enough memory: you tried to allocate 911360 bytes."
            )

    class _FakeCore:
        async def _get_or_create_comfykit(self):
            return _ExplodingKit()

    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=_FakeCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: _workflow_info(
            "selfhost/image_z_image_turbo_gguf.json"
        ),
    )

    with pytest.raises(RuntimeError, match="ran out of memory"):
        await service(prompt="a cat", media_type="image")


@pytest.mark.asyncio
async def test_media_service_formats_selfhost_connection_errors_with_comfyui_guidance(
    monkeypatch,
):
    class _ExplodingCore:
        async def execute_comfykit_workflow(self, workflow_input, workflow_params, *, workflow_source):
            raise RuntimeError(
                "Cannot connect to host 127.0.0.1:8000 ssl:default [Connection refused]"
            )

    service = MediaService(
        {
            "comfyui": {
                "comfyui_url": "http://127.0.0.1:8000",
                "image": {"default_workflow": None},
            }
        },
        core=_ExplodingCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: _workflow_info(
            "selfhost/image_z_image_turbo_gguf.json"
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await service(prompt="a cat", media_type="image")

    message = str(exc_info.value)
    assert "Self-hosted workflow 'selfhost/image_z_image_turbo_gguf.json'" in message
    assert "Current ComfyUI URL: http://127.0.0.1:8000" in message
    assert "http://127.0.0.1:8188" in message
