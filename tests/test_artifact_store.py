from pathlib import Path

import pytest

import api.runtime_context as runtime_context_module
from api.config import APIConfig
from api.runtime_context import build_api_runtime_context
from api.tasks.artifacts import LocalArtifactStore
from api.tasks.factory import build_task_runtime


@pytest.mark.asyncio
async def test_local_artifact_store_persists_existing_video(tmp_path):
    source_dir = tmp_path / "work"
    source_dir.mkdir()
    source = source_dir / "final.mp4"
    source.write_bytes(b"video")
    store = LocalArtifactStore(
        output_root=tmp_path / "output",
        base_url="http://test/api/files",
    )

    result = await store.persist_video(
        task_id="task-1",
        source_path=source,
        duration=3.5,
    )

    assert result["storage_backend"] == "local"
    assert result["storage_key"] == "task-1/final.mp4"
    assert "video_url" not in result
    assert result["file_size"] == 5
    assert result["duration"] == 3.5
    assert await store.exists(result["storage_key"]) is True


@pytest.mark.asyncio
async def test_local_artifact_store_does_not_return_transport_url(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    store = LocalArtifactStore(output_root=tmp_path / "output")

    result = await store.persist_video(
        task_id="task-1",
        source_path=source,
        duration=3.5,
    )

    assert result == {
        "storage_backend": "local",
        "storage_key": "task-1/source.mp4",
        "file_size": 5,
        "duration": 3.5,
    }


@pytest.mark.asyncio
async def test_local_artifact_store_reports_missing_key(tmp_path):
    store = LocalArtifactStore(output_root=tmp_path / "output", base_url="/api/files")

    assert await store.exists("missing/final.mp4") is False


@pytest.mark.asyncio
async def test_local_artifact_store_rejects_path_escape(tmp_path):
    store = LocalArtifactStore(output_root=tmp_path / "output", base_url="/api/files")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")

    assert await store.exists("../outside.mp4") is False
    assert await store.exists(str(Path("task-1") / ".." / ".." / outside.name)) is False


def test_local_artifact_store_rejects_ambiguous_relative_root():
    with pytest.raises(ValueError, match="output_root must be absolute"):
        LocalArtifactStore(output_root="output")


def test_task_runtime_anchors_relative_artifact_path_to_project_root(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    unrelated_cwd = tmp_path / "unrelated"
    project_root.mkdir()
    unrelated_cwd.mkdir()
    context = build_api_runtime_context(project_root)
    monkeypatch.setattr(runtime_context_module, "_API_RUNTIME_CONTEXT", context)
    monkeypatch.chdir(unrelated_cwd)

    runtime = build_task_runtime(APIConfig(artifact_base_path="output"))
    artifact_store = runtime.task_manager.registry.artifact_store

    assert isinstance(artifact_store, LocalArtifactStore)
    assert artifact_store.output_root == project_root / "output"
    assert not (unrelated_cwd / "output").exists()
