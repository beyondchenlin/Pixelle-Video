import asyncio
from types import SimpleNamespace

import pytest

from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig
from pixelle_video.pipelines.standard import StandardPipeline
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.media import MediaService
from pixelle_video.services.prompt_trace_artifacts import (
    write_single_media_prompt_trace_context,
)
from pixelle_video.services.tts_service import TTSService


def _media_prompt_trace_context(
    tmp_path,
    *,
    prompt: str = "a cat",
    workflow: str = "selfhost/image_z_image_turbo_gguf.json",
) -> dict[str, object]:
    task_id = "task-media-routing"
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


def _dual_backend_config() -> PixelleVideoConfig:
    return PixelleVideoConfig.model_validate(
        {
            "comfyui": {
                "backends": {
                    "image": {"url": "http://127.0.0.1:8001"},
                    "tts": {"url": "http://127.0.0.1:8002"},
                },
                "workflow_routing": {"image": "image", "tts": "tts"},
            }
        }
    )


@pytest.mark.asyncio
async def test_core_caches_comfykit_per_backend(monkeypatch):
    monkeypatch.setattr(config_manager, "config", _dual_backend_config())
    created = []

    class FakeComfyKit:
        def __init__(self, **config):
            self.config = config
            created.append(config)

    monkeypatch.setattr("pixelle_video.service.ComfyKit", FakeComfyKit)

    core = PixelleVideoCore()
    image_kit = await core._get_or_create_comfykit("image")
    tts_kit = await core._get_or_create_comfykit("tts")
    image_kit_again = await core._get_or_create_comfykit("image")

    assert image_kit is image_kit_again
    assert image_kit is not tts_kit
    assert created[0]["comfyui_url"] == "http://127.0.0.1:8001"
    assert created[1]["comfyui_url"] == "http://127.0.0.1:8002"


@pytest.mark.asyncio
async def test_media_service_passes_selfhost_image_backend_role(monkeypatch, tmp_path):
    monkeypatch.setattr(config_manager, "config", _dual_backend_config())
    calls = []

    class RecordingCore:
        def _get_comfyui_backend_registry(self):
            return PixelleVideoCore()._get_comfyui_backend_registry()

        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role,
            media_prompt_trace_context,
            media_type,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert media_prompt_trace_context is not None
            assert media_type == "image"
            assert resolved_workflow == "selfhost/image_z_image_turbo_gguf.json"
            assert workflow_file_trace
            calls.append(
                {
                    "workflow_input": workflow_input,
                    "workflow_source": workflow_source,
                    "backend_role": backend_role,
                }
            )
            return SimpleNamespace(status="completed", images=["generated.png"])

    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=RecordingCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo_gguf.json",
            "path": "workflows/selfhost/image_z_image_turbo_gguf.json",
        },
    )

    await service(
        prompt="a cat",
        media_type="image",
        media_prompt_trace_context=_media_prompt_trace_context(tmp_path),
    )

    assert calls == [
        {
            "workflow_input": "workflows/selfhost/image_z_image_turbo_gguf.json",
            "workflow_source": "selfhost",
            "backend_role": "image",
        }
    ]


@pytest.mark.asyncio
async def test_tts_service_passes_selfhost_tts_backend_role(monkeypatch):
    monkeypatch.setattr(config_manager, "config", _dual_backend_config())
    calls = []

    class RecordingCore:
        def _get_comfyui_backend_registry(self):
            return PixelleVideoCore()._get_comfyui_backend_registry()

        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role,
            tts_workflow_trace_context,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert tts_workflow_trace_context is not None
            assert resolved_workflow == "selfhost/tts_edge.json"
            assert workflow_file_trace
            calls.append(
                {
                    "workflow_input": workflow_input,
                    "workflow_source": workflow_source,
                    "backend_role": backend_role,
                }
            )
            return SimpleNamespace(status="completed", audios=["generated.wav"])

    service = TTSService(
        {"comfyui": {"tts": {"default_workflow": None, "inference_mode": "comfyui"}}},
        core=RecordingCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None: {
            "source": "selfhost",
            "key": "selfhost/tts_edge.json",
            "path": "workflows/selfhost/tts_edge.json",
        },
    )
    monkeypatch.setattr(service, "_get_workflow_metadata", lambda workflow_info: None)

    await service(text="hello")

    assert calls == [
        {
            "workflow_input": "workflows/selfhost/tts_edge.json",
            "workflow_source": "selfhost",
            "backend_role": "tts",
        }
    ]


