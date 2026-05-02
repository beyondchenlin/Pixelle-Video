from __future__ import annotations

from urllib.parse import urljoin, urlparse

from pixelle_video.services.artifact_access_urls import normalize_artifact_access_url


def artifact_url_for_streamlit(value: str | None, *, api_base_url: str) -> str | None:
    normalized = normalize_artifact_access_url(value)
    if normalized is None:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme:
        return normalized

    api_origin = _api_origin(api_base_url)
    return urljoin(f"{api_origin}/", normalized.lstrip("/"))


def _api_origin(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("api_base_url must be an absolute http(s) URL")
    return f"{parsed.scheme}://{parsed.netloc}"


__all__ = ["artifact_url_for_streamlit"]
