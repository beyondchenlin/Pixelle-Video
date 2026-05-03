from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web.utils.asset_bible_api import (
    list_asset_bibles,
    list_scene_casts,
    load_asset_bible,
    load_scene_cast,
    save_asset_bible,
    save_scene_cast,
)


class HttpIPDesignClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        asset_bible_loader: Callable[..., list[dict[str, Any]]] = list_asset_bibles,
        asset_bible_getter: Callable[..., dict[str, Any]] = load_asset_bible,
        asset_bible_saver: Callable[..., dict[str, Any]] = save_asset_bible,
        scene_cast_loader: Callable[..., list[dict[str, Any]]] = list_scene_casts,
        scene_cast_getter: Callable[..., dict[str, Any]] = load_scene_cast,
        scene_cast_saver: Callable[..., dict[str, Any]] = save_scene_cast,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self._asset_bible_loader = asset_bible_loader
        self._asset_bible_getter = asset_bible_getter
        self._asset_bible_saver = asset_bible_saver
        self._scene_cast_loader = scene_cast_loader
        self._scene_cast_getter = scene_cast_getter
        self._scene_cast_saver = scene_cast_saver

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "asset_bibles": self._asset_bible_loader(
                api_base_url=self.api_base_url,
                workspace_id=workspace_id,
                project_id=project_id,
            ),
        }

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]:
        return self._asset_bible_getter(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._asset_bible_saver(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            payload=payload,
        )

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "scene_casts": self._scene_cast_loader(
                api_base_url=self.api_base_url,
                workspace_id=workspace_id,
                project_id=project_id,
                asset_bible_id=asset_bible_id,
            ),
        }

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any]:
        return self._scene_cast_getter(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
        )

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._scene_cast_saver(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            payload=payload,
        )


__all__ = ["HttpIPDesignClient"]