@pytest.mark.asyncio
async def test_services_without_backend_registry_fall_back_to_default_role(monkeypatch, tmp_path):
    calls = []

    class LegacyCore:
        async def execute_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role,
            media_prompt_trace_context,
            media_type,
            resolved_workflow,
            workflow_file_trace,
        ):
            assert media_prompt_trace_context is not None
            assert media_type == "image"
            assert resolved_workflow == "selfhost/image_z_image_turbo_gguf.json"
            assert workflow_file_trace
            calls.append((workflow_input, workflow_source, backend_role))
            return SimpleNamespace(status="completed", images=["generated.png"])

    service = MediaService(
        {"comfyui": {"image": {"default_workflow": None}}},
        core=LegacyCore(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_workflow",
        lambda workflow=None, workflow_domain=None: {
            "source": "selfhost",
            "key": "selfhost/image_z_image_turbo_gguf.json",
            "path": "workflows/selfhost/image_z_image_turbo_gguf.json",
        },
    )

    await service(
        prompt="a cat",
        media_type="image",
        media_prompt_trace_context=_media_prompt_trace_context(tmp_path),
    )

    assert calls == [
        (
            "workflows/selfhost/image_z_image_turbo_gguf.json",
            "selfhost",
            "default",
        )
    ]


def test_media_and_tts_registry_choose_dedicated_roles(monkeypatch):
    monkeypatch.setattr(config_manager, "config", _dual_backend_config())
    core = PixelleVideoCore()
    registry = core._get_comfyui_backend_registry()

    assert registry.resolve_role_for_media("selfhost/image_z.json", "image") == "image"
    assert registry.resolve_role_for_tts("selfhost/tts_index2.json") == "tts"


@pytest.mark.asyncio
async def test_restart_is_tracked_per_backend_role(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {
                            "url": "http://127.0.0.1:8001",
                            "restart_after_batch": True,
                        }
                    },
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    calls = []

    async def fake_restart(role, reason):
        calls.append((role, reason))

    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)

    core.schedule_comfyui_backend_restart("image", "post-image-batch")
    core.schedule_comfyui_backend_restart("image", "duplicate")
    await core.await_comfyui_backend_ready("image")

    assert calls == [("image", "post-image-batch")]


@pytest.mark.asyncio
async def test_stage_restart_waits_for_scheduled_backend_restart(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {
                            "url": "http://127.0.0.1:8001",
                            "restart_after_batch": True,
                        }
                    },
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    pipeline = StandardPipeline(core)
    restart_started = asyncio.Event()
    release_restart = asyncio.Event()
    events = []

    async def fake_restart(role, reason):
        events.append(("start", role, reason))
        restart_started.set()
        await release_restart.wait()
        events.append(("end", role, reason))
        return True

    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)

    stage_task = asyncio.create_task(
        pipeline._schedule_stage_backend_restart_if_needed(
            backend_role="image",
            reason="post-image-batch",
        )
    )

    try:
        await asyncio.wait_for(restart_started.wait(), timeout=1)
        assert not stage_task.done()
    finally:
        release_restart.set()
        await asyncio.gather(
            stage_task,
            core.await_comfyui_backend_ready("image"),
            return_exceptions=True,
        )

    assert events == [
        ("start", "image", "post-image-batch"),
        ("end", "image", "post-image-batch"),
    ]


@pytest.mark.asyncio
async def test_local_workflow_waits_for_other_backend_restart(monkeypatch):
    monkeypatch.setattr(config_manager, "config", _dual_backend_config())
    core = PixelleVideoCore()
    restart_started = asyncio.Event()
    release_restart = asyncio.Event()
    workflow_started = asyncio.Event()

    async def fake_restart(role, reason):
        restart_started.set()
        await release_restart.wait()
        return True

    async def fake_prepare(*, backend_role="default"):
        return None

    async def fake_execute(workflow_input, workflow_params, *, backend_role="default"):
        workflow_started.set()
        return "ok"

    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)
    monkeypatch.setattr(core, "prepare_comfyui_for_local_workflow", fake_prepare)
    monkeypatch.setattr(core, "_execute_local_comfykit_workflow", fake_execute)

    core.schedule_comfyui_backend_restart("image", "post-image-batch")
    await asyncio.wait_for(restart_started.wait(), timeout=1)

    workflow_task = asyncio.create_task(
        core._execute_comfykit_workflow_unchecked(
            "workflows/selfhost/tts_edge.json",
            {},
            workflow_source="selfhost",
            backend_role="tts",
        )
    )

    try:
        await asyncio.sleep(0)
        assert not workflow_started.is_set()
    finally:
        release_restart.set()
        await asyncio.gather(
            workflow_task,
            core.await_comfyui_backend_ready("image"),
            return_exceptions=True,
        )

    assert workflow_task.result() == "ok"


@pytest.mark.asyncio
async def test_cpu_oom_restarts_managed_backend_before_retry(monkeypatch):
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "backends": {
                        "image": {"url": "http://127.0.0.1:8001"},
                    },
                    "workflow_routing": {"image": "image"},
                }
            }
        ),
    )
    core = PixelleVideoCore()
    attempts = 0
    restarted = []

    async def fake_once(workflow_input, workflow_params, *, backend_role="default"):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("DefaultCPUAllocator: not enough memory")
        return "ok"

    async def fake_release(
        *,
        context,
        backend_role="default",
        include_extensions=False,
        extensions=(),
    ):
        return True

    async def fake_restart(role, reason):
        restarted.append((role, reason))

    async def fake_prepare(*, backend_role="default"):
        return None

    monkeypatch.setattr(core, "_execute_local_comfykit_workflow_once", fake_once)
    monkeypatch.setattr(core, "force_release_comfyui_memory", fake_release)
    monkeypatch.setattr(core, "_restart_comfyui_backend_role", fake_restart)
    monkeypatch.setattr(core, "prepare_comfyui_for_local_workflow", fake_prepare)

    result = await core._execute_local_comfykit_workflow(
        "workflows/selfhost/image_z.json",
        {},
        backend_role="image",
    )

    assert result == "ok"
    assert restarted == [("image", "oom-recovery")]
