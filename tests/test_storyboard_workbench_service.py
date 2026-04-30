from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Mapping

import pytest

from pixelle_video.models.artifact import ArtifactVersion, ArtifactVersionStatus
from pixelle_video.models.generation_event import GenerationEventAction
from pixelle_video.models.storyboard_workbench import (
    FrameLockPolicy,
    FrameStaleFlag,
    StoryboardFrameWorkbenchState,
)
from pixelle_video.repositories.artifacts import StoredArtifactFile
from pixelle_video.services.storyboard_workbench import (
    FrameImageLockedError,
    StoryboardWorkbenchService,
    UnsafeArtifactUrlError,
)


@dataclass
class FakeArtifactRepository:
    versions_by_artifact_id: dict[str, list[dict[str, object]]]
    selected_versions: list[tuple[str, str, str]]

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
        raise NotImplementedError

    async def select_artifact_version(
        self,
        workspace_id: str,
        artifact_id: str,
        version_id: str,
    ) -> dict[str, object]:
        self.selected_versions.append((workspace_id, artifact_id, version_id))
        return {
            "artifact_id": artifact_id,
            "selected_version_id": version_id,
        }

    async def list_artifact_versions(
        self,
        workspace_id: str,
        artifact_id: str,
    ) -> list[dict[str, object]]:
        return list(self.versions_by_artifact_id.get(artifact_id, []))

    async def mark_artifact_failed(
        self,
        workspace_id: str,
        artifact_id: str,
        failure: Mapping[str, object],
    ) -> dict[str, object]:
        raise NotImplementedError


@dataclass
class FakeArtifactObjectStore:
    urls_by_storage_key: dict[str, str]
    requested_urls: list[str]

    async def put_file(
        self,
        workspace_id: str,
        source_path: str | PathLike[str],
        metadata: Mapping[str, object] | None = None,
    ) -> StoredArtifactFile:
        raise NotImplementedError

    async def get_file_url(
        self,
        storage_key: str,
        options: Mapping[str, object] | None = None,
    ) -> str:
        self.requested_urls.append(storage_key)
        return self.urls_by_storage_key[storage_key]

    async def exists(self, storage_key: str) -> bool:
        return storage_key in self.urls_by_storage_key


