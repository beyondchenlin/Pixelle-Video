from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web.utils.stale_api import get_stale_target_summary
from web.utils.storyboard_workbench_api import (
    get_storyboard_workbench_capabilities,
    list_storyboard_image_candidates,
    regenerate_storyboard_frame_image,
    select_storyboard_image_candidate,
)
from web.workbench.display import remote_image_display


class HttpStoryboardWorkbenchClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        capability_loader: Callable[..., dict[str, Any]] = get_storyboard_workbench_capabilities,
        candidate_loader: Callable[..., dict[str, Any]] = list_storyboard_image_candidates,
        candidate_selector: Callable[..., dict[str, Any]] = select_storyboard_image_candidate,
        frame_regenerator: Callable[..., dict[str, Any]] = regenerate_storyboard_frame_image,
        stale_summary_loader: Callable[..., dict[str, Any]] = get_stale_target_summary,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self._capability_loader = capability_loader
        self._candidate_loader = candidate_loader
        self._candidate_selector = candidate_selector
        self._frame_regenerator = frame_regenerator
        self._stale_summary_loader = stale_summary_loader

    def get_capabilities(self) -> dict[str, Any]:
        data = self._capability_loader(api_base_url=self.api_base_url)
        return {
            "can_regenerate_frame_image": bool(data.get("can_regenerate_frame_image")),
            "regenerate_unavailable_reason": data.get("regenerate_unavailable_reason"),
        }

    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        response = self._candidate_loader(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            frame_id=frame_id,
            artifact_id=artifact_id,
        )
        return {
            **response,
            "candidates": [
                self._candidate_with_display(candidate)
                for candidate in response.get("candidates", [])
                if isinstance(candidate, dict)
            ],
        }

    def select_image_candidate(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
        version_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        return self._candidate_selector(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            frame_id=frame_id,
            artifact_id=artifact_id,
            version_id=version_id,
            actor_id=actor_id,
        )

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        return self._frame_regenerator(
            api_base_url=self.api_base_url,
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            frame_id=frame_id,
            artifact_id=artifact_id,
        )

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]:
        return self._stale_summary_loader(
            api_base_url=self.api_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            target_type="prompt_plan",
            target_id=prompt_plan_id,
        )

    def _candidate_with_display(self, candidate: dict[str, Any]) -> dict[str, Any]:
        payload = dict(candidate)
        url = payload.pop("url", None)
        display = remote_image_display(url=url, api_base_url=self.api_base_url)
        if display is not None:
            payload["image_display"] = display
        return payload


__all__ = ["HttpStoryboardWorkbenchClient"]
