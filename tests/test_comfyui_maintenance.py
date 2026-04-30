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

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((request.method, request.url.path, payload))
        if request.url.path == "/queue" and request.method == "GET":
            if self.queue_payloads:
                return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
            return httpx.Response(200, json=self.queue_payload, request=request)
        if request.url.path == "/system_stats" and request.method == "GET":
            payload = self.system_stats_payloads.pop(0) if self.system_stats_payloads else {}
            return httpx.Response(200, json=payload, request=request)
        if request.url.path == "/pixelle/indextts2/free":
            return httpx.Response(
                200,
                json={
                    "released": True,
                    "loaders_seen": 1,
                    "loaders_released": 1,
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
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/indextts2/free", {}),
    ]


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

    assert result.released is True
    assert result.comfyui_released is True
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
            "missing_endpoint": False,
            "message": "",
            "vram": {
                "cuda_allocated_before": 2048,
                "cuda_allocated_after": 512,
                "cuda_reserved_before": 4096,
                "cuda_reserved_after": 1024,
            },
            "raw_response": {
                "released": True,
                "loaders_seen": 1,
                "loaders_released": 1,
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
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
        ("GET", "/system_stats", None),
        ("POST", "/pixelle/indextts2/free", {}),
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
async def test_preflight_extension_release_endpoints_fails_fast_when_required_endpoint_is_missing():
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

    with pytest.raises(RuntimeError, match="tools/patch_indextts2_plugin.py"):
        await client.preflight_extension_release_endpoints(extensions=("indextts2",))

    assert transport.calls == [("POST", "/pixelle/indextts2/free", {})]


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
