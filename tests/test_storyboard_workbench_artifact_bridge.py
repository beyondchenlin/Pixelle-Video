from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import Mapping

import pytest

from pixelle_video.models.prompt_plan import PromptPlan
from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.repositories.artifacts import StoredArtifactFile


class _PipelineCore:
    llm = None
    tts = None
    media = None
    video = None


@dataclass
class _RecordingArtifactRepository:
    created_artifacts: list[tuple[str, dict[str, object]]]
    created_versions: list[tuple[str, str, dict[str, object]]]

    async def create_artifact(
        self,
        workspace_id: str,
        artifact: Mapping[str, object],
    ) -> dict[str, object]:
        payload = dict(artifact)
        self.created_artifacts.append((workspace_id, payload))
        return payload

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
        return {"artifact_id": artifact_id, "selected_version_id": version_id}

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
class _RecordingObjectStore:
    uploaded_files: list[tuple[str, str, Mapping[str, object] | None]]

    async def put_file(
        self,
        workspace_id: str,
        source_path: str | PathLike[str],
        metadata: Mapping[str, object] | None = None,
    ) -> StoredArtifactFile:
        self.uploaded_files.append((workspace_id, str(source_path), metadata))
        return StoredArtifactFile(
            storage_key="artifacts/workspace_1/artifact_version_001.png",
            url="https://cdn.pixelle.test/artifacts/workspace_1/artifact_version_001.png",
        )

    async def get_file_url(
        self,
        storage_key: str,
        options: Mapping[str, object] | None = None,
    ) -> str:
        return f"https://cdn.pixelle.test/{storage_key}"

    async def exists(self, storage_key: str) -> bool:
        return storage_key == "artifacts/workspace_1/artifact_version_001.png"


@dataclass
class _RecordingTraceRepository:
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
class _RecordingWorkbenchStateStore:
    states: list[tuple[str, str, str, dict[str, object]]]

    async def load_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
    ) -> dict[str, object] | None:
        for stored_workspace_id, stored_storyboard_id, stored_frame_id, state in reversed(self.states):
            if (
                stored_workspace_id == workspace_id
                and stored_storyboard_id == storyboard_id
                and stored_frame_id == frame_id
            ):
                return dict(state)
        return None

    async def save_frame_state(
        self,
        workspace_id: str,
        storyboard_id: str,
        frame_id: str,
        state: dict[str, object],
    ) -> dict[str, object]:
        payload = dict(state)
        self.states.append((workspace_id, storyboard_id, frame_id, payload))
        return payload


def _prompt_plan() -> PromptPlan:
    return PromptPlan(
        prompt_plan_id="prompt_plan_001",
        storyboard_plan_id="storyboard_001",
        frame_id="frame_0001",
        image_prompt_draft_id="draft_001",
        prompt_sections={"visual_goal": "Show a cinematic lab."},
        final_prompt="Show a cinematic lab.",
    )


@pytest.mark.asyncio
async def test_attach_generated_image_to_workbench_creates_artifact_and_state(tmp_path):
    from pixelle_video.services.storyboard_workbench_artifact_bridge import (
        StoryboardWorkbenchArtifactBridge,
    )

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-png")
    frame = StoryboardFrame(
        index=0,
        narration="Scene one",
        image_prompt="Show a cinematic lab.",
        image_path=str(image_path),
    )
    artifact_repository = _RecordingArtifactRepository(
        created_artifacts=[],
        created_versions=[],
    )
    object_store = _RecordingObjectStore(uploaded_files=[])
    trace_repository = _RecordingTraceRepository(events=[])
    bridge = StoryboardWorkbenchArtifactBridge(
        artifact_repository=artifact_repository,
        object_store=object_store,
        trace_repository=trace_repository,
    )

    state = await bridge.attach_generated_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame=frame,
        frame_id="frame_0001",
        prompt_plan=_prompt_plan(),
        source_path=str(image_path),
        provider="comfyui",
        width=1024,
        height=1024,
    )

    assert state.frame_id == "frame_0001"
    assert state.prompt_plan_id == "prompt_plan_001"
    assert state.selected_image_artifact_id == "artifact_storyboard_001_frame_0001_image"
    assert state.selected_image_version_id.startswith("artifact_version_")
    assert state.candidate_image_version_ids == (state.selected_image_version_id,)
    assert frame.workbench_state == state
    assert object_store.uploaded_files == [
        (
            "workspace_1",
            str(image_path),
            {
                "storyboard_id": "storyboard_001",
                "frame_id": "frame_0001",
                "prompt_plan_id": "prompt_plan_001",
                "artifact_id": "artifact_storyboard_001_frame_0001_image",
            },
        )
    ]
    assert artifact_repository.created_artifacts[0][1]["artifact_id"] == (
        "artifact_storyboard_001_frame_0001_image"
    )
    assert artifact_repository.created_versions[0][2]["storage_key"] == (
        "artifacts/workspace_1/artifact_version_001.png"
    )
    assert artifact_repository.created_versions[0][2]["status"] == "selected"
    assert trace_repository.events[-1]["action"] == "generate"
    assert "local_path" not in str(artifact_repository.created_versions[0][2])


