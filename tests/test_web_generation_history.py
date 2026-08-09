from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from web.utils import generation_history
from web.utils.generation_history import WebGenerationRun


def _mp4_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isomvideo"


class PersistenceStub:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    async def save_task_metadata(self, task_id: str, metadata: dict[str, Any]) -> None:
        assert task_id == metadata["task_id"]
        self.saved.append(metadata)


class CoreStub:
    def __init__(self) -> None:
        self.persistence = PersistenceStub()
        self.config: dict[str, Any] = {}


@pytest.fixture
def task_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    task_dir = tmp_path / "output" / "task-1"
    (task_dir / "frames").mkdir(parents=True)
    monkeypatch.setattr(
        generation_history,
        "create_task_output_dir",
        lambda: (str(task_dir), "task-1"),
    )
    monkeypatch.setattr(generation_history, "_probe_video_duration", lambda path: 2.5)
    return task_dir


@pytest.mark.asyncio
async def test_generation_run_persists_running_and_completed_lifecycle(
    task_directory: Path,
) -> None:
    core = CoreStub()
    run = await WebGenerationRun.start(
        core=core,
        pipeline="image_to_video",
        input_params={
            "text": "hello",
            "audio_assets": ["one.png", "two.png"],
            "api_key": "secret-value",
        },
    )

    async def operation(active_run: WebGenerationRun) -> str:
        source = active_run.task_dir / "source.mp4"
        source.write_bytes(_mp4_bytes())
        return str(source)

    result = await run.execute(operation)

    assert result == str(task_directory / "final.mp4")
    assert (task_directory / "final.mp4").read_bytes() == _mp4_bytes()
    assert [item["status"] for item in core.persistence.saved] == ["running", "completed"]
    assert core.persistence.saved[0]["input"]["audio_assets"] == {"count": 2}
    assert core.persistence.saved[0]["input"]["api_key"] == "***"
    assert core.persistence.saved[-1]["result"] == {
        "video_path": str(task_directory / "final.mp4"),
        "duration": 2.5,
        "file_size": len(_mp4_bytes()),
        "n_frames": 0,
    }


@pytest.mark.asyncio
async def test_generation_run_persists_redacted_failure(task_directory: Path) -> None:
    core = CoreStub()
    run = await WebGenerationRun.start(
        core=core,
        pipeline="digital_human",
        input_params={},
    )

    async def operation(active_run: WebGenerationRun) -> str:
        raise RuntimeError("api_key=do-not-persist")

    with pytest.raises(RuntimeError, match="do-not-persist"):
        await run.execute(operation)

    assert [item["status"] for item in core.persistence.saved] == ["running", "failed"]
    assert "do-not-persist" not in core.persistence.saved[-1]["error"]
    assert "***" in core.persistence.saved[-1]["error"]
