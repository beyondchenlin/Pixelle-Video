from __future__ import annotations

from web.components import progressive_load_trigger


def test_progressive_component_uses_viewport_observation_and_safe_text_assignment():
    script = progressive_load_trigger._PROGRESSIVE_LOAD_JS

    assert "IntersectionObserver" in script
    assert "rootMargin: '800px 0px'" in script
    assert "setTriggerValue('request_more', true)" in script
    assert "textContent = data.label" in script
    assert "showFallback()" in script
    assert "observer?.disconnect()" in script
    assert "innerHTML" not in script


def test_progressive_component_binds_the_request_callback(monkeypatch):
    captured = {}

    def callback():
        return None

    def _component(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        progressive_load_trigger,
        "_PROGRESSIVE_LOAD_COMPONENT",
        _component,
    )

    automatic = progressive_load_trigger.render_progressive_load_trigger(
        label="继续加载",
        key="gallery_loader",
        on_request_more=callback,
    )

    assert automatic is True
    assert captured["data"] == {"label": "继续加载"}
    assert captured["key"] == "gallery_loader"
    assert captured["on_request_more_change"] is callback


def test_progressive_component_has_a_non_pagination_fallback(monkeypatch):
    captured = {}

    def callback():
        return None

    class _FakeUI:
        def button(self, label, **kwargs):
            captured["label"] = label
            captured.update(kwargs)
            return False

    monkeypatch.setattr(
        progressive_load_trigger,
        "_PROGRESSIVE_LOAD_COMPONENT",
        None,
    )

    automatic = progressive_load_trigger.render_progressive_load_trigger(
        label="继续加载更多视频",
        key="gallery_loader",
        on_request_more=callback,
        ui=_FakeUI(),
    )

    assert automatic is False
    assert captured["label"] == "继续加载更多视频"
    assert captured["key"] == "gallery_loader_fallback"
    assert captured["on_click"] is callback
