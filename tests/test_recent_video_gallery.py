import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from web.components import recent_video_gallery as gallery


def test_normalize_history_task_skips_missing_video_file(tmp_path):
    task = {
        "task_id": "task-1",
        "title": "Missing",
        "video_path": str(tmp_path / "missing.mp4"),
        "duration": 1.2,
        "n_frames": 3,
        "created_at": "2026-04-24T01:00:00",
        "completed_at": "2026-04-24T01:01:00",
    }

    assert gallery.normalize_recent_video_item(task, file_exists=lambda value: Path(value).exists()) is None


def test_merge_recent_video_items_puts_current_first_and_dedupes(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    history_video = tmp_path / "history.mp4"
    history_video.write_bytes(b"video")
    current = {
        "task_id": "task-current",
        "title": "Current",
        "video_path": str(video),
        "duration": 9.0,
        "n_frames": 5,
        "created_at": "2026-04-24T02:00:00",
        "source": "current",
    }
    history = [
        {**current, "source": "history"},
        {
            "task_id": "task-history",
            "title": "History",
            "video_path": str(history_video),
            "duration": 4.0,
            "n_frames": 2,
            "created_at": "2026-04-24T01:00:00",
            "source": "history",
        },
    ]

    merged = gallery.merge_recent_video_items(current, history, limit=4)

    assert [item["task_id"] for item in merged] == ["task-current", "task-history"]


def test_fetch_recent_history_video_items_scans_pages_until_limit(tmp_path):
    valid_paths = []
    for index in range(4):
        path = tmp_path / f"valid-{index}.mp4"
        path.write_bytes(b"video")
        valid_paths.append(str(path))

    pages = {
        1: {
            "tasks": [
                {"task_id": "bad-1", "video_path": str(tmp_path / "missing-1.mp4")},
                {"task_id": "bad-2", "video_path": str(tmp_path / "missing-2.mp4")},
            ],
            "total_pages": 3,
        },
        2: {
            "tasks": [
                {
                    "task_id": f"valid-{index}",
                    "title": f"Valid {index}",
                    "video_path": valid_paths[index],
                    "duration": float(index),
                    "n_frames": index + 1,
                    "created_at": f"2026-04-24T0{index}:00:00",
                    "completed_at": f"2026-04-24T0{index}:01:00",
                }
                for index in range(3)
            ],
            "total_pages": 3,
        },
        3: {
            "tasks": [
                {
                    "task_id": "valid-3",
                    "title": "Valid 3",
                    "video_path": valid_paths[3],
                    "duration": 3.0,
                    "n_frames": 4,
                    "created_at": "2026-04-24T03:00:00",
                    "completed_at": "2026-04-24T03:01:00",
                }
            ],
            "total_pages": 3,
        },
    }

    class FakeHistory:
        async def get_task_list(self, **kwargs):
            return pages[kwargs["page"]]

    class FakePixelleVideo:
        history = FakeHistory()

    items = gallery.fetch_recent_history_video_items(
        FakePixelleVideo(),
        runner=lambda awaitable: asyncio.run(awaitable),
        file_exists=lambda value: Path(value).exists(),
    )

    assert [item["task_id"] for item in items] == ["valid-0", "valid-1", "valid-2", "valid-3"]


def test_store_and_clear_recent_generated_video(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    session_state = {}
    result = SimpleNamespace(
        video_path=str(video),
        duration=12.5,
        created_at=datetime.fromisoformat("2026-04-24T02:00:00"),
        storyboard=SimpleNamespace(
            title="Generated",
            config=SimpleNamespace(task_id="task-generated"),
            frames=[object(), object()],
        ),
    )

    gallery.store_recent_generated_video(result, session_state)
    assert session_state[gallery.RECENT_GENERATED_VIDEO_KEY]["task_id"] == "task-generated"
    assert session_state[gallery.RECENT_GENERATED_VIDEO_KEY]["n_frames"] == 2

    gallery.clear_recent_generated_video(session_state)
    assert gallery.RECENT_GENERATED_VIDEO_KEY not in session_state


def test_get_current_recent_video_item_clears_missing_session_video(tmp_path):
    session_state = {
        gallery.RECENT_GENERATED_VIDEO_KEY: {
            "task_id": "task-current",
            "title": "Current",
            "video_path": str(tmp_path / "deleted.mp4"),
            "duration": 12.5,
            "n_frames": 2,
            "created_at": "2026-04-24T02:00:00",
        }
    }

    current = gallery.get_current_recent_video_item(
        session_state,
        file_exists=lambda value: Path(value).exists(),
    )

    assert current is None
    assert gallery.RECENT_GENERATED_VIDEO_KEY not in session_state


def test_build_recent_video_gallery_css_is_scoped_and_responsive():
    css = gallery.build_recent_video_gallery_css()

    assert gallery.RECENT_VIDEO_LIMIT == 9
    assert ".st-key-recent_video_gallery" in css
    assert ".st-key-recent_video_grid" in css
    assert f".st-key-{gallery.RECENT_VIDEO_GRID_KEY} {{" in css
    assert "repeat(auto-fill, minmax(min(220px, 100%), 1fr))" in css
    assert "justify-content: stretch" in css
    assert "gap: 0.65rem" in css
    assert f'.st-key-{gallery.RECENT_VIDEO_GRID_KEY} > div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"]' in css
    assert "padding: 0.5rem !important" in css
    assert ".recent-video-placeholder" in css
    assert "linear-gradient" in css
    assert "min-height: 4.5rem" in css
    assert ".recent-video-section-title" in css
    assert "margin: 0 0 0.55rem" in css
    assert ":has(.recent-video-info)" in css
    assert "margin-bottom: 0 !important" in css
    assert ".recent-video-info" in css
    assert "gap: 0.2rem" in css
    assert ".recent-video-title" in css
    assert "margin: 0" in css
    assert '.st-key-recent_video_grid div[data-testid="stHorizontalBlock"]' in css
    assert "width: min(8.5rem, 72%)" in css
    assert "margin-inline: auto" in css
    assert "justify-content: space-between" in css
    assert "flex: 0 0 auto !important" in css
    assert ".st-key-recent_video_gallery .stColumn button" in css
    assert "min-height: 1.45rem" in css
    assert "padding: 0" in css
    assert f".st-key-{gallery.RECENT_VIDEO_GRID_KEY} > div[data-testid=\"stVerticalBlock\"]" not in css


def test_render_recent_video_gallery_applies_refresh_key_suffix(monkeypatch):
    captured = {"containers": [], "card_suffixes": [], "css": []}

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeStreamlit:
        session_state = {}

        def markdown(self, body, **_kwargs):
            captured["css"].append(body)

        def container(self, **kwargs):
            captured["containers"].append(kwargs.get("key"))
            return _FakeContext()

        def info(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(gallery, "st", _FakeStreamlit())
    monkeypatch.setattr(gallery, "get_current_recent_video_item", lambda _state: None)
    monkeypatch.setattr(
        gallery,
        "fetch_recent_history_video_items",
        lambda _pixelle_video: [{"task_id": "task-1", "video_path": "final.mp4"}],
    )
    monkeypatch.setattr(
        gallery,
        "render_recent_video_card",
        lambda _item, *, api_base_url, key_suffix="": captured["card_suffixes"].append(
            key_suffix
        ),
    )

    gallery.render_recent_video_gallery(object(), key_suffix="_refresh_2")

    assert gallery.RECENT_VIDEO_GALLERY_KEY + "_refresh_2" in captured["containers"]
    assert gallery.RECENT_VIDEO_GRID_KEY + "_refresh_2" in captured["containers"]
    assert captured["card_suffixes"] == ["_refresh_2"]
    assert f".st-key-{gallery.RECENT_VIDEO_GALLERY_KEY}_refresh_2" in captured["css"][0]


def test_render_recent_video_card_links_to_file_service_without_loading_media(monkeypatch):
    captured = {"links": [], "markdown": [], "buttons": []}

    class _FakeContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeStreamlit:
        session_state = {}

        def container(self, **_kwargs):
            return _FakeContext()

        def columns(self, count, **_kwargs):
            return [_FakeContext() for _ in range(count)]

        def markdown(self, body, **_kwargs):
            captured["markdown"].append(body)

        def button(self, label, **kwargs):
            captured["buttons"].append((label, kwargs))
            return False

        def link_button(self, label, url, **kwargs):
            captured["links"].append((label, url, kwargs))

    monkeypatch.setattr(gallery, "st", _FakeStreamlit())
    monkeypatch.setattr(gallery, "tr", lambda key: key)
    monkeypatch.setattr(
        gallery,
        "build_output_media_urls",
        lambda *_args, **_kwargs: SimpleNamespace(
            stream_url="http://127.0.0.1:6789/api/files/stream/output/task/final.mp4",
            download_url="http://127.0.0.1:6789/api/files/download/output/task/final.mp4"
        ),
    )

    gallery.render_recent_video_card(
        {
            "task_id": "task-1",
            "title": "Safe video",
            "video_path": "output/task/final.mp4",
            "duration": 1.0,
            "n_frames": 1,
        }
    )

    assert len(captured["links"]) == 2
    assert captured["links"][0][1].endswith("/output/task/final.mp4")
    assert captured["links"][1][1].endswith("/output/task/final.mp4")
    assert any("recent-video-placeholder" in body for body in captured["markdown"])
