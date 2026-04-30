import json
import re
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol
from uuid import uuid4

RAW_PAYLOAD_PREFIX = "raw-payloads"
OBJECT_ID_HEX_LENGTH = 32
LOWER_HEX_DIGITS = frozenset("0123456789abcdef")
WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
WORKSPACE_DIR_PREFIX = "workspace-"


class RawPayloadReadError(Exception):
    """Base error for raw payload reads that fail at the storage contract boundary."""


class RawPayloadNotFoundError(RawPayloadReadError):
    """Raised when a syntactically valid raw payload key has no stored object."""


class RawPayloadInvalidError(RawPayloadReadError):
    """Raised when stored raw payload bytes are not a JSON object payload."""


class RawPayloadStore(Protocol):
    async def put_json(self, workspace_id: str, payload: Mapping[str, object]) -> str:
        ...

    async def get_json(self, storage_key: str) -> dict[str, object]:
        ...

    async def exists(self, storage_key: str) -> bool:
        ...


class FilesystemDevRawPayloadStore:
    """Dev/test adapter that stores JSON locally while returning platform storage keys.

    Production async adapters should avoid blocking filesystem I/O in request paths.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    async def put_json(self, workspace_id: str, payload: Mapping[str, object]) -> str:
        self._validate_workspace_id(workspace_id)

        storage_key = f"{RAW_PAYLOAD_PREFIX}/{workspace_id}/{uuid4().hex}.json"
        target_path = self._path_for_storage_key(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return storage_key

    async def get_json(self, storage_key: str) -> dict[str, object]:
        target_path = self._path_for_storage_key(storage_key)
        try:
            decoded_payload = json.loads(target_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RawPayloadNotFoundError("raw payload object was not found") from exc
        except UnicodeDecodeError as exc:
            raise RawPayloadInvalidError("raw payload object is not valid UTF-8 JSON") from exc
        except json.JSONDecodeError as exc:
            raise RawPayloadInvalidError("raw payload object is not valid JSON") from exc
        except OSError as exc:
            raise RawPayloadReadError("raw payload object could not be read") from exc

        if not isinstance(decoded_payload, dict):
            raise RawPayloadInvalidError("raw payload object must decode to a JSON object")
        return decoded_payload

    async def exists(self, storage_key: str) -> bool:
        try:
            return self._path_for_storage_key(storage_key).is_file()
        except ValueError:
            return False

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> None:
        if not FilesystemDevRawPayloadStore._is_valid_workspace_id(workspace_id):
            raise ValueError("workspace_id must not contain path syntax")

    @staticmethod
    def _is_valid_workspace_id(workspace_id: str) -> bool:
        return bool(WORKSPACE_ID_PATTERN.fullmatch(workspace_id))

    def _path_for_storage_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        parts = key.parts
        normalized_key = key.as_posix()

        if (
            not storage_key
            or storage_key != normalized_key
            or storage_key.startswith("/")
            or "\\" in storage_key
            or ":" in storage_key
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) != 3
            or parts[0] != RAW_PAYLOAD_PREFIX
            or not self._is_valid_workspace_id(parts[1])
            or not self._is_valid_object_filename(parts[2])
        ):
            raise ValueError("invalid raw payload storage key")

        target_path = self._root.joinpath(
            parts[0], self._filesystem_workspace_dir(parts[1]), parts[2]
        ).resolve()
        if not target_path.is_relative_to(self._root):
            raise ValueError("storage key escapes configured root")
        return target_path

    @staticmethod
    def _filesystem_workspace_dir(workspace_id: str) -> str:
        return f"{WORKSPACE_DIR_PREFIX}{workspace_id}"

    @staticmethod
    def _is_valid_object_filename(filename: str) -> bool:
        if not filename.endswith(".json"):
            return False

        object_id = filename.removesuffix(".json")
        return (
            len(object_id) == OBJECT_ID_HEX_LENGTH
            and object_id == object_id.lower()
            and all(character in LOWER_HEX_DIGITS for character in object_id)
        )
