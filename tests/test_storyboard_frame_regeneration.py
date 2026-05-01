from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from typing import Mapping

import pytest

from api.tasks import TaskType
from api.tasks.artifacts import MissingArtifactStore
from api.tasks.lease import InMemoryGenerationLease
from api.tasks.registry import GenerationRegistry
from api.tasks.store import InMemoryTaskStore
from pixelle_video.models.generation_event import GenerationEventAction
from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.storyboard_workbench import StoryboardFrameWorkbenchState
from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.services.artifact_dependency_integration import ArtifactDependencyWriteService
from pixelle_video.services.storyboard_workbench import StoryboardWorkbenchService


@dataclass
class RecordingArtifactRepository:
    created_versions: list[tuple[str, str, dict[str, object]]]

    async def create_artifact(
        self,
        workspace_id: str,
        artifact: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def create_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version: Mapping[str, object],
    ) -> dict[str, object]:
        payload = dict(version)
        self.created_versions.append((workspace_id, artifact_id, payload))
        return payload

    async def select_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> dict[str, object]:
        raise NotImplementedError

    async def list_artifact_versions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> list[dict[str, object]]:
        return [
            version
            for stored_workspace_id, stored_artifact_id, version in self.created_versions
            if stored_workspace_id == workspace_id and stored_artifact_id == artifact_id
        ]

    async def mark_artifact_failed(
        self,
        workspace_id: str,
        artifact_id: str,
        failure: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError


@dataclass
class RecordingObjectStore:
    uploaded_files: list[tuple[str, str, Mapping[str, object] | None]]

    async def put_file(
        self,
        workspace_id: str,
        source_path: str | PathLike[str],
        metadata: Mapping[str, object] | None = None,
    ) -> StoredArtifactFile:
        self.uploaded_files.append((workspace_id, str(source_path), metadata))
        return StoredArtifactFile(
            storage_key="artifacts/workspace_1/frame_0001/regenerated.png",
            url="https://cdn.pixelle.test/artifacts/workspace_1/frame_0001/regenerated.png",
        )

    async def get_file_url(
        self,
        storage_key: str,
        options: Mapping[str, object] | None = None,
    ) -> str:
        return f"https://cdn.pixelle.test/{storage_key}"

    async def exists(self, storage_key: str) -> bool:
        return storage_key == "artifacts/workspace_1/frame_0001/regenerated.png"


@dataclass
class RecordingTraceRepository:
    events: list[dict[str, object]]

    async def append_llm_interaction(
        self,
        workspace_id: str,
        trace: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def list_llm_interactions(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    async def append_generation_event(
        self,
        workspace_id: str,
        event: Mapping[str, object],
    ) -> dict[str, object]:
        payload = dict(event)
        self.events.append(payload)
        return payload

    async def list_generation_events(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return list(self.events)


@dataclass
class RecordingDependencyEdgeRepository:
    edges: list[dict[str, object]] = field(default_factory=list)

    async def save_dependency_edge(
        self,
        workspace_id: str,
        edge: Mapping[str, object],
    ) -> dict[str, object]:
        payload = dict(edge)
        self.edges.append(payload)
        return payload

    async def list_downstream_edges(
        self,
        workspace_id: str,
        upstream_type: str,
        upstream_id: str,
    ) -> list[dict[str, object]]:
        return []


class UnusedPromptPlanRepository:
    async def save_prompt_plan_bundle(
        self,
        workspace_id: str,
        bundle: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError

    async def load_prompt_plans_by_storyboard(
        self,
        workspace_id: str,
        storyboard_id: str,
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    async def mark_prompt_plan_stale(
        self,
        workspace_id: str,
        prompt_plan_id: str,
        reason: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        raise NotImplementedError


def _state() -> StoryboardFrameWorkbenchState:
    return StoryboardFrameWorkbenchState(
        frame_id="frame_0001",
        prompt_plan_id="prompt_plan_001",
        selected_image_artifact_id="artifact_frame_0001_image",
        selected_image_version_id="artifact_version_001",
        candidate_image_version_ids=("artifact_version_001",),
    )


def _prompt_plan() -> PromptPlan:
    return PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"visual_goal": "Show Luna in the lab."},
        final_prompt="Show Luna in the lab.",
    )


def _service(
    artifact_repository: RecordingArtifactRepository,
    object_store: RecordingObjectStore,
    trace_repository: RecordingTraceRepository,
) -> StoryboardWorkbenchService:
    return StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=UnusedPromptPlanRepository(),
    )


def test_task_type_includes_frame_image_regeneration():
    assert TaskType.FRAME_IMAGE_REGENERATION.value == "frame_image_regeneration"


@pytest.mark.asyncio
async def test_frame_image_regeneration_task_reserves_with_frame_prompt_and_artifact_ids():
    registry = GenerationRegistry(
        store=InMemoryTaskStore(),
        lease=InMemoryGenerationLease(),
        artifact_store=MissingArtifactStore(),
        task_id_factory=lambda: "regen-task-1",
    )
    service = _service(
        RecordingArtifactRepository(created_versions=[]),
        RecordingObjectStore(uploaded_files=[]),
        RecordingTraceRepository(events=[]),
    )

    task_request = service.build_frame_image_regeneration_task_request(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        state=_state(),
        artifact_id="artifact_frame_0001_image",
        provider="comfyui",
        model="z-image",
    )
    outcome = await registry.reserve_or_reuse(
        fingerprint=task_request.generation_fingerprint,
        task_type=TaskType.FRAME_IMAGE_REGENERATION,
        request_params=task_request.request_params,
        reuse_completed_within_seconds=0,
    )

    assert outcome.created is True
    assert outcome.task.task_id == "regen-task-1"
    assert outcome.task.task_type is TaskType.FRAME_IMAGE_REGENERATION
    assert outcome.task.request_params["workspace_id"] == "workspace_1"
    assert outcome.task.request_params["storyboard_id"] == "storyboard_001"
    assert outcome.task.request_params["frame_id"] == "frame_0001"
    assert outcome.task.request_params["prompt_plan_id"] == "prompt_plan_001"
    assert outcome.task.request_params["artifact_id"] == "artifact_frame_0001_image"
    assert outcome.task.request_params["provider"] == "comfyui"
    assert outcome.task.request_params["model"] == "z-image"
    assert outcome.task.request_params["generation_fingerprint"] == (
        task_request.generation_fingerprint
    )


@pytest.mark.asyncio
async def test_frame_image_regeneration_result_writes_candidate_version_and_trace(tmp_path):
    generated_file = tmp_path / "generated.png"
    generated_file.write_bytes(b"image")
    artifact_repository = RecordingArtifactRepository(created_versions=[])
    object_store = RecordingObjectStore(uploaded_files=[])
    trace_repository = RecordingTraceRepository(events=[])
    service = _service(artifact_repository, object_store, trace_repository)

    result = await service.record_frame_image_regeneration_result(
        workspace_id="workspace_1",
        task_id="regen-task-1",
        state=_state(),
        artifact_id="artifact_frame_0001_image",
        source_path=generated_file,
        provider="comfyui",
        provider_metadata={"workflow": "selfhost/image_z_image_turbo_gguf.json"},
        width=1024,
        height=1024,
    )

    assert object_store.uploaded_files == [
        (
            "workspace_1",
            str(generated_file),
            {
                "artifact_id": "artifact_frame_0001_image",
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "task_id": "regen-task-1",
            },
        )
    ]
    assert len(artifact_repository.created_versions) == 1
    workspace_id, artifact_id, version_payload = artifact_repository.created_versions[0]
    assert workspace_id == "workspace_1"
    assert artifact_id == "artifact_frame_0001_image"
    assert version_payload["artifact_id"] == "artifact_frame_0001_image"
    assert version_payload["frame_id"] == "frame_0001"
    assert version_payload["source_prompt_plan_id"] == "prompt_plan_001"
    assert version_payload["storage_key"] == "artifacts/workspace_1/frame_0001/regenerated.png"
    assert version_payload["status"] == "candidate"
    assert version_payload["provider"] == "comfyui"
    assert version_payload["provider_metadata"] == {
        "workflow": "selfhost/image_z_image_turbo_gguf.json"
    }
    assert version_payload["width"] == 1024
    assert version_payload["height"] == 1024
    assert result.artifact_version.to_dict() == version_payload
    assert result.workbench_state.last_generation_job_id == "regen-task-1"
    assert result.artifact_version.version_id in (
        result.workbench_state.candidate_image_version_ids
    )
    assert result.workbench_state.selected_image_version_id == "artifact_version_001"
    assert trace_repository.events[-1]["action"] == GenerationEventAction.REGENERATE.value
    assert trace_repository.events[-1]["task_id"] == "regen-task-1"
    assert trace_repository.events[-1]["artifact_version_id"] == (
        result.artifact_version.version_id
    )
    assert trace_repository.events[-1]["storage_key"] == (
        "artifacts/workspace_1/frame_0001/regenerated.png"
    )


@pytest.mark.asyncio
async def test_frame_image_regeneration_result_records_prompt_plan_dependency_edge(tmp_path):
    generated_file = tmp_path / "generated.png"
    generated_file.write_bytes(b"image")
    artifact_repository = RecordingArtifactRepository(created_versions=[])
    object_store = RecordingObjectStore(uploaded_files=[])
    trace_repository = RecordingTraceRepository(events=[])
    edge_repository = RecordingDependencyEdgeRepository()
    service = StoryboardWorkbenchService(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
        prompt_plan_repository=UnusedPromptPlanRepository(),
        artifact_dependency_service=ArtifactDependencyWriteService(edge_repository=edge_repository),
    )

    result = await service.record_frame_image_regeneration_result(
        workspace_id="workspace_1",
        project_id="project_1",
        task_id="regen-task-1",
        state=_state(),
        artifact_id="artifact_frame_0001_image",
        source_path=generated_file,
        prompt_plan=_prompt_plan(),
        provider="comfyui",
    )

    assert result.artifact_version.artifact_id == "artifact_frame_0001_image"
    assert edge_repository.edges[0]["relation"] == "image_artifact.generated_from_prompt_plan"
    assert edge_repository.edges[0]["upstream_id"] == "prompt_plan_001"
    assert edge_repository.edges[0]["downstream_id"] == "artifact_frame_0001_image"
    assert "storage_key" not in str(edge_repository.edges[0])
