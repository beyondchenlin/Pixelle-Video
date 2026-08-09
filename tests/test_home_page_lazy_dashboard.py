from pathlib import Path


def test_home_dashboard_returns_before_generation_core_initialization():
    source = (
        Path(__file__).resolve().parents[1] / "web" / "pages" / "1_🎬_Home.py"
    ).read_text(encoding="utf-8")

    dashboard_boundary = source.index("if not editor_open:")
    dashboard_return = source.index("return", dashboard_boundary)
    core_initialization = source.index("pixelle_video = get_pixelle_video()")

    assert dashboard_boundary < dashboard_return < core_initialization
    assert 'render_recent_video_gallery(None, key_suffix="_dashboard")' in source
