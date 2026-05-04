import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp.client_exceptions import ClientConnectorError
from aiohttp.client_reqrep import ConnectionKey

from pixelle_video import service as service_module
from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.generation_coordinator import (
    GenerationCoordinator,
    build_generation_fingerprint,
)


def _install_noop_extension_preflight(core):
    async def _preflight(*, context, extensions=("indextts2",)):
        return True

    core.preflight_comfyui_extension_release_endpoints = _preflight


def test_generation_fingerprint_ignores_runtime_only_fields():
    first = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 5,
            "request_id": "req-one",
            "session_id": "sess-one",
            "api_task_id": "api-one",
            "progress_callback": lambda _event: None,
            "title": None,
            "template_params": {"accent": "#fff", "unused": None},
        },
    )
    second = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "template_params": {"unused": None, "accent": "#fff"},
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 5,
            "request_id": "req-two",
            "session_id": "sess-two",
            "api_task_id": "api-two",
            "progress_callback": lambda _event: None,
        },
    )
    changed = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={
            "storyboard_mode": "smart",
            "storyboard_count_mode": "manual",
            "storyboard_scene_count": 6,
            "template_params": {"accent": "#fff"},
        },
    )

    assert first == second
    assert first != changed


def test_generation_fingerprint_ignores_progress_dispatcher():
    first = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={"progress_dispatcher": object(), "frame_template": "a.html"},
    )
    second = build_generation_fingerprint(
        text="demo",
        pipeline="standard",
        params={"progress_dispatcher": object(), "frame_template": "a.html"},
    )

    assert first == second


@pytest.mark.asyncio
async def test_core_generate_video_reuses_identical_inflight_generation():
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowPipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            started.set()
            await release.wait()
            return SimpleNamespace(text=text, kwargs=kwargs, marker=object())

    core = PixelleVideoCore()
    pipeline = _SlowPipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    first = asyncio.create_task(
        core.generate_video(
            text="demo",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
            frame_template="1080x1920/image_default.html",
            request_id="req-one",
            session_id="sess-one",
            progress_callback=lambda _event: None,
        )
    )
    await started.wait()

    second = asyncio.create_task(
        core.generate_video(
            text="demo",
            storyboard_mode="smart",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
            frame_template="1080x1920/image_default.html",
            request_id="req-two",
            session_id="sess-two",
            progress_callback=lambda _event: None,
        )
    )
    await asyncio.sleep(0)

    assert pipeline.calls == 1

    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result is second_result
    assert pipeline.calls == 1


@pytest.mark.asyncio
async def test_core_generate_video_releases_fingerprint_after_completion():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, call_number=self.calls)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    first = await core.generate_video(text="demo", storyboard_mode="smart")
    second = await core.generate_video(text="demo", storyboard_mode="smart")

    assert first.call_number == 1
    assert second.call_number == 2
    assert pipeline.calls == 2


@pytest.mark.asyncio
async def test_core_generate_video_normalizes_storyboard_contract_for_standard_pipeline():
    captured = {}

    class _Pipeline:
        async def __call__(self, *, text, **kwargs):
            captured["text"] = text
            captured["kwargs"] = dict(kwargs)
            return SimpleNamespace(ok=True)

    core = PixelleVideoCore()
    core.pipelines = {"standard": _Pipeline()}
    core.generate_video = core._create_generate_video_wrapper()

    await core.generate_video(
        text="demo",
        storyboard_mode="sentence",
        storyboard_count_mode="manual",
        storyboard_scene_count=6,
        storyboard_prompt_language="  unexpected  ",
        world_preset_id="  neutral_knowledge_storyboard  ",
        shot_preset_id="  balanced_explainer  ",
    )

    assert captured["text"] == "demo"
    assert captured["kwargs"]["storyboard_mode"] == "sentence"
    assert captured["kwargs"]["storyboard_count_mode"] == "auto"
    assert captured["kwargs"]["storyboard_scene_count"] is None
    assert captured["kwargs"]["storyboard_prompt_language"] == "zh_CN"
    assert captured["kwargs"]["world_preset_id"] == "neutral_knowledge_storyboard"
    assert captured["kwargs"]["shot_preset_id"] == "balanced_explainer"


