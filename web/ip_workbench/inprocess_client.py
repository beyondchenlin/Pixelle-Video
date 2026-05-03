from __future__ import annotations

from typing import Any

from web.state.async_runtime import get_async_runtime


class InProcessStoryboardIPWorkbenchClient:
    def __init__(self, *, pixelle_video: Any, async_runner=None) -> None:
        self.pixelle_video = pixelle_video
        self._async_runner = async_runner

    def list_asset_bibles(
        self,
        *,
        workspace_id: str,
        project_id: str,
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        asset_bibles = self._run_async(
            repository.list_asset_bibles(workspace_id, project_id)
        )
        return {"success": True, "asset_bibles": list(asset_bibles)}

    def list_scene_casts(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        scene_casts = self._run_async(
            repository.list_scene_casts(workspace_id, project_id, asset_bible_id)
        )
        return {"success": True, "scene_casts": list(scene_casts)}

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
        service = self._require_attr("asset_prompt_plan_apply_service")
        result = self._run_async(
            service.apply_scene_cast_to_prompt_plan_bundle(
                workspace_id=workspace_id,
                project_id=project_id,
                asset_bible_id=asset_bible_id,
                scene_cast_id=scene_cast_id,
                storyboard_plan_id=storyboard_plan_id,
                frame_id=frame_id,
                actor_id=actor_id,
            )
        )
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        return {"success": True, "application": payload}

    def _require_attr(self, name: str) -> Any:
        value = getattr(self.pixelle_video, name, None)
        if value is None:
            raise ValueError(f"{name} is not configured")
        return value

    def _run_async(self, coro):
        if self._async_runner is not None:
            return self._async_runner(coro)
        return get_async_runtime().run(coro)


__all__ = ["InProcessStoryboardIPWorkbenchClient"]
