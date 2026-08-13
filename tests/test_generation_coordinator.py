import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.client_exceptions import ClientConnectorError
from aiohttp.client_reqrep import ConnectionKey

from pixelle_video import service as service_module
from pixelle_video.config.schema import ComfyUIConfig, PixelleVideoConfig
from pixelle_video.service import PixelleVideoCore
from pixelle_video.services.analysis_trace_artifacts import (
    write_analysis_workflow_trace_context,
)
from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.services.comfyui_backend_manager import ComfyUIBackendState
from pixelle_video.services.generation_coordinator import (
    GenerationCoordinator,
    build_generation_fingerprint,
)
from pixelle_video.services.prompt_trace_artifacts import (
    write_single_media_prompt_trace_context,
)
from pixelle_video.services.tts_trace_artifacts import write_tts_workflow_trace_context


def _install_noop_extension_preflight(core):
    async def _preflight(
        *,
        context,
        backend_role="default",
        extensions=("indextts2",),
        missing_endpoint="required",
    ):
        return True

    core.preflight_comfyui_extension_release_endpoints = _preflight


def _tts_trace_context(
    tmp_path,
    *,
    workflow: str,
    workflow_params: dict,
    workflow_input: str | None = None,
    text: str | None = None,
):
    resolved_text = str(
        text
        if text is not None
        else workflow_params.get("text") or workflow_params.get("prompt") or ""
    )
    return write_tts_workflow_trace_context(
        tmp_path / "tts_trace",
        task_id="task-tts",
        text=resolved_text,
        workflow=workflow,
        workflow_input=workflow_input or workflow,
        source="test",
        workflow_params=workflow_params,
    )


def _analysis_trace_context(
    tmp_path,
    *,
    workflow: str,
    workflow_params: dict,
    workflow_input: str | None = None,
    media_path: str = "input.png",
    media_type: str = "image",
    service_domain: str = "image_analysis",
):
    return write_analysis_workflow_trace_context(
        tmp_path / "analysis_trace",
        task_id="task-analysis",
        media_path=media_path,
        media_type=media_type,
        workflow=workflow,
        workflow_input=workflow_input or workflow,
        source="test",
        service_domain=service_domain,
        workflow_params=workflow_params,
    )


def _use_test_runninghub_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))


def _patch_maintenance_client(monkeypatch, client_cls):
    class _ClientFactory(client_cls):
        def __init__(self, base_url, **kwargs):
            try:
                super().__init__(base_url, **kwargs)
            except TypeError as exc:
                if "idle_wait_timeout" not in kwargs:
                    raise
                filtered_kwargs = dict(kwargs)
                filtered_kwargs.pop("idle_wait_timeout", None)
                try:
                    super().__init__(base_url, **filtered_kwargs)
                except TypeError:
                    raise exc

    monkeypatch.setattr(
        "pixelle_video.services.comfyui_backend_registry.ComfyUIMaintenanceClient",
        _ClientFactory,
    )


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
async def test_core_generate_video_releases_generation_resources_once_for_identical_inflight_generation():
    started = asyncio.Event()
    release = asyncio.Event()
    release_calls = []

    class _SlowPipeline:
        def __init__(self):
            self.calls = 0

        async def __call__(self, *, text, **kwargs):
            self.calls += 1
            started.set()
            await release.wait()
            return SimpleNamespace(text=text, kwargs=kwargs)

    core = PixelleVideoCore()
    pipeline = _SlowPipeline()

    async def _release_generation_resources_unlocked(*, reason):
        release_calls.append((reason, core._active_generation_count))
        return True

    core._release_generation_resources_unlocked = _release_generation_resources_unlocked
    core.pipelines = {"standard": pipeline}
    core.generate_video = core._create_generate_video_wrapper()

    first = asyncio.create_task(core.generate_video(text="demo", storyboard_mode="smart"))
    await started.wait()
    second = asyncio.create_task(core.generate_video(text="demo", storyboard_mode="smart"))
    await asyncio.sleep(0)

    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result is second_result
    assert pipeline.calls == 1
    assert release_calls == [("post-video-generation:standard", 0)]


@pytest.mark.asyncio
async def test_core_generate_video_defers_resource_release_until_concurrent_generations_finish():
    started = {"one": asyncio.Event(), "two": asyncio.Event()}
    release = {"one": asyncio.Event(), "two": asyncio.Event()}
    release_calls = []

    class _Pipeline:
        async def __call__(self, *, text, **kwargs):
            started[text].set()
            await release[text].wait()
            return SimpleNamespace(text=text)

    core = PixelleVideoCore()

    async def _release_generation_resources_unlocked(*, reason):
        release_calls.append((reason, core._active_generation_count))
        return True

    core._release_generation_resources_unlocked = _release_generation_resources_unlocked
    core.pipelines = {"standard": _Pipeline()}
    core.generate_video = core._create_generate_video_wrapper()

    first = asyncio.create_task(core.generate_video(text="one", storyboard_mode="smart"))
    second = asyncio.create_task(core.generate_video(text="two", storyboard_mode="smart"))
    await asyncio.gather(started["one"].wait(), started["two"].wait())

    release["one"].set()
    first_result = await first
    await asyncio.sleep(0)

    assert first_result.text == "one"
    assert release_calls == []

    release["two"].set()
    second_result = await second

    assert second_result.text == "two"
    assert release_calls == [("post-video-generation:standard", 0)]


@pytest.mark.asyncio
async def test_core_generate_video_preserves_result_when_resource_release_fails():
    class _Pipeline:
        async def __call__(self, *, text, **kwargs):
            return SimpleNamespace(text=text, ok=True)

    core = PixelleVideoCore()

    async def _release_generation_resources_unlocked(*, reason):
        raise RuntimeError("release failed")

    core._release_generation_resources_unlocked = _release_generation_resources_unlocked
    core.pipelines = {"standard": _Pipeline()}
    core.generate_video = core._create_generate_video_wrapper()

    result = await core.generate_video(text="demo", storyboard_mode="smart")

    assert result.ok is True
    assert result.text == "demo"


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
async def test_core_runtime_config_can_disable_generation_resource_release(monkeypatch):
    config = PixelleVideoConfig.model_validate(
        {"runtime": {"release_resources_after_video_generation": False}}
    )
    monkeypatch.setattr(service_module.config_manager, "config", config)

    core = PixelleVideoCore()

    async def _cleanup():
        raise AssertionError("cleanup should not run when release is disabled")

    core.cleanup = _cleanup

    assert await core.release_generation_resources(reason="test") is False


@pytest.mark.asyncio
async def test_core_release_generation_resources_closes_idle_executors_and_browser(monkeypatch):
    from pixelle_video.services.frame_html import HTMLFrameGenerator

    config = PixelleVideoConfig.model_validate(
        {
            "runtime": {
                "release_resources_after_video_generation": True,
                "close_comfykit_after_generation": True,
                "close_html_browser_after_generation": True,
                "collect_garbage_after_generation": False,
                "log_process_memory_after_generation": False,
            }
        }
    )
    monkeypatch.setattr(service_module.config_manager, "config", config)
    calls = []

    core = PixelleVideoCore()

    async def _cleanup():
        calls.append("cleanup")

    async def _close_browser():
        calls.append("close_browser")

    core.cleanup = _cleanup
    monkeypatch.setattr(
        HTMLFrameGenerator,
        "close_browser",
        staticmethod(_close_browser),
    )

    assert await core.release_generation_resources(reason="test") is True
    assert calls == ["cleanup", "close_browser"]


@pytest.mark.asyncio
async def test_core_release_generation_resources_releases_alignment_and_managed_backends(
    monkeypatch,
):
    config = PixelleVideoConfig.model_validate(
        {
            "runtime": {
                "release_resources_after_video_generation": True,
                "close_comfykit_after_generation": False,
                "close_html_browser_after_generation": False,
                "close_alignment_service_after_generation": True,
                "stop_managed_comfyui_backends_after_generation": True,
                "collect_garbage_after_generation": False,
                "log_process_memory_after_generation": False,
            }
        }
    )
    monkeypatch.setattr(service_module.config_manager, "config", config)
    calls = []

    class _AlignmentService:
        def release_resources(self):
            calls.append("alignment_service")
            return True

    core = PixelleVideoCore()
    core.alignment_service = _AlignmentService()

    async def _stop_managed_backends(*, reason):
        calls.append(f"stop_backends:{reason}")
        return ["image_backend", "tts_backend"]

    core._stop_idle_managed_comfyui_backends = _stop_managed_backends

    assert await core.release_generation_resources(reason="test") is True
    assert calls == ["alignment_service", "stop_backends:test"]


@pytest.mark.asyncio
async def test_core_releases_alignment_model_at_stage_boundary(monkeypatch):
    config = PixelleVideoConfig.model_validate(
        {"runtime": {"release_alignment_service_after_use": True}}
    )
    monkeypatch.setattr(service_module.config_manager, "config", config)
    calls = []

    class _AlignmentService:
        def release_resources(self):
            calls.append("release")
            return True

    core = PixelleVideoCore()
    core.alignment_service = _AlignmentService()

    assert await core.release_alignment_service_after_use(context="before-media") is True
    assert calls == ["release"]


@pytest.mark.asyncio
async def test_core_serializes_shared_alignment_use_and_release():
    core = PixelleVideoCore()
    events = []
    first_started = asyncio.Event()
    finish_first = asyncio.Event()

    async def _first_operation():
        events.append("first:start")
        first_started.set()
        await finish_first.wait()
        events.append("first:end")

    async def _second_operation():
        events.append("second:start")
        events.append("second:end")

    async def _release(*, context):
        events.append(f"release:{context}")
        return True

    core.release_alignment_service_after_use = _release

    first_task = asyncio.create_task(
        core.execute_alignment_operation(_first_operation, context="first")
    )
    await first_started.wait()
    second_task = asyncio.create_task(
        core.execute_alignment_operation(_second_operation, context="second")
    )
    await asyncio.sleep(0)

    assert events == ["first:start"]

    finish_first.set()
    await asyncio.gather(first_task, second_task)

    assert events == [
        "first:start",
        "first:end",
        "release:first",
        "second:start",
        "second:end",
        "release:second",
    ]


@pytest.mark.asyncio
async def test_core_alignment_cleanup_never_replaces_business_outcome():
    core = PixelleVideoCore()

    async def _broken_release(*, context):
        raise RuntimeError(f"cleanup failed: {context}")

    core.release_alignment_service_after_use = _broken_release

    assert (
        await core.execute_alignment_operation(lambda: "aligned", context="success")
        == "aligned"
    )

    def _broken_operation():
        raise ValueError("alignment failed")

    with pytest.raises(ValueError, match="alignment failed"):
        await core.execute_alignment_operation(_broken_operation, context="failure")


@pytest.mark.asyncio
async def test_core_stop_idle_managed_comfyui_backends_uses_recent_roles_and_dedupes():
    stop_calls = []
    close_calls = []

    class _Backend:
        def __init__(self, role):
            self.role = role

        def can_manage(self):
            return True

        async def stop(self, *, reason):
            stop_calls.append((self.role, reason))
            return SimpleNamespace(payload={"stopped": True})

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="image_backend",
                tts="tts_backend",
                default="default",
            ),
            backends={
                "default": SimpleNamespace(url="http://127.0.0.1:8001"),
                "image_backend": SimpleNamespace(url="http://127.0.0.1:8001"),
                "tts_backend": SimpleNamespace(url="http://127.0.0.1:8002"),
            },
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend(role)

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {
        "image_backend": None,
        "tts_backend": None,
        "default": None,
    }

    async def _close_comfykit_instance(role=None):
        close_calls.append(role)

    core._close_comfykit_instance = _close_comfykit_instance

    stopped = await core._stop_idle_managed_comfyui_backends(reason="test")

    assert stopped == ["image_backend", "tts_backend"]
    assert stop_calls == [
        ("image_backend", "test generation resource release"),
        ("tts_backend", "test generation resource release"),
    ]
    assert close_calls == ["image_backend", "tts_backend"]


@pytest.mark.asyncio
async def test_core_stop_idle_backends_does_not_probe_unused_routed_backends():
    core = PixelleVideoCore()

    def _unexpected_registry_access():
        raise AssertionError("unused routed backends must not be inspected")

    core._get_comfyui_backend_registry = _unexpected_registry_access

    assert await core._stop_idle_managed_comfyui_backends(reason="test") == []


