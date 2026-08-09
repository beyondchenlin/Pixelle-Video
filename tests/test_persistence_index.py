from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pixelle_video.services.persistence import PersistenceService


def _metadata(task_id: str, created_at: datetime) -> dict:
    return {
        "task_id": task_id,
        "created_at": created_at.isoformat(),
        "status": "completed",
        "input": {"title": task_id, "custom": {"preserved": True}},
        "result": {
            "duration": 1.5,
            "file_size": 10,
            "n_frames": 1,
            "video_path": f"output/{task_id}/final.mp4",
        },
        "config": {"pipeline": "test"},
    }


@pytest.mark.asyncio
async def test_index_updates_do_not_lose_concurrent_writes_across_service_instances(
    tmp_path: Path,
) -> None:
    first = PersistenceService(output_dir=str(tmp_path))
    second = PersistenceService(output_dir=str(tmp_path))
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    await asyncio.gather(
        *[
            (first if index % 2 == 0 else second).save_task_metadata(
                f"task-{index:03d}",
                _metadata(f"task-{index:03d}", base_time + timedelta(seconds=index)),
            )
            for index in range(40)
        ]
    )

    index_data = json.loads((tmp_path / ".index.json").read_text(encoding="utf-8"))
    assert len(index_data["tasks"]) == 40
    assert {item["task_id"] for item in index_data["tasks"]} == {
        f"task-{index:03d}" for index in range(40)
    }


@pytest.mark.asyncio
async def test_list_tasks_uses_index_for_paging_and_returns_full_metadata(
    tmp_path: Path,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(3):
        task_id = f"task-{index}"
        await service.save_task_metadata(
            task_id,
            _metadata(task_id, base_time + timedelta(seconds=index)),
        )

    tasks = await service.list_tasks(limit=1, offset=1)

    assert [item["task_id"] for item in tasks] == ["task-1"]
    assert tasks[0]["input"]["custom"] == {"preserved": True}
    assert tasks[0]["config"] == {"pipeline": "test"}


@pytest.mark.asyncio
async def test_corrupt_index_recovers_listing_from_canonical_metadata(tmp_path: Path) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    await service.save_task_metadata(
        "task-1",
        _metadata("task-1", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )
    service.index_file.write_text("{broken", encoding="utf-8")

    tasks = await service.list_tasks()

    assert [item["task_id"] for item in tasks] == ["task-1"]


@pytest.mark.asyncio
async def test_persistence_rejects_task_path_escape(tmp_path: Path) -> None:
    service = PersistenceService(output_dir=str(tmp_path))

    with pytest.raises(ValueError, match="unsafe path"):
        service.get_task_dir("../escape")
    assert await service.delete_task("../escape") is False