@pytest.mark.asyncio
async def test_attach_generated_image_skips_frame_without_media_path():
    from pixelle_video.services.storyboard_workbench_artifact_bridge import (
        StoryboardWorkbenchArtifactBridge,
    )

    frame = StoryboardFrame(
        index=0,
        narration="Scene one",
        image_prompt="Show a cinematic lab.",
    )
    bridge = StoryboardWorkbenchArtifactBridge(
        artifact_repository=_RecordingArtifactRepository([], []),
        object_store=_RecordingObjectStore([]),
        trace_repository=_RecordingTraceRepository([]),
    )

    state = await bridge.attach_generated_image(
        workspace_id="workspace_1",
        storyboard_id="storyboard_001",
        frame=frame,
        frame_id="frame_0001",
        prompt_plan=_prompt_plan(),
        source_path=None,
    )

    assert state is None
    assert frame.workbench_state is None


@pytest.mark.asyncio
async def test_standard_pipeline_registers_generated_images_when_repositories_exist(tmp_path):
    from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
    from pixelle_video.pipelines.linear import PipelineContext
    from pixelle_video.pipelines.standard import StandardPipeline

    class _Core(_PipelineCore):
        artifact_repository = _RecordingArtifactRepository([], [])
        artifact_object_store = _RecordingObjectStore([])
        trace_repository = _RecordingTraceRepository([])
        storyboard_workbench_state_store = _RecordingWorkbenchStateStore([])

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-png")
    frame = StoryboardFrame(
        index=0,
        narration="Scene one",
        image_prompt="Show a cinematic lab.",
        image_path=str(image_path),
    )
    ctx = PipelineContext(
        input_text="demo",
        params={"workspace_id": "workspace_1"},
    )
    ctx.task_id = "task_001"
    ctx.storyboard = Storyboard(
        title="Demo",
        config=StoryboardConfig(
            task_id="task_001",
            media_width=1024,
            media_height=1024,
        ),
        frames=[frame],
        planning_snapshot={
            "storyboard_generation": {
                "plan_id": "storyboard_001",
                "frames": [{"frame_id": "frame_0001"}],
            },
            "prompt_plan_bundle": {
                "prompt_plans": [_prompt_plan().to_dict()],
            },
            "frames": [{"scene_id": "scene-1"}],
        },
    )
    ctx.planning_snapshot = ctx.storyboard.planning_snapshot

    await StandardPipeline(_Core())._register_storyboard_workbench_artifacts(ctx)

    assert frame.workbench_state is not None
    assert frame.workbench_state.selected_image_artifact_id == (
        "artifact_storyboard_001_frame_0001_image"
    )
    snapshot_frame = ctx.storyboard.planning_snapshot["storyboard_generation"]["frames"][0]
    assert snapshot_frame["image_artifact_id"] == (
        "artifact_storyboard_001_frame_0001_image"
    )
    assert ctx.storyboard.planning_snapshot["frames"][0]["image_artifact_id"] == (
        "artifact_storyboard_001_frame_0001_image"
    )
    assert "workbench_state" not in snapshot_frame
    assert "workbench_state" not in ctx.storyboard.planning_snapshot["frames"][0]
    assert _Core.storyboard_workbench_state_store.states[-1][0:3] == (
        "workspace_1",
        "storyboard_001",
        "frame_0001",
    )
    assert _Core.storyboard_workbench_state_store.states[-1][3]["selected_image_artifact_id"] == (
        "artifact_storyboard_001_frame_0001_image"
    )
    assert _Core.artifact_repository.created_versions[0][2]["status"] == "selected"


