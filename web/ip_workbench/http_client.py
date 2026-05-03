from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web.utils.asset_bible_api import (
    apply_scene_cast_to_prompt_plan,
    list_asset_bibles,
    list_scene_casts,
)


class HttpStoryboardIPWorkbenchClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        asset_bible_loader: Callable[..., list[dict[str, Any]]] = list_asset_bibles,
        scene_cast_loader: Callable[..., list[dict[str, Any]]] = list_scene_casts,
        scene_cast_applier: Callable[..., dict[str, Any]] = apply_scene_cast_to_prompt_plan,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self._asset_bible_loader = asset_bible_loader
        self._scene_cast_loader = scene_cast_loader
        self._scene_cast_applier = scene_cast_applier

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

    def apply_scene_cast_to_prompt_plan(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        storyboard_plan_id: str,
        frame_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        return self._scene_cast_applier(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            project_id=project_id,
            asset_bible_id=asset_bible_id,
            scene_cast_id=scene_cast_id,
            storyboard_plan_id=storyboard_plan_id,
            frame_id=frame_id,
            actor_id=actor_id,
        )


__all__ = ["HttpStoryboardIPWorkbenchClient"]
