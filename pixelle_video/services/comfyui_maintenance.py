from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Literal

import httpx
from loguru import logger

ComfyUICleanupMode = Literal["force", "conservative"]
ComfyUIReleaseIntensity = Literal["high", "low"]
ComfyUIExtensionName = Literal["indextts2"]
ComfyUIExtensionMissingEndpointMode = Literal["optional", "required"]
_IDLE_POLL_INTERVAL_SECONDS = 0.2


_FREE_MEMORY_PAYLOADS: dict[ComfyUIReleaseIntensity, dict[str, bool]] = {
    "high": {"unload_models": True, "free_memory": True},
    "low": {"unload_models": True, "free_memory": False},
}

_EXTENSION_RELEASE_ENDPOINTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "/pixelle/indextts2/free",
}
_EXTENSION_HEALTH_ENDPOINTS: dict[ComfyUIExtensionName, str] = {
    "indextts2": "/pixelle/indextts2/health",
}

_VRAM_RESPONSE_KEYS = (
    "cuda_allocated_before",
    "cuda_allocated_after",
    "cuda_reserved_before",
    "cuda_reserved_after",
)
_SYSTEM_VRAM_DEVICE_KEYS = (
    "name",
    "type",
    "vram_total",
    "vram_free",
    "torch_vram_total",
    "torch_vram_free",
)


@dataclass(frozen=True)
class ComfyUIExtensionReleaseResult:
    extension: str
    endpoint: str
    released: bool
    missing_endpoint: bool = False
    message: str = ""
    response: dict[str, Any] | None = None

    def to_log_dict(self) -> dict[str, Any]:
        vram = {}
        if self.response is not None:
            vram = {
                key: self.response[key]
                for key in _VRAM_RESPONSE_KEYS
                if key in self.response
            }
        return {
            "extension": self.extension,
            "endpoint": self.endpoint,
            "released": self.released,
            "missing_endpoint": self.missing_endpoint,
            "message": self.message,
            "vram": vram,
            "raw_response": self.response or {},
        }


@dataclass(frozen=True)
class ComfyUIMemoryReleaseResult:
    attempted: bool
    released: bool
    comfyui_released: bool = False
    skipped: bool = False
    skipped_reason: str = ""
    intensity: ComfyUIReleaseIntensity | None = None
    queue_running: int | None = None
    queue_pending: int | None = None
    system_vram_before: dict[str, Any] | None = None
    system_vram_after: dict[str, Any] | None = None
    extensions: tuple[ComfyUIExtensionReleaseResult, ...] = ()

    def __bool__(self) -> bool:
        return self.released

    def to_log_fields(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "released": self.released,
            "comfyui_released": self.comfyui_released,
            "skipped": self.skipped,
            "skipped_reason": self.skipped_reason,
            "intensity": self.intensity,
            "queue_running": self.queue_running,
            "queue_pending": self.queue_pending,
            "system_vram_before": self.system_vram_before,
            "system_vram_after": self.system_vram_after,
            "extension_results": [
                extension.to_log_dict()
                for extension in self.extensions
            ],
        }