@dataclass
class FakeTraceRepository:
    generation_events: list[dict[str, object]]

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
        stored = dict(event)
        self.generation_events.append(stored)
        return stored

    async def list_generation_events(
        self,
        workspace_id: str,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return list(self.generation_events)


@dataclass
class FakePromptPlanRepository:
    stale_calls: list[tuple[str, str, Mapping[str, object] | None]]

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
        self.stale_calls.append((workspace_id, prompt_plan_id, reason))
        return {"prompt_plan_id": prompt_plan_id, "stale": True}


def _version(
    version_id: str,
    storage_key: str,
    status: ArtifactVersionStatus | str = ArtifactVersionStatus.SUCCEEDED,
) -> dict[str, object]:
    return ArtifactVersion(
        version_id=version_id,
        artifact_id="artifact_frame_0001_image",
        workspace_id="workspace_1",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_001",
        storage_key=storage_key,
        status=status,
        provider="comfyui",
        width=1024,
        height=1024,
    ).to_dict()


def _service() -> tuple[
    StoryboardWorkbenchService,
    FakeArtifactRepository,
    FakeArtifactObjectStore,
    FakeTraceRepository,
    FakePromptPlanRepository,
]:
    artifact_repository = FakeArtifactRepository(
        versions_by_artifact_id={
            "artifact_frame_0001_image": [
                _version(
                    "artifact_version_001",
                    "artifacts/workspace_1/frame_0001/artifact_version_001.png",
                ),
                _version(
                    "artifact_version_002",
                    "artifacts/workspace_1/frame_0001/artifact_version_002.png",
                ),
            ]
        },
        selected_versions=[],
    )
    object_store = FakeArtifactObjectStore(
        urls_by_storage_key={
            "artifacts/workspace_1/frame_0001/artifact_version_001.png": (
                "https://cdn.pixelle.test/artifacts/workspace_1/frame_0001/artifact_version_001.png"
            ),
            "artifacts/workspace_1/frame_0001/artifact_version_002.png": (
                "https://cdn.pixelle.test/artifacts/workspace_1/frame_0001/artifact_version_002.png"
            ),
        },
        requested_urls=[],
    )
    trace_repository = FakeTraceRepository(generation_events=[])
    prompt_plan_repository = FakePromptPlanRepository(stale_calls=[])
    return (
        StoryboardWorkbenchService(
            artifact_repository=artifact_repository,
            object_store=object_store,
            trace_repository=trace_repository,
            prompt_plan_repository=prompt_plan_repository,
        ),
        artifact_repository,
        object_store,
        trace_repository,
        prompt_plan_repository,
    )


def _state(**overrides: object) -> StoryboardFrameWorkbenchState:
    values = {
        "frame_id": "frame_0001",
        "prompt_plan_id": "prompt_plan_001",
        "selected_image_artifact_id": "artifact_frame_0001_image",
        "selected_image_version_id": "artifact_version_001",
        "candidate_image_version_ids": ("artifact_version_001",),
    }
    values.update(overrides)
    return StoryboardFrameWorkbenchState(**values)


@pytest.mark.asyncio
async def test_list_image_candidates_returns_storage_keys_and_controlled_urls():
    service, _, object_store, _, _ = _service()

    candidates = await service.list_image_candidates(
        workspace_id="workspace_1",
        artifact_id="artifact_frame_0001_image",
    )

    assert [candidate.version_id for candidate in candidates] == [
        "artifact_version_001",
        "artifact_version_002",
    ]
    assert candidates[0].storage_key == "artifacts/workspace_1/frame_0001/artifact_version_001.png"
    assert candidates[0].url == (
        "https://cdn.pixelle.test/artifacts/workspace_1/frame_0001/artifact_version_001.png"
    )
    assert object_store.requested_urls == [
        "artifacts/workspace_1/frame_0001/artifact_version_001.png",
        "artifacts/workspace_1/frame_0001/artifact_version_002.png",
    ]
    assert "local_path" not in candidates[0].to_dict()


@pytest.mark.asyncio
async def test_list_image_candidates_accepts_candidate_lifecycle_status():
    service, artifact_repository, _, _, _ = _service()
    artifact_repository.versions_by_artifact_id["artifact_frame_0001_image"] = [
        _version(
            "artifact_version_candidate",
            "artifacts/workspace_1/frame_0001/artifact_version_001.png",
            status="candidate",
        )
    ]

    candidates = await service.list_image_candidates(
        workspace_id="workspace_1",
        artifact_id="artifact_frame_0001_image",
    )

    assert candidates[0].status == "candidate"


@pytest.mark.asyncio
async def test_list_image_candidates_rejects_local_path_urls():
    service, _, object_store, _, _ = _service()
    object_store.urls_by_storage_key[
        "artifacts/workspace_1/frame_0001/artifact_version_001.png"
    ] = "/tmp/pixelle/frame.png"

    with pytest.raises(UnsafeArtifactUrlError):
        await service.list_image_candidates(
            workspace_id="workspace_1",
            artifact_id="artifact_frame_0001_image",
        )


@pytest.mark.asyncio
async def test_select_image_version_updates_artifact_selection_and_records_trace():
    service, artifact_repository, _, trace_repository, _ = _service()

    updated_state = await service.select_image_version(
        workspace_id="workspace_1",
        state=_state(),
        artifact_id="artifact_frame_0001_image",
        version_id="artifact_version_002",
        actor_id="user_1",
    )

    assert artifact_repository.selected_versions == [
        ("workspace_1", "artifact_frame_0001_image", "artifact_version_002")
    ]
    assert updated_state.selected_image_version_id == "artifact_version_002"
    assert updated_state.candidate_image_version_ids == (
        "artifact_version_001",
        "artifact_version_002",
    )
    assert updated_state.stale_flags == (
        FrameStaleFlag.VIDEO_SEGMENT,
        FrameStaleFlag.FINAL_VIDEO,
    )
    assert trace_repository.generation_events[-1]["action"] == GenerationEventAction.SELECT.value
    assert trace_repository.generation_events[-1]["prompt_plan_id"] == "prompt_plan_001"
    assert trace_repository.generation_events[-1]["artifact_version_id"] == "artifact_version_002"
    assert trace_repository.generation_events[-1]["metadata"]["actor_id"] == "user_1"


@pytest.mark.asyncio
async def test_locked_frame_keeps_generated_candidate_without_auto_replacing_selection():
    service, artifact_repository, _, trace_repository, _ = _service()

    updated_state = await service.add_image_candidate_version(
        workspace_id="workspace_1",
        state=_state(lock_policy=FrameLockPolicy.LOCKED_ARTIFACT),
        artifact_id="artifact_frame_0001_image",
        version_id="artifact_version_002",
        auto_select=True,
    )

    assert updated_state.selected_image_version_id == "artifact_version_001"
    assert updated_state.candidate_image_version_ids == (
        "artifact_version_001",
        "artifact_version_002",
    )
    assert artifact_repository.selected_versions == []
    assert trace_repository.generation_events == []


@pytest.mark.asyncio
async def test_select_image_version_rejects_locked_frame_without_override():
    service, artifact_repository, _, trace_repository, _ = _service()

    with pytest.raises(FrameImageLockedError):
        await service.select_image_version(
            workspace_id="workspace_1",
            state=_state(lock_policy=FrameLockPolicy.LOCKED_ARTIFACT),
            artifact_id="artifact_frame_0001_image",
            version_id="artifact_version_002",
        )

    assert artifact_repository.selected_versions == []
    assert trace_repository.generation_events == []


@pytest.mark.asyncio
async def test_prompt_plan_change_marks_frame_state_stale_and_records_trace():
    service, _, _, trace_repository, prompt_plan_repository = _service()

    updated_state = await service.mark_prompt_plan_change_stale(
        workspace_id="workspace_1",
        state=_state(),
        reason="prompt_plan_changed",
    )

    assert prompt_plan_repository.stale_calls == [
        (
            "workspace_1",
            "prompt_plan_001",
            {
                "frame_id": "frame_0001",
                "reason": "prompt_plan_changed",
            },
        )
    ]
    assert updated_state.stale_flags == (
        FrameStaleFlag.IMAGE_ARTIFACT,
        FrameStaleFlag.VIDEO_SEGMENT,
        FrameStaleFlag.FINAL_VIDEO,
    )
    assert trace_repository.generation_events[-1]["action"] == GenerationEventAction.STALE_MARK.value
    assert trace_repository.generation_events[-1]["stale_reason"] == "prompt_plan_changed"
