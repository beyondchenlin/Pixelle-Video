from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import unquote, urlparse

DEFAULT_CONTROLLED_ARTIFACT_URL_PREFIXES: tuple[str, ...] = (
    "/api/files/",
    "/artifacts/",
)


def normalize_artifact_access_url(
    value: str | None,
    *,
    allowed_relative_prefixes: Iterable[str] | None = None,
) -> str | None:
    """Validate public artifact access URLs without accepting local paths."""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if is_safe_artifact_access_url(
        normalized,
        allowed_relative_prefixes=allowed_relative_prefixes,
    ):
        return normalized
    raise ValueError("artifact access URL must be http(s) or a controlled relative URL")


def is_safe_artifact_access_url(
    value: str,
    *,
    allowed_relative_prefixes: Iterable[str] | None = None,
) -> bool:
    normalized = str(value or "").strip()
    if not normalized or _looks_like_local_file_reference(normalized):
        return False

    parsed = urlparse(normalized)
    if parsed.scheme:
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and _has_safe_url_path(parsed.path)
        )

    if parsed.netloc or not normalized.startswith("/") or normalized.startswith("//"):
        return False
    if not _has_safe_url_path(parsed.path):
        return False

    path = unquote(parsed.path)
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in _normalize_relative_prefixes(allowed_relative_prefixes)
    )


def _looks_like_local_file_reference(value: str) -> bool:
    lowered = value.lower()
    return (
        "\\" in value
        or lowered.startswith("file:")
        or value.startswith("~")
        or _looks_like_windows_path(value)
    )


def _looks_like_windows_path(value: str) -> bool:
    return len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}


def _has_safe_url_path(path: str) -> bool:
    decoded_path = unquote(path or "")
    if "\\" in decoded_path:
        return False
    return all(part not in {"", ".", ".."} for part in decoded_path.split("/") if part)


def _normalize_relative_prefixes(prefixes: Iterable[str] | None) -> tuple[str, ...]:
    source_prefixes = (
        DEFAULT_CONTROLLED_ARTIFACT_URL_PREFIXES
        if prefixes is None
        else tuple(prefixes)
    )
    normalized: list[str] = []
    for prefix in source_prefixes:
        text = str(prefix or "").strip()
        if not text:
            continue
        parsed = urlparse(text)
        if parsed.scheme or parsed.netloc:
            continue
        path = unquote(parsed.path).rstrip("/")
        if not path.startswith("/") or not _has_safe_url_path(path):
            continue
        normalized_prefix = f"{path}/"
        if normalized_prefix not in normalized:
            normalized.append(normalized_prefix)
    return tuple(normalized)


__all__ = [
    "DEFAULT_CONTROLLED_ARTIFACT_URL_PREFIXES",
    "is_safe_artifact_access_url",
    "normalize_artifact_access_url",
]
