from __future__ import annotations

from typing import Any, Protocol


class IPDesignClientError(RuntimeError):
    """Raised when the IP design client cannot satisfy a requested operation."""


class IPDesignClient(Protocol):
    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]: ...

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]: ...

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]: ...

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any]: ...

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


__all__ = ["IPDesignClient", "IPDesignClientError"]
