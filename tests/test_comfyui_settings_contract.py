from pathlib import Path

import pytest
import requests

from web.components.settings import (
    _apply_backend_lifecycle_policy,
    _probe_comfyui_connection,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_does_not_render_retired_gguf_cleanup_strategy():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )

    assert "gguf_cleanup_strategy" not in source


def test_settings_page_recommends_required_without_silently_migrating_old_config():
    source = (PROJECT_ROOT / "web" / "components" / "settings.py").read_text(
        encoding="utf-8"
    )
    chinese_locale = (
        PROJECT_ROOT / "web" / "i18n" / "locales" / "zh_CN.json"
    ).read_text(encoding="utf-8")

    assert '"backend_management_mode",\n                    "disabled"' in source
    assert "按需启停完整本地服务（推荐）" in chinese_locale
    assert "图片或音频批次结束后关闭完整的 ComfyUI 服务" in chinese_locale


def test_required_lifecycle_policy_enables_owned_batch_stop_for_every_profile():
    original = {
        "default": {
            "managed": False,
            "restart_after_batch": False,
            "url": "http://127.0.0.1:8000",
        },
        "tts": {
            "managed": True,
            "stop_after_batch": False,
            "url": "http://127.0.0.1:8002",
        },
    }

    result = _apply_backend_lifecycle_policy(original, "required")

    assert result["default"]["managed"] is True
    assert result["default"]["stop_after_batch"] is True
    assert "restart_after_batch" not in result["default"]
    assert result["tts"]["managed"] is True
    assert result["tts"]["stop_after_batch"] is True
    assert original["default"]["managed"] is False


def test_external_lifecycle_policy_preserves_profile_controls():
    original = {"default": {"managed": False, "stop_after_batch": False}}

    assert _apply_backend_lifecycle_policy(original, "disabled") == original


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
