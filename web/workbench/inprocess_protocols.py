from __future__ import annotations

from typing import Protocol


class LocalReadableArtifactSource(Protocol):
    async def get_local_file_uri(self, storage_key: str) -> str: ...


__all__ = ["LocalReadableArtifactSource"]
