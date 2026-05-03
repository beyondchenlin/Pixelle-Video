from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeComponents:
    def __init__(self):
        self.html_calls: list[dict[str, Any]] = []

    def html(self, html, **kwargs):
        self.html_calls.append({"html": html, **kwargs})


class _FakeUI:
    def __init__(self):
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[dict[str, Any]] = []
        self.captions: list[str] = []
        self.buttons: list[dict[str, Any]] = []
        self.infos: list[str] = []

    def container(self, **_kwargs):
        return _NoopContext()

    def markdown(self, body, **kwargs):
        self.markdowns.append({"body": body, **kwargs})

    def caption(self, body):
        self.captions.append(body)

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        return bool(self.session_state.get(kwargs.get("key"), False))

    def info(self, body):
        self.infos.append(body)


def _recent_buttons(fake_ui: _FakeUI) -> list[dict[str, Any]]:
    return [
        button
        for button in fake_ui.buttons
        if button["key"].startswith("layout_preview_recent_preset_")
    ]


def _spec_payload() -> dict[str, Any]:
    return {
        "version": "layered_template.v1",
        "template_id": "portrait_news",
        "template_name": "Portrait News",
        "template_type": "image",
        "canvas_width": 720,
        "canvas_height": 1280,
        "media_width": 640,
        "media_height": 960,
        "safe_area": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
        "layers": [
            {
                "id": "background",
                "type": "background",
                "name": "Background",
                "rect": {"x": 0, "y": 0, "width": 720, "height": 1280, "unit": "px"},
                "z_index": 0,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": None,
                "style": {},
                "role": None,
            },
            {
                "id": "media",
                "type": "image",
                "name": "Generated media",
                "rect": {"x": 40, "y": 180, "width": 640, "height": 960, "unit": "px"},
                "z_index": 10,
                "opacity": 1,
                "rotation": 0,
                "locked": False,
                "source": {
                    "kind": "generated_media",
                    "ref": "generated://primary",
                    "metadata": {},
                },
                "style": {},
                "role": None,
            },
        ],
        "metadata": {"render_backend": "hyperframes", "render_summary": "HyperFrames"},
    }


def test_render_layout_preview_workbench_sorts_recent_presets_and_limits_to_five(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    selected = layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": f"preset_{index}",
                "template_name": f"Template {index}",
                "last_used_at": f"2026-05-02T10:0{index}:00",
                "spec": _spec_payload(),
            }
            for index in range(7)
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert selected is None
    assert rendered.count("Template ") == 5
    assert "Template 6" in rendered
    assert "Template 2" in rendered
    assert "Template 1" not in rendered
    assert len(_recent_buttons(fake_ui)) == 5


def test_render_layout_preview_workbench_sorts_recent_presets_by_datetime(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": "old",
                "template_name": "Old",
                "last_used_at": "2026-05-02T09:30:00Z",
                "spec": _spec_payload(),
            },
            {
                "preset_id": "new",
                "template_name": "New",
                "last_used_at": datetime(2026, 5, 2, 18, 0, tzinfo=timezone.utc),
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        ui=fake_ui,
    )

    button_labels = [item["label"] for item in _recent_buttons(fake_ui)]
    assert button_labels == ["\u5957\u7528 New", "\u5957\u7528 Old"]


def test_render_layout_preview_workbench_sorts_recent_presets_by_absolute_time(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": "utc_later",
                "template_name": "UTC Later",
                "last_used_at": "2026-05-02T18:00:00+00:00",
                "spec": _spec_payload(),
            },
            {
                "preset_id": "offset_earlier",
                "template_name": "Offset Earlier",
                "last_used_at": "2026-05-03T00:30:00+08:00",
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        ui=fake_ui,
    )

    button_labels = [item["label"] for item in _recent_buttons(fake_ui)]
    assert button_labels == ["\u5957\u7528 UTC Later", "\u5957\u7528 Offset Earlier"]


