import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol
from uuid import uuid4

RAW_PAYLOAD_PREFIX = "raw-payloads"


class RawPayloadStore(Protocol):
    def put_json(self, workspace_id: str, payload: Mapping[str, object]) -> str:
        ...

    def get_json(self, storage_key: str) -> dict[str, object]:
        ...

    def exists(self, storage_key: str) -> bool:
        ...


class FilesystemDevRawPayloadStore:
    """Dev/test adapter that stores JSON locally while returning platform storage keys."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put_json(self, workspace_id: str, payload: Mapping[str, object]) -> str:
        self._validate_workspace_id(workspace_id)

        storage_key = f"{RAW_PAYLOAD_PREFIX}/{workspace_id}/{uuid4().hex}.json"
        target_path = self._path_for_storage_key(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return storage_key

    def get_json(self, storage_key: str) -> dict[str, object]:
        target_path = self._path_for_storage_key(storage_key)
        return json.loads(target_path.read_text(encoding="utf-8"))

    def exists(self, storage_key: str) -> bool:
        try:
            return self._path_for_storage_key(storage_key).is_file()
        except ValueError:
            return False

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> None:
        if (
            not workspace_id
            or workspace_id.strip() != workspace_id
            or "/" in workspace_id
            or "\\" in workspace_id
            or ".." in workspace_id
        ):
            raise ValueError("workspace_id must not contain path syntax")

    def _path_for_storage_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        parts = key.parts

        if (
            not storage_key
            or storage_key.startswith("/")
            or "\\" in storage_key
            or ":" in storage_key
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) != 3
            or parts[0] != RAW_PAYLOAD_PREFIX
            or not parts[2].endswith(".json")
        ):
            raise ValueError("invalid raw payload storage key")

        target_path = self._root.joinpath(*parts).resolve()
        if not target_path.is_relative_to(self._root):
            raise ValueError("storage key escapes configured root")
        return target_path
