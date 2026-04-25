from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.file_access import sanitize_upload_filename
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


def test_stream_empty_file_without_range_returns_empty_response(monkeypatch, tmp_path):
    empty_file = tmp_path / "output" / "empty.mp4"
    empty_file.parent.mkdir(parents=True)
    empty_file.write_bytes(b"")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/stream/empty.mp4")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-length"] == "0"
    assert response.headers["accept-ranges"] == "bytes"


def test_stream_file_clamps_overlong_range_end(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/stream/task-1/final.mp4",
        headers={"Range": "bytes=0-999"},
    )

    assert response.status_code == 206
    assert response.content == b"video"
    assert response.headers["content-range"] == "bytes 0-4/5"


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
    assert response.headers["content-range"] == "bytes */5"


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
    assert response.headers["content-range"] == "bytes */5"


def test_download_file_uses_attachment_disposition(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/download/task-1/final.mp4")

    assert response.status_code == 200
    assert response.content == b"video"
    assert response.headers["content-disposition"] == 'attachment; filename="final.mp4"'


def test_get_file_uses_inline_disposition(monkeypatch, tmp_path):
    image = tmp_path / "output" / "preview.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/preview.png")

    assert response.status_code == 200
    assert response.content == b"image"
    assert response.headers["content-disposition"] == 'inline; filename="preview.png"'


@pytest.mark.parametrize(
    "filename",
    [
        "",
        ".",
        "..",
        "bad\x00name.txt",
        "bad\x1fname.txt",
        "clip.mp4:ads",
        "trailing.",
        "trailing ",
        "CON",
        "nul.txt",
        "PrN",
        "aux.png",
        "COM1",
        "com9.txt",
        "LPT1",
        "lpt9.txt",
        "CONIN$",
        "conout$.txt",
    ],
)
def test_sanitize_upload_filename_rejects_risky_names(filename):
    with pytest.raises(HTTPException) as exc_info:
        sanitize_upload_filename(filename)

    assert exc_info.value.status_code == 400
