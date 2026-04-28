from __future__ import annotations

from typing import Literal

import httpx
from loguru import logger

ComfyUICleanupMode = Literal["force", "conservative"]


class ComfyUIMaintenanceClient:
    """Small client for ComfyUI maintenance endpoints used before long renders."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    async def cleanup_before_generation(self, mode: ComfyUICleanupMode) -> None:
        if mode == "force":
            await self._force_cleanup()
            return
        if mode == "conservative":
            await self._conservative_cleanup()
            return
        raise ValueError(f"Unsupported ComfyUI cleanup mode: {mode}")

    async def _force_cleanup(self) -> None:
        logger.info("Running force ComfyUI cleanup before video generation")
        await self._post("/interrupt", {})
        await self._post("/queue", {"clear": True})
        await self.free_memory()

    async def _conservative_cleanup(self) -> None:
        queue = await self._get_queue()
        running = queue.get("queue_running") or []
        pending = queue.get("queue_pending") or []
        if running or pending:
            logger.info(
                "Skipping conservative ComfyUI cleanup because queue is busy "
                f"(running={len(running)}, pending={len(pending)})"
            )
            return

        logger.info("Running conservative ComfyUI cleanup before video generation")
        await self.free_memory()

    async def free_memory(self) -> None:
        await self._post("/free", {"unload_models": True, "free_memory": True})

    async def _get_queue(self) -> dict:
        response = await self._request("GET", "/queue")
        data = response.json()
        return data if isinstance(data, dict) else {}

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