@pytest.mark.asyncio
async def test_generation_cleanup_waits_for_accelerator_before_delegating_stop():
    events = []

    class _Backend:
        def can_manage(self):
            return True

        async def stop(self, *, reason):
            events.append("stop")
            return SimpleNamespace(payload={"stopped": True})

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="default",
                tts="default",
                default="default",
            ),
            backends={"default": SimpleNamespace(url="http://127.0.0.1:8000")},
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend()

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"default": None}
    async def _close_comfykit_instance(role=None):
        return None

    core._close_comfykit_instance = _close_comfykit_instance
    await core._local_comfyui_accelerator_lock.acquire()
    cleanup = asyncio.create_task(
        core._stop_idle_managed_comfyui_backends(reason="test")
    )
    await asyncio.sleep(0)
    assert events == []
    core._local_comfyui_accelerator_lock.release()

    assert await cleanup == ["default"]
    assert events == ["stop"]


@pytest.mark.asyncio
async def test_core_stop_idle_managed_comfyui_backends_uses_recent_roles_when_available():
    stop_calls = []

    class _Backend:
        def __init__(self, role):
            self.role = role

        def can_manage(self):
            return True

        async def stop(self, *, reason):
            stop_calls.append(self.role)
            return SimpleNamespace(payload={"stopped": True})

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="image_backend",
                tts="tts_backend",
                default="default",
            ),
            backends={
                "default": SimpleNamespace(url="http://127.0.0.1:8001"),
                "image_backend": SimpleNamespace(url="http://127.0.0.1:8001"),
                "tts_backend": SimpleNamespace(url="http://127.0.0.1:8002"),
            },
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend(role)

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"tts_backend": None}

    async def _close_comfykit_instance(role=None):
        return None

    core._close_comfykit_instance = _close_comfykit_instance

    stopped = await core._stop_idle_managed_comfyui_backends(reason="test")

    assert stopped == ["tts_backend"]
    assert stop_calls == ["tts_backend"]
    assert core._recent_local_comfyui_backend_roles == {}


@pytest.mark.asyncio
async def test_core_stop_idle_backends_treats_absence_as_idempotent_success():
    close_calls = []

    class _Backend:
        def can_manage(self):
            return True

        async def stop(self, *, reason):
            return SimpleNamespace(
                payload={
                    "stopped": False,
                    "skipped": True,
                    "reason": "backend_absent",
                    "sensitive_state": "must-not-be-logged",
                }
            )

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="default",
                tts="default",
                default="default",
            ),
            backends={"default": SimpleNamespace(url="http://127.0.0.1:8000")},
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend()

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"default": None}

    async def _close_comfykit_instance(role=None):
        close_calls.append(role)

    core._close_comfykit_instance = _close_comfykit_instance
    warning_messages = []
    sink_id = service_module.logger.add(
        lambda message: warning_messages.append(str(message)),
        level="WARNING",
    )
    try:
        stopped = await core._stop_idle_managed_comfyui_backends(reason="test")
    finally:
        service_module.logger.remove(sink_id)

    assert stopped == []
    assert close_calls == ["default"]
    assert core._recent_local_comfyui_backend_roles == {}
    assert warning_messages == []


@pytest.mark.asyncio
async def test_core_stop_idle_backends_warns_safely_for_unknown_stop_result():
    class _Backend:
        def can_manage(self):
            return True

        async def stop(self, *, reason):
            return SimpleNamespace(
                payload={
                    "stopped": False,
                    "reason": "unexpected_state",
                    "sensitive_state": "must-not-be-logged",
                }
            )

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="default",
                tts="default",
                default="default",
            ),
            backends={"default": SimpleNamespace(url="http://127.0.0.1:8000")},
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend()

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"default": None}

    async def _close_comfykit_instance(role=None):
        return None

    core._close_comfykit_instance = _close_comfykit_instance
    warning_messages = []
    sink_id = service_module.logger.add(
        lambda message: warning_messages.append(str(message)),
        level="WARNING",
    )
    try:
        stopped = await core._stop_idle_managed_comfyui_backends(reason="test")
    finally:
        service_module.logger.remove(sink_id)

    assert stopped == []
    assert len(warning_messages) == 1
    assert "unexpected_state" in warning_messages[0]
    assert "must-not-be-logged" not in warning_messages[0]


@pytest.mark.asyncio
async def test_core_stop_idle_backends_preserves_external_process_and_executor():
    close_calls = []

    class _Backend:
        def can_manage(self):
            return True

        async def stop(self, *, reason):
            return SimpleNamespace(
                payload={
                    "stopped": False,
                    "skipped": True,
                    "reason": "external_backend_not_owned",
                }
            )

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="default",
                tts="default",
                default="default",
            ),
            backends={"default": SimpleNamespace(url="http://127.0.0.1:8000")},
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend()

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"default": None}

    async def _close_comfykit_instance(role=None):
        close_calls.append(role)

    core._close_comfykit_instance = _close_comfykit_instance

    stopped = await core._stop_idle_managed_comfyui_backends(reason="test")

    assert stopped == []
    assert close_calls == []
    assert core._recent_local_comfyui_backend_roles == {}


@pytest.mark.asyncio
async def test_core_stop_idle_backends_cleans_orphan_without_closing_external_executor():
    close_calls = []

    class _Backend:
        def can_manage(self):
            return True

        async def stop(self, *, reason):
            return SimpleNamespace(
                payload={
                    "stopped": True,
                    "preserved_external_listener": True,
                }
            )

    class _Registry:
        config = SimpleNamespace(
            workflow_routing=SimpleNamespace(
                image="default",
                tts="default",
                default="default",
            ),
            backends={"default": SimpleNamespace(url="http://127.0.0.1:8000")},
        )

        def profile(self, role):
            return self.config.backends[role]

        def managed_backend(self, role):
            return _Backend()

    core = PixelleVideoCore()
    core._get_comfyui_backend_registry = lambda: _Registry()
    core._recent_local_comfyui_backend_roles = {"default": None}

    async def _close_comfykit_instance(role=None):
        close_calls.append(role)

    core._close_comfykit_instance = _close_comfykit_instance

    stopped = await core._stop_idle_managed_comfyui_backends(reason="test")

    assert stopped == []
    assert close_calls == []
    assert core._recent_local_comfyui_backend_roles == {}


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

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release(*, backend_role="default"):
        calls.append(("release",))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/lifecycle.json",
        {},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", "workflows/selfhost/lifecycle.json", {}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_preserves_successful_workflow_result_when_cleanup_fails():
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release(*, backend_role="default"):
        calls.append(("release",))
        raise RuntimeError("post-workflow release was not confirmed")

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/lifecycle.json",
        {},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("execute", "workflows/selfhost/lifecycle.json"),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_preserves_failed_result_and_logs_cleanup_as_secondary_failure():
    cleanup_events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            return SimpleNamespace(status="failed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        return None

    async def _release(*, backend_role="default"):
        raise RuntimeError("post-workflow release was not confirmed")

    async def _get_kit(backend_role="default"):
        return _Kit()

    def _record_cleanup(**kwargs):
        cleanup_events.append(kwargs)

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit
    core._log_local_comfyui_cleanup_failure = _record_cleanup

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/lifecycle.json",
        {},
        workflow_source="selfhost",
    )

    assert result.status == "failed"
    assert cleanup_events[0]["business_operation_failed"] is True


@pytest.mark.asyncio
async def test_core_execute_standalone_index_tts2_workflow_releases_models_after_execute(
    tmp_path,
):
    calls = []
    workflow_params = {"prompt": "demo"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release_workflow(*, backend_role="default"):
        raise AssertionError("standalone IndexTTS2 workflow should use the IndexTTS2 release path")

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        calls.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _preflight(
        *,
        context,
        backend_role="default",
        extensions=("indextts2",),
        missing_endpoint="required",
    ):
        raise AssertionError("process-stop cleanup must not require extension preflight")

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_index2.json",
        workflow_params,
        workflow_source="selfhost",
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow="workflows/selfhost/tts_index2.json",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
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

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release_workflow(*, backend_role="default"):
        raise AssertionError("GGUF workflow should use the extension release path")

    async def _release_extensions(*, context, backend_role="default", extensions=("indextts2",), missing_endpoint="optional"):
        calls.append(("extension_release", context, extensions, missing_endpoint))
        return True

    async def _preflight(
        *,
        context,
        backend_role="default",
        extensions=("indextts2",),
        missing_endpoint="required",
    ):
        raise AssertionError("process-stop cleanup must not require extension preflight")

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        str(workflow_path),
        {},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", str(workflow_path), {}),
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

    async def _prepare(*, backend_role="default"):
        calls.append("prepare")

    async def _release(*, backend_role="default"):
        calls.append("release")

    async def _get_kit(backend_role="default"):
        calls.append("get_kit")
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="workflow failed"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/failing_lifecycle.json",
            {},
            workflow_source="selfhost",
        )

    assert calls == ["prepare", "get_kit", "execute", "release"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_shape", ("exception", "error_result"))
async def test_core_execute_local_comfy_workflow_does_not_retry_same_config_after_oom(
    failure_shape,
):
    calls = []
    attempts = 0

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            nonlocal attempts
            attempts += 1
            calls.append(("execute", attempts, workflow_input, workflow_params))
            if attempts == 1:
                error_message = (
                    "[enforce fail at alloc_cpu.cpp:117] data. "
                    "DefaultCPUAllocator: not enough memory: you tried to allocate 11141120 bytes."
                )
                if failure_shape == "error_result":
                    return SimpleNamespace(status="error", msg=error_message)
                raise RuntimeError(error_message)
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release(*, backend_role="default"):
        calls.append(("release",))
        return True

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    async def _force_release(
        *,
        context,
        backend_role="default",
        include_extensions=False,
        extensions=(),
    ):
        calls.append(("force_release", context))
        return True

    async def _restart(backend_role, reason):
        calls.append(("restart", backend_role, reason))
        return True

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core.force_release_comfyui_memory = _force_release
    core._restart_comfyui_backend_role = _restart
    core._get_or_create_comfykit = _get_kit

    if failure_shape == "error_result":
        with pytest.raises(RuntimeError, match="did not retry the same workflow"):
            await core.execute_comfykit_workflow(
                "workflows/selfhost/oom_lifecycle.json",
                {},
                workflow_source="selfhost",
            )
    else:
        with pytest.raises(RuntimeError, match="did not retry the same workflow"):
            await core.execute_comfykit_workflow(
                "workflows/selfhost/oom_lifecycle.json",
                {},
                workflow_source="selfhost",
            )

    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1, "workflows/selfhost/oom_lifecycle.json", {}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_core_uses_recent_managed_log_to_classify_secondary_cublas_failure(
    monkeypatch,
):
    calls = []
    core = PixelleVideoCore()

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        calls.append("execute")
        return SimpleNamespace(
            status="error",
            msg="CUDA error: CUBLAS_STATUS_EXECUTION_FAILED",
        )

    monkeypatch.setattr(core, "_execute_local_comfykit_workflow_once", _execute_once)
    monkeypatch.setattr(
        core,
        "_diagnose_recent_comfyui_backend_failure",
        lambda **_kwargs: "memory_exhaustion",
    )

    with pytest.raises(RuntimeError, match="did not retry the same workflow"):
        await core._execute_local_comfykit_workflow(
            "selfhost/image_z_image_turbo_gguf.json",
            {},
        )

    assert calls == ["execute"]


@pytest.mark.asyncio
async def test_core_execute_index_tts2_oom_stops_without_same_config_retry(
    monkeypatch,
    tmp_path,
):
    calls = []
    attempts = 0
    workflow_params = {"text": "hello"}

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

        async def free_memory_with_extensions_when_idle(
            self,
            *,
            intensity="high",
            extensions=("indextts2",),
            missing_endpoint="optional",
        ):
            calls.append(
                ("free_with_extensions", intensity, extensions, missing_endpoint)
            )
            return True

        async def free_memory_when_idle(self, *, intensity="high"):
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
    _patch_maintenance_client(monkeypatch, _Client)

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        calls.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _restart(backend_role, reason):
        calls.append(("restart", backend_role, reason))
        return True

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core._restart_comfyui_backend_role = _restart
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="did not retry the same workflow"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            workflow_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow="workflows/selfhost/tts_index2.json",
                workflow_params=workflow_params,
            ),
        )

    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1, "workflows/selfhost/tts_index2.json"),
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

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare",))

    async def _release(*, backend_role="default"):
        calls.append(("release",))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit",))
        return _Kit()

    async def _force_release(
        *,
        context,
        backend_role="default",
        include_extensions=False,
        extensions=(),
    ):
        calls.append(("force_release", context))
        return False

    async def _restart(backend_role, reason):
        calls.append(("restart", backend_role, reason))
        return False

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core.force_release_comfyui_memory = _force_release
    core._restart_comfyui_backend_role = _restart
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="did not retry the same workflow"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/oom_release_failure.json",
            {},
            workflow_source="selfhost",
        )

    assert calls == [
        ("prepare",),
        ("get_kit",),
        ("execute", 1),
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

    async def _prepare(*, backend_role="default"):
        calls.append("prepare")
        raise RuntimeError("cleanup failed")

    async def _release(*, backend_role="default"):
        calls.append("release")

    async def _get_kit(backend_role="default"):
        calls.append("get_kit")
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/cleanup_failure.json",
            {},
            workflow_source="selfhost",
        )

    assert calls == ["prepare"]


