from typing import Mapping, Protocol


class ArtifactRepository(Protocol):
    async def create_artifact(
        self,
        workspace_id: str,
        artifact: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def create_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version: Mapping[str, object],
    ) -> dict[str, object]:
        ...

    async def select_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> dict[str, object]:
        ...

    async def list_artifact_versions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> list[dict[str, object]]:
        ...

    async def mark_artifact_failed(
        self,
        workspace_id: str,
        artifact_id: str,
        failure: Mapping[str, object],
    ) -> dict[str, object]:
        ...


class ArtifactObjectStore(Protocol):
    async def put_file(
        self,
        workspace_id: str,
        source_path: str,
        metadata: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    async def get_file_url(
        self,
        storage_key: str,
        options: Mapping[str, object] | None = None,
    ) -> str:
        ...

    async def exists(self, storage_key: str) -> bool:
        ...

