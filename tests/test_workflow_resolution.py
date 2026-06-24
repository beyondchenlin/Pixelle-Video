import hashlib
import json
from pathlib import Path

import pytest

from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.config.workflow_defaults import (
    BUILTIN_DEFAULT_WORKFLOWS,
    get_configured_default_workflow,
    resolve_default_workflow,
)
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import (
    write_single_media_prompt_trace_context,
)
from pixelle_video.utils.workflow_capabilities import get_workflow_capabilities
from pixelle_video.workflow_content_contracts import workflow_content_contract
from web.utils.workflow_defaults import resolve_selectbox_default_index


def test_runninghub_workflow_descriptors_declare_explicit_contracts():
    allowed_non_media_domains = {"tts", "image_analysis", "video_analysis"}
    for path in Path("workflows/runninghub").glob("*.json"):
        descriptor = json.loads(path.read_text(encoding="utf-8"))
        assert descriptor.get("source") == "runninghub", path
        assert descriptor.get("workflow_id"), path

        media_type = str(descriptor.get("media_type") or "").strip().lower()
        workflow_domain = str(descriptor.get("workflow_domain") or "").strip().lower()
        service_domain = str(descriptor.get("service_domain") or "").strip().lower()
        declared_domains = {value for value in (workflow_domain, service_domain) if value}

        if media_type:
            assert media_type in {"image", "video"}, path
            assert not declared_domains - {"image", "video"}, path
            continue

        assert declared_domains, path
        assert declared_domains <= allowed_non_media_domains, path


def test_media_service_accepts_runninghub_media_type_descriptor_without_image_prefix(
    monkeypatch,
):
    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            {
                "source": "runninghub",
                "key": "runninghub/af_scail.json",
                "path": "workflows/runninghub/af_scail.json",
                "workflow_id": "rh-upscale",
                "media_type": "image",
            }
        ],
    )

    workflow_info = service._resolve_workflow(
        workflow="runninghub/af_scail.json",
        workflow_domain="image",
    )

    assert workflow_info["key"] == "runninghub/af_scail.json"
    assert workflow_info["media_type"] == "image"


def test_media_service_treats_runninghub_media_type_as_authoritative(monkeypatch):
    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=object(),
    )
    monkeypatch.setattr(
        service,
        "_scan_workflows",
        lambda: [
            {
                "source": "runninghub",
                "key": "runninghub/video_wan2.2.json",
                "path": "workflows/runninghub/video_wan2.2.json",
                "workflow_id": "rh-video",
                "media_type": "video",
                "service_domain": "image",
            }
        ],
    )

    with pytest.raises(ValueError, match="not compatible with domain 'image'"):
        service._resolve_workflow(
            workflow="runninghub/video_wan2.2.json",
            workflow_domain="image",
        )


def test_media_service_skips_selfhost_media_prefixed_tts_workflow(monkeypatch, tmp_path):
    workflow_dir = tmp_path / "workflows" / "selfhost"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "image_voice_spoof.json"
    workflow_path.write_text(
        json.dumps(
            {
                "5": {
                    "inputs": {"text": ["3", 0]},
                    "class_type": "IndexTTS2BaseNode",
                }
            }
        ),
        encoding="utf-8",
    )
    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=object(),
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.list_resource_dirs",
        lambda _kind: ["selfhost"],
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.list_resource_files",
        lambda _kind, _source: ["image_voice_spoof.json"],
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.get_resource_path",
        lambda _kind, _source, _filename: str(workflow_path),
    )

    assert service._scan_workflows() == []


def test_media_service_ignores_non_media_selfhost_workflows_before_parse(
    monkeypatch,
    tmp_path,
):
    workflow_dir = tmp_path / "workflows" / "selfhost"
    workflow_dir.mkdir(parents=True)
    workflow_path = workflow_dir / "tts_omnivoice_longform_bf16.json"
    workflow_path.write_text("{not valid json", encoding="utf-8")
    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=object(),
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.list_resource_dirs",
        lambda _kind: ["selfhost"],
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.list_resource_files",
        lambda _kind, _source: ["tts_omnivoice_longform_bf16.json"],
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.get_resource_path",
        lambda _kind, _source, _filename: str(workflow_path),
    )
    monkeypatch.setattr(
        service,
        "_parse_workflow_file",
        lambda *_args, **_kwargs: pytest.fail("non-media workflow should not be parsed"),
    )

    assert service._scan_workflows() == []


