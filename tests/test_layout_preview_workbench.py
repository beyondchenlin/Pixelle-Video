from pixelle_video.models.layered_template import LayeredTemplateSpec
from web.components import layout_preview_workbench
from web.components.layered_template_state import LAYERED_TEMPLATE_EDITOR_STATE_KEY


def _spec_payload(template_id="demo", *, canvas_width=1080, canvas_height=1920):
    return {
        "version": "layered_template.v1",
        "template_id": template_id,
        "template_name": "Demo",
        "template_type": "image",
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
        "media_width": canvas_width,
        "media_height": canvas_height,
        "safe_area": {
            "x": 64,
            "y": 64,
            "width": canvas_width - 128,
            "height": canvas_height - 128,
            "unit": "px",
        },
        "layers": [],
        "metadata": {},
    }


def test_recent_template_shortcuts_are_sorted_by_last_used_desc():
    items = [
        {"preset_id": "a", "name": "A", "last_used_at": "2026-05-02T08:00:00Z"},
        {"preset_id": "b", "name": "B", "last_used_at": "2026-05-02T10:00:00Z"},
        {"preset_id": "c", "name": "C", "last_used_at": "2026-05-02T09:00:00Z"},
    ]

    ordered = layout_preview_workbench.sort_recent_template_shortcuts(items, limit=2)

    assert [item["preset_id"] for item in ordered] == ["b", "c"]


def test_recent_template_shortcut_loads_full_spec_into_editor_state(monkeypatch):
    current_spec = _spec_payload("current", canvas_width=720, canvas_height=1280)
    recent_spec = _spec_payload("recent", canvas_width=1280, canvas_height=720)
    captured = {"buttons": [], "used": []}

    class _Context:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeStreamlit:
        def __init__(self):
            self.session_state = {}

        def container(self, **_kwargs):
            return _Context()

        def markdown(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

        def button(self, label, **kwargs):
            captured["buttons"].append((label, kwargs))
            return kwargs["key"] == "recent_template_recent"

    class _Registry:
        def mark_used(self, preset_id):
            captured["used"].append(preset_id)

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(layout_preview_workbench, "st", fake_st)
    monkeypatch.setattr(
        layout_preview_workbench,
        "render_layered_template_preview_html",
        lambda **_kwargs: "<div>preview</div>",
    )

    layout_preview_workbench.render_layout_preview_workbench(
        spec=current_spec,
        title_text="Title",
        caption_text="Caption",
        text_rendering={},
        recent_templates=[
            {
                "preset_id": "recent",
                "name": "Recent",
                "last_used_at": "2026-05-02T10:00:00Z",
                "spec": LayeredTemplateSpec.from_dict(recent_spec),
            }
        ],
        real_preview_state=None,
        registry=_Registry(),
        session_state=fake_st.session_state,
    )

    loaded = fake_st.session_state[LAYERED_TEMPLATE_EDITOR_STATE_KEY]
    assert captured["used"] == ["recent"]
    assert (loaded.canvas_width, loaded.canvas_height) == (1280, 720)
