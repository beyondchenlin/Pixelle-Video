import inspect
import os

import pytest

from pixelle_video.storage.object_store import (
    FilesystemDevRawPayloadStore,
    RawPayloadInvalidError,
    RawPayloadNotFoundError,
    RawPayloadReadError,
    RawPayloadStore,
)

VALID_OBJECT_ID = "00000000000000000000000000000000"
WINDOWS_RESERVED_WORKSPACE_IDS = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
UNSAFE_WORKSPACE_IDS = [
    "a?b",
    "a*b",
    "a<b",
    "a>b",
    "a|b",
    'a"b',
    "a\nb",
    "workspace 1",
]
INVALID_STORAGE_KEYS = [
    "../secret.json",
    "raw-payloads/workspace-1/../../secret.json",
    "raw-payloads/workspace-1//x.json",
    "raw-payloads/workspace-1/./x.json",
    "raw-payloads/workspace-1/x/../y.json",
    "/raw-payloads/workspace-1/x.json",
    "C:/raw-payloads/workspace-1/x.json",
    "raw-payloads\\workspace-1\\x.json",
    "payloads/workspace-1/x.json",
    "raw-payloads/workspace-1/x.txt",
    "raw-payloads/workspace-1/.json",
    "raw-payloads/workspace-1/0.json",
    "raw-payloads/workspace-1/000000000000000000000000000000000.json",
    "raw-payloads/workspace-1/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.json",
    "raw-payloads/workspace-1/gggggggggggggggggggggggggggggggg.json",
    f"raw-payloads/workspace..1/{VALID_OBJECT_ID}.json",
    *[
        f"raw-payloads/{workspace_id}/{VALID_OBJECT_ID}.json"
        for workspace_id in UNSAFE_WORKSPACE_IDS
    ],
]


def test_raw_payload_store_contract_exposes_required_methods():
    assert inspect.iscoroutinefunction(RawPayloadStore.put_json)
    assert inspect.iscoroutinefunction(RawPayloadStore.get_json)
    assert inspect.iscoroutinefunction(RawPayloadStore.exists)


def test_filesystem_dev_store_contract_exposes_async_methods():
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.put_json)
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.get_json)
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.exists)


def test_storage_package_exports_public_contract_types():
    import pixelle_video.storage as storage

    assert storage.FilesystemDevRawPayloadStore is FilesystemDevRawPayloadStore
    assert storage.RawPayloadStore is RawPayloadStore
    assert storage.RawPayloadReadError is RawPayloadReadError
    assert storage.RawPayloadNotFoundError is RawPayloadNotFoundError
    assert storage.RawPayloadInvalidError is RawPayloadInvalidError


async def test_filesystem_dev_store_returns_storage_key_and_round_trips_payload(tmp_path):
    store = FilesystemDevRawPayloadStore(root=tmp_path)
    payload = {"prompt": "hello", "metadata": {"count": 2, "enabled": True}}

    storage_key = await store.put_json(workspace_id="workspace-1", payload=payload)
    object_id = storage_key.removeprefix("raw-payloads/workspace-1/").removesuffix(".json")

    assert storage_key.startswith("raw-payloads/workspace-1/")
    assert storage_key.endswith(".json")
    assert len(object_id) == 32
    assert object_id == object_id.lower()
    assert all(character in "0123456789abcdef" for character in object_id)
    assert not os.path.isabs(storage_key)
    assert "\\" not in storage_key

    assert await store.get_json(storage_key) == payload
    assert await store.exists(storage_key) is True


@pytest.mark.parametrize("workspace_id", WINDOWS_RESERVED_WORKSPACE_IDS)
async def test_filesystem_dev_store_round_trips_reserved_workspace_ids(
    tmp_path, workspace_id
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)
    payload = {"workspace_id": workspace_id}

    storage_key = await store.put_json(workspace_id=workspace_id, payload=payload)
    object_id = storage_key.removeprefix(f"raw-payloads/{workspace_id}/").removesuffix(
        ".json"
    )

    assert storage_key.startswith(f"raw-payloads/{workspace_id}/")
    assert len(object_id) == 32
    assert all(character in "0123456789abcdef" for character in object_id)
    assert await store.get_json(storage_key) == payload
    assert await store.exists(storage_key) is True


@pytest.mark.parametrize(
    "storage_key",
    INVALID_STORAGE_KEYS,
)
async def test_filesystem_dev_store_exists_rejects_non_canonical_keys(tmp_path, storage_key):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    assert await store.exists(storage_key) is False


@pytest.mark.parametrize(
    "storage_key",
    INVALID_STORAGE_KEYS,
)
async def test_filesystem_dev_store_get_json_rejects_non_canonical_keys(
    tmp_path, storage_key
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(ValueError):
        await store.get_json(storage_key)


async def test_filesystem_dev_store_get_json_raises_contract_error_for_missing_payload(
    tmp_path,
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(RawPayloadNotFoundError):
        await store.get_json(f"raw-payloads/workspace-1/{VALID_OBJECT_ID}.json")


@pytest.mark.parametrize(
    ("stored_text", "expected_error"),
    [
        ("not-json", RawPayloadInvalidError),
        ("[]", RawPayloadInvalidError),
    ],
)
async def test_filesystem_dev_store_get_json_raises_contract_error_for_invalid_payload(
    tmp_path, stored_text, expected_error
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)
    storage_key = await store.put_json(workspace_id="workspace-1", payload={"valid": True})
    target_path = store._path_for_storage_key(storage_key)
    target_path.write_text(stored_text, encoding="utf-8")

    with pytest.raises(expected_error):
        await store.get_json(storage_key)


async def test_filesystem_dev_store_get_json_raises_invalid_error_for_invalid_utf8(
    tmp_path,
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)
    storage_key = await store.put_json(workspace_id="workspace-1", payload={"valid": True})
    target_path = store._path_for_storage_key(storage_key)
    target_path.write_bytes(b"\xff\xfe")

    with pytest.raises(RawPayloadInvalidError):
        await store.get_json(storage_key)


@pytest.mark.parametrize(
    "workspace_id",
    [
        "../workspace-1",
        "workspace/1",
        "workspace\\1",
        "workspace..1",
        "..",
        *UNSAFE_WORKSPACE_IDS,
    ],
)
async def test_filesystem_dev_store_rejects_workspace_ids_with_path_syntax(
    tmp_path, workspace_id
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(ValueError):
        await store.put_json(workspace_id=workspace_id, payload={"value": 1})
