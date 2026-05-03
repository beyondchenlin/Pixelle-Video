from __future__ import annotations

from typing import Any

from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from web.state.async_runtime import get_async_runtime
from web.workbench.display import local_bytes_image_display


class InProcessStoryboardWorkbenchClient:
    def __init__(self, *, pixelle_video: Any, async_runner=None) -> None:
        self.pixelle_video = pixelle_video
        self._async_runner = async_runner

    def get_capabilities(self) -> dict[str, Any]:
        submitter = getattr(self.pixelle_video, "storyboard_workbench_task_submitter", None)
        if submitter is None:
            return {
                "can_regenerate_frame_image": False,
                "regenerate_unavailable_reason": "task submitter is not configured",
            }
        capabilities = self._run_async(submitter.get_capabilities())
        return self._capabilities_to_dict(capabilities)

    def list_image_candidates(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        service = self._require_attr("storyboard_workbench_service")
        candidates = self._run_async(
            service.list_image_candidates(
                workspace_id=workspace_id,
                artifact_id=artifact_id,
            )
        )
        return {
            "workspace_id": workspace_id,
            "storyboard_id": storyboard_id,
            "frame_id": frame_id,
            "artifact_id": artifact_id,
            "candidates": [
                self._candidate_with_display(candidate)
                for candidate in candidates
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
        service = self._require_attr("storyboard_workbench_service")
        state_store = self._require_attr("storyboard_workbench_state_store")
        state = self._load_frame_state(
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            frame_id=frame_id,
        )
        updated_state = self._run_async(
            service.select_image_version(
                workspace_id=workspace_id,
                state=state,
                artifact_id=artifact_id,
                version_id=version_id,
                actor_id=actor_id,
            )
        )
        self._run_async(
            state_store.save_frame_state(
                workspace_id,
                storyboard_id,
                frame_id,
                updated_state.to_dict(),
            )
        )
        return {
            "success": True,
            "workspace_id": workspace_id,
            "storyboard_id": storyboard_id,
            "frame_id": frame_id,
            "state": updated_state.to_dict(),
        }

    def regenerate_frame_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        service = self._require_attr("storyboard_workbench_service")
        submitter = getattr(self.pixelle_video, "storyboard_workbench_task_submitter", None)
        if submitter is None:
            return {
                "success": False,
                "code": "regenerate_unavailable",
                "reason": "task submitter is not configured",
            }
        capabilities = self._run_async(submitter.get_capabilities())
        capability_payload = self._capabilities_to_dict(capabilities)
        if not capability_payload["can_regenerate_frame_image"]:
            return {
                "success": False,
                "code": "regenerate_unavailable",
                "reason": capability_payload["regenerate_unavailable_reason"],
            }
        state = self._load_frame_state(
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            frame_id=frame_id,
        )
        task_request = service.build_frame_image_regeneration_task_request(
            workspace_id=workspace_id,
            storyboard_id=storyboard_id,
            state=state,
            artifact_id=artifact_id,
        )
        submission = self._run_async(
            submitter.reserve_frame_image_regeneration(
                generation_fingerprint=task_request.generation_fingerprint,
                request_params=dict(task_request.request_params),
            )
        )
        return {"success": True, **submission.to_dict()}

    def get_prompt_plan_stale_summary(
        self,
        *,
        workspace_id: str,
        project_id: str,
        prompt_plan_id: str,
    ) -> dict[str, Any]:
        service = self._require_attr("stale_dependency_read_service")
        summary = self._run_async(
            service.get_target_summary(
                workspace_id=workspace_id,
                project_id=project_id,
                target_type="prompt_plan",
                target_id=prompt_plan_id,
            )
        )
        return {"success": True, "stale_summary": summary.to_dict()}

    def _candidate_with_display(self, candidate: Any) -> dict[str, Any]:
        payload = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
        storage_key = payload.get("storage_key")
        payload.pop("url", None)
        object_store = self._require_attr("artifact_object_store")
        file_uri = self._run_async(object_store.get_local_file_uri(storage_key))
        payload["image_display"] = local_bytes_image_display(file_uri=file_uri)
        return payload

    def _load_frame_state(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
    ) -> StoryboardFrameWorkbenchState:
        state_store = self._require_attr("storyboard_workbench_state_store")
        payload = self._run_async(
            state_store.load_frame_state(workspace_id, storyboard_id, frame_id)
        )
        if payload is None:
            raise ValueError("storyboard frame workbench state was not found")
        if isinstance(payload, StoryboardFrameWorkbenchState):
            return payload
        return StoryboardFrameWorkbenchState.from_dict(payload)

    def _require_attr(self, name: str) -> Any:
        value = getattr(self.pixelle_video, name, None)
        if value is None:
            raise ValueError(f"{name} is not configured")
        return value

    @staticmethod
    def _capabilities_to_dict(capabilities: Any) -> dict[str, Any]:
        payload = capabilities.to_dict() if hasattr(capabilities, "to_dict") else dict(capabilities)
        return {
            "can_regenerate_frame_image": bool(payload.get("can_regenerate_frame_image")),
            "regenerate_unavailable_reason": payload.get("regenerate_unavailable_reason"),
        }

    def _run_async(self, coro):
        if self._async_runner is not None:
            return self._async_runner(coro)
        return get_async_runtime().run(coro)


__all__ = ["InProcessStoryboardWorkbenchClient"]