@pytest.mark.asyncio
async def test_core_execute_runninghub_workflow_bypasses_local_comfy_cleanup(tmp_path):
    calls = []
    workflow_params = {"prompt": "final visual prompt"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-runninghub-cleanup",
        prompt="final visual prompt",
        workflow="runninghub/image_flux.json",
        workflow_input="runninghub-workflow-id",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        raise AssertionError("RunningHub workflow should not prepare local ComfyUI")

    async def _release(*, backend_role="default"):
        raise AssertionError("RunningHub workflow should not release local ComfyUI")

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core._execute_media_comfykit_workflow(
        "runninghub-workflow-id",
        workflow_params,
        workflow_source="runninghub",
        media_service_domain="image",
        media_prompt_trace_context=trace_context,
        media_type="image",
        resolved_workflow="runninghub/image_flux.json",
    )

    assert result.status == "completed"
    assert calls == [
        ("execute", "runninghub-workflow-id", workflow_params),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_runninghub_without_contract_even_empty_params():
    core = PixelleVideoCore()

    async def fail_if_kit_requested(*_args, **_kwargs):
        raise AssertionError("contractless RunningHub workflow must not execute")

    core._get_or_create_comfykit = fail_if_kit_requested

    with pytest.raises(ValueError, match="explicit service workflow contract"):
        await core.execute_comfykit_workflow(
            "runninghub-workflow-id",
            {},
            workflow_source="runninghub",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_public_runninghub_tts_resolved_spoof_empty_params():
    core = PixelleVideoCore()

    async def fail_if_kit_requested(*_args, **_kwargs):
        raise AssertionError("public resolved_workflow must not create a TTS contract")

    core._get_or_create_comfykit = fail_if_kit_requested

    with pytest.raises(ValueError, match="explicit service workflow contract"):
        await core.execute_comfykit_workflow(
            "rh-opaque-id",
            {},
            workflow_source="runninghub",
            resolved_workflow="runninghub/tts_edge.json",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_public_runninghub_tts_domain_spoof_empty_params():
    core = PixelleVideoCore()

    async def fail_if_kit_requested(*_args, **_kwargs):
        raise AssertionError("public workflow_domain must not create a TTS contract")

    core._get_or_create_comfykit = fail_if_kit_requested

    with pytest.raises(ValueError, match="explicit service workflow contract"):
        await core.execute_comfykit_workflow(
            "rh-opaque-id",
            {},
            workflow_source="runninghub",
            workflow_domain="tts",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_media_prompt_boundary():
    core = PixelleVideoCore()

    async def fail_if_prepared(*_args, **_kwargs):
        raise AssertionError("untraced media prompt must be rejected before execution")

    core.prepare_comfyui_for_local_workflow = fail_if_prepared

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/image_z_image_turbo.json",
            {"prompt": "untraced prompt"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_runninghub_media_params():
    core = PixelleVideoCore()

    async def fail_if_kit_requested(*_args, **_kwargs):
        raise AssertionError("untraced runninghub media params must be rejected")

    core._get_or_create_comfykit = fail_if_kit_requested

    with pytest.raises(
        ValueError,
        match="media_prompt_trace_context|explicit media workflow contract",
    ):
        await core.execute_comfykit_workflow(
            "runninghub-workflow-id",
            {"prompt": "untraced prompt", "image": "input.png"},
            workflow_source="runninghub",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_media_params_without_prompt():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("untraced media params must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(
        ValueError,
        match="media_prompt_trace_context|explicit media workflow contract",
    ):
        await core.execute_comfykit_workflow(
            "runninghub-workflow-id",
            {"image": "input.png", "seed": 123},
            workflow_source="runninghub",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/compose.json",
            {"image": "input.png", "seed": 123},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_custom_text_alias():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("untraced alias/custom text params must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(
        ValueError,
        match="media_prompt_trace_context|workflow prompt alias",
    ):
        await core.execute_comfykit_workflow(
            "workflows/custom/generic.json",
            {
                "prompt": "approved final prompt",
                "image_prompt": "hidden different prompt",
                "goodstype": "luxury handbag",
            },
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_prompt_only_selfhost():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("prompt-only media params must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/generic.json",
            {"prompt": "untraced final-media prompt"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_case_variant_prompt_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("case-variant prompt params must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/generic.json",
            {"Prompt": "untraced final-media prompt"},
            workflow_source="selfhost",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "generic",
            {"Prompt": "untraced final-media prompt"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow_params",
    [
        {},
        {"prompt": "demo"},
        {"prompt": "not-demo"},
        {"prompt": " demo "},
        {"positive_prompt": "demo"},
        {"image_prompt": "demo"},
        {"video_prompt": "demo"},
        {"text_prompt": "demo"},
    ],
)
async def test_core_execute_comfykit_workflow_rejects_raw_prompt_non_compat_without_trace(
    workflow_params,
):
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("raw workflow prompt non-compat calls must require trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="raw workflow.json"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            workflow_params,
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_raw_prompt_uppercase_workflow_name():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("raw workflow compatibility name must be exact lowercase")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="raw workflow.json"):
        await core.execute_comfykit_workflow(
            "WORKFLOW.JSON",
            {"prompt": "demo"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_raw_workflow_resolved_workflow_spoof():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("raw workflow.json must not be relabeled by resolved_workflow")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="raw workflow.json"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            {},
            workflow_source="selfhost",
            resolved_workflow="selfhost/image_flux.json",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow_params", "trace_prompt"),
    [
        ({"prompt": "not-demo"}, "not-demo"),
        ({"Prompt": "demo"}, "demo"),
        ({"positive_prompt": "demo"}, "demo"),
        ({"image_prompt": "demo"}, "demo"),
        ({"video_prompt": "demo"}, "demo"),
        ({"text_prompt": "demo"}, "demo"),
    ],
)
async def test_core_execute_comfykit_workflow_rejects_raw_prompt_non_compat_with_trace(
    tmp_path,
    workflow_params,
    trace_prompt,
):
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("raw workflow prompt non-compat calls must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-raw",
        prompt=trace_prompt,
        workflow="workflow.json",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    with pytest.raises(ValueError, match="raw workflow"):
        await core.execute_comfykit_workflow(
            "workflow.json",
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_prompt_dimensions_selfhost():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("prompt and dimensions must be rejected without trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/composite.json",
            {"prompt": "final visual prompt", "width": 768, "height": 512},
            workflow_source="selfhost",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "generic",
            {"prompt": "final visual prompt", "width": 768, "height": 512},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_untraced_custom_text_without_prompt():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("custom text params must be rejected without trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/product.json",
            {"goodstype": "luxury handbag"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_workflow_requires_and_writes_analysis_trace(
    tmp_path,
):
    calls = []
    core = PixelleVideoCore()
    workflow_params = {"image": "input.png"}

    async def _execute_unchecked(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        calls.append((workflow_input, workflow_params, workflow_source, backend_role))
        return SimpleNamespace(status="completed")

    core._execute_comfykit_workflow_unchecked = _execute_unchecked
    trace_context = _analysis_trace_context(
        tmp_path,
        workflow="workflows/runninghub/analyse_image.json",
        workflow_params=workflow_params,
    )

    result = await core._execute_analysis_comfykit_workflow(
        "workflows/runninghub/analyse_image.json",
        workflow_params,
        workflow_source="runninghub",
        workflow_domain="analysis",
        analysis_service_domain="image_analysis",
        analysis_workflow_trace_context=trace_context,
    )
    result_text = Path(trace_context["artifact_path"]).with_name(
        "analysis_workflow_result.md"
    ).read_text(encoding="utf-8")

    assert result.status == "completed"
    assert "pixelle.analysis_workflow_result.v1" in result_text
    assert str(trace_context["artifact_sha256"]) in result_text
    assert calls == [
        (
            "workflows/runninghub/analyse_image.json",
            workflow_params,
            "runninghub",
            "default",
        )
    ]


@pytest.mark.asyncio
async def test_core_execute_analysis_workflow_rejects_missing_analysis_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis workflow must require analysis trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="analysis_workflow_trace_context"):
        await core._execute_analysis_comfykit_workflow(
            "workflows/runninghub/analyse_image.json",
            {"image": "input.png"},
            workflow_source="runninghub",
            workflow_domain="analysis",
            analysis_service_domain="image_analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_public_media_trace_cannot_relabel_analysis_workflow(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "final visual prompt", "image": "input.png"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-analysis-relabel",
        prompt="final visual prompt",
        workflow="workflows/selfhost/analyse_image.json",
        workflow_input="workflows/selfhost/analyse_image.json",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis workflow must not execute through media boundary")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="analysis service workflow"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/analyse_image.json",
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
            resolved_workflow="workflows/selfhost/analyse_image.json",
        )


@pytest.mark.asyncio
async def test_core_execute_public_rejects_raw_workflow_mapping():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("raw workflow mapping must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="raw workflow mappings"):
        await core.execute_comfykit_workflow(
            {"1": {"class_type": "KSampler", "inputs": {}}},
            {},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_media_workflow_cannot_use_analysis_domain_to_bypass_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("media workflow must not bypass prompt trace via analysis domain")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow_domain analysis"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/video_i2v.json",
            {"image": "input.png", "width": 512},
            workflow_source="selfhost",
            workflow_domain="analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_domain_rejects_media_generation_controls():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis workflow controls must not execute without trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="analysis workflow params"):
        await core._execute_analysis_comfykit_workflow(
            "workflows/selfhost/analysis_i2v.json",
            {"image": "input.png", "width": 512},
            workflow_source="selfhost",
            workflow_domain="analysis",
            analysis_service_domain="image_analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_named_workflow_requires_analysis_domain():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis-looking workflow must still declare analysis domain")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(
        ValueError,
        match="analysis service workflow",
    ):
        await core.execute_comfykit_workflow(
            "workflows/runninghub/analyse_image.json",
            {"image": "input.png"},
            workflow_source="runninghub",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_domain_requires_service_contract():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("direct analysis-looking workflow must not bypass trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="resolved analysis service workflow"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/image_analysis.json",
            {"image": "input.png"},
            workflow_source="selfhost",
            workflow_domain="analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_contract_domain_is_not_public():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("public analysis contract spoof must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(TypeError, match="workflow_contract_domain"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/image_analysis.json",
            {"image": "input.png"},
            workflow_source="selfhost",
            workflow_domain="analysis",
            workflow_contract_domain="image_analysis",
        )


@pytest.mark.asyncio
async def test_comfy_base_service_uses_controlled_analysis_core_entrypoint():
    calls = []

    class _Core:
        async def execute_comfykit_workflow(self, *_args, **_kwargs):
            raise AssertionError("analysis service must not use the public core entrypoint")

        async def _execute_analysis_comfykit_workflow(
            self,
            workflow_input,
            workflow_params,
            *,
            workflow_source,
            backend_role="default",
            workflow_domain=None,
            analysis_service_domain,
            analysis_workflow_trace_context=None,
            resolved_workflow=None,
            workflow_file_trace=None,
        ):
            calls.append(
                {
                    "workflow_input": workflow_input,
                    "workflow_params": workflow_params,
                    "workflow_source": workflow_source,
                    "backend_role": backend_role,
                    "workflow_domain": workflow_domain,
                    "analysis_service_domain": analysis_service_domain,
                    "analysis_workflow_trace_context": analysis_workflow_trace_context,
                    "resolved_workflow": resolved_workflow,
                    "workflow_file_trace": workflow_file_trace,
                }
            )
            return SimpleNamespace(status="completed")

    service = ComfyBaseService({}, service_name="image_analysis", core=_Core())

    result = await service._execute_workflow(
        "rh-analysis-id",
        {"image": "input.png"},
        {
            "source": "runninghub",
            "key": "runninghub/analyse_image.json",
            "service_domain": "image_analysis",
        },
        workflow_domain="analysis",
    )

    assert result.status == "completed"
    assert len(calls) == 1
    call = calls[0]
    workflow_file_trace = call.pop("workflow_file_trace")
    assert call == {
        "workflow_input": "rh-analysis-id",
        "workflow_params": {"image": "input.png"},
        "workflow_source": "runninghub",
        "backend_role": "default",
        "workflow_domain": "analysis",
        "analysis_service_domain": "image_analysis",
        "analysis_workflow_trace_context": None,
        "resolved_workflow": "runninghub/analyse_image.json",
    }
    assert set(workflow_file_trace or {}) == {
        "workflow_file_sha256",
        "workflow_prompt_literals",
        "workflow_prompt_literals_sha256",
    }


@pytest.mark.asyncio
async def test_core_execute_analysis_workflow_rejects_prompt_without_analysis_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis prompt must not execute without trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="analysis_prompt_trace_context"):
        await core._execute_analysis_comfykit_workflow(
            "workflows/runninghub/analyse_image.json",
            {"image": "input.png", "prompt": "describe the image"},
            workflow_source="runninghub",
            workflow_domain="analysis",
            analysis_service_domain="image_analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_analysis_workflow_rejects_prompt_aliases_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("analysis prompt aliases must not execute without trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="analysis_prompt_trace_context"):
        await core._execute_analysis_comfykit_workflow(
            "workflows/runninghub/analyse_image.json",
            {"image": "input.png", "prompt_text": "describe the image"},
            workflow_source="runninghub",
            workflow_domain="analysis",
            analysis_service_domain="image_analysis",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_known_tts_params_without_tts_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("TTS workflow params must require a TTS trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            {"text": "hello", "ref_audio": "voice.wav"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_opaque_runninghub_tts_params_with_media_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"text": "hello", "voice": "narrator"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-opaque-tts",
        prompt="hello",
        workflow="rh-tts-id",
        workflow_input="rh-tts-id",
        media_type="image",
        source="test",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("opaque TTS params must require TTS trace before execution")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "rh-tts-id",
            workflow_params,
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_opaque_runninghub_text_only_tts_with_media_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-opaque-text-tts",
        prompt="hello",
        workflow="rh-tts-id",
        workflow_input="rh-tts-id",
        media_type="image",
        source="test",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("opaque text-only TTS must require TTS trace before execution")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "rh-tts-id",
            {"text": "hello"},
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_opaque_runninghub_prompt_only_tts_with_media_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-opaque-prompt-tts",
        prompt="hello",
        workflow="rh-tts-id",
        workflow_input="rh-tts-id",
        media_type="image",
        source="test",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("opaque prompt-only TTS must require TTS trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "rh-tts-id",
            {"prompt": "hello"},
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_opaque_runninghub_text_emotion_tts_with_media_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-opaque-emotion-tts",
        prompt="hello",
        workflow="rh-tts-id",
        workflow_input="rh-tts-id",
        media_type="image",
        source="test",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("opaque TTS emotion payload must require TTS trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "rh-tts-id",
            {"text": "hello", "emotion": "happy"},
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_public_runninghub_media_contract_spoof(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "hello"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-public-runninghub-media-spoof",
        prompt="hello",
        workflow="runninghub/image_flux.json",
        workflow_input="rh-opaque-tts-id",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("public RunningHub workflow classification must not be trusted")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "rh-opaque-tts-id",
            workflow_params,
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
            resolved_workflow="runninghub/image_flux.json",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_public_tts_resolved_workflow_spoof(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "hello"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-public-tts-resolved-spoof",
        prompt="hello",
        workflow="runninghub/image_flux.json",
        workflow_input="rh-opaque-tts-id",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    with pytest.raises(TypeError, match="tts_resolved_workflow"):
        await core.execute_comfykit_workflow(
            "rh-opaque-tts-id",
            workflow_params,
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
            tts_resolved_workflow="runninghub/image_flux.json",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_public_runninghub_visual_param_spoof(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "hello", "width": 512}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-public-runninghub-visual-spoof",
        prompt="hello",
        workflow="runninghub/image_flux.json",
        workflow_input="rh-opaque-tts-id",
        media_type="image",
        source="test",
        media_width=512,
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("public RunningHub media_type must not be trusted")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="explicit media workflow contract"):
        await core.execute_comfykit_workflow(
            "rh-opaque-tts-id",
            workflow_params,
            workflow_source="runninghub",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
            resolved_workflow="runninghub/image_flux.json",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_known_tts_visual_params_with_media_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "hello", "width": 512}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-known-tts-visual-spoof",
        prompt="hello",
        workflow="selfhost/image_flux.json",
        workflow_input="workflows/selfhost/tts_edge.json",
        media_type="image",
        source="test",
        media_width=512,
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("known TTS workflow must require a TTS trace first")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=media_trace_context,
            media_type="image",
            resolved_workflow="selfhost/image_flux.json",
        )


@pytest.mark.asyncio
async def test_core_execute_media_comfykit_workflow_allows_prompt_only_runninghub_media_contract(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"prompt": "final visual prompt"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-runninghub-media-contract",
        prompt="final visual prompt",
        workflow="runninghub/image_flux.json",
        workflow_input="rh-image-id",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def _execute_unchecked(*_args, **_kwargs):
        return SimpleNamespace(status="completed", images=["generated.png"])

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    result = await core._execute_media_comfykit_workflow(
        "rh-image-id",
        workflow_params,
        workflow_source="runninghub",
        media_service_domain="image",
        media_prompt_trace_context=media_trace_context,
        media_type="image",
        resolved_workflow="runninghub/image_flux.json",
    )

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_known_tts_unknown_params_without_tts_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("known TTS workflow must require TTS trace for unknown TTS controls")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            {"text": "hello", "emotion": "happy"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_allows_known_tts_params_with_tts_trace(
    tmp_path,
):
    calls = []
    workflow_params = {"text": "hello", "ref_audio": "voice.wav"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()
    core.prepare_comfyui_for_local_workflow = lambda *, backend_role="default": None
    core.release_comfyui_after_local_workflow = lambda *, backend_role="default": None

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        calls.append(("release", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_edge.json",
        workflow_params,
        workflow_source="selfhost",
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow="workflows/selfhost/tts_edge.json",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        (
            "execute",
            "workflows/selfhost/tts_edge.json",
            {"text": "hello", "ref_audio": "voice.wav"},
        ),
        ("release", "default"),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_allows_known_tts_unknown_params_with_tts_trace(
    tmp_path,
):
    calls = []
    workflow_params = {"text": "hello", "emotion": "happy"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        calls.append(("release", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_edge.json",
        workflow_params,
        workflow_source="selfhost",
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow="workflows/selfhost/tts_edge.json",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        (
            "execute",
            "workflows/selfhost/tts_edge.json",
            {"text": "hello", "emotion": "happy"},
        ),
        ("release", "default"),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_tts_trace_text_mismatch(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow_params = {"text": "visible text"}

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("mismatched TTS trace must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="text does not match"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            workflow_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow="workflows/selfhost/tts_edge.json",
                workflow_params={"text": "hidden text"},
            ),
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_allows_known_tts_prompt_param_without_media_trace(
    tmp_path,
):
    calls = []
    workflow_params = {"prompt": "hello"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        calls.append(("release", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit
    _install_noop_extension_preflight(core)

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/tts_edge.json",
        workflow_params,
        workflow_source="selfhost",
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow="workflows/selfhost/tts_edge.json",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        (
            "execute",
            "workflows/selfhost/tts_edge.json",
            {"prompt": "hello"},
        ),
        ("release", "default"),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_known_tts_case_variant_prompt_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("case-variant prompt must not be treated as TTS text")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="lowercase"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            {"Prompt": "hello"},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "workflow_params",
    [
        {"Text": "hello"},
        {"Ref_Audio": "voice.wav"},
        {"Prompt_Text": "reference transcript"},
    ],
)
async def test_core_execute_comfykit_workflow_rejects_known_tts_case_variant_text_params(
    workflow_params,
):
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("case-variant TTS text params must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="lowercase"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_edge.json",
            workflow_params,
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_allows_omnivoice_tts_params_without_media_trace(
    tmp_path,
):
    calls = []
    workflow_params = {"text": "hello", "ref_audio": "voice.wav"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        calls.append(("release", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit
    _install_noop_extension_preflight(core)

    result = await core.execute_comfykit_workflow(
        "workflows/selfhost/OmniVoice_all.json",
        workflow_params,
        workflow_source="selfhost",
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow="workflows/selfhost/OmniVoice_all.json",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        (
            "execute",
            "workflows/selfhost/OmniVoice_all.json",
            {"text": "hello", "ref_audio": "voice.wav"},
        ),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_tts_named_visual_params_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("tts/audio names must not exempt visual media params")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/audio_image.json",
            {
                "prompt": "untraced final-media prompt",
                "width": 768,
                "height": 512,
            },
            workflow_source="selfhost",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/OmniVoice_image.json",
            {"Prompt": "untraced final-media prompt", "seed": 123},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_audio_named_seed_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("audio-like names must not exempt generation controls")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/audio_seed.json",
            {"seed": 123},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_unknown_scalar_control_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("unknown scalar controls must require trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/generic.json",
            {"control_weight": 0.8},
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_fake_tts_payload_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("fake TTS names must not exempt text/ref_audio payloads")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/tts_fake_visual.json",
            {
                "text": "cinematic product shot",
                "ref_audio": "voice.wav",
            },
            workflow_source="selfhost",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_allows_omnivoice_tts_without_media_trace(
    tmp_path,
):
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    workflow = tmp_path / "OmniVoice_all.json"
    workflow.write_text(
        json.dumps(
            {
                "1": {
                    "inputs": {"text": "hello"},
                    "class_type": "OmniVoiceLongformTTS",
                }
            }
        ),
        encoding="utf-8",
    )
    core.prepare_comfyui_for_local_workflow = _prepare
    core._get_or_create_comfykit = _get_kit
    _install_noop_extension_preflight(core)
    workflow_params = {"text": "hello", "ref_audio": "voice.wav"}

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow=str(workflow),
            workflow_input=str(workflow),
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        (
            "execute",
            str(workflow),
            {"text": "hello", "ref_audio": "voice.wav"},
        ),
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_tts_descriptor_without_tts_trace(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "tts_edge.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-tts-123",
                "workflow_domain": "tts",
                "service_domain": "tts",
            }
        ),
        encoding="utf-8",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("RunningHub TTS descriptor must require TTS trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"text": "hello"},
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_descriptor_tts_params_without_tts_trace(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "speech.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-speech-123",
                "workflow_domain": "tts",
                "service_domain": "tts",
            }
        ),
        encoding="utf-8",
    )
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-speech-descriptor",
        prompt="hello",
        workflow="rh-speech-123",
        workflow_input="rh-speech-123",
        media_type="image",
        source="test",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("RunningHub TTS-shaped descriptor must require TTS trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"text": "hello", "voice": "narrator"},
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_media_domain_without_media_type(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "opaque_descriptor.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-opaque-123",
                "service_domain": "image",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "final visual prompt"}
    media_trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-opaque-descriptor-domain",
        prompt="final visual prompt",
        workflow="rh-opaque-123",
        workflow_input="rh-opaque-123",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("service_domain image without media_type must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="explicit media_type"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=media_trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_uses_runninghub_analysis_service_contract(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    calls = []
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "analyse_image.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-analysis-123",
                "workflow_domain": "image_analysis",
                "service_domain": "image_analysis",
            }
        ),
        encoding="utf-8",
    )

    async def _execute_unchecked(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        calls.append((workflow_input, workflow_params, workflow_source, backend_role))
        return SimpleNamespace(status="completed")

    core._execute_comfykit_workflow_unchecked = _execute_unchecked
    workflow_params = {"image": "input.png"}
    trace_context = _analysis_trace_context(
        tmp_path,
        workflow=str(workflow),
        workflow_input="rh-analysis-123",
        workflow_params=workflow_params,
    )

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        analysis_workflow_trace_context=trace_context,
    )
    result_text = Path(trace_context["artifact_path"]).with_name(
        "analysis_workflow_result.md"
    ).read_text(encoding="utf-8")

    assert result.status == "completed"
    assert "pixelle.analysis_workflow_result.v1" in result_text
    assert calls == [
        ("rh-analysis-123", workflow_params, "runninghub", "default")
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_allows_runninghub_tts_descriptor_with_tts_trace(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    calls = []
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "tts_edge.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-tts-123",
                "workflow_domain": "tts",
                "service_domain": "tts",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"text": "hello"}

    async def _execute_unchecked(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        calls.append((workflow_input, workflow_params, workflow_source, backend_role))
        return SimpleNamespace(status="completed")

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        tts_workflow_trace_context=_tts_trace_context(
            tmp_path,
            workflow=str(workflow),
            workflow_input="rh-tts-123",
            workflow_params=workflow_params,
        ),
    )

    assert result.status == "completed"
    assert calls == [
        ("rh-tts-123", {"text": "hello"}, "runninghub", "default")
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_writes_tts_result_artifact(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "voice_descriptor.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-voice-123",
                "workflow_domain": "tts",
                "service_domain": "tts",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"text": "hello"}

    async def _execute_unchecked(*_args, **_kwargs):
        return SimpleNamespace(
            status="completed",
            audios=["generated.wav"],
            files=[],
            outputs={},
        )

    core._execute_comfykit_workflow_unchecked = _execute_unchecked
    trace_context = _tts_trace_context(
        tmp_path,
        workflow=str(workflow),
        workflow_input="rh-voice-123",
        workflow_params=workflow_params,
    )

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        tts_workflow_trace_context=trace_context,
    )

    result_path = Path(trace_context["artifact_path"]).with_name(
        "tts_workflow_result.md"
    )
    result_text = result_path.read_text(encoding="utf-8")

    assert result.status == "completed"
    assert '"status": "completed"' in result_text
    assert "generated.wav" in result_text


@pytest.mark.asyncio
async def test_core_execute_workflow_file_writes_media_result_artifact(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "video_i2v.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-video-123",
                "media_type": "video",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {
        "prompt": "final visual prompt",
        "image": "input.png",
        "width": 768,
        "height": 512,
    }
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-workflow-file-media",
        prompt="final visual prompt",
        workflow="rh-video-123",
        workflow_input="rh-video-123",
        media_type="video",
        source="test",
        media_width=768,
        media_height=512,
        generation_context={"workflow_file": str(workflow)},
        workflow_params=workflow_params,
    )

    async def _execute_unchecked(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        assert workflow_input == "rh-video-123"
        assert workflow_source == "runninghub"
        return SimpleNamespace(
            status="completed",
            videos=["generated.mp4"],
            outputs={"node": {"video": "generated.mp4"}},
        )

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        media_prompt_trace_context=trace_context,
        media_type="video",
    )

    result_path = Path(trace_context["artifact_path"]).with_name(
        "media_workflow_result.md"
    )
    result_text = result_path.read_text(encoding="utf-8")

    assert result.status == "completed"
    assert "pixelle.media_workflow_result.v1" in result_text
    assert str(trace_context["artifact_sha256"]) in result_text
    assert "generated.mp4" in result_text


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_omnivoice_path_visual_params_without_trace(
    tmp_path,
):
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("visual workflow in omnivoice path must require trace")

    workflow_dir = tmp_path / "some_OmniVoice_folder"
    workflow_dir.mkdir()
    workflow = workflow_dir / "image_visual.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")
    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {
                "prompt": "untraced final-media prompt",
                "width": 768,
                "height": 512,
            },
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_omnivoice_path_custom_text_without_trace(
    tmp_path,
):
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("custom text in omnivoice path must require trace")

    workflow_dir = tmp_path / "some_OmniVoice_folder"
    workflow_dir.mkdir()
    workflow = workflow_dir / "image_visual.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")
    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"goodstype": "luxury handbag"},
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_accepts_traced_media_prompt_boundary(
    tmp_path,
):
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    calls = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            calls.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        calls.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        calls.append(("release", backend_role))

    async def _get_kit(backend_role="default"):
        calls.append(("get_kit", backend_role))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit
    workflow_params = {"prompt": "traced prompt", "seed": 123}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-raw-media",
        prompt="traced prompt",
        workflow=str(workflow),
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    result = await core.execute_comfykit_workflow(
        str(workflow),
        workflow_params,
        workflow_source="selfhost",
        media_prompt_trace_context=trace_context,
        media_type="image",
        resolved_workflow=str(workflow),
    )

    assert result.status == "completed"
    assert calls == [
        ("prepare", "default"),
        ("get_kit", "default"),
        ("execute", str(workflow), workflow_params),
        ("release", "default"),
    ]


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_writes_media_result_artifact(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    workflow_params = {"prompt": "traced prompt", "width": 768, "height": 512}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-core-media-result",
        prompt="traced prompt",
        workflow=str(workflow),
        workflow_input=str(workflow),
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
        workflow_params=workflow_params,
    )

    async def _execute_unchecked(*_args, **_kwargs):
        return SimpleNamespace(
            status="completed",
            images=["generated.png"],
            outputs={"node": {"image": "generated.png"}},
        )

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    result = await core.execute_comfykit_workflow(
        str(workflow),
        workflow_params,
        workflow_source="selfhost",
        media_prompt_trace_context=trace_context,
        media_type="image",
        resolved_workflow=str(workflow),
    )

    result_path = Path(trace_context["artifact_path"]).with_name(
        "media_workflow_result.md"
    )
    result_text = result_path.read_text(encoding="utf-8")

    assert result.status == "completed"
    assert str(trace_context["artifact_sha256"]) in result_text
    assert "generated.png" in result_text


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_writes_failed_media_result_artifact(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    workflow_params = {"prompt": "traced prompt"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-core-media-failed",
        prompt="traced prompt",
        workflow=str(workflow),
        workflow_input=str(workflow),
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def _execute_unchecked(*_args, **_kwargs):
        return SimpleNamespace(status="failed", msg="backend refused")

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    result = await core.execute_comfykit_workflow(
        str(workflow),
        workflow_params,
        workflow_source="selfhost",
        media_prompt_trace_context=trace_context,
        media_type="image",
        resolved_workflow=str(workflow),
    )

    result_text = Path(trace_context["artifact_path"]).with_name(
        "media_workflow_result.md"
    ).read_text(encoding="utf-8")

    assert result.status == "failed"
    assert '"status": "failed"' in result_text
    assert "backend refused" in result_text


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_writes_exception_media_result_artifact(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    workflow_params = {"prompt": "traced prompt"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-core-media-error",
        prompt="traced prompt",
        workflow=str(workflow),
        workflow_input=str(workflow),
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def _execute_unchecked(*_args, **_kwargs):
        raise RuntimeError("boom")

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    with pytest.raises(RuntimeError, match="boom"):
        await core.execute_comfykit_workflow(
            str(workflow),
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=trace_context,
            media_type="image",
            resolved_workflow=str(workflow),
        )

    result_text = Path(trace_context["artifact_path"]).with_name(
        "media_workflow_result.md"
    ).read_text(encoding="utf-8")

    assert '"status": "error"' in result_text
    assert "boom" in result_text


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_negative_alias_mismatch(
    tmp_path,
):
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("negative alias mismatch must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed
    workflow_params = {
        "prompt": "traced prompt",
        "negative": "untraced negative prompt",
        "width": 768,
        "height": 512,
    }
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-raw-media",
        prompt="traced prompt",
        workflow=str(workflow),
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
        workflow_params=workflow_params,
    )

    with pytest.raises(ValueError, match="negative prompt"):
        await core.execute_comfykit_workflow(
            str(workflow),
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=trace_context,
            media_type="image",
            resolved_workflow=str(workflow),
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_case_variant_negative_alias(
    tmp_path,
):
    workflow = tmp_path / "image_trace.json"
    workflow.write_text("{}", encoding="utf-8")
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("case-variant negative alias must be rejected")

    core._execute_comfykit_workflow_unchecked = fail_if_executed
    workflow_params = {
        "prompt": "traced prompt",
        "negative_prompt": "safe negative",
        "Negative_Prompt": "hidden negative",
        "width": 768,
        "height": 512,
    }
    traced_workflow_params = {
        key: value
        for key, value in workflow_params.items()
        if key != "Negative_Prompt"
    }
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-raw-media",
        prompt="traced prompt",
        negative_prompt="safe negative",
        workflow=str(workflow),
        media_type="image",
        source="test",
        media_width=768,
        media_height=512,
        workflow_params=traced_workflow_params,
    )

    with pytest.raises(ValueError, match="negative prompt alias"):
        await core.execute_comfykit_workflow(
            str(workflow),
            workflow_params,
            workflow_source="selfhost",
            media_prompt_trace_context=trace_context,
            media_type="image",
            resolved_workflow=str(workflow),
        )


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_tts_named_negative_only_without_trace():
    core = PixelleVideoCore()

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("negative-only visual params must require trace")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_negative.json",
            {"negative_prompt": "hidden negative"},
            workflow_source="selfhost",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/audio_negative.json",
            {"negative": "hidden negative"},
            workflow_source="selfhost",
        )

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow(
            "workflows/custom/OmniVoice_negative.json",
            {"Negative_Prompt": "hidden negative"},
            workflow_source="selfhost",
        )


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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _release(*, backend_role="default"):
        events.append("release")

    async def _get_kit(backend_role="default"):
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
async def test_local_comfyui_workflow_session_prepares_and_stops_once_for_two_item_batch():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release(*, backend_role="default"):
        events.append(("release",))

    async def _get_kit(backend_role="default"):
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session(stop_after_session=True):
        first = await core.execute_comfykit_workflow(
            "first.json",
            {},
            workflow_source="selfhost",
        )
        second = await core.execute_comfykit_workflow(
            "second.json",
            {},
            workflow_source="selfhost",
        )

    assert first.status == "completed"
    assert second.status == "completed"
    assert events == [
        ("prepare",),
        ("get_kit",),
        ("execute", "first.json", {}),
        ("get_kit",),
        ("execute", "second.json", {}),
        ("release",),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_releases_models_once_at_session_exit(
    tmp_path,
):
    events = []
    first_params = {"prompt": "first"}
    second_params = {"prompt": "second"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input, workflow_params))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit(backend_role="default"):
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session(stop_after_session=True):
        first = await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            first_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow="workflows/selfhost/tts_index2.json",
                workflow_params=first_params,
            ),
        )
        second = await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            second_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow="workflows/selfhost/tts_index2.json",
                workflow_params=second_params,
            ),
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

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _preflight(
        *,
        context,
        backend_role="default",
        extensions=("indextts2",),
        missing_endpoint="required",
    ):
        events.append(("preflight", context, extensions))
        return True

    async def _get_kit(backend_role="default"):
        events.append(("get_kit",))
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core._get_or_create_comfykit = _get_kit
    workflow_params = {"prompt": "first"}

    async with core.local_comfyui_workflow_session(stop_after_session=True):
        result = await core.execute_comfykit_workflow(
            str(workflow_path),
            workflow_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow=str(workflow_path),
                workflow_params=workflow_params,
            ),
        )

    assert result.status == "completed"
    assert events == [
        ("prepare",),
        ("get_kit",),
        ("execute", str(workflow_path), {"prompt": "first"}),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_releases_models_at_session_exit(tmp_path):
    events = []
    workflow_params = {"text": "hello"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    _install_noop_extension_preflight(core)
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session():
            await core.execute_comfykit_workflow(
                "workflows/selfhost/tts_index2.json",
                workflow_params,
                workflow_source="selfhost",
                tts_workflow_trace_context=_tts_trace_context(
                    tmp_path,
                    workflow="workflows/selfhost/tts_index2.json",
                    workflow_params=workflow_params,
                ),
            )

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-task-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_does_not_require_extension_release_preflight(
    tmp_path,
):
    events = []
    workflow_params = {"text": "hello"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _preflight(
        *,
        context,
        backend_role="default",
        extensions=("indextts2",),
        missing_endpoint="required",
    ):
        events.append(("preflight", context, extensions))
        return True

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.preflight_comfyui_extension_release_endpoints = _preflight
    core.release_comfyui_after_index_tts2_workflow = _release_index_tts2
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_workflow_session(stop_after_session=True):
        await core.execute_comfykit_workflow(
            "workflows/selfhost/tts_index2.json",
            workflow_params,
            workflow_source="selfhost",
            tts_workflow_trace_context=_tts_trace_context(
                tmp_path,
                workflow="workflows/selfhost/tts_index2.json",
                workflow_params=workflow_params,
            ),
        )

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_index_tts2_workflow_session_does_not_force_release_on_normal_completion(
    tmp_path,
):
    events = []
    workflow_params = {"text": "hello"}

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_index_tts2(*, context, backend_role="default", missing_endpoint="optional"):
        events.append(("index_tts2_release", context, missing_endpoint))
        return True

    async def _force_release(
        *,
        context,
        backend_role="default",
        include_extensions=False,
        extensions=(),
    ):
        events.append(("force_release", context))
        raise AssertionError("IndexTTS2 should not force-release ComfyUI memory after a successful run")

    async def _get_kit(backend_role="default"):
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
                workflow_params,
                workflow_source="selfhost",
                tts_workflow_trace_context=_tts_trace_context(
                    tmp_path,
                    workflow="workflows/selfhost/tts_index2.json",
                    workflow_params=workflow_params,
                ),
            )

        assert events == [
            ("prepare",),
            ("execute", "workflows/selfhost/tts_index2.json"),
        ]

    assert events == [
        ("prepare",),
        ("execute", "workflows/selfhost/tts_index2.json"),
        ("index_tts2_release", "post-task-index-tts2-workflow", "required"),
    ]


@pytest.mark.asyncio
async def test_local_comfyui_task_scope_releases_at_task_exit_after_workflow_session():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_workflow(*, backend_role="default"):
        events.append(("workflow_release",))
        core._mark_local_comfyui_released()
        return True

    async def _release_task(*, backend_role="default"):
        events.append(("task_release",))
        return True

    async def _get_kit(backend_role="default"):
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
async def test_explicit_workflow_batch_stops_inside_task_scope():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_workflow(*, backend_role="default"):
        events.append(("workflow_release",))
        core._mark_local_comfyui_released()
        return True

    async def _release_task(*, backend_role="default"):
        events.append(("task_release",))
        return True

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_task = _release_task
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session(stop_after_session=True):
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
async def test_failed_batch_stop_preserves_success_and_retries_once_at_task_exit():
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare",))

    async def _release_workflow(*, backend_role="default"):
        events.append(("workflow_release",))
        raise RuntimeError("post-workflow stop was not confirmed")

    async def _release_task(*, backend_role="default"):
        events.append(("task_release",))
        core._mark_local_comfyui_released(backend_role=backend_role)
        return True

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release_workflow
    core.release_comfyui_after_local_task = _release_task
    core._get_or_create_comfykit = _get_kit

    async with core.local_comfyui_task_scope():
        async with core.local_comfyui_workflow_session(stop_after_session=True):
            result = await core.execute_comfykit_workflow(
                "image_batch.json",
                {},
                workflow_source="selfhost",
            )

    assert result.status == "completed"
    assert events == [
        ("prepare",),
        ("execute", "image_batch.json"),
        ("workflow_release",),
        ("task_release",),
    ]


def test_stop_after_batch_requires_effective_lifecycle_management(monkeypatch):
    core = PixelleVideoCore()
    registry = SimpleNamespace(
        profile=lambda role: SimpleNamespace(stop_after_batch=True)
    )
    controller = SimpleNamespace(can_manage=lambda: False)

    monkeypatch.setattr(core, "_get_comfyui_backend_registry", lambda: registry)
    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": controller,
    )

    assert core._stop_after_batch_for_role("default") is False


@pytest.mark.asyncio
async def test_task_start_external_ownership_prevents_late_stop_inspection(monkeypatch):
    core = PixelleVideoCore()

    class _ExternalBackend:
        management_mode = "auto"
        profile = SimpleNamespace(managed=True)

        async def inspect_state(self, *, reason):
            raise AssertionError(f"task-start ownership must remain authoritative: {reason}")

    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _ExternalBackend(),
    )

    async with core.local_comfyui_task_scope():
        core._record_local_comfyui_backend_ownership("default", "external")
        assert await core._preserve_external_comfyui_backend(
            "default",
            reason="post-task",
        ) is True


@pytest.mark.asyncio
async def test_unknown_task_start_ownership_requires_live_pixelle_confirmation(monkeypatch):
    core = PixelleVideoCore()

    class _PixelleBackend:
        management_mode = "auto"
        profile = SimpleNamespace(managed=True)

        async def inspect_state(self, *, reason):
            return ComfyUIBackendState(
                ownership="pixelle",
                listener_present=True,
                pid_file_present=True,
                payload={"reason": reason},
            )

    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _PixelleBackend(),
    )

    async with core.local_comfyui_task_scope():
        core._record_local_comfyui_backend_ownership("default", "unknown")
        assert await core._preserve_external_comfyui_backend(
            "default",
            reason="post-task",
        ) is False


def _install_pixelle_owned_comfyui_backend(monkeypatch, core):
    class _PixelleOwnedBackend:
        management_mode = "auto"

        async def inspect_state(self, *, reason):
            return ComfyUIBackendState(
                ownership="pixelle",
                listener_present=True,
                pid_file_present=True,
                payload={},
            )

    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _PixelleOwnedBackend(),
    )


@pytest.mark.asyncio
async def test_release_comfyui_after_local_workflow_stops_owned_service_without_restart(
    monkeypatch,
):
    events = []
    core = PixelleVideoCore()

    async def _stop(backend_role, reason):
        events.append(("stop", backend_role, reason))
        return True

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    _install_pixelle_owned_comfyui_backend(monkeypatch, core)
    monkeypatch.setattr(core, "_get_comfyui_maintenance_client", lambda role: None)
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", _stop)
    monkeypatch.setattr(
        core,
        "_restart_comfyui_backend_role",
        lambda *args, **kwargs: pytest.fail("batch cleanup must not restart ComfyUI"),
    )

    assert await core.release_comfyui_after_local_workflow() is True
    assert events == [("stop", "default", "post-workflow batch stop")]


@pytest.mark.asyncio
async def test_next_local_batch_starts_service_on_demand_after_previous_batch_stop(
    monkeypatch,
):
    events = []

    class _Controller:
        management_mode = "required"
        profile = SimpleNamespace(managed=True)

        def __init__(self):
            self.running = False

        async def ensure_ready(self, *, reason):
            started = not self.running
            self.running = True
            events.append(("ensure", reason, started))
            return SimpleNamespace(
                ownership="pixelle",
                started=started,
                reused_existing=not started,
            )

        async def inspect_state(self, *, reason):
            events.append(("inspect_owner", reason))
            return ComfyUIBackendState(
                ownership="pixelle" if self.running else "absent",
                listener_present=self.running,
                pid_file_present=self.running,
                payload={},
            )

        async def stop(self, *, reason):
            await _Maintenance().wait_until_idle()
            events.append(("stop", reason))
            self.running = False
            return SimpleNamespace(payload={"stopped": True})

    class _Maintenance:
        async def inspect_queue_before_generation(self):
            events.append(("inspect_queue",))

        async def wait_until_idle(self):
            events.append(("idle",))

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            events.append(("execute", workflow_input))
            return SimpleNamespace(status="completed")

    controller = _Controller()
    core = PixelleVideoCore()

    async def _get_kit(backend_role="default"):
        return _Kit()

    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": controller,
    )
    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    monkeypatch.setattr(
        core,
        "_get_comfyui_maintenance_client",
        lambda backend_role="default": _Maintenance(),
    )
    monkeypatch.setattr(core, "_get_or_create_comfykit", _get_kit)

    for workflow_name in ("image_batch.json", "audio_batch.json"):
        async with core.local_comfyui_workflow_session(stop_after_session=True):
            await core.execute_comfykit_workflow(
                workflow_name,
                {},
                workflow_source="selfhost",
            )

    assert events == [
        ("ensure", "pre-workflow", True),
        ("inspect_queue",),
        ("execute", "image_batch.json"),
        ("inspect_owner", "post-workflow batch stop"),
        ("idle",),
        ("stop", "post-workflow batch stop"),
        ("ensure", "pre-workflow", True),
        ("inspect_queue",),
        ("execute", "audio_batch.json"),
        ("inspect_owner", "post-workflow batch stop"),
        ("idle",),
        ("stop", "post-workflow batch stop"),
    ]


@pytest.mark.asyncio
async def test_workflow_batches_for_different_roles_do_not_interleave_service_lifecycle():
    events = []
    image_started = asyncio.Event()
    release_image = asyncio.Event()

    class _Kit:
        def __init__(self, role):
            self.role = role

        async def execute(self, workflow_input, workflow_params):
            events.append(("execute_start", self.role))
            if self.role == "image":
                image_started.set()
                await release_image.wait()
            events.append(("execute_end", self.role))
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        events.append(("prepare", backend_role))

    async def _release(*, backend_role="default"):
        events.append(("release", backend_role))
        return True

    async def _get_kit(backend_role="default"):
        return _Kit(backend_role)

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    async def _run(role):
        async with core.local_comfyui_workflow_session(
            backend_role=role,
            stop_after_session=True,
        ):
            await core.execute_comfykit_workflow(
                f"{role}.json",
                {},
                workflow_source="selfhost",
                backend_role=role,
            )

    image_task = asyncio.create_task(_run("image"))
    await image_started.wait()
    tts_task = asyncio.create_task(_run("tts"))
    await asyncio.sleep(0)

    assert ("prepare", "tts") not in events
    release_image.set()
    await asyncio.gather(image_task, tts_task)

    assert events == [
        ("prepare", "image"),
        ("execute_start", "image"),
        ("execute_end", "image"),
        ("release", "image"),
        ("prepare", "tts"),
        ("execute_start", "tts"),
        ("execute_end", "tts"),
        ("release", "tts"),
    ]


@pytest.mark.asyncio
async def test_nested_workflow_sessions_for_different_roles_fail_instead_of_deadlocking():
    core = PixelleVideoCore()

    async with core.local_comfyui_workflow_session(backend_role="image"):
        with pytest.raises(RuntimeError, match="Cannot nest.*different backend roles"):
            async with core.local_comfyui_workflow_session(backend_role="tts"):
                pass


@pytest.mark.asyncio
async def test_cancelled_workflow_batch_finishes_service_stop_before_releasing_locks():
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()
    body_started = asyncio.Event()
    events = []

    class _Kit:
        async def execute(self, workflow_input, workflow_params):
            return SimpleNamespace(status="completed")

    core = PixelleVideoCore()

    async def _prepare(*, backend_role="default"):
        return None

    async def _release(*, backend_role="default"):
        events.append("cleanup_start")
        cleanup_started.set()
        await allow_cleanup.wait()
        events.append("cleanup_end")
        return True

    async def _get_kit(backend_role="default"):
        return _Kit()

    core.prepare_comfyui_for_local_workflow = _prepare
    core.release_comfyui_after_local_workflow = _release
    core._get_or_create_comfykit = _get_kit

    async def _run_batch():
        async with core.local_comfyui_workflow_session(stop_after_session=True):
            await core.execute_comfykit_workflow(
                "image.json",
                {},
                workflow_source="selfhost",
            )
            body_started.set()
            await asyncio.Future()

    task = asyncio.create_task(_run_batch())
    await body_started.wait()
    task.cancel()
    await cleanup_started.wait()
    await asyncio.sleep(0)
    assert not task.done()

    allow_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ["cleanup_start", "cleanup_end"]
    await asyncio.wait_for(core._local_comfyui_accelerator_lock.acquire(), timeout=1)
    core._local_comfyui_accelerator_lock.release()
    await asyncio.wait_for(core._get_backend_lock("default").acquire(), timeout=1)
    core._get_backend_lock("default").release()


@pytest.mark.asyncio
async def test_release_comfyui_after_local_workflow_preserves_external_backend(monkeypatch):
    core = PixelleVideoCore()

    class _ExternalBackend:
        management_mode = "auto"

        async def inspect_state(self, *, reason):
            return SimpleNamespace(ownership="external", pid_file_present=False)

    async def fail_stop(backend_role, reason):
        raise AssertionError(f"external backend must not stop: {backend_role} {reason}")

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _ExternalBackend(),
    )
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", fail_stop)

    assert await core.release_comfyui_after_local_workflow() is True


@pytest.mark.asyncio
async def test_release_preserves_backend_when_auto_ownership_inspection_fails(monkeypatch):
    core = PixelleVideoCore()

    class _UninspectableBackend:
        management_mode = "auto"

        async def inspect_state(self, *, reason):
            raise PermissionError(f"process inspection denied: {reason}")

    async def fail_stop(backend_role, reason):
        raise AssertionError(f"unverified backend must not stop: {backend_role} {reason}")

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _UninspectableBackend(),
    )
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", fail_stop)

    assert await core.release_comfyui_after_local_workflow() is True


@pytest.mark.asyncio
async def test_release_fails_when_required_ownership_inspection_fails(monkeypatch):
    core = PixelleVideoCore()

    class _UninspectableBackend:
        management_mode = "required"

        async def inspect_state(self, *, reason):
            raise PermissionError(f"process inspection denied: {reason}")

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    monkeypatch.setattr(
        core,
        "_get_comfyui_backend_controller",
        lambda backend_role="default": _UninspectableBackend(),
    )

    with pytest.raises(RuntimeError, match="strict backend management is required"):
        await core.release_comfyui_after_local_workflow()


@pytest.mark.asyncio
async def test_release_comfyui_after_local_workflow_refuses_to_stop_busy_queue(
    monkeypatch,
):
    core = PixelleVideoCore()

    async def fail_stop(backend_role, reason):
        raise RuntimeError(
            "ComfyUI queue could not be confirmed idle before stopping the "
            f"Pixelle-owned backend '{backend_role}'"
        )

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    _install_pixelle_owned_comfyui_backend(monkeypatch, core)
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", fail_stop)

    with pytest.raises(RuntimeError, match="queue could not be confirmed idle"):
        await core.release_comfyui_after_local_workflow()


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_fails_when_stop_is_not_confirmed(
    monkeypatch,
):
    core = PixelleVideoCore()

    async def _stop(backend_role, reason):
        return False

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    _install_pixelle_owned_comfyui_backend(monkeypatch, core)
    monkeypatch.setattr(core, "_get_comfyui_maintenance_client", lambda role: None)
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", _stop)

    with pytest.raises(RuntimeError, match="service stop was not confirmed"):
        await core.release_comfyui_after_index_tts2_workflow(
            context="post-index-tts2-workflow",
            missing_endpoint="required",
        )


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_stops_service_when_enabled(
    monkeypatch,
):
    events = []

    core = PixelleVideoCore()

    async def _stop(backend_role, reason):
        events.append(("stop", backend_role, reason))
        return True

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: True)
    _install_pixelle_owned_comfyui_backend(monkeypatch, core)
    monkeypatch.setattr(core, "_get_comfyui_maintenance_client", lambda role: None)
    monkeypatch.setattr(core, "_stop_comfyui_backend_role", _stop)

    assert await core.release_comfyui_after_index_tts2_workflow(
        context="post-index-tts2-workflow",
        missing_endpoint="optional",
    ) is True
    assert events == [
        ("stop", "default", "post-index-tts2-workflow batch stop"),
    ]


@pytest.mark.asyncio
async def test_release_comfyui_after_index_tts2_workflow_keeps_service_when_disabled(
    monkeypatch,
):
    events = []

    core = PixelleVideoCore()

    async def _stop(backend_role, reason):
        events.append(("stop", backend_role, reason))
        raise AssertionError("stop_after_batch=False should keep the backend alive")

    monkeypatch.setattr(core, "_stop_after_batch_for_role", lambda backend_role: False)
    core._stop_comfyui_backend_role = _stop

    assert await core.release_comfyui_after_index_tts2_workflow(
        context="post-index-tts2-workflow",
        missing_endpoint="required",
    ) is True
    assert events == []


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
            missing_endpoint="required",
        ):
            events.append(("preflight", extensions, missing_endpoint))
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
    _patch_maintenance_client(monkeypatch, _Client)

    core = PixelleVideoCore()

    assert await core.preflight_comfyui_extension_release_endpoints(
        context="pre-index-tts2-workflow",
        extensions=("indextts2",),
    ) is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("preflight", ("indextts2",), "required"),
    ]


@pytest.mark.asyncio
async def test_prepare_comfyui_for_local_workflow_ensures_backend_then_inspects_queue(monkeypatch):
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

        async def inspect_queue_before_generation(self):
            events.append(("inspect_queue",))

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
            )
        ),
    )
    _patch_maintenance_client(monkeypatch, _Client)

    core = PixelleVideoCore()

    async def _ensure_backend(backend_role, *, reason):
        events.append(("ensure_backend", backend_role, reason))

    monkeypatch.setattr(
        core,
        "_ensure_comfyui_backend_started",
        _ensure_backend,
    )

    await core.prepare_comfyui_for_local_workflow()

    assert events == [
        ("ensure_backend", "default", "pre-workflow"),
        ("client", "http://127.0.0.1:8000", "secret", 20.0),
        ("inspect_queue",),
    ]


@pytest.mark.asyncio
async def test_force_release_comfyui_memory_waits_for_idle_queue_in_comfyui_only_mode(
    monkeypatch,
):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_when_idle(self, *, intensity="high"):
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
    _patch_maintenance_client(monkeypatch, _Client)

    core = PixelleVideoCore()

    assert await core.force_release_comfyui_memory(context="oom-recovery") is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("force_release", "high"),
    ]


@pytest.mark.asyncio
async def test_force_release_comfyui_memory_waits_for_idle_queue_with_extensions(
    monkeypatch,
):
    events = []

    class _Client:
        def __init__(self, base_url, *, api_key=None):
            events.append(("client", base_url, api_key))

        async def free_memory_with_extensions_when_idle(
            self,
            *,
            intensity="high",
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
    _patch_maintenance_client(monkeypatch, _Client)

    core = PixelleVideoCore()

    assert await core.force_release_comfyui_memory(
        context="oom-recovery",
        include_extensions=True,
    ) is True
    assert events == [
        ("client", "http://127.0.0.1:8000", "secret"),
        ("free_with_extensions", "high", ("indextts2",), "required"),
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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _release(*, backend_role="default"):
        events.append("release")

    async def _get_kit(backend_role="default"):
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

        async def _prepare(*, backend_role="default"):
            events.append((name, "prepare"))

        async def _release(*, backend_role="default"):
            events.append((name, "release"))

        async def _get_kit(backend_role="default"):
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
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_shape", ("error_result", "exception"))
async def test_core_execute_gguf_connection_loss_restarts_managed_backend_and_retries(
    monkeypatch,
    failure_shape,
):
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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _register_use(*, backend_role="default"):
        events.append("register_use")

    async def _restart(backend_role, reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(
        *,
        context,
        backend_role="default",
        extensions,
        missing_endpoint="required",
    ):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        return True

    call_count = 0

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        nonlocal call_count
        call_count += 1
        events.append(("execute_once", call_count, workflow_input))
        if call_count == 1:
            if failure_shape == "error_result":
                return SimpleNamespace(
                    status="error",
                    msg=(
                        "Cannot connect to host 127.0.0.1:8001 "
                        "ssl:default [remote computer refused the network connection]"
                    ),
                )
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
    core._restart_comfyui_backend_role = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    _install_noop_extension_preflight(core)

    result = await core.execute_comfykit_workflow(
        "selfhost/image_z_image_turbo_gguf.json",
        {},
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
        ("release_extensions", "post-gguf-workflow", ("gguf",), "required"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_shape", ("error_result", "exception"))
@pytest.mark.parametrize(
    "transient_error_message",
    (
        "GET was unable to find an engine to execute this computation",
        (
            "CUDA error: unknown error\n"
            "Search for `cudaErrorUnknown' in CUDA docs."
        ),
    ),
)
async def test_core_execute_gguf_transient_engine_failure_restarts_managed_backend_and_retries(
    monkeypatch,
    failure_shape,
    transient_error_message,
):
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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _register_use(*, backend_role="default"):
        events.append("register_use")

    async def _restart(backend_role, reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(
        *,
        context,
        backend_role="default",
        extensions,
        missing_endpoint="required",
    ):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        return True

    call_count = 0

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        nonlocal call_count
        call_count += 1
        events.append(("execute_once", call_count, workflow_input))
        if call_count == 1:
            if failure_shape == "exception":
                raise RuntimeError(transient_error_message)
            return SimpleNamespace(
                status="error",
                msg=transient_error_message,
            )
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core._register_local_comfyui_task_use = _register_use
    core._execute_local_comfykit_workflow_once = _execute_once
    core._restart_comfyui_backend_role = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    _install_noop_extension_preflight(core)

    result = await core.execute_comfykit_workflow(
        "selfhost/image_z_image_turbo_gguf.json",
        {},
        workflow_source="selfhost",
    )

    assert result.status == "completed"
    assert events == [
        "prepare",
        "register_use",
        ("execute_once", 1, "selfhost/image_z_image_turbo_gguf.json"),
        ("restart", "transient_engine_error_during_workflow"),
        "prepare",
        "register_use",
        ("execute_once", 2, "selfhost/image_z_image_turbo_gguf.json"),
        ("release_extensions", "post-gguf-workflow", ("gguf",), "required"),
    ]


@pytest.mark.asyncio
async def test_core_execute_gguf_retry_records_attempt_history_in_media_result_artifact(
    monkeypatch,
    tmp_path,
):
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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _register_use(*, backend_role="default"):
        events.append("register_use")

    async def _restart(backend_role, reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(
        *,
        context,
        backend_role="default",
        extensions,
        missing_endpoint="required",
    ):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        return True

    call_count = 0

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        nonlocal call_count
        call_count += 1
        events.append(("execute_once", call_count, workflow_input))
        if call_count == 1:
            return SimpleNamespace(
                status="error",
                msg=(
                    "CUDA error: unknown error\n"
                    "Search for `cudaErrorUnknown' in CUDA docs."
                ),
            )
        return SimpleNamespace(status="completed", images=["generated.png"])

    core.prepare_comfyui_for_local_workflow = _prepare
    core._register_local_comfyui_task_use = _register_use
    core._execute_local_comfykit_workflow_once = _execute_once
    core._restart_comfyui_backend_role = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    _install_noop_extension_preflight(core)

    workflow_params = {"prompt": "traced prompt"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "trace",
        task_id="task-gguf-retry-attempts",
        prompt="traced prompt",
        workflow="selfhost/image_z_image_turbo_gguf.json",
        workflow_input="selfhost/image_z_image_turbo_gguf.json",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    result = await core.execute_comfykit_workflow(
        "selfhost/image_z_image_turbo_gguf.json",
        workflow_params,
        workflow_source="selfhost",
        media_prompt_trace_context=trace_context,
        media_type="image",
        resolved_workflow="selfhost/image_z_image_turbo_gguf.json",
    )

    result_text = Path(trace_context["artifact_path"]).with_name(
        "media_workflow_result.md"
    ).read_text(encoding="utf-8")

    assert result.status == "completed"
    assert '"workflow_attempts"' in result_text
    assert '"reason": "transient_backend_execution_error"' in result_text
    assert '"recovery_action": "restart_backend"' in result_text
    assert '"trigger": "result"' in result_text
    assert '"trigger": "final_result"' in result_text
    assert "CUDA error: unknown error" in result_text
    assert "generated.png" in result_text


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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _restart(backend_role, reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(
        *,
        context,
        backend_role="default",
        extensions,
        missing_endpoint="required",
    ):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        return True

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        events.append(("execute_once", workflow_input))
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core._restart_comfyui_backend_role = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    core._execute_local_comfykit_workflow_once = _execute_once
    _install_noop_extension_preflight(core)

    async with core.local_comfyui_workflow_session(release_after_session=True):
        await core.execute_comfykit_workflow(
            "selfhost/image_z_image_turbo_gguf.json",
            {},
            workflow_source="selfhost",
        )

    assert events == [
        "prepare",
        ("execute_once", "selfhost/image_z_image_turbo_gguf.json"),
        ("release_extensions", "post-gguf-workflow", ("gguf",), "required"),
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

    async def _prepare(*, backend_role="default"):
        events.append("prepare")

    async def _restart(backend_role, reason):
        events.append(("restart", reason))
        return True

    async def _release_extensions(*, context, backend_role="default", extensions, missing_endpoint="required"):
        events.append(("release_extensions", context, extensions, missing_endpoint))
        core._mark_local_comfyui_released()
        return True

    async def _execute_once(workflow_input, workflow_params, *, backend_role="default"):
        events.append(("execute_once", workflow_input))
        return SimpleNamespace(status="completed")

    core.prepare_comfyui_for_local_workflow = _prepare
    core._restart_comfyui_backend_role = _restart
    core.release_comfyui_after_local_workflow_extensions = _release_extensions
    core._execute_local_comfykit_workflow_once = _execute_once
    _install_noop_extension_preflight(core)

    async with core.local_comfyui_workflow_session(release_after_session=True):
        await core.execute_comfykit_workflow(
            "selfhost/image_z_image_turbo_gguf.json",
            {},
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

    core._comfykit_by_backend["default"] = _ComfyKit()
    core._comfykit_config_hash_by_backend["default"] = "configured"
    monkeypatch.setattr(
        core,
        "_get_managed_comfyui_backend",
        lambda backend_role="default": _Backend(),
    )

    restarted = await core.restart_managed_comfyui_backend("post_gguf_workflow")

    assert restarted is True
    assert closed == ["http"]
    assert core._comfykit_by_backend == {}
    assert core._comfykit_config_hash_by_backend == {}


@pytest.mark.asyncio
async def test_restart_managed_comfyui_backend_does_not_hang_on_stale_comfykit_close(
    monkeypatch,
):
    core = PixelleVideoCore()
    core._comfykit_close_timeout_seconds = 0.01

    class _HangingExecutor:
        async def close(self):
            await asyncio.Event().wait()

    class _ComfyKit:
        _runninghub_executor = object()
        _http_executor = _HangingExecutor()
        _websocket_executor = object()

    class _Backend:
        async def restart(self, *, reason):
            return True

    core._comfykit_by_backend["default"] = _ComfyKit()
    core._comfykit_config_hash_by_backend["default"] = "configured"
    monkeypatch.setattr(
        core,
        "_get_managed_comfyui_backend",
        lambda backend_role="default": _Backend(),
    )

    restarted = await asyncio.wait_for(
        core.restart_managed_comfyui_backend("post_gguf_workflow"),
        timeout=0.5,
    )

    assert restarted is True
    assert core._comfykit_by_backend == {}
    assert core._comfykit_config_hash_by_backend == {}


@pytest.mark.asyncio
async def test_core_execute_workflow_file_resolves_runninghub_and_selfhost_inputs(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    calls = []
    core = PixelleVideoCore()

    async def _execute(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        calls.append((workflow_input, workflow_params, workflow_source, backend_role))
        return SimpleNamespace(status="completed")

    core._execute_comfykit_workflow_unchecked = _execute

    selfhost_workflow = tmp_path / "selfhost.json"
    selfhost_workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")
    await core.execute_comfykit_workflow_file(
        selfhost_workflow,
        {"prompt": "local"},
        media_prompt_trace_context=write_single_media_prompt_trace_context(
            tmp_path / "selfhost_trace",
            task_id="task-selfhost",
            prompt="local",
            workflow=str(selfhost_workflow),
            media_type="image",
            source="test",
        ),
        media_type="image",
    )

    runninghub_dir = tmp_path / "workflows" / "runninghub"
    runninghub_dir.mkdir(parents=True)
    runninghub_workflow = runninghub_dir / "image_runninghub.json"
    runninghub_workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-123",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    await core.execute_comfykit_workflow_file(
        runninghub_workflow,
        {"prompt": "cloud"},
        media_prompt_trace_context=write_single_media_prompt_trace_context(
            tmp_path / "runninghub_trace",
            task_id="task-runninghub",
            prompt="cloud",
            workflow="rh-123",
            media_type="image",
            source="test",
            generation_context={"workflow_file": str(runninghub_workflow)},
        ),
        media_type="image",
    )

    assert calls == [
        (str(selfhost_workflow), {"prompt": "local"}, "selfhost", "default"),
        ("rh-123", {"prompt": "cloud"}, "runninghub", "default"),
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_context_with_file_path(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "runninghub.json"
    workflow.write_text(
        json.dumps({"source": "runninghub", "workflow_id": "rh-123"}),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            "workflow does not match|tts_workflow_trace_context|"
            "explicit media_type|explicit domain contract"
        ),
    ):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "cloud"},
            media_prompt_trace_context=write_single_media_prompt_trace_context(
                tmp_path / "runninghub_trace",
                task_id="task-runninghub",
                prompt="cloud",
                workflow=str(workflow),
                media_type="image",
                source="test",
            ),
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_unregistered_runninghub_descriptor(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_runninghub.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-123",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "cloud"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "runninghub_trace",
        task_id="task-unregistered-runninghub",
        prompt="cloud",
        workflow="rh-image-123",
        workflow_input="rh-image-123",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    with pytest.raises(ValueError, match="packaged .* registry"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_image_prefixed_runninghub_tts_spoof(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "image_spoof.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-tts-spoof",
                "workflow_domain": "tts",
                "service_domain": "tts",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "hello"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "runninghub_trace",
        task_id="task-runninghub-image-spoof",
        prompt="hello",
        workflow="rh-tts-spoof",
        workflow_input="rh-tts-spoof",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("image-prefixed RunningHub TTS descriptor must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="tts_workflow_trace_context"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_analysis_without_service_domain(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "analyse_image.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-analysis-123",
                "workflow_domain": "image_analysis",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="explicit service_domain"):
        await core.execute_comfykit_workflow_file(workflow, {"image": "input.png"})


@pytest.mark.asyncio
async def test_core_execute_workflow_file_allows_runninghub_image_descriptor_prompt_media_trace(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    calls = []
    core = PixelleVideoCore()

    async def _execute_unchecked(
        workflow_input,
        workflow_params,
        *,
        workflow_source,
        backend_role="default",
    ):
        calls.append((workflow_input, workflow_params, workflow_source, backend_role))
        return SimpleNamespace(status="completed", images=["cloud.png"])

    core._execute_comfykit_workflow_unchecked = _execute_unchecked

    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "image_runninghub.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-123",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "cloud"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "runninghub_trace",
        task_id="task-runninghub-image",
        prompt="cloud",
        workflow="rh-image-123",
        media_type="image",
        source="test",
        generation_context={"workflow_file": str(workflow)},
        workflow_params=workflow_params,
    )

    result = await core.execute_comfykit_workflow_file(
        workflow,
        workflow_params,
        media_prompt_trace_context=trace_context,
        media_type="image",
    )

    assert result.status == "completed"
    assert calls == [
        ("rh-image-123", {"prompt": "cloud"}, "runninghub", "default")
    ]


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_media_trace_without_descriptor_hash(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "image_runninghub.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-123",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "cloud"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "runninghub_trace",
        task_id="task-runninghub-image-missing-file-trace",
        prompt="cloud",
        workflow="rh-image-123",
        workflow_input="rh-image-123",
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("RunningHub descriptor without workflow file trace must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow file trace"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_runninghub_media_type_contract_mismatch(
    monkeypatch,
    tmp_path,
):
    _use_test_runninghub_registry(monkeypatch, tmp_path)
    core = PixelleVideoCore()
    workflow_dir = tmp_path / "workflows" / "runninghub"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "image_runninghub.json"
    workflow.write_text(
        json.dumps(
            {
                "source": "runninghub",
                "workflow_id": "rh-image-123",
                "media_type": "image",
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "cloud"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "runninghub_trace",
        task_id="task-runninghub-media-mismatch",
        prompt="cloud",
        workflow="rh-image-123",
        workflow_input="rh-image-123",
        media_type="video",
        source="test",
        generation_context={"workflow_file": str(workflow)},
        workflow_params=workflow_params,
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("descriptor media_type mismatch must not execute")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="media_type does not match"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="video",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_selfhost_media_trace_for_tts_content(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_voice_spoof.json"
    workflow.write_text(
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
    workflow_params = {"prompt": "hello"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace",
        task_id="task-selfhost-tts-spoof",
        prompt="hello",
        workflow=str(workflow),
        workflow_input=str(workflow),
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )

    with pytest.raises(ValueError, match="TTS nodes"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_selfhost_prompt_literals_missing_trace_hash(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_hidden_prompt.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {
                    "inputs": {"text": "hardcoded prompt hidden in workflow"},
                    "class_type": "CLIPTextEncode",
                }
            }
        ),
        encoding="utf-8",
    )
    workflow_params = {"prompt": "runtime final prompt"}
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "media_trace_missing_literal_hash",
        task_id="task-selfhost-hidden-prompt",
        prompt="runtime final prompt",
        workflow=str(workflow),
        media_type="image",
        source="test",
        workflow_params=workflow_params,
    )
    trace_context.pop("workflow_prompt_literals", None)
    trace_context.pop("workflow_prompt_literals_sha256", None)

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("selfhost workflow prompt literals must be traced")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow_prompt_literals_sha256"):
        await core.execute_comfykit_workflow_file(
            workflow,
            workflow_params,
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_validates_prompt_trace_dimensions(tmp_path):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    with pytest.raises(ValueError, match="media_width"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "local", "width": 1024, "height": 768},
            media_prompt_trace_context=write_single_media_prompt_trace_context(
                tmp_path / "selfhost_trace",
                task_id="task-selfhost",
                prompt="local",
                workflow=str(workflow),
                media_type="image",
                source="test",
                media_width=768,
                media_height=768,
            ),
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_validates_negative_prompt_artifact(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "selfhost_trace",
        task_id="task-selfhost",
        prompt="local",
        negative_prompt="artifact negative",
        workflow=str(workflow),
        media_type="image",
        source="test",
    )
    trace_context["negative_prompt"] = "call negative"

    with pytest.raises(ValueError, match="artifact negative prompt"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "local", "negative_prompt": "call negative"},
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_validates_traced_asset_workflow_params(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("asset workflow param mismatch must be rejected")

    core.execute_comfykit_workflow = fail_if_executed
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "selfhost_trace",
        task_id="task-selfhost",
        prompt="local",
        workflow=str(workflow),
        media_type="image",
        source="test",
        generation_context={"image": "expected.png"},
        workflow_params={"prompt": "local", "image": "expected.png"},
    )

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "local", "image": "actual.png"},
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_validates_custom_text_workflow_params(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("custom text workflow param mismatch must be rejected")

    core.execute_comfykit_workflow = fail_if_executed
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "selfhost_trace",
        task_id="task-selfhost",
        prompt="local",
        workflow=str(workflow),
        media_type="image",
        source="test",
        generation_context={"goodstype": "expected product category"},
        workflow_params={
            "prompt": "local",
            "goodstype": "expected product category",
        },
    )

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "local", "goodstype": "actual product category"},
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_validates_duration_workflow_params(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("duration workflow param mismatch must be rejected")

    core.execute_comfykit_workflow = fail_if_executed
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "selfhost_trace",
        task_id="task-selfhost",
        prompt="local",
        workflow=str(workflow),
        media_type="video",
        source="test",
        generation_context={"duration": 4},
        workflow_params={"prompt": "local", "duration": 4},
    )

    with pytest.raises(ValueError, match="workflow_param_inputs"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "local", "duration": 99},
            media_prompt_trace_context=trace_context,
            media_type="video",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_mismatched_prompt_alias(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("mismatched prompt alias must be rejected")

    core.execute_comfykit_workflow = fail_if_executed
    trace_context = write_single_media_prompt_trace_context(
        tmp_path / "selfhost_trace",
        task_id="task-selfhost",
        prompt="safe prompt",
        workflow=str(workflow),
        media_type="image",
        source="test",
        workflow_params={"prompt": "safe prompt"},
    )

    with pytest.raises(ValueError, match="workflow prompt alias"):
        await core.execute_comfykit_workflow_file(
            workflow,
            {"prompt": "safe prompt", "image_prompt": "hidden prompt"},
            media_prompt_trace_context=trace_context,
            media_type="image",
        )


@pytest.mark.asyncio
async def test_core_execute_workflow_file_rejects_prompt_without_trace(tmp_path):
    core = PixelleVideoCore()
    workflow = tmp_path / "selfhost.json"
    workflow.write_text(json.dumps({"source": "selfhost"}), encoding="utf-8")

    with pytest.raises(ValueError, match="media_prompt_trace_context"):
        await core.execute_comfykit_workflow_file(workflow, {"prompt": "local"})


@pytest.mark.asyncio
async def test_core_execute_comfykit_workflow_rejects_embedded_prompt_without_trace(
    tmp_path,
):
    core = PixelleVideoCore()
    workflow = tmp_path / "image_hidden_prompt.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {
                    "inputs": {"text": "hidden hardcoded prompt"},
                    "class_type": "CLIPTextEncode",
                }
            }
        ),
        encoding="utf-8",
    )

    async def fail_if_executed(*_args, **_kwargs):
        raise AssertionError("embedded workflow prompt must not execute untraced")

    core._execute_comfykit_workflow_unchecked = fail_if_executed

    with pytest.raises(ValueError, match="workflow prompt literals"):
        await core.execute_comfykit_workflow(
            str(workflow),
            {},
            workflow_source="selfhost",
            media_type="image",
            resolved_workflow=str(workflow),
        )


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
    core._comfykit_by_backend["default"] = _ComfyKit()
    core._comfykit_config_hash_by_backend["default"] = "configured"

    await core.cleanup()

    assert closed == ["runninghub"]
    assert core._comfykit_by_backend == {}
    assert core._comfykit_config_hash_by_backend == {}


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
