from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from httpx import Timeout
from loguru import logger
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from pixelle_video.utils.asyncio_util import await_cancel_safe_cleanup
from pixelle_video.utils.network_proxy import ProviderProxyConfig


@dataclass(frozen=True)
class OpenAIClientSettings:
    """Connection settings with a credential-safe cache fingerprint."""

    api_key: str = field(repr=False)
    base_url: str = ""
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 180.0
    write_timeout_seconds: float = 30.0
    pool_timeout_seconds: float = 10.0
    max_retries: int = 1
    proxy: ProviderProxyConfig = field(
        default_factory=lambda: ProviderProxyConfig(
            mode="direct",
            trust_env=False,
            reason="default direct connection",
        )
    )

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key:
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(self.base_url, str):
            raise TypeError("base_url must be a string")
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "write_timeout_seconds",
            "pool_timeout_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if not isinstance(self.proxy, ProviderProxyConfig):
            raise TypeError("proxy must be a ProviderProxyConfig")

    @property
    def fingerprint(self) -> str:
        material = {
            "api_key_sha256": hashlib.sha256(self.api_key.encode("utf-8")).hexdigest(),
            "base_url": self.base_url,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "read_timeout_seconds": self.read_timeout_seconds,
            "write_timeout_seconds": self.write_timeout_seconds,
            "pool_timeout_seconds": self.pool_timeout_seconds,
            "max_retries": self.max_retries,
            "proxy": self.proxy.fingerprint,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def timeout(self) -> Timeout:
        return Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )


@dataclass
class _PoolEntry:
    client: Any
    active_leases: int = 0
    retired: bool = False


ClientFactory = Callable[[], Any | Awaitable[Any]]


class AsyncOpenAIClientPool:
    """Bounded lazy client pool with in-flight-safe eviction and shutdown."""

    def __init__(self, *, max_size: int = 4) -> None:
        if type(max_size) is not int or max_size < 1:
            raise ValueError("max_size must be a positive integer")
        self._max_size = max_size
        self._entries: OrderedDict[str, _PoolEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._closed = False

    @asynccontextmanager
    async def acquire(
        self,
        *,
        fingerprint: str,
        factory: ClientFactory,
    ) -> AsyncIterator[Any]:
        entry, close_before_yield = await self._acquire_entry(
            fingerprint=fingerprint,
            factory=factory,
        )
        await _close_clients(close_before_yield, strict=False)
        try:
            yield entry.client
        finally:
            await await_cancel_safe_cleanup(self._release_entry(fingerprint, entry))

    async def _acquire_entry(
        self,
        *,
        fingerprint: str,
        factory: ClientFactory,
    ) -> tuple[_PoolEntry, list[Any]]:
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("client fingerprint must be a non-empty string")
        clients_to_close: list[Any] = []
        async with self._lock:
            if self._closed:
                raise RuntimeError("OpenAI-compatible client pool is closed")
            entry = self._entries.get(fingerprint)
            if entry is None:
                client = factory()
                if inspect.isawaitable(client):
                    client = await client
                entry = _PoolEntry(client=client)
                self._entries[fingerprint] = entry
            else:
                self._entries.move_to_end(fingerprint)
            entry.active_leases += 1
            clients_to_close.extend(self._retire_idle_overflow(exclude=fingerprint))
        return entry, clients_to_close

    async def _release_entry(self, fingerprint: str, entry: _PoolEntry) -> None:
        clients_to_close: list[Any] = []
        async with self._lock:
            if entry.active_leases < 1:
                raise RuntimeError("client pool lease accounting underflow")
            entry.active_leases -= 1
            if entry.retired and entry.active_leases == 0:
                if self._entries.get(fingerprint) is entry:
                    self._entries.pop(fingerprint, None)
                clients_to_close.append(entry.client)
            clients_to_close.extend(self._retire_idle_overflow())
        await _close_clients(clients_to_close, strict=False)

    def _retire_idle_overflow(self, *, exclude: str | None = None) -> list[Any]:
        clients_to_close: list[Any] = []
        while len(self._entries) > self._max_size:
            victim_key = next(
                (
                    key
                    for key, candidate in self._entries.items()
                    if key != exclude and candidate.active_leases == 0
                ),
                None,
            )
            if victim_key is None:
                break
            victim = self._entries.pop(victim_key)
            victim.retired = True
            clients_to_close.append(victim.client)
        return clients_to_close

    async def close(self) -> None:
        clients_to_close: list[Any] = []
        async with self._lock:
            self._closed = True
            for key, entry in list(self._entries.items()):
                entry.retired = True
                if entry.active_leases == 0:
                    self._entries.pop(key, None)
                    clients_to_close.append(entry.client)
        await _close_clients(clients_to_close, strict=True)


async def create_openai_client(settings: OpenAIClientSettings) -> AsyncOpenAI:
    """Create one client with proxy behavior isolated to its HTTP transport."""

    http_kwargs: dict[str, Any] = {
        "timeout": settings.timeout(),
        "trust_env": settings.proxy.trust_env,
    }
    if settings.proxy.proxy_url:
        http_kwargs["proxy"] = settings.proxy.proxy_url
    http_client = DefaultAsyncHttpxClient(**http_kwargs)
    client_kwargs: dict[str, Any] = {
        "api_key": settings.api_key,
        "timeout": settings.timeout(),
        "max_retries": settings.max_retries,
        "http_client": http_client,
    }
    if settings.base_url:
        client_kwargs["base_url"] = settings.base_url
    try:
        return AsyncOpenAI(**client_kwargs)
    except Exception:
        await http_client.aclose()
        raise


async def _close_clients(clients: list[Any], *, strict: bool) -> None:
    first_error: Exception | None = None
    seen: set[int] = set()
    for client in clients:
        if id(client) in seen:
            continue
        seen.add(id(client))
        close = getattr(client, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # pragma: no cover - exercised through pool tests
            first_error = first_error or exc
    if first_error is not None:
        if strict:
            raise RuntimeError("failed to close OpenAI-compatible client") from first_error
        logger.warning(
            "Failed to close an evicted OpenAI-compatible client: {}",
            type(first_error).__name__,
        )


__all__ = [
    "AsyncOpenAIClientPool",
    "OpenAIClientSettings",
    "create_openai_client",
]
