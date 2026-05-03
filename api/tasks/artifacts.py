"""Generated artifact storage abstractions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class ArtifactStore(Protocol):
    async def persist_video(
        self,
        *,
        task_id: str,
        source_path: str | Path,
        duration: float,
    ) -> dict:
        raise NotImplementedError

    async def exists(self, storage_key: str | None) -> bool:
        raise NotImplementedError


class LocalArtifactStore:
    """Filesystem artifact store for local development and single-host Docker."""

    def __init__(self, *, output_root: str | Path = "output", base_url: str = "/api/files") -> None:
        self.output_root = Path(output_root)
        self.base_url = base_url.rstrip("/")

    async def persist_video(
        self,
        *,
        task_id: str,
        source_path: str | Path,
        duration: float,
    ) -> dict:
        source = Path(source_path)
        target_dir = self.output_root / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name

        if source.resolve() != target.resolve():
            shutil.copy2(source, target)

        storage_key = f"{task_id}/{target.name}"
        return {
            "storage_backend": "local",
            "storage_key": storage_key,
            "file_size": target.stat().st_size,
            "duration": duration,
        }

    async def exists(self, storage_key: str | None) -> bool:
        path = self._resolve_storage_key(storage_key)
        return bool(path and path.is_file())

    def _resolve_storage_key(self, storage_key: str | None) -> Path | None:
        if not storage_key:
            return None

        root = self.output_root.resolve()
        candidate = (root / storage_key).resolve()
        if not candidate.is_relative_to(root):
            return None
        return candidate


class MissingArtifactStore:
    """Small test artifact store controlled by an in-memory key set."""

    def __init__(self, existing_keys: set[str] | None = None) -> None:
        self.existing_keys = set(existing_keys or set())

    async def persist_video(
        self,
        *,
        task_id: str,
        source_path: str | Path,
        duration: float,
    ) -> dict:
        storage_key = f"{task_id}/{Path(source_path).name}"
        self.existing_keys.add(storage_key)
        return {
            "storage_backend": "memory",
            "storage_key": storage_key,
            "file_size": 0,
            "duration": duration,
        }

    async def exists(self, storage_key: str | None) -> bool:
        return bool(storage_key and storage_key in self.existing_keys)
