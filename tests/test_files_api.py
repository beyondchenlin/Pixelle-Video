from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from api.file_access import sanitize_upload_filename
from api.routers import files as files_router_module
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


@pytest.mark.asyncio
async def test_get_file_returns_404_for_missing_file(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("missing.mp4")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_file_returns_400_for_directory_path(monkeypatch, tmp_path):
    directory = tmp_path / "output" / "task-1"
    directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("task-1")

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_file_hides_internal_exception_details(monkeypatch):
    secret = r"D:\private\customer-secret.txt"

    def fail_resolution(_file_path):
        raise RuntimeError(f"failed to open {secret}")

    monkeypatch.setattr(files_router_module, "resolve_allowed_file_path", fail_resolution)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("final.mp4")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "File service failed"
    assert secret not in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relative_path", "expected_bytes"),
    [
        ("data/reference_audio/voice.wav", b"voice"),
        ("data/materials/clip.png", b"image"),
    ],
)
async def test_get_file_allows_data_asset_prefixes(monkeypatch, tmp_path, relative_path, expected_bytes):
    asset = tmp_path / relative_path
    asset.parent.mkdir(parents=True)
    asset.write_bytes(expected_bytes)
    monkeypatch.chdir(tmp_path)

    response = await get_file(relative_path)

    assert Path(response.path) == asset


def _files_client() -> TestClient:
    app = FastAPI()
    app.include_router(files_router)
    return TestClient(app)


def test_video_cover_endpoint_creates_and_reuses_small_preview(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    frame = video.parent / "frames" / "01_image.png"
    frame.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    Image.new("RGB", (720, 1280), color="navy").save(frame)
    monkeypatch.chdir(tmp_path)

    first = _files_client().get("/files/cover/output/task-1/final.mp4")
    second = _files_client().get("/files/cover/output/task-1/final.mp4")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.headers["cache-control"] == "private, max-age=3600"
    assert first.content == second.content
    assert len(first.content) < 100_000


def test_video_cover_endpoint_rejects_non_output_file(monkeypatch, tmp_path):
    resource = tmp_path / "resources" / "sample.mp4"
    resource.parent.mkdir(parents=True)
    resource.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get("/files/cover/resources/sample.mp4")

    assert response.status_code == 404


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


def test_download_file_uses_safe_preferred_filename(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/download/task-1/final.mp4",
        params={"filename": "Customer Story.mov"},
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename*=utf-8''Customer%20Story.mp4"
    )


def test_download_file_falls_back_for_unsafe_preferred_filename(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = _files_client().get(
        "/files/download/task-1/final.mp4",
        params={"filename": "../secret.txt"},
    )

    assert response.status_code == 200
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


@pytest.mark.parametrize(
    "filename",
    [
        'bad"name.txt',
        "bad<name.txt",
        "bad>name.txt",
        "bad|name.txt",
        "bad?name.txt",
        "bad*name.txt",
    ],
)
def test_sanitize_upload_filename_rejects_windows_illegal_characters(filename):
    with pytest.raises(HTTPException) as exc_info:
        sanitize_upload_filename(filename)

    assert exc_info.value.status_code == 400