@pytest.mark.asyncio
async def test_core_generate_video_releases_fingerprint_after_failure():
    class _FlakyPipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return SimpleNamespace(text=text, call_number=self.calls)

    core = PixelleVideoCore()
    pipeline = _FlakyPipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(RuntimeError, match="temporary failure"):
        await core.generate_video(text="demo", storyboard_mode="smart")

    result = await core.generate_video(text="demo", storyboard_mode="smart")

    assert result.call_number == 2
    assert pipeline.calls == 2


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflow_runs_cleanup_around_execute():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release():
        calls.append(("release",))

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflow.json",
        {"prompt": "demo"},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", "workflow.json", {"prompt": "demo"}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_execute_standalone_index_tts2_workflow_releases_models_after_execute():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release_workflow():
        raise AssertionError("standalone IndexTTS2 workflow should use the IndexTTS2 release path")

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        calls.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _preflight(*, context, extensions=("indextts2",)):
        calls.append(("preflight", context, extensions))
        return True

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_index2.json",
        {"prompt": "demo"},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("preflight", "pre-index-tts2-workflow", ("indextts2",)),
        ("get_kit",),
        ("execute", "workflows/selfhost/tts_index2.json", {"prompt": "demo"}),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_core_execute_gguf_workflow_releases_gguf_extension_after_execute(tmp_path):
    workflow_path = tmp_path / "image_gguf.json"
    workflow_path.write_text(
        json.dumps(
            {
                "37": {
                    "inputs": {"unet_name": "z-image-turbo-Q4_K_M.gguf"},
                    "class_type": "UnetLoaderGGUF",
                },
                "38": {
                    "inputs": {"clip_name": "Qwen3-4B-Q4_K_M.gguf"},
                    "class_type": "CLIPLoaderGGUF",
                },
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release_workflow():
        raise AssertionError("GGUF workflow should use the extension release path")

    async def _release_extensions(*, context, extensions=("indextts2",), missing_endpoint="optional"):
        calls.append(("extension_release", context, extensions, missing_endpoint))
        return True

    async def _preflight(*, context, extensions=("indextts2",)):
        calls.append(("preflight", context, extensions))
        return True

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        str(workflow_path),
        {"prompt": "demo"},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("preflight", "pre-gguf-workflow", ("gguf",)),
        ("get_kit",),
        ("execute", str(workflow_path), {"prompt": "demo"}),
        ("extension_release", "post-gguf-workflow", ("gguf",), "required"),
    ]


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflow_releases_after_failure():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append("execute")
            raise RuntimeError("workflow failed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append("prepare")

    async def _release():
        calls.append("release")

    async def _get_kit():
        calls.append("get_kit")
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="workflow failed"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )

    assert calls == ["prepare", "get_kit", "execute", "release"]


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflow_recovers_once_after_oom():
    calls = []
    attempts = 0

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            nonlocal attempts
            attempts += 1
            calls.append(("execute", attempts, workflow_input, workflow_params))
            if attempts == 1:
                raise RuntimeError(
                    "[enforce fail at alloc_cpu.cpp:117] data. "
                    "DefaultCPUAllocator: not enough memory: you tried to allocate 11141120 bytes."
                )
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release():
        calls.append(("release",))
        return True

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    async def _force_release(*, context):
        calls.append(("force_release", context))
        return True

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core.force_release_comfyui_memory = _force_release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflow.json",
        {"prompt": "demo"},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1, "workflow.json", {"prompt": "demo"}),
        ("force_release", "oom-recovery"),
        ("prepare",),
        ("get_kit",),
        ("execute", 2, "workflow.json", {"prompt": "demo"}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_execute_index_tts2_oom_recovery_releases_plugin_cache_in_comfyui_mode(monkeypatch):
    calls = []
    attempts = 0

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            nonlocal attempts
            attempts += 1
            calls.append(("execute", attempts, workflow_input))
            if attempts == 1:
                raise RuntimeError("CUDA out of memory while allocating tensor")
            return SimpleNamespace(status="completed")

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            calls.append(("client", base_url, api_key))

        async def free_memory_with_extensions(
            self,
            intensity="high",
            *,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            calls.append(
                ("free_with_extensions", intensity, extensions, missing_endpoint)
            )
            return True

        async def free_memory(self, intensity="high"):
            raise AssertionError("IndexTTS2 OOM recovery must clean plugin caches")

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                model_cleanup_mode="comfyui",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        calls.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_index2.json",
        {},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1, "workflows/selfhost/tts_index2.json"),
        ("client", "http://127.0.0.1:8000", "secret"),
        ("free_with_extensions", "high", ("indextts2",), "required"),
        ("prepare",),
        ("get_kit",),
        ("execute", 2, "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflow_stops_when_oom_release_fails():
    calls = []
    attempts = 0

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            nonlocal attempts
            attempts += 1
            calls.append(("execute", attempts))
            if attempts == 1:
                raise RuntimeError("CUDA out of memory while allocating tensor")
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append(("prepare",))

    async def _release():
        calls.append(("release",))

    async def _get_kit():
        calls.append(("get_kit",))
        return _Kit()

    async def _force_release(*, context):
        calls.append(("force_release", context))
        return False

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core.force_release_comfyui_memory = _force_release
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="without confirmed memory release"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )

    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1),
        ("force_release", "oom-recovery"),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflow_stops_when_cleanup_fails():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append("execute")
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        calls.append("prepare")
        raise RuntimeError("cleanup failed")

    async def _release():
        calls.append("release")

    async def _get_kit():
        calls.append("get_kit")
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )

    assert calls == ["prepare"]


