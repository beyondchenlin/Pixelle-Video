from __future__ import annotations

from typing import Any, Protocol

from .models import (
    ListAssetBiblesResponse,
    ListSceneCastsResponse,
    SaveResponse,
)


class IPDesignClientError(RuntimeError):
    """Raised when the IP design client cannot satisfy a requested operation."""


class IPDesignClient(Protocol):
    def list_asset_bible_presets(self) -> list[dict[str, Any]]: ...

    def import_asset_bible_preset(
        self,
        *,
        workspace_id: str,
        project_id: str,
        preset_id: str,
        asset_bible_id: str | None = None,
    ) -> dict[str, Any]: ...

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> ListAssetBiblesResponse: ...

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
    ) -> SaveResponse: ...

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> ListSceneCastsResponse: ...

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
    ) -> SaveResponse: ...


__all__ = ["IPDesignClient", "IPDesignClientError"]
