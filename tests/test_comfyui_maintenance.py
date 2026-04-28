import json

import httpx
import pytest

from pixelle_video.services.comfyui_maintenance import ComfyUIMaintenanceClient


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, queue_payload=None):
        self.calls = []
        self.queue_payload = queue_payload or {"queue_running": [], "queue_pending": []}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append((request.method, request.url.path, payload))
        if request.url.path == "/queue" and request.method == "GET":
            return httpx.Response(200, json=self.queue_payload, request=request)
        return httpx.Response(200, request=request)


@pytest.mark.asyncio
async def test_force_cleanup_interrupts_clears_queue_and_frees_memory():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    await client.cleanup_before_generation("force")

    assert transport.calls == [
        ("POST", "/interrupt", {}),
        ("POST", "/queue", {"clear": True}),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
    ]


@pytest.mark.asyncio
async def test_conservative_cleanup_frees_memory_only_when_queue_is_idle():
    transport = _RecordingTransport()
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    await client.cleanup_before_generation("conservative")

    assert transport.calls == [
        ("GET", "/queue", None),
        ("POST", "/free", {"unload_models": True, "free_memory": True}),
    ]


@pytest.mark.asyncio
async def test_conservative_cleanup_skips_free_when_queue_is_busy():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [["running"]], "queue_pending": []}
    )
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
async def test_free_memory_when_idle_skips_when_queue_is_busy():
    transport = _RecordingTransport(
        queue_payload={"queue_running": [], "queue_pending": [["pending"]]}
    )
    client = ComfyUIMaintenanceClient("http://127.0.0.1:8000", transport=transport)

    released = await client.free_memory_when_idle()

    assert released is False
    assert transport.calls == [("GET", "/queue", None)]
