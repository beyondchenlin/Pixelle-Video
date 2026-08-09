from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from pixelle_video.services.remote_media import (
    RemoteMediaError,
    materialize_media_source,
)
from pixelle_video.utils.path_safety import resolve_path_within, validate_task_id
from web.utils.upload_store import IMAGE_UPLOAD_POLICY, store_uploaded_files


class UploadedFileStub:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self._content = content

    def getbuffer(self) -> memoryview:
        return memoryview(self._content)


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(output, format="PNG")
    return output.getvalue()


def _mp4_bytes(payload: bytes = b"video") -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom" + payload


@pytest.mark.parametrize(
    "task_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "nested/task",
        r"nested\task",
        " task",
        "CON",
        "nul.txt",
        "task.",
    ],
)
def test_task_ids_reject_unsafe_path_components(task_id: str) -> None:
    with pytest.raises(ValueError):
        validate_task_id(task_id)


def test_resolve_path_within_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_path_within(tmp_path, "..", "escape")


def test_resolve_path_within_rejects_absolute_component_even_below_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="relative"):
        resolve_path_within(tmp_path, tmp_path / "child")


def test_upload_store_uses_generated_name_and_validates_image(tmp_path: Path) -> None:
    stored = store_uploaded_files(
        [UploadedFileStub("portrait.png", _png_bytes())],
        tmp_path,
        policy=IMAGE_UPLOAD_POLICY,
    )

    stored_path = Path(stored[0])
    assert stored_path.parent == tmp_path.resolve()
    assert stored_path.name != "portrait.png"
    assert stored_path.suffix == ".png"
    assert stored_path.read_bytes() == _png_bytes()


def test_upload_store_reuses_content_addressed_file_on_rerun(tmp_path: Path) -> None:
    upload = UploadedFileStub("portrait.png", _png_bytes())

    first = store_uploaded_files([upload], tmp_path, policy=IMAGE_UPLOAD_POLICY)
    second = store_uploaded_files([upload], tmp_path, policy=IMAGE_UPLOAD_POLICY)

    assert first == second
    assert len(list(tmp_path.glob("upload_*.png"))) == 1


@pytest.mark.parametrize("name", ["../portrait.png", r"..\portrait.png", "/portrait.png"])
def test_upload_store_rejects_path_like_filenames(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="plain basename"):
        store_uploaded_files(
            [UploadedFileStub(name, _png_bytes())],
            tmp_path,
            policy=IMAGE_UPLOAD_POLICY,
        )


def test_upload_store_rejects_extension_content_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid|match"):
        store_uploaded_files(
            [UploadedFileStub("portrait.png", b"not an image")],
            tmp_path,
            policy=IMAGE_UPLOAD_POLICY,
        )


@pytest.mark.asyncio
async def test_remote_media_streams_valid_content_atomically(tmp_path: Path) -> None:
    payload = _mp4_bytes()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "8.8.8.8"
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4", "content-length": str(len(payload))},
            content=payload,
        )

    target = tmp_path / "final.mp4"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await materialize_media_source(
            "https://8.8.8.8/output.mp4",
            target,
            media_type="video",
            client=client,
        )

    assert result == target.resolve()
    assert target.read_bytes() == payload


@pytest.mark.asyncio
async def test_remote_media_blocks_untrusted_private_network(tmp_path: Path) -> None:
    target = tmp_path / "final.mp4"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=_mp4_bytes()))
    ) as client:
        with pytest.raises(RemoteMediaError, match="non-public"):
            await materialize_media_source(
                "http://127.0.0.1/output.mp4",
                target,
                media_type="video",
                client=client,
            )


@pytest.mark.asyncio
async def test_remote_media_allows_explicit_private_origin(tmp_path: Path) -> None:
    target = tmp_path / "final.mp4"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=_mp4_bytes()))
    ) as client:
        await materialize_media_source(
            "http://127.0.0.1:8188/output.mp4",
            target,
            media_type="video",
            trusted_private_origins=("http://127.0.0.1:8188",),
            client=client,
        )

    assert target.read_bytes() == _mp4_bytes()


@pytest.mark.asyncio
async def test_remote_media_preserves_existing_target_after_failed_download(
    tmp_path: Path,
) -> None:
    target = tmp_path / "final.mp4"
    target.write_bytes(b"existing")
    oversized = _mp4_bytes(b"x" * 100)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=oversized))
    ) as client:
        with pytest.raises(RemoteMediaError, match="byte limit"):
            await materialize_media_source(
                "https://8.8.8.8/output.mp4",
                target,
                media_type="video",
                max_bytes=32,
                client=client,
            )

    assert target.read_bytes() == b"existing"


@pytest.mark.asyncio
async def test_local_media_must_be_within_trusted_runtime_root(tmp_path: Path) -> None:
    trusted_root = tmp_path / "trusted"
    trusted_target_dir = trusted_root / "nested"
    untrusted_root = tmp_path / "untrusted"
    trusted_target_dir.mkdir(parents=True)
    untrusted_root.mkdir()
    source = untrusted_root / "source.mp4"
    source.write_bytes(_mp4_bytes())

    with pytest.raises(RemoteMediaError, match="trusted runtime roots"):
        await materialize_media_source(
            str(source),
            trusted_target_dir / "final.mp4",
            media_type="video",
        )
