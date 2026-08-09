from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "access_key",
        "access_token",
        "apikey",
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "password",
        "private_key",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "secret_key",
        "set_cookie",
        "token",
    }
)
_SENSITIVE_KEY_SUFFIXES = (
    "_access_key",
    "_access_token",
    "_api_key",
    "_credential",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret",
    "_secret_key",
    "_token",
)
_COMPACT_SENSITIVE_KEY_MARKERS = (
    "accesskey",
    "accesstoken",
    "apikey",
    "clientsecret",
    "privatekey",
    "refreshtoken",
    "secretkey",
)
_CREDENTIAL_KEY_FRAGMENT = (
    r"(?:access[_-]?key|access[_-]?token|api[_-]?key|authorization|bearer|cookie|"
    r"credential|password|private[_-]?key|refresh[_-]?token|secret|token)"
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    rf"(?P<prefix>(?<![A-Za-z0-9_])['\"]?[A-Za-z0-9_-]*"
    rf"{_CREDENTIAL_KEY_FRAGMENT}[A-Za-z0-9_-]*['\"]?\s*[:=]\s*)"
    rf"(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^\s,;}}\]]+))",
    re.IGNORECASE,
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[^\s,;\"'}\]]+")
_URL_USERINFO_RE = re.compile(r"(?i)(https?://)[^/@\s]+@")


def normalize_sensitive_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(key).strip().lower()).strip("_")


def is_sensitive_key(key: Any) -> bool:
    normalized = normalize_sensitive_key(key)
    compact = normalized.replace("_", "")
    segments = set(normalized.split("_"))
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)
        or bool(
            segments
            & {
                "authorization",
                "bearer",
                "cookie",
                "credential",
                "credentials",
                "password",
                "secret",
                "token",
            }
        )
        or any(marker in compact for marker in _COMPACT_SENSITIVE_KEY_MARKERS)
    )


def redact_credentials_in_text(message: Any, *, replacement: str = "***") -> str:
    """Redact credential assignments, bearer tokens, and URL user information."""

    redacted = _BEARER_TOKEN_RE.sub(f"Bearer {replacement}", str(message))
    redacted = _URL_USERINFO_RE.sub(rf"\1{replacement}@", redacted)

    def _replace_assignment(match: re.Match[str]) -> str:
        quote = match.group("quote") or ""
        return f"{match.group('prefix')}{quote}{replacement}{quote}"

    return _CREDENTIAL_ASSIGNMENT_RE.sub(_replace_assignment, redacted)


__all__ = [
    "is_sensitive_key",
    "normalize_sensitive_key",
    "redact_credentials_in_text",
]
