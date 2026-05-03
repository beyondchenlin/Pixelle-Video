from __future__ import annotations

from typing import Any, Protocol


class StoryboardIPWorkbenchClientError(RuntimeError):
    """Raised when the IP Workbench client cannot satisfy a requested operation."""


class StoryboardIPWorkbenchClient(Protocol):
    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]: ...

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...


__all__ = ["StoryboardIPWorkbenchClient", "StoryboardIPWorkbenchClientError"]
