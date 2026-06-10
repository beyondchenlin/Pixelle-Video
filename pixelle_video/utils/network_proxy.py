from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

from loguru import logger

_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def apply_adaptive_proxy_env(*, provider_base_url: str | None = None) -> dict[str, object]:
    """Adapt proxy env vars to current runtime instead of forcing users to choose.

    PIXELLE_PROXY_MODE:
      auto   default. Keep reachable proxies; disable dead loopback proxies.
      system leave environment untouched.
      proxy  leave environment untouched; for users who require a proxy.
      direct remove proxy variables for this process.

    This is intentionally process-local. It does not edit Windows or shell-level
    environment variables, so opening or closing a proxy app later is still safe.
    """
    mode = os.getenv("PIXELLE_PROXY_MODE", "auto").strip().lower() or "auto"
    if mode in {"system", "proxy"}:
        return {"mode": mode, "changed": False, "reason": "proxy environment left untouched"}
    if mode == "direct":
        removed = _remove_proxy_envs()
        return {"mode": "direct", "changed": bool(removed), "removed": removed}
    if mode != "auto":
        logger.warning("Unknown PIXELLE_PROXY_MODE=%s; falling back to auto", mode)

    disabled: dict[str, str] = {}
    active: dict[str, str] = {}
    for name in _PROXY_ENV_NAMES:
        value = os.environ.get(name)
        if not value:
            continue
        endpoint = _parse_proxy_endpoint(value)
        if endpoint is None:
            active[name] = value
            continue
        host, port = endpoint
        if _is_loopback(host) and not _can_connect(host, port):
            disabled[name] = value
            os.environ.pop(name, None)
        else:
            active[name] = value
    if disabled:
        logger.warning(
            "Disabled unreachable loopback proxy env vars for current process: %s; provider_base_url=%s",
            sorted(disabled),
            provider_base_url or "",
        )
    return {
        "mode": "auto",
        "changed": bool(disabled),
        "disabled": disabled,
        "active": active,
        "provider_base_url": provider_base_url,
    }


def _remove_proxy_envs() -> dict[str, str]:
    removed: dict[str, str] = {}
    for name in _PROXY_ENV_NAMES:
        value = os.environ.pop(name, None)
        if value:
            removed[name] = value
    if removed:
        logger.info("Removed proxy env vars for current process: %s", sorted(removed))
    return removed


def _parse_proxy_endpoint(value: str) -> tuple[str, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urlparse(text)
    except Exception:
        return None
    if not parsed.hostname:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.hostname, int(port)


def _is_loopback(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    return normalized in _LOOPBACK_HOSTS


def _can_connect(host: str, port: int, *, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


__all__ = ["apply_adaptive_proxy_env"]
