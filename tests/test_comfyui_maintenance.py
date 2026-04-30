import json

import httpx
import pytest

from pixelle_video.services import comfyui_maintenance as maintenance_module
from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, queue_payload=None, queue_payloads=None):
        self.calls = []
        self.queue_payload = queue_payload or {"queue_running": [], "queue_pending": []}
        self.queue_payloads = list(queue_payloads or [])

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((request.method, request.url.path, payload))
        if request.url.path == "/queue" and request.method == "GET":
            if self.queue_payloads:
                return httpx.Response(200, json=self.queue_payloads.pop(0), request=request)
            return httpx.Response(200, json=self.queue_payload, request=request)
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

    assert released is True
    assert transport.calls == [
        ("GET", "/queue", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
    ]


@pytest.mark.asyncio
async def test_free_memory_when_idle_supports_low_intensity_release():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle(intensity="low")

    assert released is True
    assert transport.calls == [
        ("GET", "/queue", None),
        ("POST", "/free", {"unload_models": True, "free_memory": False}),
    ]


@pytest.mark.asyncio
async def test_free_memory_when_idle_skips_when_queue_is_busy():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [], "queue_pending": [["pending"]]}
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle()

    assert released is False
    assert transport.calls == [("GET", "/queue", None)]
