"""Canonical ComfyUI endpoint identities and managed-endpoint validation."""

from urllib.parse import SplitResult, urlsplit

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _parse_absolute_endpoint(url: str | None) -> SplitResult:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(
            "ComfyUI backend URL must be absolute and include a scheme and hostname"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("ComfyUI backend URL contains an invalid port") from exc
    if port is not None and port < 1:
        raise ValueError("ComfyUI backend URL port must be between 1 and 65535")
    return parsed


def comfyui_listener_identity(
    url: str | None,
) -> tuple[str, str, int | None]:
    """Return the socket listener identity, ignoring HTTP routing syntax."""
    parsed = _parse_absolute_endpoint(url)
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").rstrip(".").casefold()
    if host in _LOCAL_HOSTS:
        host = "loopback"
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, host, port


def validate_pixelle_managed_comfyui_url(url: str | None) -> tuple[str, int]:
    """Validate the exact local HTTP listener contract supported by the launcher."""
    parsed = _parse_absolute_endpoint(url)
    if parsed.scheme.casefold() != "http":
        raise ValueError("managed ComfyUI backend URL must use http")
    host = (parsed.hostname or "").rstrip(".").casefold()
    if host not in _LOCAL_HOSTS:
        raise ValueError("managed ComfyUI backend URL must use a loopback hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("managed ComfyUI backend URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError(
            "managed ComfyUI backend URL must identify the listener root without "
            "a path, query, or fragment"
        )
    port = parsed.port if parsed.port is not None else 80
    if port == 8188:
        raise ValueError(
            "port 8188 is reserved for the externally managed desktop service"
        )
    return host, port
