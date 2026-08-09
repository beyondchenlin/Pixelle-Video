from __future__ import annotations

import asyncio

import pytest

from pixelle_video.services.openai_client_pool import (
    AsyncOpenAIClientPool,
    OpenAIClientSettings,
)
from pixelle_video.utils.network_proxy import ProviderProxyConfig


class _FakeClient:
    def __init__(self, name: str, *, close_error: Exception | None = None) -> None:
        self.name = name
        self.close_calls = 0
        self.close_error = close_error

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.asyncio
async def test_pool_reuses_one_client_for_concurrent_identical_settings():
    pool = AsyncOpenAIClientPool(max_size=2)
    factory_calls = 0
    release = asyncio.Event()

    async def factory():
        nonlocal factory_calls
        factory_calls += 1
        return _FakeClient("shared")

    async def use_client():
        async with pool.acquire(fingerprint="same", factory=factory) as client:
            await release.wait()
            return client

    tasks = [asyncio.create_task(use_client()) for _ in range(5)]
    await asyncio.sleep(0)
    release.set()
    clients = await asyncio.gather(*tasks)

    assert factory_calls == 1
    assert len({id(client) for client in clients}) == 1
    await pool.close()
    assert clients[0].close_calls == 1


@pytest.mark.asyncio
async def test_pool_does_not_close_active_client_during_overflow():
    pool = AsyncOpenAIClientPool(max_size=1)
    first = _FakeClient("first")
    second = _FakeClient("second")

    async with pool.acquire(fingerprint="first", factory=lambda: first):
        async with pool.acquire(fingerprint="second", factory=lambda: second):
            assert first.close_calls == 0
            assert second.close_calls == 0
        assert second.close_calls == 1
        assert first.close_calls == 0

    await pool.close()
    assert first.close_calls == 1


@pytest.mark.asyncio
async def test_eviction_close_failure_does_not_mask_successful_lease():
    pool = AsyncOpenAIClientPool(max_size=1)
    broken = _FakeClient("broken", close_error=RuntimeError("close failed"))
    healthy = _FakeClient("healthy")

    async with pool.acquire(fingerprint="broken", factory=lambda: broken):
        pass
    async with pool.acquire(fingerprint="healthy", factory=lambda: healthy) as client:
        assert client is healthy

    await pool.close()


@pytest.mark.asyncio
async def test_close_rejects_new_leases_and_defers_active_close():
    pool = AsyncOpenAIClientPool(max_size=1)
    client = _FakeClient("active")

    async with pool.acquire(fingerprint="active", factory=lambda: client):
        await pool.close()
        assert client.close_calls == 0
        with pytest.raises(RuntimeError, match="pool is closed"):
            async with pool.acquire(
                fingerprint="new",
                factory=lambda: _FakeClient("new"),
            ):
                pass

    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_lease_release_survives_repeated_task_cancellation(monkeypatch):
    pool = AsyncOpenAIClientPool(max_size=1)
    client = _FakeClient("cancelled")
    using_client = asyncio.Event()
    release_started = asyncio.Event()
    allow_release = asyncio.Event()
    original_release = pool._release_entry

    async def delayed_release(fingerprint, entry):
        release_started.set()
        await allow_release.wait()
        await original_release(fingerprint, entry)

    monkeypatch.setattr(pool, "_release_entry", delayed_release)

    async def use_client():
        async with pool.acquire(fingerprint="cancelled", factory=lambda: client):
            using_client.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(use_client())
    await using_client.wait()
    task.cancel()
    await release_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    allow_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    await pool.close()
    assert client.close_calls == 1


def test_settings_fingerprint_is_secret_safe_and_transport_sensitive():
    direct = ProviderProxyConfig(mode="direct", trust_env=False)
    first = OpenAIClientSettings(
        api_key="secret-one",
        base_url="https://api.example/v1",
        proxy=direct,
    )
    second = OpenAIClientSettings(
        api_key="secret-two",
        base_url="https://api.example/v1",
        proxy=direct,
    )
    changed_timeout = OpenAIClientSettings(
        api_key="secret-one",
        base_url="https://api.example/v1",
        read_timeout_seconds=181,
        proxy=direct,
    )

    assert first.fingerprint != second.fingerprint
    assert first.fingerprint != changed_timeout.fingerprint
    assert "secret-one" not in repr(first)


@pytest.mark.parametrize(
    "overrides",
    [
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": float("nan")},
        {"max_retries": -1},
        {"max_retries": True},
    ],
)
def test_settings_reject_invalid_transport_limits(overrides):
    defaults = {
        "api_key": "key",
        "proxy": ProviderProxyConfig(mode="direct", trust_env=False),
    }
    with pytest.raises((TypeError, ValueError)):
        OpenAIClientSettings(**defaults, **overrides)
