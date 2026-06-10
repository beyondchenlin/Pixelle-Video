from __future__ import annotations

from pixelle_video.utils.network_proxy import apply_adaptive_proxy_env


def test_auto_proxy_disables_unreachable_loopback(monkeypatch):
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "auto")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    result = apply_adaptive_proxy_env(provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/")
    assert result["changed"] is True
    assert "HTTPS_PROXY" not in result["active"]


def test_system_proxy_mode_leaves_env(monkeypatch):
    monkeypatch.setenv("PIXELLE_PROXY_MODE", "system")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    result = apply_adaptive_proxy_env(provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/")
    assert result["changed"] is False
    assert result["mode"] == "system"
