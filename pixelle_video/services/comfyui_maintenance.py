from __future__ import annotations

import asyncio
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ComfyUIExtensionReleaseResult:
    extension: str
    released: bool
    missing_endpoint: bool = False
    message: str = ""
    response: dict[str, Any] | None = None


class ComfyUIMaintenanceClient:
    """Small client for ComfyUI maintenance endpoints used before long renders."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        idle_wait_timeout: float = 20.0,
    ) -> None:
        if idle_wait_timeout <= 0:
            raise ValueError("idle_wait_timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
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

    async def free_memory(self, intensity: ComfyUIReleaseIntensity = "high") -> None:
        payload = _FREE_MEMORY_PAYLOADS.get(intensity)
        if payload is None:
            raise ValueError(f"Unsupported ComfyUI release intensity: {intensity}")
        await self._post("/free", dict(payload))

    async def free_memory_with_extensions(
        self,
        intensity: ComfyUIReleaseIntensity = "high",
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> list[ComfyUIExtensionReleaseResult]:
        await self.free_memory(intensity)
        return await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )

    async def free_extension_models(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> list[ComfyUIExtensionReleaseResult]:
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
                    released=bool(data.get("released")),
                    response=data,
                )
            )
        return results

    async def free_extension_models_when_idle(
        self,
        *,
        extensions: tuple[ComfyUIExtensionName, ...] = ("indextts2",),
        missing_endpoint: ComfyUIExtensionMissingEndpointMode = "optional",
    ) -> bool:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI extension memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return False

        results = await self.free_extension_models(
            extensions=extensions,
            missing_endpoint=missing_endpoint,
        )
        return any(result.released for result in results)

    async def free_memory_when_idle(
        self,
        *,
        intensity: ComfyUIReleaseIntensity = "high",
    ) -> bool:
        queue = await self._get_queue()
        running, pending = self._queue_counts(queue)
        if running or pending:
            logger.info(
                "Skipping ComfyUI memory release because queue is busy "
                f"(running={running}, pending={pending})"
            )
            return False

        logger.info(f"Releasing ComfyUI memory after idle workflow completion ({intensity})")
        await self.free_memory(intensity)
        return True

    async def _get_queue(self) -> dict:
        response = await self._request("GET", "/queue")
        data = response.json()
        return data if isinstance(data, dict) else {}

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
