from __future__ import annotations

from typing import Any

from api.schemas.asset_bible import AssetBibleDraftRequest, SceneCastDraftRequest
from pixelle_video.models.asset_bible import AssetBible
from pixelle_video.services.scene_casting import validate_scene_cast
from web.state.async_runtime import get_async_runtime


class InProcessIPDesignClient:
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
        asset_bibles = self._run_async(repository.list_asset_bibles(workspace_id, project_id))
        return {"success": True, "asset_bibles": list(asset_bibles)}

    def load_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        asset_bible = self._run_async(repository.load_asset_bible(workspace_id, asset_bible_id))
        if asset_bible is None:
            raise ValueError("asset bible draft was not found")
        if asset_bible.get("project_id") != project_id:
            raise ValueError("asset bible project does not match request")
        return {"success": True, "asset_bible": dict(asset_bible)}

    def save_asset_bible(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        request = AssetBibleDraftRequest(
            **{
                **dict(payload),
                "workspace_id": workspace_id,
                "asset_bible_id": asset_bible_id,
            }
        )
        saved = self._run_async(
            repository.save_asset_bible(
                workspace_id,
                request.to_model(project_id=project_id).to_dict(),
            )
        )
        return {"success": True, "asset_bible": dict(saved)}

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

    def load_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        scene_cast = self._run_async(repository.load_scene_cast(workspace_id, scene_cast_id))
        if scene_cast is None:
            raise ValueError("scene cast draft was not found")
        if scene_cast.get("project_id") != project_id:
            raise ValueError("scene cast project does not match request")
        if scene_cast.get("asset_bible_id") != asset_bible_id:
            raise ValueError("scene cast asset bible does not match request")
        return {"success": True, "scene_cast": dict(scene_cast)}

    def save_scene_cast(
        self,
        *,
        workspace_id: str,
        project_id: str,
        asset_bible_id: str,
        scene_cast_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        repository = self._require_attr("asset_bible_repository")
        loaded_asset_bible = self._run_async(
            repository.load_asset_bible(workspace_id, asset_bible_id)
        )
        if loaded_asset_bible is None:
            raise ValueError("asset bible draft was not found")
        asset_bible = AssetBible.from_dict(loaded_asset_bible)
        if asset_bible.project_id != project_id:
            raise ValueError("asset bible project does not match request")
        request = SceneCastDraftRequest(
            **{
                **dict(payload),
                "workspace_id": workspace_id,
                "scene_cast_id": scene_cast_id,
            }
        )
        scene_cast = request.to_model(
            project_id=project_id,
            asset_bible_id=asset_bible_id,
        )
        validate_scene_cast(scene_cast, asset_bible)
        saved = self._run_async(
            repository.save_scene_cast(
                workspace_id,
                scene_cast.to_dict(),
            )
        )
        return {"success": True, "scene_cast": dict(saved)}

    def _require_attr(self, name: str) -> Any:
        value = getattr(self.pixelle_video, name, None)
        if value is None:
            raise ValueError(f"{name} is not configured")
        return value

    def _run_async(self, coro):
        if self._async_runner is not None:
            return self._async_runner(coro)
        return get_async_runtime().run(coro)


__all__ = ["InProcessIPDesignClient"]
