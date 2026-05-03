from __future__ import annotations

from typing import Any, Protocol


class StoryboardWorkbenchClientError(RuntimeError):
    """Raised when the Workbench client cannot satisfy a requested operation."""


class StoryboardWorkbenchClient(Protocol):
    def get_capabilities(self) -> dict[str, Any]: ...

    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def select_image_candidate(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]: ...

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]: ...

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]: ...


__all__ = ["StoryboardWorkbenchClient", "StoryboardWorkbenchClientError"]