class ComfyUIMaintenanceClient:
    """Small client for ComfyUI maintenance endpoints used before long renders."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        system_stats_timeout: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        idle_wait_timeout: float = 20.0,
    ) -> None:
        if idle_wait_timeout <= 0:
            raise ValueError("idle_wait_timeout must be positive")
        if system_stats_timeout <= 0:
            raise ValueError("system_stats_timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.system_stats_timeout = system_stats_timeout
        self.transport = transport
        self.idle_wait_timeout = idle_wait_timeout

    async def cleanup_before_generation(self, mode: ComfyUICleanupMode) -> None:
        if mode == "force":
            await self._force_cleanup()
            return
        if mode == "conservative":
            await self._conservative_cleanup()
            return
        raise ValueError(f"Unsupported ComfyUI cleanup mode: {mode}")

    async def _force_cleanup(self) -> None:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running == 0 and pending == 0:
            logger.info("Skipping force ComfyUI queue cleanup because queue is already idle")
            return

        logger.info(
            "Running force ComfyUI queue cleanup before video generation "
            f"(running={running}, pending={pending})"
        )
        await self._post("/interrupt", {})
        await self._post("/queue", {"clear": True})
        await self._wait_until_idle()

    async def _conservative_cleanup(self) -> None:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping conservative ComfyUI cleanup because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return

        logger.info("Skipping conservative ComfyUI cleanup because queue is already idle")

    async def free_memory(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
    ) -> ComfyUIMemoryReleaseResult:
        payload = _FREE_MEMORY_PAYLOADS.get(intensity)
        if payload is None:
            raise ValueError(f"Unsupported ComfyUI release intensity: {intensity}")
        system_vram_before = await self._get_system_vram_snapshot()
        await self._post("/free", dict(payload))
        system_vram_after = await self._get_system_vram_snapshot()
        return ComfyUIMemoryReleaseResult(
            attempted=True,
            released=True,
            comfyui_released=True,
            intensity=intensity,
            system_vram_before=system_vram_before,
            system_vram_after=system_vram_after,
        )

    async def free_memory_with_extensions(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        result = await self.free_memory(intensity)
        extension_results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return replace(
            result,
            released=result.released or any(extension.released for extension in extension_results),
            extensions=extension_results,
        )

    async def free_memory_with_extensions_when_idle(
        self,
        *,
        intensity: ComfyUIReleaseIntensity = "high",
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI memory and extension release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                intensity=intensity,
                queue_running=running,
                queue_pending=pending,
            )

        logger.info(
            "Releasing ComfyUI memory and extension caches after idle workflow "
            f"completion ({intensity})"
        )
        result = await self.free_memory_with_extensions(
            intensity,
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return replace(result, queue_running=running, queue_pending=pending)

    async def preflight_extension_release_endpoints(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        results: list[ComfyUIExtensionReleaseResult] = []
        for extension in extensions:
            endpoint = _EXTENSION_HEALTH_ENDPOINTS[extension]
            try:
                response = await self._request("GET", endpoint)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    message = (
                        f"ComfyUI extension health endpoint {endpoint} is missing. "
                        "Run tools/patch_indextts2_plugin.py against ComfyUI-Index-TTS, "
                        "then restart ComfyUI."
                    )
                    raise RuntimeError(message) from exc
                raise

            payload = response.json()
            data = payload if isinstance(payload, dict) else {}
            results.append(
                ComfyUIExtensionReleaseResult(
                    extension=extension,
                    endpoint=endpoint,
                    released=False,
                    response=data,
                )
            )
        return tuple(results)

    async def free_extension_models(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> tuple[ComfyUIExtensionReleaseResult, ...]:
        results: list[ComfyUIExtensionReleaseResult] = []
        for extension in extensions:
            endpoint = _EXTENSION_RELEASE_ENDPOINTS[extension]
            try:
                response = await self._request("POST", endpoint, json={})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    message = (
                        f"ComfyUI extension cleanup endpoint {endpoint} is missing. "
                        "Run tools/patch_indextts2_plugin.py against ComfyUI-Index-TTS, "
                        "then restart ComfyUI."
                    )
                    if missing_endpoint == "optional":
                        logger.warning(message)
                        results.append(
                            ComfyUIExtensionReleaseResult(
                                extension=extension,
                                endpoint=endpoint,
                                released=False,
                                missing_endpoint=True,
                                message=message,
                            )
                        )
                        continue
                    raise RuntimeError(message) from exc
                raise

            payload = response.json()
            data = payload if isinstance(payload, dict) else {}
            results.append(
                ComfyUIExtensionReleaseResult(
                    extension=extension,
                    endpoint=endpoint,
                    released=bool(data.get("released")),
                    response=data,
                )
            )
        return tuple(results)

    async def free_extension_models_when_idle(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI extension memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                queue_running=running,
                queue_pending=pending,
            )

        results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return ComfyUIMemoryReleaseResult(
            attempted=True,
            released=any(result.released for result in results),
            queue_running=running,
            queue_pending=pending,
            extensions=results,
        )

    async def free_memory_when_idle(
        self,
        *,
        intensity: ComfyUIReleaseIntensity = "high",
    ) -> ComfyUIMemoryReleaseResult:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return ComfyUIMemoryReleaseResult(
                attempted=False,
                released=False,
                skipped=True,
                skipped_reason="queue_busy",
                intensity=intensity,
                queue_running=running,
                queue_pending=pending,
            )

        logger.info(f"Releasing ComfyUI memory after idle workflow completion ({intensity})")
        result = await self.free_memory(intensity)
        return replace(result, queue_running=running, queue_pending=pending)

    async def _get_queue(self) -> dict:
        response = await self._request("GET", "/queue")
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def _get_system_vram_snapshot(self) -> dict[str, Any] | None:
        try:
            response = await self._request(
                "GET",
                "/system_stats",
                timeout=self.system_stats_timeout,
            )
            data = response.json()
        except Exception as exc:
            logger.debug(f"Skipping ComfyUI system VRAM snapshot: {exc}")
            return None
        return self._extract_system_vram_snapshot(data)

    def _extract_system_vram_snapshot(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        devices = data.get("devices")
        if not isinstance(devices, list):
            return None

        normalized_devices = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            normalized = {
                key: device[key]
                for key in _SYSTEM_VRAM_DEVICE_KEYS
                if key in device
            }
            if normalized:
                normalized_devices.append(normalized)

        if not normalized_devices:
            return None
        return {"devices": normalized_devices}

    async def _wait_until_idle(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.idle_wait_timeout
        while True:
            queue = await self._get_queue()
            running, pending = self._queue_counts(queue)
            if running == 0 and pending == 0:
                return
            if loop.time() >= deadline:
                raise TimeoutError(
                    "Timed out waiting for ComfyUI queue to become idle after "
                    f"{self.idle_wait_timeout:g}s (running={running}, pending={pending}). "
                    "Check the ComfyUI queue for a stuck prompt before retrying."
                )
            await asyncio.sleep(_IDLE_POLL_INTERVAL_SECONDS)

    def _queue_counts(self, queue: dict) -> tuple[int, int]:
        running = queue.get("queue_running") or []
        pending = queue.get("queue_pending") or []
        return len(running), len(pending)

    async def _post(self, path: str, payload: dict) -> None:
        await self._request("POST", path, json=payload)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        timeout = httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0))
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
