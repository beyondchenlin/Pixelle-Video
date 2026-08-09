from __future__ import annotations

import asyncio
import hashlib
import os
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from loguru import logger

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
_VALID_PROXY_MODES = {"auto", "direct", "proxy", "system"}


@dataclass(frozen=True)
class ProviderProxyConfig:
    """Immutable per-client proxy decision that never mutates process state."""

    mode: str
    trust_env: bool
    proxy_url: str | None = field(default=None, repr=False)
    reason: str = ""

    @property
    def fingerprint(self) -> str:
        proxy_digest = hashlib.sha256(
            str(self.proxy_url or "").encode("utf-8")
        ).hexdigest()
        material = f"{self.mode}|{self.trust_env}|{proxy_digest}|{self.reason}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def diagnostics(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "trust_env": self.trust_env,
            "proxy_configured": self.proxy_url is not None,
            "reason": self.reason,
        }


async def resolve_provider_proxy_async(
    *,
    provider_base_url: str | None = None,
) -> ProviderProxyConfig:
    """Resolve proxy settings without blocking the caller's event loop."""

    return await asyncio.to_thread(
        resolve_provider_proxy,
        provider_base_url=provider_base_url,
    )


def resolve_provider_proxy(*, provider_base_url: str | None = None) -> ProviderProxyConfig:
    """Resolve proxy behavior for one provider client without editing ``os.environ``."""

    configured_mode = os.getenv("PIXELLE_PROXY_MODE", "auto").strip().lower() or "auto"
    mode = configured_mode
    if mode not in _VALID_PROXY_MODES:
        logger.warning("Unknown PIXELLE_PROXY_MODE; falling back to auto")
        mode = "auto"

    if mode == "system":
        return ProviderProxyConfig(
            mode=mode,
            trust_env=True,
            reason="proxy environment delegated to HTTP client",
        )
    if mode == "direct":
        return ProviderProxyConfig(
            mode=mode,
            trust_env=False,
            reason="proxy explicitly disabled",
        )

    parsed_provider = urlparse(str(provider_base_url or ""))
    if mode == "proxy":
        proxy_url = _proxy_url_for_scheme(parsed_provider.scheme)
        if not proxy_url:
            raise ValueError(
                "PIXELLE_PROXY_MODE=proxy requires a proxy environment variable"
            )
        if _parse_proxy_endpoint(proxy_url) is None:
            raise ValueError(
                "PIXELLE_PROXY_MODE=proxy requires a valid proxy URL"
            )
        return ProviderProxyConfig(
            mode=mode,
            trust_env=False,
            proxy_url=proxy_url,
            reason="proxy explicitly required",
        )

    provider_host = parsed_provider.hostname or ""
    try:
        parsed_port = parsed_provider.port
    except ValueError:
        logger.warning("Provider base URL contains an invalid port; ignoring proxy")
        return ProviderProxyConfig(
            mode="auto",
            trust_env=False,
            reason="provider URL contained an invalid port",
        )
    provider_port = _provider_port(parsed_provider.scheme, parsed_port)
    if provider_host and _matches_no_proxy(provider_host, provider_port):
        return ProviderProxyConfig(
            mode="auto",
            trust_env=False,
            reason="provider matched no-proxy rules",
        )

    proxy_url = _proxy_url_for_scheme(parsed_provider.scheme)
    if not proxy_url:
        return ProviderProxyConfig(
            mode="auto",
            trust_env=False,
            reason="no proxy configured for provider scheme",
        )

    endpoint = _parse_proxy_endpoint(proxy_url)
    if endpoint is None:
        logger.warning("Ignoring invalid proxy configuration for provider client")
        return ProviderProxyConfig(
            mode="auto",
            trust_env=False,
            reason="configured proxy URL was invalid",
        )

    proxy_host, proxy_port = endpoint
    if _is_loopback(proxy_host) and not _can_connect(proxy_host, proxy_port):
        logger.warning(
            "Ignoring unreachable loopback proxy for provider client: host={} port={}",
            proxy_host,
            proxy_port,
        )
        return ProviderProxyConfig(
            mode="auto",
            trust_env=False,
            reason="configured loopback proxy was unreachable",
        )

    return ProviderProxyConfig(
        mode="auto",
        trust_env=False,
        proxy_url=proxy_url,
        reason="using validated explicit proxy",
    )


def _proxy_url_for_scheme(scheme: str | None) -> str | None:
    normalized = str(scheme or "https").strip().lower()
    names = (
        ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
        if normalized == "https"
        else ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
    )
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def _matches_no_proxy(host: str, port: int | None) -> bool:
    raw = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    normalized_host = host.strip().lower().strip("[]").rstrip(".")
    for item in raw.split(","):
        rule = item.strip().lower()
        if not rule:
            continue
        if rule == "*":
            return True
        rule_host, rule_port = _split_no_proxy_rule(rule)
        if rule_port is not None and port != rule_port:
            continue
        normalized_rule = rule_host.removeprefix("*.").lstrip(".").rstrip(".")
        if not normalized_rule:
            continue
        if normalized_host == normalized_rule or normalized_host.endswith(
            f".{normalized_rule}"
        ):
            return True
    return False


def _split_no_proxy_rule(rule: str) -> tuple[str, int | None]:
    value = rule
    if "://" in value:
        parsed = urlparse(value)
        return parsed.hostname or "", parsed.port
    if value.startswith("[") and "]" in value:
        host, _, suffix = value[1:].partition("]")
        if suffix.startswith(":") and suffix[1:].isdigit():
            return host, int(suffix[1:])
        return host, None
    if value.count(":") == 1:
        host, candidate_port = value.rsplit(":", 1)
        if candidate_port.isdigit():
            return host, int(candidate_port)
    return value, None


def _provider_port(scheme: str | None, port: int | None) -> int | None:
    if port is not None:
        return port
    if str(scheme or "").lower() == "https":
        return 443
    if str(scheme or "").lower() == "http":
        return 80
    return None


def _parse_proxy_endpoint(value: str) -> tuple[str, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urlparse(text)
        if not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (TypeError, ValueError):
        return None
    return parsed.hostname, int(port)


def _is_loopback(host: str) -> bool:
    return host.strip().lower().strip("[]") in _LOOPBACK_HOSTS


def _can_connect(host: str, port: int, *, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


__all__ = [
    "ProviderProxyConfig",
    "resolve_provider_proxy",
    "resolve_provider_proxy_async",
]