@pytest.mark.asyncio
async def test_core_execute_runninghub_workflow_bypasses_local_comfy_cleanup():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        raise AssertionError("RunningHub workflow should not prepare local ComfyUI")

    async def _release():
        raise AssertionError("RunningHub workflow should not release local ComfyUI")

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "runninghub-workflow-id",
        {"prompt": "demo"},
        workflow_source="runninghub",
    )

    assert result.status == "completed"
    assert calls == [
        ("execute", "runninghub-workflow-id", {"prompt": "demo"}),
    ]


@pytest.mark.asyncio
async def test_core_execute_local_comfy_workflows_serialize_cleanup_boundary():
    events = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(f"{workflow_input}:start")
            if workflow_input == "first":
                first_started.set()
                await release_first.wait()
            events.append(f"{workflow_input}:end")
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append("prepare")

    async def _release():
        events.append("release")

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    first_task = asyncio.create_task(
        core.execute_comfykit_workflow("first", {}, workflow_source="selfhost")
    )
    await first_started.wait()

    second_task = asyncio.create_task(
        core.execute_comfykit_workflow("second", {}, workflow_source="selfhost")
    )
    await asyncio.sleep(0.01)

    assert events == ["prepare", "first:start"]

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert events == [
        "prepare",
        "first:start",
        "first:end",
        "release",
        "prepare",
        "second:start",
        "second:end",
        "release",
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_keeps_lifecycle_open_across_batch():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release():
        events.append(("release",))

    async def _get_kit():
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        first = await core.execute_comfykit_workflow(
            "first.json",
            {"prompt": "first"},
            workflow_source="selfhost",
        )
        second = await core.execute_comfykit_workflow(
            "second.json",
            {"prompt": "second"},
            workflow_source="selfhost",
        )

    assert first.status == "completed"
    assert second.status == "completed"
    assert events == [
        ("prepare",),
        ("get_kit",),
        ("execute", "first.json", {"prompt": "first"}),
        ("get_kit",),
        ("execute", "second.json", {"prompt": "second"}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_releases_models_once_at_session_exit():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit():
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        first = await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            {"prompt": "first"},
            workflow_source="selfhost",
        )
        second = await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            {"prompt": "second"},
            workflow_source="selfhost",
        )

    assert first.status == "completed"
    assert second.status == "completed"
    assert events == [
        ("prepare",),
        ("get_kit",),
        ("execute", "workflows/selfhost/tts_index2.json", {"prompt": "first"}),
        ("get_kit",),
        ("execute", "workflows/selfhost/tts_index2.json", {"prompt": "second"}),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_releases_models_for_renamed_index_tts2_file(tmp_path):
    workflow_path = tmp_path / "voice_batch.json"
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
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _preflight(*, context, extensions=("indextts2",)):
        events.append(("preflight", context, extensions))
        return True

    async def _get_kit():
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        result = await core.execute_comfykit_workflow(
            str(workflow_path),
            {"prompt": "first"},
            workflow_source="selfhost",
        )

    assert result.status == "completed"
    assert events == [
        ("prepare",),
        ("preflight", "pre-index-tts2-workflow", ("indextts2",)),
        ("get_kit",),
        ("execute", str(workflow_path), {"prompt": "first"}),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_releases_models_at_session_exit():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session():
            await core.execute_comfykit_workflow(
                "workflows/selfhost/tts_index2.json",
                {},
                workflow_source="selfhost",
            )

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_preflights_required_extension_endpoint_before_execute():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _preflight(*, context, extensions=("indextts2",)):
        events.append(("preflight", context, extensions))
        return True

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            {},
            workflow_source="selfhost",
        )

    assert events == [
        ("prepare",),
        ("preflight", "pre-index-tts2-workflow", ("indextts2",)),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_does_not_force_release_on_normal_completion():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_index_tts2(*, context, missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _force_release(*, context):
        events.append(("force_release", context))
        raise AssertionError("IndexTTS2 should not force-release ComfyUI memory after a successful run")

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core.force_release_comfyui_memory = _force_release
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session():
            await core.execute_comfykit_workflow(
                "workflows/selfhost/tts_index2.json",
                {},
                workflow_source="selfhost",
            )

        assert events == [
            ("prepare",),
            ("execute", "workflows/selfhost/tts_index2.json"),
            ("index_tts2_release", "post-index-tts2-workflow", "required"),
        ]

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_task_scope_releases_at_task_exit_after_workflow_session():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_workflow():
        events.append(("workflow_release",))
        core._mark_local_comfyui_released()
        return True

    async def _release_task():
        events.append(("task_release",))
        return True

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_task = _release_task
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session():
            await core.execute_comfykit_workflow(
                "first.json",
                {},
                workflow_source="selfhost",
            )

        assert events == [
            ("prepare",),
            ("execute", "first.json"),
        ]

    assert events == [
        ("prepare",),
        ("execute", "first.json"),
        ("task_release",),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_can_release_at_batch_exit_inside_task_scope():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _release_workflow():
        events.append(("workflow_release",))
        core._mark_local_comfyui_released()
        return True

    async def _release_task():
        events.append(("task_release",))
        return True

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_task = _release_task
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session(release_after_session=True):
            await core.execute_comfykit_workflow(
                "image_batch.json",
                {},
                workflow_source="selfhost",
            )

    assert events == [
        ("prepare",),
        ("execute", "image_batch.json"),
        ("workflow_release",),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_fails_when_stage_release_is_not_confirmed(monkeypatch):
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_when_idle(self, *, intensity):
            events.append(("idle_release_skipped", intensity))
            return False

    core = PixelleVideoCore()

    async def _prepare():
        events.append(("prepare",))

    async def _get_kit():
        return _Kit()

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
            )
        )
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)
    core.prepare_comfyui_for_local_workflow = _prepare
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="post-workflow"):
        async with core.local_comfyui_task_scope():
            async with core.local_comfyui_workflow_session(release_after_session=True):
                await core.execute_comfykit_workflow(
                    "image_batch.json",
                    {},
                    workflow_source="selfhost",
                )

    assert events == [
        ("prepare",),
        ("execute", "image_batch.json"),
        ("client", "http://127.0.0.1:8000", "secret"),
        ("idle_release_skipped", "high"),
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_local_workflow_releases_models_after_batch(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_when_idle(
            self,
            *,
            intensity,
        ):
            events.append(("idle_release", intensity))
            return True

        async def free_memory_with_extensions_when_idle(self, **kwargs):
            raise AssertionError("image/media phase release must not call extension cleanup")

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.release_comfyui_after_local_workflow() is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("idle_release", "high"),
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_local_workflow_logs_structured_release_result(monkeypatch):
    log_events = []

    class _BoundLogger:
        def __init__(self, fields=None):
            self.fields = fields or {}

        def bind(self, **fields):
            return _BoundLogger({**self.fields, **fields})

        def info(self, message):
            log_events.append(("info", message, self.fields))

        def warning(self, message):
            log_events.append(("warning", message, self.fields))

    release_result = SimpleNamespace(
        released=True,
        to_log_fields=lambda: {
            "released": True,
            "comfyui_released": True,
            "skipped": False,
            "extension_results": [],
        },
    )

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            pass

        async def free_memory_when_idle(
            self,
            *,
            intensity,
        ):
            return release_result

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)
    monkeypatch.setattr(service_module, "logger", _BoundLogger())

    core = PixelleVideoCore()

    assert await core.release_comfyui_after_local_workflow() is True
    assert log_events == [
        (
            "info",
            "ComfyUI post-workflow memory release completed",
            {
                "channel": "runtime",
                "event": "comfyui_memory_release",
                "context": "post-workflow",
                "model_cleanup_mode": "comfyui_and_extensions",
                "released": True,
                "comfyui_released": True,
                "skipped": False,
                "extension_results": [],
            },
        )
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_logs_failed_confirmation_as_warning(monkeypatch):
    log_events = []

    class _BoundLogger:
        def __init__(self, fields=None):
            self.fields = fields or {}

        def bind(self, **fields):
            return _BoundLogger({**self.fields, **fields})

        def info(self, message):
            log_events.append(("info", message, self.fields))

        def warning(self, message):
            log_events.append(("warning", message, self.fields))

    release_result = SimpleNamespace(
        released=False,
        to_log_fields=lambda: {
            "released": False,
            "comfyui_released": False,
            "release_confirmed": False,
            "safe_to_continue": False,
            "release_confirmation_reason": "release_not_observed",
            "extension_results": [],
        },
    )

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            pass

        async def free_memory_with_extensions_when_idle(
            self,
            *,
            intensity,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            return release_result

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)
    monkeypatch.setattr(service_module, "logger", _BoundLogger())

    core = PixelleVideoCore()

    with pytest.raises(RuntimeError, match="memory release was not confirmed"):
        await core.release_comfyui_after_index_tts2_workflow(
            context="post-index-tts2-workflow",
            missing_endpoint="required",
        )

    assert log_events == [
        (
            "warning",
            "ComfyUI post-index-tts2-workflow memory release not confirmed",
            {
                "channel": "runtime",
                "event": "comfyui_memory_release",
                "context": "post-index-tts2-workflow",
                "model_cleanup_mode": "comfyui_and_extensions",
                "released": False,
                "comfyui_released": False,
                "release_confirmed": False,
                "safe_to_continue": False,
                "release_confirmation_reason": "release_not_observed",
                "extension_results": [],
            },
        )
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_releases_standard_and_plugin_models(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_with_extensions_when_idle(
            self,
            *,
            intensity,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            events.append(("idle_release_with_extensions", intensity, extensions, missing_endpoint))
            return True

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.release_comfyui_after_index_tts2_workflow(
        context="post-index-tts2-workflow",
        missing_endpoint="optional",
    ) is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("idle_release_with_extensions", "high", ("indextts2",), "optional"),
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_forces_extension_cleanup_in_comfyui_mode(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_with_extensions_when_idle(
            self,
            *,
            intensity,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            events.append(("idle_release_with_extensions", intensity, extensions, missing_endpoint))
            return True

        async def free_memory_when_idle(self, *, intensity):
            raise AssertionError("IndexTTS2 release must also clean plugin caches")

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                model_cleanup_mode="comfyui",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.release_comfyui_after_index_tts2_workflow(
        context="post-index-tts2-workflow",
        missing_endpoint="required",
    ) is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("idle_release_with_extensions", "high", ("indextts2",), "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_release_preflight_runs_in_comfyui_cleanup_mode(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def preflight_extension_release_endpoints(
            self,
            *,
            extensions=("indextts2",),
        ):
            events.append(("preflight", extensions))
            return []

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                model_cleanup_mode="comfyui",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.preflight_comfyui_extension_release_endpoints(
        context="pre-index-tts2-workflow",
        extensions=("indextts2",),
    ) is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("preflight", ("indextts2",)),
    ]


@pytest.mark.asyncio
async def test_prepare_comfyui_for_local_workflow_only_cleans_queue(monkeypatch):
    events = []

    class _Client:
        def __init__(
            self,
            base_url,
            *,
            api_key=None,
            timeout=5.0,
            transport=None,
            idle_wait_timeout=20.0,
        ):
            events.append(("client", base_url, api_key, idle_wait_timeout))

        async def cleanup_before_generation(self, mode):
            events.append(("cleanup", mode))

        async def free_memory_with_extensions(
            self,
            intensity="high",
            *,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            events.append(("free_with_extensions", intensity, extensions, missing_endpoint))
            return []

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                pre_generation_cleanup_mode="force",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    await core.prepare_comfyui_for_local_workflow()

    assert events == [
        ("client", "http://127.0.0.1:8000", "secret", 20.0),
        ("cleanup", "force"),
    ]


@pytest.mark.asyncio
async def test_force_release_comfyui_memory_uses_comfyui_only_mode_high_intensity(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory(self, intensity="high"):
            events.append(("force_release", intensity))
            return True

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "post_generation_cleanup_intensity": "low",
                    "model_cleanup_mode": "comfyui",
                    "comfyui_api_key": "secret",
                }
            }
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.force_release_comfyui_memory(context="oom-recovery") is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("force_release", "high"),
    ]


@pytest.mark.asyncio
async def test_force_release_comfyui_memory_uses_required_extension_endpoint(monkeypatch):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_with_extensions(
            self,
            intensity="high",
            *,
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            events.append(("free_with_extensions", intensity, extensions, missing_endpoint))
            return True

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                model_cleanup_mode="comfyui_and_extensions",
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    assert await core.force_release_comfyui_memory(context="oom-recovery") is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("free_with_extensions", "high", ("indextts2",), "required"),
    ]


@pytest.mark.asyncio
async def test_prepare_comfyui_for_local_workflow_uses_configured_cleanup_timeout(monkeypatch):
    events = []

    class _Client:
        def __init__(
            self,
            base_url,
            *,
            api_key=None,
            timeout=5.0,
            transport=None,
            idle_wait_timeout=15.0,
        ):
            events.append(("client", base_url, api_key, idle_wait_timeout))

        async def cleanup_before_generation(self, mode):
            events.append(("cleanup", mode))

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
                comfyui_api_key="secret",
                pre_generation_cleanup_mode="conservative",
                pre_generation_cleanup_timeout_seconds=45.0,
            )
        ),
    )
    monkeypatch.setattr(service_module, "ComfyUIMaintenanceClient", _Client)

    core = PixelleVideoCore()

    await core.prepare_comfyui_for_local_workflow()

    assert events == [
        ("client", "http://127.0.0.1:8000", "secret", 45.0),
        ("cleanup", "conservative"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_serializes_concurrent_workflows():
    events = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(f"{workflow_input}:start")
            if workflow_input == "first":
                first_started.set()
                await release_first.wait()
            events.append(f"{workflow_input}:end")
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare():
        events.append("prepare")

    async def _release():
        events.append("release")

    async def _get_kit():
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session():
        first_task = asyncio.create_task(
            core.execute_comfykit_workflow(
                "first",
                {},
                workflow_source="selfhost",
            )
        )
        await first_started.wait()
        second_task = asyncio.create_task(
            core.execute_comfykit_workflow(
                "second",
                {},
                workflow_source="selfhost",
            )
        )
        await asyncio.sleep(0.01)

        assert events == ["prepare", "first:start"]

        release_first.set()
        await asyncio.gather(first_task, second_task)

    assert events == [
        "prepare",
        "first:start",
        "first:end",
        "second:start",
        "second:end",
        "release",
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_is_scoped_to_core_instance():
    events = []

    def configure_core(name: str) -> PixelleVideoCore:
        class _Kit:
            async def execute(self, workflow_input, workflow_params):
                events.append((name, "execute", workflow_input))
                return SimpleNamespace(status="completed")

        core = PixelleVideoCore()

        async def _prepare():
            events.append((name, "prepare"))

        async def _release():
            events.append((name, "release"))

        async def _get_kit():
            return _Kit()

        core.prepare_comfyui_for_local_workflow = _prepare
        core.release_comfyui_after_local_workflow = _release
        core._get_or_create_comfykit = _get_kit
        return core

    first_core = configure_core("first_core")
    second_core = configure_core("second_core")

    async with first_core.local_comfyui_workflow_session():
        await first_core.execute_comfykit_workflow(
            "first-session-workflow",
            {},
            workflow_source="selfhost",
        )
        await second_core.execute_comfykit_workflow(
            "second-core-workflow",
            {},
            workflow_source="selfhost",
        )

    assert events == [
        ("first_core", "prepare"),
        ("first_core", "execute", "first-session-workflow"),
        ("second_core", "prepare"),
        ("second_core", "execute", "second-core-workflow"),
        ("second_core", "release"),
        ("first_core", "release"),
    ]


@pytest.mark.asyncio
async def test_core_execute_gguf_connection_loss_restarts_managed_backend_and_retries(monkeypatch):
    events = []
    core = PixelleVideoCore()

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(
            comfyui=ComfyUIConfig(
                comfyui_url="http://127.0.0.1:8000",
            )
        ),
    )

    async def _prepare():
        events.append("prepare")

    async def _register_use():
        events.append("register_use")

    async def _restart(reason):
        events.append(("restart", reason))
        return True

    async def _release_memory(context, *, include_extensions=False, extensions=(), missing_endpoint="optional"):
        events.append(("release_memory", context, include_extensions, extensions, missing_endpoint))
        return True

    call_count = 0

    async def _execute_once(workflow_input, workflow_params):
        nonlocal call_count
        call_count += 1
        events.append(("execute_once", call_count, workflow_input))
        if call_count == 1:
            key = ConnectionKey(
                host="127.0.0.1",
                port=8000,
                is_ssl=False,
                ssl=True,
                proxy=None,
                proxy_auth=None,
                proxy_headers_hash=None,
            )
            raise ClientConnectorError(key, ConnectionRefusedError(1225, "connection refused"))
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core._register_local_comfyui_task_use = _register_use
    core._execute_local_comfykit_workflow_once = _execute_once
    core.restart_managed_comfyui_backend = _restart
    core._release_comfyui_memory_when_idle = _release_memory
    _install_noop_extension_preflight(core)

    result = await core.execute_comfykit_workflow(
        "selfhost/image_z_image_turbo_gguf.json",
        {"prompt": "demo"},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert events == [
        "prepare",
        "register_use",
        ("execute_once", 1, "selfhost/image_z_image_turbo_gguf.json"),
        ("restart", "connection_lost_during_workflow"),
        "prepare",
        "register_use",
        ("execute_once", 2, "selfhost/image_z_image_turbo_gguf.json"),
        ("release_memory", "post-gguf-workflow", True, ("gguf",), "required"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_ignores_legacy_gguf_restart_config(monkeypatch):
    events = []
    core = PixelleVideoCore()

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig.model_validate(
            {
                "comfyui": {
                    "comfyui_url": "http://127.0.0.1:8000",
                    "gguf_cleanup_strategy": "process_restart",
                }
            }
        ),
    )

    async def _prepare():
        events.append("prepare")

    async def _restart(reason):
        events.append(("restart", reason))
        return True

    async def _release_memory(context, *, include_extensions=False, extensions=(), missing_endpoint="optional"):
        events.append(("release_memory", context, include_extensions, extensions, missing_endpoint))
        return True

    async def _execute_once(workflow_input, workflow_params):
        events.append(("execute_once", workflow_input))
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core.restart_managed_comfyui_backend = _restart
    core._release_comfyui_memory_when_idle = _release_memory
    core._execute_local_comfykit_workflow_once = _execute_once
    _install_noop_extension_preflight(core)

    async with core.local_comfyui_workflow_session(release_after_session=True):
        await core.execute_comfykit_workflow(
            "selfhost/image_z_image_turbo_gguf.json",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )

    assert events == [
        "prepare",
        ("execute_once", "selfhost/image_z_image_turbo_gguf.json"),
        ("release_memory", "post-gguf-workflow", True, ("gguf",), "required"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_workflow_session_releases_gguf_batch(monkeypatch):
    events = []
    core = PixelleVideoCore()

    monkeypatch.setattr(
        service_module.config_manager,
        "config",
        PixelleVideoConfig(comfyui=ComfyUIConfig(comfyui_url="http://127.0.0.1:8000")),
    )

    async def _prepare():
        events.append("prepare")

    async def _restart(reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(*, context, extensions, missing_endpoint="required"):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        core._mark_local_comfyui_released()
        return True

    async def _execute_once(workflow_input, workflow_params):
        events.append(("execute_once", workflow_input))
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core.restart_managed_comfyui_backend = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    core._execute_local_comfykit_workflow_once = _execute_once
    _install_noop_extension_preflight(core)

    async with core.local_comfyui_workflow_session(release_after_session=True):
        await core.execute_comfykit_workflow(
            "selfhost/image_z_image_turbo_gguf.json",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )

    assert events == [
        "prepare",
        ("execute_once", "selfhost/image_z_image_turbo_gguf.json"),
        (
            "release_extensions",
            "post-gguf-workflow",
            ("gguf",),
            "required",
        ),
    ]


@pytest.mark.asyncio
async def test_restart_managed_comfyui_backend_closes_old_comfykit(monkeypatch):
    closed = []
    core = PixelleVideoCore()

    class _CloseableExecutor:
        async def close(self):
            closed.append("http")

    class _ComfyKit:
        _runninghub_executor = object()
        _http_executor = _CloseableExecutor()
        _websocket_executor = object()

    class _Backend:
        async def restart(self, *, reason):
            assert reason == "post_gguf_workflow"
            return True

    core._comfykit = _ComfyKit()
    core._comfykit_config_hash = "configured"
    monkeypatch.setattr(core, "_get_managed_comfyui_backend", lambda: _Backend())

    restarted = await core.restart_managed_comfyui_backend("post_gguf_workflow")

    assert restarted is True
    assert closed == ["http"]
    assert core._comfykit is None
    assert core._comfykit_config_hash is None


@pytest.mark.asyncio
async def test_core_execute_workflow_file_resolves_runninghub_and_selfhost_inputs(tmp_path):
    calls = []
    core = PixelleVideoCore()

    async def _execute(workflow_input, workflow_params, *, workflow_source):
        calls.append((workflow_input, workflow_params, workflow_source))
        return SimpleNamespace(status="completed")

    core.execute_comfykit_workflow = _execute

    selfhost_workflow = tmp_path / "selfhost.json"
    selfhost_workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")
    await core.execute_comfykit_workflow_file(selfhost_workflow, {"prompt": "local"})

    runninghub_workflow = tmp_path / "runninghub.json"
    runninghub_workflow.write_text(
        json.dumps({"source": "runninghub", "workflow_id": "rh-123"}),
        encoding="utf-8",
    )
    await core.execute_comfykit_workflow_file(runninghub_workflow, {"prompt": "cloud"})

    assert calls == [
        (str(selfhost_workflow), {"prompt": "local"}, "selfhost"),
        ("rh-123", {"prompt": "cloud"}, "runninghub"),
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_non_object_json(tmp_path):
    core = PixelleVideoCore()
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps(["not", "a", "workflow"]), encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a JSON object"):
        await core.execute_comfykit_workflow_file(workflow, {})


@pytest.mark.asyncio
async def test_core_cleanup_skips_comfykit_executors_without_close():
    closed = []

    class _CloseableExecutor:
        async def close(self):
            closed.append("runninghub")

    class _ComfyKit:
        _runninghub_executor = _CloseableExecutor()
        _http_executor = object()
        _websocket_executor = object()

    core = PixelleVideoCore()
    core._comfykit = _ComfyKit()
    core._comfykit_config_hash = "configured"

    await core.cleanup()

    assert closed == ["runninghub"]
    assert core._comfykit is None
    assert core._comfykit_config_hash is None


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_params", [{"n_scenes": 5}, {"split_mode": "sentence"}])
async def test_core_generate_video_rejects_legacy_storyboard_fields_for_standard_pipeline(legacy_params):
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="legacy storyboard parameter"):
        await core.generate_video(text="demo", **legacy_params)

    assert pipeline.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_params",
    [
        {"mode": "bogus"},
        {"storyboard_mode": "bogus"},
        {"storyboard_count_mode": "bogus"},
        {"script_length_mode": "bogus"},
        {"script_length_mode": "custom", "script_target_words": 0},
        {"tts_audio_strategy": "bogus"},
    ],
)
async def test_core_generate_video_rejects_invalid_contract_enums_for_standard_pipeline(invalid_params):
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="unsupported|invalid"):
        await core.generate_video(text="demo", **invalid_params)

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_generate_video_rejects_scene_count_above_contract_limit():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="storyboard_scene_count"):
        await core.generate_video(
            text="demo",
            storyboard_count_mode="manual",
            storyboard_scene_count=31,
        )

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_generate_video_rejects_scene_count_above_configured_limit():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    core.config = {"storyboard": {"min_scene_count": 1, "max_scene_count": 4}}
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="storyboard_scene_count"):
        await core.generate_video(
            text="demo",
            storyboard_count_mode="manual",
            storyboard_scene_count=5,
        )

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_generate_video_rejects_per_frame_audio_strategy_for_standard_pipeline():
    class _Pipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _Pipeline()
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    with pytest.raises(ValueError, match="per_frame"):
        await core.generate_video(text="demo", tts_audio_strategy="per_frame")

    assert pipeline.calls == 0


@pytest.mark.asyncio
async def test_core_initialize_does_not_register_custom_template_pipeline_by_default(monkeypatch):
    import pixelle_video.service as service_module

    class _DummyService:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _DummyPipeline:
        def __init__(self, core):
            self.core = core

    monkeypatch.setattr(service_module, "LLMService", _DummyService)
    monkeypatch.setattr(service_module, "TTSService", _DummyService)
    monkeypatch.setattr(service_module, "MediaService", _DummyService)
    monkeypatch.setattr(service_module, "ImageAnalysisService", _DummyService)
    monkeypatch.setattr(service_module, "VideoAnalysisService", _DummyService)
    monkeypatch.setattr(service_module, "VideoService", _DummyService)
    monkeypatch.setattr(service_module, "FrameProcessor", _DummyService)
    monkeypatch.setattr(service_module, "PersistenceService", _DummyService)
    monkeypatch.setattr(service_module, "HistoryManager", _DummyService)
    monkeypatch.setattr(service_module, "AlignmentService", _DummyService)
    monkeypatch.setattr(service_module, "AudioEditService", _DummyService)
    monkeypatch.setattr(service_module, "HyperFramesProjectService", _DummyService)
    monkeypatch.setattr(service_module, "HyperFramesRenderer", _DummyService)
    monkeypatch.setattr(service_module, "StandardPipeline", _DummyPipeline)
    monkeypatch.setattr(service_module, "AssetBasedPipeline", _DummyPipeline)

    core = PixelleVideoCore()
    await core.initialize()

    assert set(core.pipelines) == {"standard", "asset_based"}


@pytest.mark.asyncio
async def test_generation_coordinator_keeps_shared_task_after_owner_cancellation():
    coordinator = GenerationCoordinator()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "generated"

    owner = asyncio.create_task(coordinator.run("same-request", factory))
    await started.wait()
    duplicate = asyncio.create_task(coordinator.run("same-request", factory))
    await asyncio.sleep(0)

    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner

    assert calls == 1
    assert coordinator.inflight_count() == 1

    release.set()
    assert await duplicate == "generated"
    await asyncio.sleep(0)
    assert coordinator.inflight_count() == 0
