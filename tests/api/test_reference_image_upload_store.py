import io

import pytest
from fastapi import UploadFile
from PIL import Image

from api.reference_image_upload_store import ReferenceImageUploadStore
from pixelle_video.services.resource_resolver import ResourceResolverError


def _upload_file(name="reference.png", size=(4, 3)) -> UploadFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buffer, format="PNG")
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


def test_reference_image_upload_store_rejects_path_like_id(tmp_path):
    store = ReferenceImageUploadStore(base_dir=tmp_path)

    with pytest.raises(Exception):
        store.resolve_upload_id("../secret")
