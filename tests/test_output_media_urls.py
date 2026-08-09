from __future__ import annotations

from urllib.parse import unquote, urlsplit

import pytest

from web.utils.output_media_urls import OutputMediaUrls, build_output_media_urls


def test_output_media_urls_preserves_legacy_positional_constructor():
    urls = OutputMediaUrls("stream", "download", "output/task/final.mp4")

    assert urls.storage_path == "output/task/final.mp4"
    assert urls.cover_url is None


def test_build_output_media_urls_uses_streaming_api_for_file_under_output(tmp_path):
    output_root = tmp_path / "output"
    video = output_root / "任务 一" / "final #1.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    urls = build_output_media_urls(
        video,
        api_base_url="http://127.0.0.1:6789/api",
        output_root=output_root,
    )

    assert urls is not None
    assert urls.storage_path == "output/任务 一/final #1.mp4"
    assert unquote(urlsplit(urls.stream_url).path) == (
        "/api/files/stream/output/任务 一/final #1.mp4"
    )
    assert unquote(urlsplit(urls.download_url).path) == (
        "/api/files/download/output/任务 一/final #1.mp4"
    )
    assert unquote(urlsplit(urls.cover_url).path) == (
        "/api/files/cover/output/任务 一/final #1.mp4"
    )


def test_build_output_media_urls_accepts_output_prefixed_relative_path(tmp_path):
    output_root = tmp_path / "output"
    video = output_root / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    urls = build_output_media_urls(
        "output/task-1/final.mp4",
        api_base_url="https://pixelle.example/api/",
        output_root=output_root,
    )

    assert urls is not None
    assert urls.download_url == (
        "https://pixelle.example/api/files/download/output/task-1/final.mp4"
    )


def test_build_output_media_urls_encodes_preferred_download_name(tmp_path):
    output_root = tmp_path / "output"
    video = output_root / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    urls = build_output_media_urls(
        video,
        api_base_url="http://127.0.0.1:6789/api",
        output_root=output_root,
        download_name="客户 标题.mp4",
    )

    assert urls is not None
    assert urls.download_url.endswith("?filename=%E5%AE%A2%E6%88%B7%20%E6%A0%87%E9%A2%98.mp4")


@pytest.mark.parametrize("candidate_name", ["missing.mp4", "directory"])
def test_build_output_media_urls_rejects_non_file_targets(tmp_path, candidate_name):
    output_root = tmp_path / "output"
    output_root.mkdir()
    if candidate_name == "directory":
        (output_root / candidate_name).mkdir()

    assert (
        build_output_media_urls(
            candidate_name,
            api_base_url="http://127.0.0.1:6789/api",
            output_root=output_root,
        )
        is None
    )


def test_build_output_media_urls_rejects_file_outside_output(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    assert (
        build_output_media_urls(
            secret,
            api_base_url="http://127.0.0.1:6789/api",
            output_root=output_root,
        )
        is None
    )


def test_build_output_media_urls_rejects_symlink_escape_when_supported(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir()
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"secret")
    link = output_root / "linked.mp4"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks are not available in this environment")

    assert (
        build_output_media_urls(
            link,
            api_base_url="http://127.0.0.1:6789/api",
            output_root=output_root,
        )
        is None
    )


def test_build_output_media_urls_fails_closed_for_credentialed_api_origin(tmp_path):
    output_root = tmp_path / "output"
    video = output_root / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")

    assert (
        build_output_media_urls(
            video,
            api_base_url="http://user:secret@127.0.0.1:6789/api",
            output_root=output_root,
        )
        is None
    )
