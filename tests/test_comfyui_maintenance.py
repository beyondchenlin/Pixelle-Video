import json

import httpx
import pytest

from pixelle_video.services import comfyui_maintenance as maintenance_module
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, queue_payload=None, queue_payloads=None, system_stats_payloads=None):
        self.calls = []
        self.queue_payload = queue_payload or {"queue_running": [], "queue_pending": []}
        self.queue_payloads = list(queue_payloads or [])
        self.system_stats_payloads = list(
            system_stats_payloads
            or [
                {
                    "devices": [
                        {
                            "name": "NVIDIA",
                            "type": "cuda",
                            "vram_total": 8192,
                            "vram_free": 4096,
                            "torch_vram_total": 4096,
                            "torch_vram_free": 2048,
                        }
                    ]
                },
                {
                    "devices": [
                        {
                            "name": "NVIDIA",
                            "type": "cuda",
                            "vram_total": 8192,
                            "vram_free": 6144,
                            "torch_vram_total": 4096,
                            "torch_vram_free": 3072,
                        }
                    ]
                },
            ]
        )
        self.last_system_stats_payload = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((request.method, request.url.path, payload))
        if request.url.path == "/queue" and request.method == "GET":
            if self.queue_payloads:
                return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
            return httpx.Response(200, json=self.queue_payload, request=request)
        if request.url.path == "/system_stats" and request.method == "GET":
            if self.system_stats_payloads:
                payload = self.system_stats_payloads.pop(0)
                self.last_system_stats_payload = payload
            else:
                payload = self.last_system_stats_payload or {}
            return httpx.Response(200, json=payload, request=request)
        if request.url.path == "/pixelle/indextts2/health":
            return httpx.Response(
                200,
                json={
                    "protocol_version": 2,
                    "ok": True,
                    "extension": "indextts2",
                    "release_endpoint": "/pixelle/indextts2/free",
                    "loaders_seen": 1,
                    "safe_to_continue": True,
                    "residual_objects": [],
                },
                request=request,
            )
        if request.url.path == "/pixelle/indextts2/free":
            return httpx.Response(
                200,
                json={
                    "protocol_version": 2,
                    "safe_to_continue": True,
                    "released": True,
                    "loaders_seen": 1,
                    "loaders_released": 1,
                    "objects_seen": ["tts"],
                    "objects_released": ["tts"],
                    "residual_objects": [],
                    "cuda_allocated_before": 2048,
                    "cuda_allocated_after": 512,
                    "cuda_reserved_before": 4096,
                    "cuda_reserved_after": 1024,
                },
                request=request,
            )
        return httpx.Response(200, request=request)


@pytest.mark.asyncio
async def test_force_cleanup_is_noop_when_queue_is_idle():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    await client.cleanup_before_generation("force")

    assert transport.calls == [
        ("GET", "/queue", None),
    ]


