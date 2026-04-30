import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OBJECT_STORE_PATH = REPO_ROOT / "pixelle_video" / "storage" / "object_store.py"


def load_object_store_module() -> ModuleType:
    spec = spec_from_file_location("pixelle_video.storage.object_store", OBJECT_STORE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_payload_store_contract_exposes_required_methods():
    object_store = load_object_store_module()

    assert hasattr(object_store.RawPayloadStore, "put_json")
    assert hasattr(object_store.RawPayloadStore, "get_json")
    assert hasattr(object_store.RawPayloadStore, "exists")


def test_filesystem_dev_store_returns_storage_key_and_round_trips_payload(tmp_path):
    object_store = load_object_store_module()
    store = object_store.FilesystemDevRawPayloadStore(root=tmp_path)
    payload = {"prompt": "hello", "metadata": {"count": 2, "enabled": True}}

    storage_key = store.put_json(workspace_id="workspace-1", payload=payload)

    assert storage_key.startswith("raw-payloads/workspace-1/")
    assert storage_key.endswith(".json")
    assert not os.path.isabs(storage_key)
    assert "\\" not in storage_key

    written_path = tmp_path / storage_key
    assert written_path.is_file()
    assert store.get_json(storage_key) == payload
    assert store.exists(storage_key) is True


@pytest.mark.parametrize(
    "storage_key",
    [
        "../secret.json",
        "raw-payloads/workspace-1/../../secret.json",
    ],
)
def test_filesystem_dev_store_exists_rejects_traversal_attempts(tmp_path, storage_key):
    object_store = load_object_store_module()
    store = object_store.FilesystemDevRawPayloadStore(root=tmp_path)

    assert store.exists(storage_key) is False


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
def test_filesystem_dev_store_rejects_workspace_ids_with_path_syntax(tmp_path, workspace_id):
    object_store = load_object_store_module()
    store = object_store.FilesystemDevRawPayloadStore(root=tmp_path)

    with pytest.raises(ValueError):
        store.put_json(workspace_id=workspace_id, payload={"value": 1})
