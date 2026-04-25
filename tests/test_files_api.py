from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers.files import get_file
from api.routers.files import router as files_router


@pytest.mark.asyncio
async def test_get_file_rejects_output_path_traversal(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "config.yaml").write_text("secret: value", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("output/../config.yaml")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_file_rejects_prefixed_traversal_into_another_allowed_root(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "leak.txt").write_text("secret", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("output/../resources/leak.txt")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_file_rejects_unprefixed_traversal_into_another_allowed_root(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "leak.txt").write_text("secret", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("../resources/leak.txt")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_file_allows_file_inside_output(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = await get_file("task-1/final.mp4")

    assert Path(response.path) == video


def _files_client() -> TestClient:
    app = FastAPI()
    app.include_router(files_router)
    return TestClient(app)


def test_stream_file_supports_range_requests(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=0-1"},
    )

    assert response.status_code == 206
    assert response.content == b"vi"
    assert response.headers["content-range"] == "bytes 0-1/5"
    assert response.headers["accept-ranges"] == "bytes"


def test_stream_file_without_range_returns_full_file(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/stream/task-1/final.mp4")

    assert response.status_code == 200
    assert response.content == b"video"
    assert response.headers["accept-ranges"] == "bytes"
    assert "content-range" not in response.headers


def test_stream_file_rejects_malformed_range(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=a-b"},
    )

    assert response.status_code == 416


def test_stream_file_rejects_unsatisfiable_range(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=99-100"},
    )

    assert response.status_code == 416


def test_download_file_uses_attachment_disposition(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/download/task-1/final.mp4")

    assert response.status_code == 200
    assert response.content == b"video"
    assert response.headers["content-disposition"] == 'attachment; filename="final.mp4"'
