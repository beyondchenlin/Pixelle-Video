from pathlib import Path

from web.components import output_preview

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_video_preview_css_overrides_streamlit_inline_width():
    css = output_preview.build_video_preview_css("output_preview_media", width="50%")

    assert ".st-key-output_preview_media [data-testid=\"stVideo\"]" in css
    assert "width: 50% !important;" in css
    assert "max-width: 100% !important;" in css
    assert "margin-inline: auto;" in css
    assert "display: block;" in css


def test_render_scaled_video_preview_uses_scoped_container(monkeypatch):
    captured = {}

    class _FakeContainer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit:
        def markdown(self, body, *, unsafe_allow_html):
            captured["markdown"] = (body, unsafe_allow_html)

        def container(self, *, key):
            captured["container_key"] = key
            return _FakeContainer()

        def video(self, path, *, width):
            captured["video"] = (path, width)

    monkeypatch.setattr(output_preview, "st", FakeStreamlit())

    output_preview.render_scaled_video_preview("final.mp4")

    css, unsafe = captured["markdown"]
    assert unsafe is True
    assert ".st-key-output_video_preview [data-testid=\"stVideo\"]" in css
    assert captured["container_key"] == "output_video_preview"
    assert captured["video"] == ("final.mp4", "stretch")


def test_video_generation_pipelines_use_shared_scaled_preview_renderer():
    files = [
        PROJECT_ROOT / "web" / "components" / "output_preview.py",
        PROJECT_ROOT / "web" / "pipelines" / "asset_based.py",
        PROJECT_ROOT / "web" / "pipelines" / "i2v.py",
        PROJECT_ROOT / "web" / "pipelines" / "digital_human.py",
        PROJECT_ROOT / "web" / "pipelines" / "action_transfer.py",
    ]

    for path in files:
        source = path.read_text(encoding="utf-8")
        assert "render_scaled_video_preview(" in source, f"{path.name} should use shared preview renderer"
