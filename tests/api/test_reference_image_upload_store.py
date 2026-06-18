import io
import json

import pytest
from fastapi import UploadFile
from PIL import Image

from api.reference_image_upload_store import ReferenceImageUploadStore
from pixelle_video.services.resource_resolver import ResourceResolverError


def _upload_file(name="reference.png", size=(4, 3), image_format="PNG") -> UploadFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buffer, format=image_format)
    buffer.seek(0)
    return UploadFile(filename=name, file=buffer)


@pytest.mark.asyncio
async def test_reference_image_upload_store_round_trip(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path, max_upload_size_mb=1)

    record = await store.store_upload(_upload_file())
    resolved_by_upload = store.resolve_upload_id(record.upload_id)
    resolved_by_artifact = store.resolve_artifact_id(record.artifact_id)

    assert resolved_by_upload.local_path == resolved_by_artifact.local_path
    assert resolved_by_upload.sha256 == record.sha256
    assert resolved_by_upload.width == 4
    assert resolved_by_upload.height == 3
    assert str(tmp_path) not in str(resolved_by_upload.to_trace_dict())


@pytest.mark.asyncio
async def test_reference_image_upload_store_rejects_non_image(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path, max_upload_size_mb=1)
    upload = UploadFile(filename="not_image.png", file=io.BytesIO(b"not an image"))

    with pytest.raises(ResourceResolverError, match="not a valid image"):
        await store.store_upload(upload)


@pytest.mark.asyncio
async def test_reference_image_upload_store_rejects_disguised_unsupported_format(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path, max_upload_size_mb=1)
    upload = _upload_file(name="reference.png", image_format="BMP")

    with pytest.raises(ResourceResolverError, match="unsupported reference image format"):
        await store.store_upload(upload)


@pytest.mark.asyncio
async def test_reference_image_upload_store_rejects_oversized_dimensions(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path, max_upload_size_mb=1, max_edge_px=4)
    upload = _upload_file(name="too_large.png", size=(8, 8))

    with pytest.raises(ResourceResolverError, match="dimensions exceed"):
        await store.store_upload(upload)


def test_reference_image_upload_store_rejects_path_like_id(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path)

    with pytest.raises(Exception):
        store.resolve_upload_id("../secret")


def test_resolve_record_rejects_metadata_file_name_escape(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path)
    record_root = tmp_path / "rimg_test"
    record_root.mkdir()
    secret = tmp_path / "secret.png"
    Image.new("RGB", (2, 2), (255, 255, 255)).save(secret, format="PNG")
    (record_root / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "pixelle.reference_image_upload.v1",
                "record": {
                    "upload_id": "rimg_test",
                    "artifact_id": "rimg_test",
                    "sha256": "",
                    "mime_type": "image/png",
                    "width": 2,
                    "height": 2,
                    "byte_size": secret.stat().st_size,
                    "original_display_name": "reference.png",
                },
                "file_name": "../secret.png",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResourceResolverError, match="escaped record directory"):
        store.resolve_upload_id("rimg_test")


def test_resolve_record_rejects_hash_mismatch(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path)
    record_root = tmp_path / "rimg_test"
    record_root.mkdir()
    image_path = record_root / "upload.png"
    Image.new("RGB", (2, 2), (255, 255, 255)).save(image_path, format="PNG")
    (record_root / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "pixelle.reference_image_upload.v1",
                "record": {
                    "upload_id": "rimg_test",
                    "artifact_id": "rimg_test",
                    "sha256": "b" * 64,
                    "mime_type": "image/png",
                    "width": 2,
                    "height": 2,
                    "byte_size": image_path.stat().st_size,
                    "original_display_name": "reference.png",
                },
                "file_name": "upload.png",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResourceResolverError, match="hash does not match"):
        store.resolve_upload_id("rimg_test")


def test_cleanup_requires_explicit_allow_cleanup(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path)

    with pytest.raises(ResourceResolverError, match="cleanup is disabled"):
        store.cleanup()