@pytest.mark.asyncio
async def test_standard_pipeline_syncs_workbench_artifact_ref_to_matching_snapshot_frame_only(tmp_path):
    from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
    from pixelle_video.pipelines.linear import PipelineContext
    from pixelle_video.pipelines.standard import StandardPipeline

    class _Core(_PipelineCore):
        artifact_repository = _RecordingArtifactRepository([], [])
        artifact_object_store = _RecordingObjectStore([])
        trace_repository = _RecordingTraceRepository([])

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-png")
    frames = [
        StoryboardFrame(
            index=0,
            narration="Scene one",
            image_prompt="Show a cinematic lab.",
            image_path=str(image_path),
        ),
        StoryboardFrame(
            index=1,
            narration="Scene two",
            image_prompt="Show a quiet hallway.",
        ),
    ]
    ctx = PipelineContext(
        input_text="demo",
        params={"workspace_id": "workspace_1"},
    )
    ctx.storyboard = Storyboard(
        title="Demo",
        config=StoryboardConfig(media_width=1024, media_height=1024),
        frames=frames,
        planning_snapshot={
            "storyboard_generation": {
                "plan_id": "storyboard_001",
                "frames": [
                    {"frame_id": "frame_0001"},
                    {"frame_id": "frame_0002"},
                ],
            },
            "prompt_plan_bundle": {
                "prompt_plans": [
                    _prompt_plan().to_dict(),
                    {
                        **_prompt_plan().to_dict(),
                        "prompt_plan_id": "prompt_plan_002",
                        "frame_id": "frame_0002",
                    },
                ],
            },
            "frames": [
                {"scene_id": "scene-1"},
                {"scene_id": "scene-2"},
            ],
        },
    )
    ctx.planning_snapshot = ctx.storyboard.planning_snapshot

    await StandardPipeline(_Core())._register_storyboard_workbench_artifacts(ctx)

    assert ctx.storyboard.planning_snapshot["frames"][0]["image_artifact_id"] == (
        "artifact_storyboard_001_frame_0001_image"
    )
    assert "image_artifact_id" not in ctx.storyboard.planning_snapshot["frames"][1]
    assert "workbench_state" not in ctx.storyboard.planning_snapshot["frames"][0]


@pytest.mark.asyncio
async def test_standard_pipeline_skips_workbench_registration_without_repositories(tmp_path):
    from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
    from pixelle_video.pipelines.linear import PipelineContext
    from pixelle_video.pipelines.standard import StandardPipeline

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-png")
    frame = StoryboardFrame(
        index=0,
        narration="Scene one",
        image_prompt="Show a cinematic lab.",
        image_path=str(image_path),
    )
    ctx = PipelineContext(input_text="demo", params={"workspace_id": "workspace_1"})
    ctx.storyboard = Storyboard(
        title="Demo",
        config=StoryboardConfig(media_width=1024, media_height=1024),
        frames=[frame],
        planning_snapshot={
            "storyboard_generation": {
                "plan_id": "storyboard_001",
                "frames": [{"frame_id": "frame_0001"}],
            },
            "prompt_plan_bundle": {
                "prompt_plans": [_prompt_plan().to_dict()],
            },
        },
    )

    await StandardPipeline(_PipelineCore())._register_storyboard_workbench_artifacts(ctx)

    assert frame.workbench_state is None


@pytest.mark.asyncio
async def test_standard_pipeline_parallel_result_registration_runs_for_each_processed_frame(tmp_path):
    from pixelle_video.models.storyboard import Storyboard, StoryboardConfig
    from pixelle_video.pipelines.linear import PipelineContext
    from pixelle_video.pipelines.standard import StandardPipeline

    class _Core(_PipelineCore):
        artifact_repository = _RecordingArtifactRepository([], [])
        artifact_object_store = _RecordingObjectStore([])
        trace_repository = _RecordingTraceRepository([])

    image_path = tmp_path / "frame.png"
    image_path.write_bytes(b"fake-png")
    frame = StoryboardFrame(
        index=0,
        narration="Scene one",
        image_prompt="Show a cinematic lab.",
        image_path=str(image_path),
    )
    ctx = PipelineContext(input_text="demo", params={"workspace_id": "workspace_1"})
    ctx.storyboard = Storyboard(
        title="Demo",
        config=StoryboardConfig(media_width=1024, media_height=1024),
        frames=[frame],
        planning_snapshot={
            "storyboard_generation": {
                "plan_id": "storyboard_001",
                "frames": [{"frame_id": "frame_0001"}],
            },
            "prompt_plan_bundle": {
                "prompt_plans": [_prompt_plan().to_dict()],
            },
            "frames": [{"scene_id": "scene-1"}],
        },
    )
    ctx.planning_snapshot = ctx.storyboard.planning_snapshot
    pipeline = StandardPipeline(_Core())

    await pipeline._register_storyboard_workbench_parallel_results(
        ctx,
        [(0, frame)],
    )

    assert ctx.storyboard.frames[0].workbench_state is not None
    assert _Core.artifact_repository.created_versions[0][1] == (
        "artifact_storyboard_001_frame_0001_image"
    )
