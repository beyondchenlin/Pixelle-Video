import inspect
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pixelle_video.storage.object_store import (  # noqa: E402
    FilesystemDevRawPayloadStore,
    RawPayloadStore,
)


def test_raw_payload_store_contract_exposes_required_methods():
    assert inspect.iscoroutinefunction(RawPayloadStore.put_json)
    assert inspect.iscoroutinefunction(RawPayloadStore.get_json)
    assert inspect.iscoroutinefunction(RawPayloadStore.exists)


def test_filesystem_dev_store_contract_exposes_async_methods():
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.put_json)
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.get_json)
    assert inspect.iscoroutinefunction(FilesystemDevRawPayloadStore.exists)


async def test_filesystem_dev_store_returns_storage_key_and_round_trips_payload(tmp_path):
    store = FilesystemDevRawPayloadStore(root=tmp_path)
    payload = {"prompt": "hello", "metadata": {"count": 2, "enabled": True}}

    storage_key = await store.put_json(workspace_id="workspace-1", payload=payload)

    assert storage_key.startswith("raw-payloads/workspace-1/")
    assert storage_key.endswith(".json")
    assert not os.path.isabs(storage_key)
    assert "\\" not in storage_key

    written_path = tmp_path / storage_key
    assert written_path.is_file()
    assert await store.get_json(storage_key) == payload
    assert await store.exists(storage_key) is True


@pytest.mark.parametrize(
    "storage_key",
    [
        "../secret.json",
        "raw-payloads/workspace-1/../../secret.json",
        "raw-payloads/workspace-1//x.json",
        "raw-payloads/workspace-1/./x.json",
        "raw-payloads/workspace-1/x/../y.json",
    ],
)
async def test_filesystem_dev_store_exists_rejects_non_canonical_keys(tmp_path, storage_key):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    assert await store.exists(storage_key) is False


@pytest.mark.parametrize(
    "storage_key",
    [
        "../secret.json",
        "raw-payloads/workspace-1/../../secret.json",
        "raw-payloads/workspace-1//x.json",
        "raw-payloads/workspace-1/./x.json",
        "raw-payloads/workspace-1/x/../y.json",
    ],
)
async def test_filesystem_dev_store_get_json_rejects_non_canonical_keys(
    tmp_path, storage_key
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(ValueError):
        await store.get_json(storage_key)


@pytest.mark.parametrize(
    "workspace_id",
    [
        "../workspace-1",
        "workspace/1",
        "workspace\\1",
        "workspace..1",
        "..",
    ],
)
async def test_filesystem_dev_store_rejects_workspace_ids_with_path_syntax(
    tmp_path, workspace_id
):
    store = FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(ValueError):
        await store.put_json(workspace_id=workspace_id, payload={"value": 1})
