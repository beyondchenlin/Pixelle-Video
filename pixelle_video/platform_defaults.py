from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import SplitResult, urlsplit, urlunsplit

DEFAULT_API_PORT = 6789
BUILTIN_API_BASE_URL = f"http://localhost:{DEFAULT_API_PORT}/api"
LEGACY_LOCAL_API_PORTS = frozenset({8001, 8888, 8899})


def parse_api_port(
    value: object | None,
    *,
    default: int = DEFAULT_API_PORT,
    setting_name: str = "PIXELLE_API_PORT",
) -> int:
    """Parse a TCP port while treating an unset or blank value as the default."""

    text = "" if value is None else str(value).strip()
    if not text:
        port = default
    else:
        try:
            port = int(text, 10)
        except ValueError as exc:
            raise ValueError(f"{setting_name} must be an integer between 1 and 65535") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{setting_name} must be between 1 and 65535")
    return port


def normalize_api_base_url(value: object, *, setting_name: str = "API base URL") -> str:
    """Validate and normalize an absolute HTTP(S) API base URL."""

    text = str(value).strip()
    if not text:
        raise ValueError(f"{setting_name} must not be blank")
    if any(character.isspace() for character in text):
        raise ValueError(f"{setting_name} must not contain whitespace")

    try:
        parsed = urlsplit(text)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{setting_name} is not a valid URL") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"{setting_name} must use http or https")
    if not parsed.hostname:
        raise ValueError(f"{setting_name} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{setting_name} must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{setting_name} must not include a query or fragment")
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        raise ValueError(f"{setting_name} contains an invalid port")

    normalized_path = parsed.path.rstrip("/")
    normalized = SplitResult(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc,
        path=normalized_path,
        query="",
        fragment="",
    )
    return urlunsplit(normalized)


def configured_api_port(environ: Mapping[str, str] | None = None) -> int:
    source = os.environ if environ is None else environ
    return parse_api_port(source.get("PIXELLE_API_PORT"))


def configured_api_base_url(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    port = configured_api_port(source)
    raw_value = source.get("PIXELLE_API_BASE_URL")
    if raw_value is None or raw_value.strip() == "":
        raw_value = f"http://localhost:{port}/api"
    return normalize_api_base_url(raw_value, setting_name="PIXELLE_API_BASE_URL")


def is_legacy_local_api_base_url(value: object) -> bool:
    try:
        parsed = urlsplit(normalize_api_base_url(value))
    except ValueError:
        return False

    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "http"
        and host in {"localhost", "127.0.0.1", "::1"}
        and parsed.port in LEGACY_LOCAL_API_PORTS
        and parsed.path in {"", "/api"}
    )


__all__ = [
    "BUILTIN_API_BASE_URL",
    "DEFAULT_API_PORT",
    "LEGACY_LOCAL_API_PORTS",
    "configured_api_base_url",
    "configured_api_port",
    "is_legacy_local_api_base_url",
    "normalize_api_base_url",
    "parse_api_port",
]
