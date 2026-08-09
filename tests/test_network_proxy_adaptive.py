from __future__ import annotations

import asyncio
import time

import pytest

from pixelle_video.utils import network_proxy
from pixelle_video.utils.network_proxy import (
    resolve_provider_proxy,
    resolve_provider_proxy_async,
)

_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)


def _clear_proxy_environment(monkeypatch) -> None:
    for name in _PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_auto_proxy_ignores_unreachable_loopback_without_mutating_environment(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    result = resolve_provider_proxy(
        provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/"
    )

    assert result.trust_env is False
    assert result.proxy_url is None
    assert result.reason == "configured loopback proxy was unreachable"
    assert network_proxy.os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"


def test_system_proxy_mode_delegates_to_client_environment(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "system")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    result = resolve_provider_proxy(
        provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/"
    )

    assert result.mode == "system"
    assert result.trust_env is True
    assert result.proxy_url is None
    assert network_proxy.os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"


def test_direct_proxy_mode_disables_environment(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "direct")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")

    result = resolve_provider_proxy(provider_base_url="https://api.example/v1")

    assert result.mode == "direct"
    assert result.trust_env is False
    assert result.proxy_url is None


def test_required_proxy_mode_uses_explicit_proxy_and_ignores_no_proxy(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "proxy")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", "api.example")

    result = resolve_provider_proxy(provider_base_url="https://api.example/v1")

    assert result.mode == "proxy"
    assert result.trust_env is False
    assert result.proxy_url == "http://proxy.example:8080"


def test_required_proxy_mode_rejects_missing_proxy(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "proxy")

    with pytest.raises(ValueError, match="requires a proxy environment variable"):
        resolve_provider_proxy(provider_base_url="https://api.example/v1")


def test_auto_proxy_uses_validated_explicit_proxy_without_exposing_credentials(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://user:secret@proxy.example:8080")
    monkeypatch.setattr(network_proxy, "_can_connect", lambda host, port: True)

    result = resolve_provider_proxy(provider_base_url="https://api.example/v1")

    assert result.trust_env is False
    assert result.proxy_url == "http://user:secret@proxy.example:8080"
    assert "secret" not in repr(result)
    assert "proxy_url" not in result.diagnostics()


@pytest.mark.parametrize(
    ("no_proxy", "base_url"),
    [
        (".example.com", "https://api.example.com/v1"),
        ("api.example.com:8443", "https://api.example.com:8443/v1"),
        ("*", "https://api.anywhere.test/v1"),
        ("[::1]:443", "https://[::1]/v1"),
    ],
)
def test_auto_proxy_honors_no_proxy_rules(monkeypatch, no_proxy, base_url):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", no_proxy)

    result = resolve_provider_proxy(provider_base_url=base_url)

    assert result.proxy_url is None
    assert result.trust_env is False
    assert result.reason == "provider matched no-proxy rules"


def test_invalid_provider_port_fails_closed_without_proxy(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")

    result = resolve_provider_proxy(provider_base_url="https://api.example:not-a-port/v1")

    assert result.proxy_url is None
    assert result.trust_env is False
    assert result.reason == "provider URL contained an invalid port"


@pytest.mark.asyncio
async def test_async_resolution_moves_loopback_probe_off_event_loop(monkeypatch):
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    def slow_probe(host, port):
        time.sleep(0.1)
        return False

    monkeypatch.setattr(network_proxy, "_can_connect", slow_probe)
    resolution = asyncio.create_task(
        resolve_provider_proxy_async(provider_base_url="https://api.example/v1")
    )
    await asyncio.sleep(0.01)

    assert resolution.done() is False
    assert await resolution == resolve_provider_proxy(
        provider_base_url="https://api.example/v1"
    )
