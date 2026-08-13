from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path


def _load_history_page():
    pages_dir = Path(__file__).resolve().parents[1] / "web" / "pages"
    module_path = next(pages_dir.glob("*_History.py"))
    spec = importlib.util.spec_from_file_location(
        "history_media_lifecycle_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HISTORY_PAGE = _load_history_page()


def test_history_media_urls_use_configured_stable_file_service(monkeypatch):
    captured = {}
    expected = HISTORY_PAGE.OutputMediaUrls(
        stream_url="http://127.0.0.1:6789/api/files/stream/output/task-1/final.mp4",
        download_url="http://127.0.0.1:6789/api/files/download/output/task-1/final.mp4",
        cover_url="http://127.0.0.1:6789/api/files/cover/output/task-1/final.mp4",
        storage_path="output/task-1/final.mp4",
    )
    monkeypatch.setitem(
        HISTORY_PAGE.st.session_state,
        "api_base_url",
        "http://127.0.0.1:6789/api",
    )

    def _build(video_path, **kwargs):
        captured.update(video_path=video_path, **kwargs)
        return expected

    monkeypatch.setattr(HISTORY_PAGE, "build_output_media_urls", _build)

    result = HISTORY_PAGE.build_history_media_urls(
        "output/task-1/final.mp4",
        download_name="测试视频.mp4",
    )

    assert result is expected
    assert captured == {
        "video_path": "output/task-1/final.mp4",
        "api_base_url": "http://127.0.0.1:6789/api",
        "download_name": "测试视频.mp4",
    }


def test_history_video_cover_uses_lazy_api_media_without_streamlit_storage(
    monkeypatch,
):
    rendered = []
    monkeypatch.setattr(
        HISTORY_PAGE.st,
        "markdown",
        lambda body, **kwargs: rendered.append((body, kwargs)),
    )
    urls = HISTORY_PAGE.OutputMediaUrls(
        stream_url="http://127.0.0.1:6789/api/files/stream/output/task/final.mp4?x=<bad>",
        download_url="http://127.0.0.1:6789/api/files/download/output/task/final.mp4",
        cover_url="http://127.0.0.1:6789/api/files/cover/output/task/final.mp4",
        storage_path="output/task/final.mp4",
    )

    assert HISTORY_PAGE.render_history_video_cover(
        urls,
        title='title <script>alert("x")</script>',
    ) is True

    body, kwargs = rendered[0]
    assert "loading=\"lazy\"" in body
    assert "fetchpriority=\"low\"" in body
    assert "history-video-cover-play" in body
    assert "aria-hidden=\"true\"" in body
    assert "&lt;bad&gt;" in body
    assert "<script>" not in body
    assert kwargs == {"unsafe_allow_html": True}


def test_history_video_cover_has_keyboard_focus_and_reduced_motion_styles():
    css = HISTORY_PAGE.build_history_page_css()

    assert ".history-video-cover-link:focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_history_list_never_opens_video_or_registers_local_media():
    grid_source = inspect.getsource(HISTORY_PAGE.render_grid_task_card)
    page_source = Path(HISTORY_PAGE.__file__).read_text(encoding="utf-8")

    assert "st.video" not in grid_source
    assert "render_history_video_cover" in grid_source
    assert "st.video(video_path" not in page_source
    assert "st.video(frame.video_segment_path" not in page_source
    assert "st.download_button(" not in page_source
    assert page_source.count("st.video(media_urls.stream_url") == 1
    assert "st.video(segment_media_urls.stream_url)" in page_source