def test_media_service_ignores_data_runninghub_descriptor_overrides(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    builtin_dir = tmp_path / "workflows" / "runninghub"
    builtin_dir.mkdir(parents=True)
    (builtin_dir / "image_safe.json").write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-safe",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    override_dir = tmp_path / "data" / "workflows" / "runninghub"
    override_dir.mkdir(parents=True)
    (override_dir / "image_fake.json").write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-hidden-analysis",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )

    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=object(),
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.list_resource_dirs",
        lambda _kind: ["runninghub"],
    )
    monkeypatch.setattr(
        "pixelle_video.services.media.runninghub_registry_root",
        lambda: builtin_dir,
    )

    assert [workflow["key"] for workflow in service._scan_workflows()] == [
        "runninghub/image_safe.json"
    ]


def test_workflow_content_contract_detects_ui_widget_prompt_literals():
    contract = workflow_content_contract(
        {
            "nodes": [
                {
                    "id": 1,
                    "type": "CLIPTextEncode",
                    "widgets_values": ["a hidden hardcoded prompt"],
                }
            ]
        }
    )

    assert contract["prompt_literals"] == [
        {
            "path": "nodes.0.widgets_values.0",
            "key": "widgets_values[0]",
            "sha256": hashlib.sha256(
                b"a hidden hardcoded prompt"
            ).hexdigest(),
            "preview": "a hidden hardcoded prompt",
        }
    ]
    assert contract["prompt_literals_sha256"]


def test_workflow_content_contract_detects_unmarked_widget_prompt_literals():
    prompt_text = "a foggy harbor at sunrise with cinematic reflections"

    contract = workflow_content_contract(
        {
            "nodes": [
                {
                    "id": 1,
                    "type": "LoadImage",
                    "widgets_values": [prompt_text],
                }
            ]
        }
    )

    assert contract["prompt_literals"] == [
        {
            "path": "nodes.0.widgets_values.0",
            "key": "widgets_values[0]",
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "preview": prompt_text,
        }
    ]


def test_workflow_content_contract_keeps_braced_prompt_templates():
    prompt_text = "Describe {image} using cinematic lighting and visible relationships"

    contract = workflow_content_contract(
        {
            "nodes": [
                {
                    "id": 1,
                    "type": "Image Loader",
                    "widgets_values": [prompt_text],
                }
            ]
        }
    )

    assert contract["prompt_literals"] == [
        {
            "path": "nodes.0.widgets_values.0",
            "key": "widgets_values[0]",
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "preview": prompt_text,
        }
    ]


def test_workflow_content_contract_detects_comma_dense_widget_prompt_literals():
    prompt_text = "{image},cinematic,high-detail"

    contract = workflow_content_contract(
        {
            "nodes": [
                {
                    "id": 1,
                    "type": "Image Loader",
                    "widgets_values": [prompt_text],
                }
            ]
        }
    )

    assert contract["prompt_literals"] == [
        {
            "path": "nodes.0.widgets_values.0",
            "key": "widgets_values[0]",
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "preview": prompt_text,
        }
    ]


def test_workflow_content_contract_detects_chat_prompt_keys():
    contract = workflow_content_contract(
        {
            "nodes": [
                {
                    "id": 1,
                    "class_type": "GenericNode",
                    "inputs": {
                        "system_prompt": "You are a visual prompt writer for image generation",
                        "message": "Return one complete semantic image prompt",
                        "content": "Use the scene, subject, style, and rendering rules coherently",
                    },
                }
            ]
        }
    )

    assert {
        (literal["path"], literal["key"])
        for literal in contract["prompt_literals"]
    } == {
        ("nodes.0.inputs.system_prompt", "system_prompt"),
        ("nodes.0.inputs.message", "message"),
        ("nodes.0.inputs.content", "content"),
    }


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


