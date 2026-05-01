from __future__ import annotations

import pytest

from pixelle_video.services.artifact_access_urls import (
    is_safe_artifact_access_url,
    normalize_artifact_access_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.pixelle.test/artifacts/workspace_1/frame.png",
        "http://localhost:8000/api/files/artifacts/workspace_1/frame.png",
        "/api/files/artifacts/workspace_1/frame.png",
        "/artifacts/workspace_1/frame.png",
    ],
)
def test_artifact_access_urls_accept_http_and_controlled_relative_urls(url):
    assert is_safe_artifact_access_url(url) is True
    assert normalize_artifact_access_url(f" {url} ") == url


@pytest.mark.parametrize(
    "url",
    [
        r"D:\output\frame.png",
        r"/tmp/pixelle/frame.png",
        "file:///tmp/pixelle/frame.png",
        "~/pixelle/frame.png",
        "../artifacts/frame.png",
        "/api/files/../private/frame.png",
        "/api/files/%2E%2E/private/frame.png",
        "//cdn.pixelle.test/artifacts/frame.png",
        "/private/artifacts/frame.png",
    ],
)
def test_artifact_access_urls_reject_local_paths_and_uncontrolled_relative_urls(url):
    assert is_safe_artifact_access_url(url) is False
    with pytest.raises(ValueError, match="artifact access URL"):
        normalize_artifact_access_url(url)
