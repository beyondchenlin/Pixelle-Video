from pathlib import Path

import pytest
import requests

from web.components.settings import _probe_comfyui_connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_does_not_render_retired_gguf_cleanup_strategy():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "gguf_cleanup_strategy" not in source


def test_comfyui_connection_probe_is_read_only_authenticated_and_no_redirects(
    monkeypatch,
):
    calls = []

    class _Response:
        def raise_for_status(self):
            calls.append(("raise_for_status",))

        def json(self):
            return {"system": {"comfyui_version": "0.31.0"}}

    def _get(url, **kwargs):
        calls.append(("get", url, kwargs))
        return _Response()

    monkeypatch.setattr(requests, "get", _get)

    payload = _probe_comfyui_connection(
        "http://127.0.0.1:8000/",
        "secret-token",
    )

    assert payload["system"]["comfyui_version"] == "0.31.0"
    assert calls == [
        (
            "get",
            "http://127.0.0.1:8000/system_stats",
            {
                "headers": {"Authorization": "Bearer secret-token"},
                "timeout": (2, 5),
                "allow_redirects": False,
            },
        ),
        ("raise_for_status",),
    ]


@pytest.mark.parametrize(
    "url",
    (
        "127.0.0.1:8000",
        "ftp://127.0.0.1:8000",
        "http://user:password@127.0.0.1:8000",
        "http://127.0.0.1:8000?token=secret",
        "http://127.0.0.1:8000#fragment",
    ),
)
def test_comfyui_connection_probe_rejects_unsafe_urls_before_network(
    monkeypatch,
    url,
):
    def _fail_get(*args, **kwargs):
        raise AssertionError("invalid URL must not reach the network")

    monkeypatch.setattr(requests, "get", _fail_get)

    with pytest.raises(ValueError):
        _probe_comfyui_connection(url, "secret-token")


def test_comfyui_connection_probe_rejects_non_comfyui_success_response(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response())

    with pytest.raises(RuntimeError, match="required system object"):
        _probe_comfyui_connection("http://127.0.0.1:8000")