@pytest.mark.asyncio
async def test_force_cleanup_interrupts_busy_queue_and_waits_for_idle():
    transport = _RecordingTransport(
        queue_payloads=[
            {"queue_running": [["running"]], "queue_pending": [["pending"]]},
            {"queue_running": [], "queue_pending": []},
        ]
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    await client.cleanup_before_generation("force")

    assert transport.calls == [
        ("GET", "/queue", None),
        ("POST", "/interrupt", {}),
        ("POST", "/queue", {"clear": True}),
        ("GET", "/queue", None),
    ]


@pytest.mark.asyncio
async def test_force_cleanup_times_out_when_queue_never_goes_idle(monkeypatch):
    transport = _RecordingTransport(
        queue_payload={"queue_running": [["running"]], "queue_pending": []}
    )
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        idle_wait_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    with pytest.raises(TimeoutError, match="Timed out waiting for ComfyUI queue to become idle"):
        await client.cleanup_before_generation("force")

    assert transport.calls[:3] == [
        ("GET", "/queue", None),
        ("POST", "/interrupt", {}),
        ("POST", "/queue", {"clear": True}),
    ]
    assert len(transport.calls) > 3
    assert all(call[:2] == ("GET", "/queue") for call in transport.calls[3:])


@pytest.mark.asyncio
async def test_conservative_cleanup_noops_when_queue_is_idle():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    await client.cleanup_before_generation("conservative")

    assert transport.calls == [("GET", "/queue", None)]


@pytest.mark.asyncio
async def test_free_memory_when_idle_checks_queue_before_freeing():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle()

    assert released.released is True
    assert released.comfyui_released is True
    assert released.queue_running == 0
    assert released.queue_pending == 0
    assert released.system_vram_before == {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 4096,
                "torch_vram_total": 4096,
                "torch_vram_free": 2048,
            }
        ]
    }
    assert released.system_vram_after == {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 6144,
                "torch_vram_total": 4096,
                "torch_vram_free": 3072,
            }
        ]
    }
    assert transport.calls == [
        ("GET", "/queue", None),
        ("GET", "/system_stats", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_waits_until_comfyui_applies_free_flag_before_confirming(monkeypatch):
    transport = _RecordingTransport(
        system_stats_payloads=[
            {
                "devices": [
                    {
                        "name": "NVIDIA",
                        "type": "cuda",
                        "vram_total": 8192,
                        "vram_free": 1024,
                        "torch_vram_total": 8192,
                        "torch_vram_free": 64,
                    }
                ]
            },
            {
                "devices": [
                    {
                        "name": "NVIDIA",
                        "type": "cuda",
                        "vram_total": 8192,
                        "vram_free": 1024,
                        "torch_vram_total": 8192,
                        "torch_vram_free": 64,
                    }
                ]
            },
            {
                "devices": [
                    {
                        "name": "NVIDIA",
                        "type": "cuda",
                        "vram_total": 8192,
                        "vram_free": 7168,
                        "torch_vram_total": 1024,
                        "torch_vram_free": 896,
                    }
                ]
            },
        ]
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory("high")

    assert result.released is True
    assert result.comfyui_released is True
    assert result.system_vram_after == {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 7168,
                "torch_vram_total": 1024,
                "torch_vram_free": 896,
            }
        ]
    }
    assert transport.calls == [
        ("GET", "/system_stats", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_reports_unconfirmed_when_busy_vram_never_drops(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }
    transport = _RecordingTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory("high")

    assert result.released is False
    assert result.comfyui_released is False
    assert result.system_vram_after == unchanged_snapshot
    assert transport.calls[:3] == [
        ("GET", "/system_stats", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_when_idle_supports_low_intensity_release():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle(intensity="low")

    assert released.released is True
    assert released.comfyui_released is True
    assert released.intensity == "low"
    assert transport.calls == [
        ("GET", "/queue", None),
        ("GET", "/system_stats", None),
        ("POST", "/free", {"unload_models": True, "free_memory": False}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_when_idle_skips_when_queue_is_busy():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [], "queue_pending": [["pending"]]}
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle()

    assert released.released is False
    assert released.skipped is True
    assert released.skipped_reason == "queue_busy"
    assert transport.calls == [("GET", "/queue", None)]


@pytest.mark.asyncio
async def test_free_memory_with_extensions_calls_comfyui_free_then_indextts2_endpoint():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    result = await client.free_memory_with_extensions("high", extensions=("indextts2",))

    assert result.released is True
    assert result.comfyui_released is True
    assert [extension.extension for extension in result.extensions] == ["indextts2"]
    assert result.extensions[0].released is True
    assert transport.calls == [
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/indextts2/free", {}),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_with_extensions_accepts_extension_safe_to_continue_when_vram_does_not_drop(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _SafeExtensionTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/queue" and request.method == "GET":
                if self.queue_payloads:
                    return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
                return httpx.Response(200, json=self.queue_payload, request=request)
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "safe_to_continue": True,
                        "released": False,
                        "loaders_seen": 1,
                        "loaders_released": 0,
                        "objects_seen": [],
                        "objects_released": [],
                        "residual_objects": [],
                        "errors": [],
                        "cuda_allocated_before": 2048,
                        "cuda_allocated_after": 2048,
                        "cuda_reserved_before": 4096,
                        "cuda_reserved_after": 4096,
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _SafeExtensionTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions(
        "high",
        extensions=("indextts2",),
    )

    assert result.comfyui_released is False
    assert result.extensions[0].released is False
    assert result.extensions[0].safe_to_continue is True
    assert result.released is True
    assert result.safe_to_continue is True
    assert result.release_confirmation_reason == "extension_safe_to_continue"
    assert transport.calls[:3] == [
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/indextts2/free", {}),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
    ]


@pytest.mark.asyncio
async def test_free_memory_with_gguf_extension_accepts_safe_to_continue_when_vram_does_not_drop(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _SafeGGUFExtensionTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/gguf/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "contract_revision": 2,
                        "safe_to_continue": True,
                        "released": True,
                        "objects_seen": ["gguf_model", "gguf_clip"],
                        "objects_released": ["gguf_model", "gguf_clip"],
                        "residual_objects": [],
                        "errors": [],
                        "cuda_allocated_before": 2048,
                        "cuda_allocated_after": 2048,
                        "cuda_reserved_before": 4096,
                        "cuda_reserved_after": 4096,
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _SafeGGUFExtensionTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions(
        "high",
        extensions=("gguf",),
    )

    assert result.comfyui_released is False
    assert result.extensions[0].extension == "gguf"
    assert result.extensions[0].safe_to_continue is True
    assert result.extensions[0].contract_revision == 2
    assert result.released is True
    assert result.safe_to_continue is True
    assert result.release_confirmation_reason == "extension_safe_to_continue"
    assert transport.calls[:3] == [
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/gguf/free", {}),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
    ]


@pytest.mark.asyncio
async def test_free_memory_with_gguf_extension_treats_residual_objects_as_diagnostics_when_safe(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _SafeGGUFResidualTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/gguf/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "contract_revision": 2,
                        "extension": "gguf",
                        "released": True,
                        "safe_to_continue": True,
                        "objects_seen": ["GGUFModelPatcher"],
                        "objects_released": [],
                        "residual_objects": ["GGUFModelPatcher"],
                        "errors": [],
                        "cuda_allocated_before": 7_977_325_732,
                        "cuda_allocated_after": 9_568_256,
                        "cuda_reserved_before": 7_985_954_816,
                        "cuda_reserved_after": 100_663_296,
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _SafeGGUFResidualTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions("high", extensions=("gguf",))

    assert result.comfyui_released is False
    assert result.extensions[0].safe_to_continue is True
    assert result.extensions[0].contract_revision == 2
    assert result.released is True
    assert result.safe_to_continue is True
    assert result.release_confirmation_reason == "extension_safe_to_continue"
    assert result.extensions[0].response["residual_objects"] == ["GGUFModelPatcher"]


@pytest.mark.asyncio
async def test_free_memory_with_gguf_extension_rejects_stale_contract_revision(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _StaleGGUFContractTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/gguf/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "safe_to_continue": True,
                        "released": True,
                        "residual_objects": [],
                        "errors": [],
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _StaleGGUFContractTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions("high", extensions=("gguf",))

    assert result.comfyui_released is False
    assert result.extensions[0].safe_to_continue is False
    assert result.extensions[0].contract_revision is None
    assert result.released is False
    assert result.safe_to_continue is False
    assert result.release_confirmation_reason == "extension_contract_revision_unconfirmed"


@pytest.mark.asyncio
async def test_free_memory_with_extension_keeps_success_when_system_stats_disappear_after_free():
    class _StatsDisappearAfterFreeTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if not any(call[:2] == ("POST", "/free") for call in self.calls):
                    return httpx.Response(
                        200,
                        json={
                            "devices": [
                                {
                                    "name": "NVIDIA",
                                    "type": "cuda",
                                    "vram_total": 8192,
                                    "vram_free": 1024,
                                    "torch_vram_total": 8192,
                                    "torch_vram_free": 64,
                                }
                            ]
                        },
                        request=request,
                    )
                return httpx.Response(503, request=request)
            if request.url.path == "/pixelle/gguf/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "contract_revision": 2,
                        "safe_to_continue": True,
                        "released": True,
                        "residual_objects": [],
                        "errors": [],
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _StatsDisappearAfterFreeTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    result = await client.free_memory_with_extensions("high", extensions=("gguf",))

    assert result.comfyui_released is False
    assert result.released is True
    assert result.safe_to_continue is True
    assert result.release_confirmation_reason == "extension_safe_to_continue"


@pytest.mark.asyncio
async def test_free_memory_with_extensions_stops_when_extension_reports_residual_objects(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _UnsafeExtensionTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/queue" and request.method == "GET":
                if self.queue_payloads:
                    return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
                return httpx.Response(200, json=self.queue_payload, request=request)
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "safe_to_continue": False,
                        "released": False,
                        "loaders_seen": 1,
                        "loaders_released": 0,
                        "objects_seen": ["tts"],
                        "objects_released": [],
                        "residual_objects": ["tts"],
                        "errors": [],
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _UnsafeExtensionTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions(
        "high",
        extensions=("indextts2",),
    )

    assert result.comfyui_released is False
    assert result.extensions[0].safe_to_continue is False
    assert result.released is False
    assert result.safe_to_continue is False
    assert result.release_confirmation_reason == "extension_residual_objects"


@pytest.mark.asyncio
async def test_free_memory_with_extensions_rejects_legacy_extension_contract_when_comfyui_vram_does_not_drop(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _LegacyExtensionTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(
                    200,
                    json={
                        "released": False,
                        "loaders_seen": 1,
                        "loaders_released": 0,
                        "errors": [],
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _LegacyExtensionTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions(
        "high",
        extensions=("indextts2",),
    )

    assert result.comfyui_released is False
    assert result.extensions[0].protocol_version is None
    assert result.extensions[0].safe_to_continue is False
    assert result.released is False
    assert result.release_confirmation_reason == "extension_legacy_contract_unconfirmed"


@pytest.mark.asyncio
async def test_free_memory_with_extensions_rejects_legacy_extension_contract_even_when_released_true(monkeypatch):
    unchanged_snapshot = {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_total": 8192,
                "vram_free": 1024,
                "torch_vram_total": 8192,
                "torch_vram_free": 64,
            }
        ]
    }

    class _LegacyReleasedTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats" and request.method == "GET":
                if self.system_stats_payloads:
                    payload = self.system_stats_payloads.pop(0)
                    self.last_system_stats_payload = payload
                else:
                    payload = self.last_system_stats_payload or {}
                return httpx.Response(200, json=payload, request=request)
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(
                    200,
                    json={
                        "released": True,
                        "loaders_seen": 1,
                        "loaders_released": 1,
                        "errors": [],
                    },
                    request=request,
                )
            return await super().handle_async_request(request)

    transport = _LegacyReleasedTransport(system_stats_payloads=[unchanged_snapshot] * 10)
    client = ComfyUIMaintenanceClient(
        "http://127.0.0.1:8000",
        transport=transport,
        release_settle_timeout=0.01,
    )

    async def _immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(maintenance_module.asyncio, "sleep", _immediate_sleep)

    result = await client.free_memory_with_extensions(
        "high",
        extensions=("indextts2",),
    )

    assert result.comfyui_released is False
    assert result.extensions[0].released is True
    assert result.extensions[0].protocol_version is None
    assert result.extensions[0].safe_to_continue is False
    assert result.released is False
    assert result.safe_to_continue is False
    assert result.release_confirmation_reason == "extension_legacy_contract_unconfirmed"


@pytest.mark.asyncio
async def test_free_memory_keeps_release_success_when_system_stats_are_unavailable():
    class _NoSystemStatsTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/system_stats":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _NoSystemStatsTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    result = await client.free_memory("high")

    assert result.released is False
    assert result.comfyui_released is False
    assert result.release_confirmation_reason == "system_stats_unavailable"
    assert result.system_vram_before is None
    assert result.system_vram_after is None
    assert transport.calls == [
        ("GET", "/system_stats", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_with_extensions_preserves_extension_vram_snapshots():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    result = await client.free_memory_with_extensions("high", extensions=("indextts2",))

    log_fields = result.to_log_fields()
    assert log_fields["released"] is True
    assert log_fields["comfyui_released"] is True
    assert log_fields["system_vram_before"]["devices"][0]["vram_free"] == 4096
    assert log_fields["system_vram_after"]["devices"][0]["vram_free"] == 6144
    assert log_fields["extension_results"] == [
        {
            "extension": "indextts2",
            "endpoint": "/pixelle/indextts2/free",
            "released": True,
            "safe_to_continue": True,
            "protocol_version": 2,
            "contract_revision": None,
            "missing_endpoint": False,
            "message": "",
            "vram": {
                "cuda_allocated_before": 2048,
                "cuda_allocated_after": 512,
                "cuda_reserved_before": 4096,
                "cuda_reserved_after": 1024,
            },
            "raw_response": {
                "protocol_version": 2,
                "safe_to_continue": True,
                "released": True,
                "loaders_seen": 1,
                "loaders_released": 1,
                "objects_seen": ["tts"],
                "objects_released": ["tts"],
                "residual_objects": [],
                "cuda_allocated_before": 2048,
                "cuda_allocated_after": 512,
                "cuda_reserved_before": 4096,
                "cuda_reserved_after": 1024,
            },
        }
    ]


@pytest.mark.asyncio
async def test_free_memory_with_extensions_when_idle_checks_queue_before_release():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_with_extensions_when_idle(
        intensity="high",
        extensions=("indextts2",),
    )

    assert released.released is True
    assert released.skipped is False
    assert released.queue_running == 0
    assert released.queue_pending == 0
    assert transport.calls == [
        ("GET", "/queue", None),
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/indextts2/free", {}),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
    ]


@pytest.mark.asyncio
async def test_free_memory_with_extensions_when_idle_skips_busy_queue():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [["running"]], "queue_pending": []}
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_with_extensions_when_idle(
        intensity="high",
        extensions=("indextts2",),
    )

    assert released.released is False
    assert released.skipped is True
    assert released.skipped_reason == "queue_busy"
    assert released.queue_running == 1
    assert released.queue_pending == 0
    assert transport.calls == [("GET", "/queue", None)]


@pytest.mark.asyncio
async def test_free_extension_models_treats_missing_optional_endpoint_as_warning():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    results = await client.free_extension_models(
        extensions=("indextts2",),
        missing_endpoint="optional",
    )

    assert results[0].extension == "indextts2"
    assert results[0].released is False
    assert results[0].missing_endpoint is True
    assert "tools/patch_indextts2_plugin.py" in results[0].message


@pytest.mark.asyncio
async def test_free_extension_models_raises_when_required_endpoint_is_missing():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/free":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="/pixelle/indextts2/free"):
        await client.free_extension_models(
            extensions=("indextts2",),
            missing_endpoint="required",
        )


@pytest.mark.asyncio
async def test_free_gguf_extension_models_missing_endpoint_points_to_gguf_patch_script():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/gguf/free":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="tools/patch_gguf_plugin.py"):
        await client.free_extension_models(
            extensions=("gguf",),
            missing_endpoint="required",
        )

    assert transport.calls == [("POST", "/pixelle/gguf/free", {})]


@pytest.mark.asyncio
async def test_preflight_extension_release_endpoints_fails_fast_when_required_endpoint_is_missing():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/health":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="tools/patch_indextts2_plugin.py"):
        await client.preflight_extension_release_endpoints(extensions=("indextts2",))

    assert transport.calls == [("GET", "/pixelle/indextts2/health", None)]


@pytest.mark.asyncio
async def test_preflight_gguf_extension_release_endpoints_points_to_gguf_patch_script():
    class _MissingEndpointTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/gguf/health":
                return httpx.Response(404, request=request)
            return httpx.Response(200, request=request)

    transport = _MissingEndpointTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="tools/patch_gguf_plugin.py"):
        await client.preflight_extension_release_endpoints(extensions=("gguf",))

    assert transport.calls == [("GET", "/pixelle/gguf/health", None)]


@pytest.mark.asyncio
async def test_preflight_extension_release_endpoints_requires_protocol_v2():
    class _LegacyHealthTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/indextts2/health":
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "extension": "indextts2",
                        "release_endpoint": "/pixelle/indextts2/free",
                        "loaders_seen": 1,
                    },
                    request=request,
                )
            return httpx.Response(200, request=request)

    transport = _LegacyHealthTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="release protocol v2"):
        await client.preflight_extension_release_endpoints(extensions=("indextts2",))

    assert transport.calls == [("GET", "/pixelle/indextts2/health", None)]


@pytest.mark.asyncio
async def test_preflight_gguf_extension_release_endpoints_requires_current_contract_revision():
    class _LegacyGGUFHealthTransport(_RecordingTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = await request.aread()
            payload = json.loads(body.decode("utf-8")) if body else None
            self.calls.append((request.method, request.url.path, payload))
            if request.url.path == "/pixelle/gguf/health":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "ok": True,
                        "extension": "gguf",
                        "release_endpoint": "/pixelle/gguf/free",
                        "safe_to_continue": True,
                        "residual_objects": [],
                    },
                    request=request,
                )
            return httpx.Response(200, request=request)

    transport = _LegacyGGUFHealthTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    with pytest.raises(RuntimeError, match="contract revision"):
        await client.preflight_extension_release_endpoints(extensions=("gguf",))

    assert transport.calls == [("GET", "/pixelle/gguf/health", None)]


@pytest.mark.asyncio
async def test_preflight_extension_release_endpoints_uses_side_effect_free_health_endpoint():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    results = await client.preflight_extension_release_endpoints(extensions=("indextts2",))

    assert results[0].extension == "indextts2"
    assert results[0].endpoint == "/pixelle/indextts2/health"
    assert results[0].released is False
    assert results[0].response == {
        "protocol_version": 2,
        "ok": True,
        "extension": "indextts2",
        "release_endpoint": "/pixelle/indextts2/free",
        "loaders_seen": 1,
        "safe_to_continue": True,
        "residual_objects": [],
    }
    assert transport.calls == [("GET", "/pixelle/indextts2/health", None)]


@pytest.mark.asyncio
async def test_system_vram_snapshot_uses_short_timeout():
    calls = []

    class _Client(ComfyUIMaintenanceClient):
        async def _request(self, method, path, **kwargs):
            calls.append((method, path, kwargs.get("timeout")))
            return httpx.Response(
                200,
                json={
                    "devices": [
                        {
                            "name": "NVIDIA",
                            "type": "cuda",
                            "vram_free": 4096,
                        }
                    ]
                },
                request=httpx.Request(method, f"http://127.0.0.1:8000{path}"),
            )

    client = _Client("http://127.0.0.1:8000", system_stats_timeout=0.25)

    snapshot = await client._get_system_vram_snapshot()

    assert snapshot == {
        "devices": [
            {
                "name": "NVIDIA",
                "type": "cuda",
                "vram_free": 4096,
            }
        ]
    }
    assert calls == [("GET", "/system_stats", 0.25)]


@pytest.mark.asyncio
async def test_free_extension_models_uses_release_request_timeout():
    calls = []

    class _Client(ComfyUIMaintenanceClient):
        async def _request(self, method, path, **kwargs):
            calls.append((method, path, kwargs.get("timeout")))
            if path == "/pixelle/gguf/free":
                return httpx.Response(
                    200,
                    json={
                        "protocol_version": 2,
                        "contract_revision": 2,
                        "safe_to_continue": True,
                        "released": True,
                        "residual_objects": [],
                        "errors": [],
                    },
                    request=httpx.Request(method, f"http://127.0.0.1:8000{path}"),
                )
            return httpx.Response(
                200,
                json={},
                request=httpx.Request(method, f"http://127.0.0.1:8000{path}"),
            )

    client = _Client(
        "http://127.0.0.1:8000",
        release_request_timeout=45.0,
    )

    result = await client.free_extension_models(extensions=("gguf",))

    assert result[0].safe_to_continue is True
    assert result[0].contract_revision == 2
    assert calls == [("POST", "/pixelle/gguf/free", 45.0)]


@pytest.mark.asyncio
async def test_free_extension_models_when_idle_skips_busy_queue():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [["running"]], "queue_pending": []}
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_extension_models_when_idle(extensions=("indextts2",))

    assert released.released is False
    assert released.skipped is True
    assert released.skipped_reason == "queue_busy"
    assert transport.calls == [("GET", "/queue", None)]
