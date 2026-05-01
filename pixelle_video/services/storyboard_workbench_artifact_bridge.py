from __future__ import annotations

from os import PathLike
from uuid import uuid4

from pixelle_video.models.artifact import Artifact, ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.generation_event import GenerationEvent, GenerationEventAction
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.repositories.artifacts import ArtifactObjectStore, ArtifactRepository
from pixelle_video.repositories.trace import TraceRepository


class StoryboardWorkbenchArtifactBridge:
    """Registers generated frame media as Stage 1B workbench artifacts."""

    def __init__(
        self,
        *,
        artifact_repository: ArtifactRepository,
        object_store: ArtifactObjectStore,
        trace_repository: TraceRepository,
    ) -> None:
        self.artifact_repository = artifact_repository
        self.object_store = object_store
        self.trace_repository = trace_repository

    async def attach_generated_image(
        self,
        *,
        workspace_id: str,
        storyboard_id: str,
        frame: StoryboardFrame,
        frame_id: str,
        prompt_plan: PromptPlan,
        source_path: str | PathLike[str] | None,
        provider: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> StoryboardFrameWorkbenchState | None:
        if source_path is None:
            return None

        artifact_id = build_frame_image_artifact_id(
            storyboard_id=storyboard_id,
            frame_id=frame_id,
        )
        artifact = Artifact(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            artifact_type="storyboard_frame_image",
            frame_id=frame_id,
            source_prompt_plan_id=prompt_plan.prompt_plan_id,
        )
        await self.artifact_repository.create_artifact(
            workspace_id,
            artifact.to_dict(),
        )

        stored_file = await self.object_store.put_file(
            workspace_id,
            source_path,
            metadata={
                "storyboard_id": storyboard_id,
                "frame_id": frame_id,
                "prompt_plan_id": prompt_plan.prompt_plan_id,
                "artifact_id": artifact_id,
            },
        )
        event_id = f"generation_event_{uuid4().hex}"
        version = ArtifactVersion(
            version_id=f"artifact_version_{uuid4().hex}",
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            frame_id=frame_id,
            source_prompt_plan_id=prompt_plan.prompt_plan_id,
            storage_key=stored_file.storage_key,
            status=ArtifactVersionStatus.SELECTED,
            provider=provider,
            width=width,
            height=height,
            trace_event_id=event_id,
        )
        stored_version_payload = await self.artifact_repository.create_artifact_version(
            workspace_id,
            artifact_id,
            version.to_dict(),
        )
        stored_version = ArtifactVersion.from_dict(stored_version_payload)
        await self.artifact_repository.select_artifact_version(
            workspace_id,
            artifact_id,
            stored_version.version_id,
        )

        state = StoryboardFrameWorkbenchState(
            frame_id=frame_id,
            prompt_plan_id=prompt_plan.prompt_plan_id,
            selected_image_artifact_id=artifact_id,
            selected_image_version_id=stored_version.version_id,
            candidate_image_version_ids=(stored_version.version_id,),
        )
        await self.trace_repository.append_generation_event(
            workspace_id,
            GenerationEvent(
                event_id=event_id,
                workspace_id=workspace_id,
                action=GenerationEventAction.GENERATE,
                frame_id=frame_id,
                prompt_plan_id=prompt_plan.prompt_plan_id,
                artifact_id=artifact_id,
                artifact_version_id=stored_version.version_id,
                storage_key=stored_version.storage_key,
                metadata={
                    "storyboard_id": storyboard_id,
                    "media_type": "image",
                },
            ).to_dict(),
        )
        frame.workbench_state = state
        return state


def build_frame_image_artifact_id(*, storyboard_id: str, frame_id: str) -> str:
    return f"artifact_{storyboard_id}_{frame_id}_image"


__all__ = [
    "StoryboardWorkbenchArtifactBridge",
    "build_frame_image_artifact_id",
]
