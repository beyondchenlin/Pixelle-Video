from dataclasses import FrozenInstanceError

import pytest

from pixelle_video.models.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactVersion,
    ArtifactVersionStatus,
)


def test_artifact_and_version_round_trip_without_local_paths():
    artifact = Artifact(
        artifact_id="artifact_frame_001",
        workspace_id="workspace_1",
        artifact_type="storyboard_image",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_001",
        status=ArtifactStatus.ACTIVE,
        selected_version_id="artifact_version_001",
        metadata={"storyboard_plan_id": "storyboard_plan_001"},
    )
    version = ArtifactVersion(
        version_id="artifact_version_001",
        artifact_id=artifact.artifact_id,
        workspace_id=artifact.workspace_id,
        frame_id=artifact.frame_id,
        source_prompt_plan_id=artifact.source_prompt_plan_id,
        storage_key="artifacts/workspace_1/frame_0001/artifact_version_001.png",
        status=ArtifactVersionStatus.SUCCEEDED,
        provider="comfyui",
        provider_metadata={"workflow_id": "workflow_storyboard_image"},
        width=1024,
        height=1024,
        trace_event_id="generation_event_001",
    )

    artifact_payload = artifact.to_dict()
    version_payload = version.to_dict()

    assert Artifact.from_dict(artifact_payload) == artifact
    assert ArtifactVersion.from_dict(version_payload) == version
    assert artifact_payload["selected_version_id"] == "artifact_version_001"
    assert version_payload["storage_key"] == "artifacts/workspace_1/frame_0001/artifact_version_001.png"
    assert "local_path" not in artifact_payload
    assert "local_path" not in version_payload
    with pytest.raises(FrozenInstanceError):
        artifact.selected_version_id = "changed"
    with pytest.raises(TypeError):
        version.provider_metadata["workflow_id"] = "changed"


def test_artifact_selection_returns_new_artifact_without_overwriting_old_version():
    artifact = Artifact(
        artifact_id="artifact_frame_001",
        workspace_id="workspace_1",
        artifact_type="storyboard_image",
        frame_id="frame_0001",
        source_prompt_plan_id="prompt_plan_001",
        selected_version_id="artifact_version_001",
    )

    updated = artifact.select_version("artifact_version_002")

    assert artifact.selected_version_id == "artifact_version_001"
    assert updated.selected_version_id == "artifact_version_002"
    assert updated.artifact_id == artifact.artifact_id
    assert updated.source_prompt_plan_id == artifact.source_prompt_plan_id


@pytest.mark.parametrize(
    "storage_key",
    [
        r"D:\demo1\Pixelle\output\frame.png",
        "/tmp/pixelle/frame.png",
        "../output/frame.png",
        "artifacts\\workspace_1\\frame.png",
        "file:///tmp/frame.png",
    ],
)
def test_artifact_version_rejects_local_or_path_escape_storage_keys(storage_key):
    with pytest.raises(ValueError, match="storage_key"):
        ArtifactVersion(
            version_id="artifact_version_001",
            artifact_id="artifact_frame_001",
            workspace_id="workspace_1",
            frame_id="frame_0001",
            source_prompt_plan_id="prompt_plan_001",
            storage_key=storage_key,
            status=ArtifactVersionStatus.SUCCEEDED,
        )
