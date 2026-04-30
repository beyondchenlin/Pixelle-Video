from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from shutil import copy2
from typing import Mapping
from uuid import uuid4

from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.storage.object_store import WORKSPACE_ID_PATTERN

ARTIFACT_PREFIX = "artifacts"
_OBJECT_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9][A-Za-z0-9_-]*$")
_SOURCE_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9_-]*$")


class FilesystemDevArtifactObjectStore:
    """Dev/test artifact store that persists files locally and returns object keys."""

    def __init__(self, root: str | Path, base_url: str | None = None) -> None:
        self._root = Path(root).expanduser().resolve()
        self._base_url = (base_url or "").rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    async def put_file(
        self,
        workspace_id: str,
        source_path: str | Path,
        metadata: Mapping[str, object] | None = None,
    ) -> StoredArtifactFile:
        self._validate_workspace_id(workspace_id)
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"artifact source file not found: {source_path}")

        if "." in source.stem:
            raise ValueError("artifact source file must use a single extension")
        extension = source.suffix.lower()
        if not _SOURCE_EXTENSION_PATTERN.fullmatch(extension):
            raise ValueError("artifact source file must have a safe extension")

        storage_key = f"{ARTIFACT_PREFIX}/{workspace_id}/{uuid4().hex}{extension}"
        target_path = self._path_for_storage_key(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, target_path)
        if metadata:
            metadata_path = target_path.with_name(f"{target_path.name}.metadata.json")
            metadata_path.write_text(
                json.dumps(dict(metadata), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return StoredArtifactFile(
            storage_key=storage_key,
            url=self._url_for_storage_key(storage_key),
        )

    async def get_file_url(
        self,
        storage_key: str,
        options: Mapping[str, object] | None = None,
    ) -> str:
        self._path_for_storage_key(storage_key)
        return self._url_for_storage_key(storage_key)

    async def exists(self, storage_key: str) -> bool:
        try:
            return self._path_for_storage_key(storage_key).is_file()
        except ValueError:
            return False

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> None:
        if not WORKSPACE_ID_PATTERN.fullmatch(workspace_id):
            raise ValueError("workspace_id must not contain path syntax")

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
            or parts[0] != ARTIFACT_PREFIX
            or not WORKSPACE_ID_PATTERN.fullmatch(parts[1])
            or not _OBJECT_FILENAME_PATTERN.fullmatch(parts[2])
        ):
            raise ValueError("invalid artifact storage key")

        target_path = self._root.joinpath(*parts).resolve()
        if not target_path.is_relative_to(self._root):
            raise ValueError("artifact storage key escapes configured root")
        return target_path

    def _url_for_storage_key(self, storage_key: str) -> str:
        if not self._base_url:
            return f"/{storage_key}"
        return f"{self._base_url}/{storage_key}"