def _media_prompt_trace_context(
    tmp_path,
    *,
    prompt: str = "a cat",
    workflow: str = "selfhost/image_z_image_turbo_gguf.json",
) -> dict[str, object]:
    task_id = "task-workflow-resolution"
    workflow_input = f"workflows/{workflow}"
    return write_single_media_prompt_trace_context(
        tmp_path,
        task_id=task_id,
        prompt=prompt,
        workflow=workflow,
        workflow_input=workflow_input,
        media_type="image",
        source="test",
        workflow_params={"prompt": prompt},
    )


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
    assert capabilities.vae_decode_mode == "tiled"
    assert capabilities.uses_tiled_vae_decode is True
    assert capabilities.prefers_isolated_local_execution is False


def test_workflow_capabilities_keep_standard_selfhost_image_workflows_batchable():
    capabilities = get_workflow_capabilities(
        _workflow_info("selfhost/image_z_image_turbo.json")
    )

    assert capabilities.uses_gguf_loaders is False
    assert capabilities.local_memory_profile == "standard"
    assert capabilities.vae_decode_mode == "standard"
    assert capabilities.uses_tiled_vae_decode is False
    assert capabilities.prefers_isolated_local_execution is False


@pytest.mark.asyncio
async def test_media_service_surfaces_actionable_oom_guidance(monkeypatch, tmp_path):
    class _FailedResult:
        status = "failed"
        msg = (
            "[enforce fail at alloc_cpu.cpp:117] data. "
            "DefaultCPUAllocator: not enough memory: you tried to allocate 911360 bytes."
        )

    class _FakeCore:
        def _get_comfyui_backend_registry(self):
            class _Registry:
                def resolve_role_for_media(self, workflow_key, media_type):
                    return "default"

            return _Registry()

        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role="default",
            media_prompt_trace_context,
            media_type,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert workflow_source == "selfhost"
            assert backend_role == "default"
            assert media_prompt_trace_context is not None
            assert media_type == "image"
            assert resolved_workflow == "selfhost/image_z_image_turbo_gguf.json"
            assert workflow_file_trace
            return _FailedResult()

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
        await service(
            prompt="a cat",
            media_type="image",
            media_prompt_trace_context=_media_prompt_trace_context(tmp_path),
        )


@pytest.mark.asyncio
async def test_media_service_formats_direct_execute_oom_exceptions(monkeypatch, tmp_path):
    class _FakeCore:
        def _get_comfyui_backend_registry(self):
            class _Registry:
                def resolve_role_for_media(self, workflow_key, media_type):
                    return "default"

            return _Registry()

        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role="default",
            media_prompt_trace_context,
            media_type,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert workflow_source == "selfhost"
            assert backend_role == "default"
            assert media_prompt_trace_context is not None
            assert media_type == "image"
            assert resolved_workflow == "selfhost/image_z_image_turbo_gguf.json"
            assert workflow_file_trace
            raise RuntimeError(
                "[enforce fail at alloc_cpu.cpp:117] data. "
                "DefaultCPUAllocator: not enough memory: you tried to allocate 911360 bytes."
            )

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
        await service(
            prompt="a cat",
            media_type="image",
            media_prompt_trace_context=_media_prompt_trace_context(tmp_path),
        )


@pytest.mark.asyncio
async def test_media_service_formats_selfhost_connection_errors_with_comfyui_guidance(
    monkeypatch,
    tmp_path,
):
    class _ExplodingCore:
        def _get_comfyui_backend_registry(self):
            class _Registry:
                def resolve_role_for_media(self, workflow_key, media_type):
                    return "default"

            return _Registry()

        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role="default",
            media_prompt_trace_context,
            media_type,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert workflow_source == "selfhost"
            assert backend_role == "default"
            assert media_prompt_trace_context is not None
            assert media_type == "image"
            assert resolved_workflow == "selfhost/image_z_image_turbo_gguf.json"
            assert workflow_file_trace
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
        await service(
            prompt="a cat",
            media_type="image",
            media_prompt_trace_context=_media_prompt_trace_context(tmp_path),
        )

    message = str(exc_info.value)
    assert "Self-hosted workflow 'selfhost/image_z_image_turbo_gguf.json'" in message
    assert "Current ComfyUI URL: http://127.0.0.1:8000" in message
    assert "http://127.0.0.1:8188" in message
