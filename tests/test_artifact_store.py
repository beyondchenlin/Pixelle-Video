from pathlib import Path

import pytest

from api.tasks.artifacts import LocalArtifactStore


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