def test_render_layout_preview_workbench_renders_spec_summary_and_safe_html(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html=layout_preview_workbench.trust_preview_html(
            "<section data-preview>trusted-service-html</section>"
        ),
        render_summary="Service render summary",
        template_summary="Portrait news template",
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert "\u5373\u65f6\u9884\u89c8\u5de5\u4f5c\u53f0" in rendered
    assert "\u753b\u5e03\u5c3a\u5bf8" in rendered
    assert "720 x 1280" in rendered
    assert "\u5a92\u4f53\u5c3a\u5bf8" in rendered
    assert "640 x 960" in rendered
    assert "\u56fe\u5c42\u6570\u91cf" in rendered
    assert "2" in rendered
    assert "Service render summary" in rendered
    assert "Portrait news template" in rendered
    assert fake_components.html_calls == [
        {
            "html": "<section data-preview>trusted-service-html</section>",
            "height": 320,
            "scrolling": True,
        }
    ]


def test_render_layout_preview_workbench_renders_media_placement_summary(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        media_placement={
            "basis": "canvas",
            "fit": "contain",
            "scale_percent": 76,
            "offset_x": 18,
            "offset_y": -24,
        },
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert "主媒体位置" in rendered
    assert "76%" in rendered
    assert "X 18px" in rendered
    assert "Y -24px" in rendered


def test_render_layout_preview_workbench_prefers_real_preview_frame(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html=layout_preview_workbench.trust_preview_html("<main>fallback</main>"),
        real_preview_frame={
            "url": "/api/files/artifacts/workspace_demo/layout-preview.png",
            "fingerprint": "preview-fingerprint",
        },
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert "layout-workbench-real-preview" in rendered
    assert "/api/files/artifacts/workspace_demo/layout-preview.png" in rendered
    assert "preview-fingerprint" in rendered
    assert fake_components.html_calls == []


def test_render_layout_preview_workbench_uses_compact_empty_preview_for_empty_spec(
    monkeypatch,
):
    from web.components import layout_preview_workbench

    empty_spec = _spec_payload()
    empty_spec["layers"] = []
    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=empty_spec,
        recent_presets=[],
        preview_html=layout_preview_workbench.trust_preview_html("<main>transparent</main>"),
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert "layout-workbench-empty-preview" in rendered
    assert "当前模板还没有图层" in rendered
    assert fake_components.html_calls == []


def test_render_layout_preview_workbench_records_clicked_recent_preset(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state[
        layout_preview_workbench._recent_preset_button_key("preset_b", key_suffix="")
    ] = True
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)
    callback_calls: list[dict[str, Any]] = []

    selected = layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": "preset_a",
                "template_name": "Template A",
                "last_used_at": "2026-05-02T10:00:00",
                "spec": _spec_payload(),
            },
            {
                "preset_id": "preset_b",
                "template_name": "Template B",
                "last_used_at": "2026-05-02T11:00:00",
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        on_preset_selected=callback_calls.append,
        ui=fake_ui,
    )

    assert selected == {
        "preset_id": "preset_b",
        "spec_payload": _spec_payload(),
    }
    assert callback_calls == [selected]
    assert "layout_preview_selected_preset_id" not in fake_ui.session_state
    assert "_layout_preview_workbench_selection" not in fake_ui.session_state


def test_render_layout_preview_workbench_returns_refresh_preview_action(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state["layout_preview_refresh_preview_frame"] = True
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    selected = layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        ui=fake_ui,
    )

    labels = [button["label"] for button in fake_ui.buttons]
    assert "\u5237\u65b0\u771f\u5b9e\u9884\u89c8\u5e27" in labels
    assert "\u4fdd\u5b58\u4e3a\u6211\u7684\u6a21\u677f" in labels
    assert selected == {"action": "refresh_preview_frame"}


def test_render_layout_preview_workbench_returns_save_template_action(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state["layout_preview_save_template"] = True
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    selected = layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html=None,
        ui=fake_ui,
    )

    labels = [button["label"] for button in fake_ui.buttons]
    assert "\u5237\u65b0\u771f\u5b9e\u9884\u89c8\u5e27" in labels
    assert "\u4fdd\u5b58\u4e3a\u6211\u7684\u6a21\u677f" in labels
    assert selected == {"action": "save_template"}


def test_render_layout_preview_workbench_applies_key_suffix_to_recent_buttons(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": "preset_a",
                "template_name": "Template A",
                "last_used_at": "2026-05-02T10:00:00",
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        key_suffix="_refresh_2",
        ui=fake_ui,
    )

    recent_buttons = _recent_buttons(fake_ui)
    assert recent_buttons[0]["key"].startswith("layout_preview_recent_preset_")
    assert recent_buttons[0]["key"].endswith("_refresh_2")


def test_render_layout_preview_workbench_uses_stable_safe_recent_button_keys(
    monkeypatch,
):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {
                "preset_id": "user:preset/a",
                "template_name": "Slash Template",
                "last_used_at": "2026-05-02T11:00:00",
                "spec": _spec_payload(),
            },
            {
                "preset_id": "user:preset_a",
                "template_name": "Underscore Template",
                "last_used_at": "2026-05-02T10:00:00",
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        key_suffix="_refresh_2",
        ui=fake_ui,
    )

    keys = [item["key"] for item in _recent_buttons(fake_ui)]
    assert len(set(keys)) == 2
    assert all(key.startswith("layout_preview_recent_preset_") for key in keys)
    assert all(key.endswith("_refresh_2") for key in keys)
    assert all("user:preset" not in key for key in keys)


def test_render_layout_preview_workbench_ignores_recent_preset_without_spec(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[
            {"preset_id": "preset_without_spec", "template_name": "Template Without Spec"},
            {
                "preset_id": "preset_with_spec",
                "template_name": "Template With Spec",
                "spec": _spec_payload(),
            },
        ],
        preview_html=layout_preview_workbench.trust_preview_html("<main>preview</main>"),
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert "Template Without Spec" not in rendered
    assert "Template With Spec" in rendered
    assert len(_recent_buttons(fake_ui)) == 1


def test_render_layout_preview_workbench_rejects_untrusted_preview_html(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=_spec_payload(),
        recent_presets=[],
        preview_html="<script>alert('raw')</script>",
        ui=fake_ui,
    )

    assert fake_components.html_calls == []
    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert (
        "\u6682\u65e0\u9884\u89c8 HTML\uff0c"
        "\u5b8c\u6210\u4e00\u6b21\u670d\u52a1\u7aef\u9884\u89c8"
        "\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002"
    ) in rendered
    assert fake_ui.infos == []


def test_render_layout_preview_workbench_handles_missing_spec_without_crashing(monkeypatch):
    from web.components import layout_preview_workbench

    fake_ui = _FakeUI()
    fake_components = _FakeComponents()
    monkeypatch.setattr(layout_preview_workbench, "components", fake_components)

    selected = layout_preview_workbench.render_layout_preview_workbench(
        spec_payload=None,
        recent_presets=[],
        preview_html=None,
        ui=fake_ui,
    )

    rendered = "\n".join(item["body"] for item in fake_ui.markdowns)
    assert selected is None
    assert "\u5373\u65f6\u9884\u89c8\u5de5\u4f5c\u53f0" in rendered
    assert "\u6682\u65e0\u53ef\u9884\u89c8\u7684\u6392\u7248\u89c4\u683c" in rendered
    assert (
        "\u6682\u65e0\u9884\u89c8 HTML\uff0c"
        "\u5b8c\u6210\u4e00\u6b21\u670d\u52a1\u7aef\u9884\u89c8"
        "\u540e\u4f1a\u663e\u793a\u5728\u8fd9\u91cc\u3002"
    ) in rendered
    assert fake_ui.infos == []
    assert fake_components.html_calls == []
