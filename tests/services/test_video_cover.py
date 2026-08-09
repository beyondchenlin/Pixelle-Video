from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from pixelle_video.services.video_cover import COVER_SIZE, ensure_video_cover


def _build_task(tmp_path):
    output_root = tmp_path / "output"
    task_dir = output_root / "task-1"
    frames_dir = task_dir / "frames"
    frames_dir.mkdir(parents=True)
    video = task_dir / "final.mp4"
    video.write_bytes(b"video-placeholder")
    frame = frames_dir / "01_image.png"
    Image.new("RGB", (720, 1280), color=(20, 80, 160)).save(frame)
    return output_root, video, frame


def test_ensure_video_cover_creates_bounded_atomic_artifact(tmp_path):
    output_root, video, frame = _build_task(tmp_path)

    cover = ensure_video_cover(video, frame_paths=[frame], output_root=output_root)

    assert cover == output_root / "task-1" / "preview" / "home-cover.jpg"
    assert cover.is_file()
    with Image.open(cover) as image:
        assert image.size == COVER_SIZE
        assert image.format == "JPEG"
    assert cover.stat().st_size < 100_000


def test_ensure_video_cover_reuses_existing_artifact(tmp_path):
    output_root, video, frame = _build_task(tmp_path)
    cover = ensure_video_cover(video, frame_paths=[frame], output_root=output_root)
    assert cover is not None
    first_mtime = cover.stat().st_mtime_ns

    reused = ensure_video_cover(video, frame_paths=[frame], output_root=output_root)

    assert reused == cover
    assert reused.stat().st_mtime_ns == first_mtime


def test_ensure_video_cover_serializes_concurrent_first_access(tmp_path):
    output_root, video, frame = _build_task(tmp_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        covers = list(
            executor.map(
                lambda _index: ensure_video_cover(
                    video,
                    frame_paths=[frame],
                    output_root=output_root,
                ),
                range(8),
            )
        )

    assert len(set(covers)) == 1
    with Image.open(covers[0]) as image:
        image.verify()


def test_ensure_video_cover_rejects_video_outside_output(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir()
    video = tmp_path / "secret.mp4"
    video.write_bytes(b"secret")

    assert ensure_video_cover(video, output_root=output_root) is None


def test_ensure_video_cover_fails_closed_without_frame_or_extractor(tmp_path, monkeypatch):
    output_root = tmp_path / "output"
    task_dir = output_root / "task-1"
    task_dir.mkdir(parents=True)
    video = task_dir / "final.mp4"
    video.write_bytes(b"not-a-video")
    monkeypatch.setattr("pixelle_video.services.video_cover.shutil.which", lambda _name: None)

    assert ensure_video_cover(video, output_root=output_root) is None


def test_ensure_video_cover_does_not_escape_through_preview_symlink(tmp_path):
    output_root, video, frame = _build_task(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    preview = video.parent / "preview"
    try:
        preview.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    assert ensure_video_cover(video, frame_paths=[frame], output_root=output_root) is None
    assert not (outside / "home-cover.jpg").exists()


def test_ensure_video_cover_contains_optional_artifact_failures(tmp_path, monkeypatch):
    output_root, video, frame = _build_task(tmp_path)
    monkeypatch.setattr(
        "pixelle_video.services.video_cover._write_cover_from_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("broken image")),
    )

    assert ensure_video_cover(video, frame_paths=[frame], output_root=output_root) is None


def test_ensure_video_cover_rejects_excessive_pixel_dimensions(tmp_path, monkeypatch):
    output_root, video, frame = _build_task(tmp_path)
    monkeypatch.setattr("pixelle_video.services.video_cover.MAX_SOURCE_IMAGE_PIXELS", 10)

    assert ensure_video_cover(video, frame_paths=[frame], output_root=output_root) is None
