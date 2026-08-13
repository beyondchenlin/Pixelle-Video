from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pixelle_video.services import persistence as persistence_module
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


@pytest.mark.asyncio
async def test_delete_task_retries_transient_windows_reader_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    task_dir = service.get_task_dir("task-locked")
    task_dir.mkdir()
    calls = []
    sleeps = []
    real_rmtree = shutil.rmtree

    def transient_rmtree(path: Path) -> None:
        calls.append(path)
        if len(calls) < 3:
            error = PermissionError("file is being read")
            error.winerror = 32
            raise error
        real_rmtree(path)

    monkeypatch.setattr(persistence_module.shutil, "rmtree", transient_rmtree)
    monkeypatch.setattr(persistence_module.time, "sleep", sleeps.append)

    assert await service.delete_task("task-locked") is True
    assert calls == [task_dir, task_dir, task_dir]
    assert sleeps == [0.05, 0.1]
    assert not task_dir.exists()


@pytest.mark.asyncio
async def test_delete_task_is_idempotent_under_concurrent_requests(
    tmp_path: Path,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    task_dir = service.get_task_dir("task-concurrent")
    task_dir.mkdir()
    (task_dir / "final.mp4").write_bytes(b"video")

    results = await asyncio.gather(
        *(service.delete_task("task-concurrent") for _ in range(8))
    )

    assert results == [True] * 8
    assert not task_dir.exists()
    assert await service.list_tasks() == []


def test_delete_task_does_not_retry_deterministic_permission_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_dir = tmp_path / "task-denied"
    task_dir.mkdir()
    calls = []

    def denied_rmtree(path: Path) -> None:
        calls.append(path)
        error = PermissionError("access denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr(persistence_module.shutil, "rmtree", denied_rmtree)
    monkeypatch.setattr(
        persistence_module.time,
        "sleep",
        lambda _delay: pytest.fail("deterministic failures must not be retried"),
    )

    with pytest.raises(PermissionError, match="access denied"):
        PersistenceService._delete_task_directory(task_dir)
    assert calls == [task_dir]


@pytest.mark.asyncio
async def test_metadata_success_is_not_reversed_by_rebuildable_index_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    metadata = _metadata("task-1", datetime(2026, 1, 1, tzinfo=timezone.utc))
    metadata.pop("task_id")

    def fail_index_update(*_args, **_kwargs) -> None:
        raise OSError("simulated index write failure")

    monkeypatch.setattr(service, "_replace_index_entry", fail_index_update)

    await service.save_task_metadata("task-1", metadata)

    assert (tmp_path / "task-1" / "metadata.json").is_file()
    assert service.index_dirty_file.is_file()
    assert "task_id" not in metadata

    monkeypatch.undo()
    tasks = await service.list_tasks()

    assert [task["task_id"] for task in tasks] == ["task-1"]
    assert not service.index_dirty_file.exists()


@pytest.mark.asyncio
async def test_paginated_listing_handles_mixed_and_invalid_timestamps(
    tmp_path: Path,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))
    index = {
        "version": "1.0",
        "tasks": [
            {"task_id": "invalid", "created_at": "not-a-date"},
            {"task_id": "aware", "created_at": "2026-01-02T00:00:00+08:00"},
            {"task_id": "naive", "created_at": "2026-01-01T00:00:00"},
            {"task_id": "missing", "created_at": None},
        ],
    }
    service._save_index(index)

    result = await service.list_tasks_paginated(page=1, page_size=10)

    assert [task["task_id"] for task in result["tasks"]] == [
        "aware",
        "naive",
        "invalid",
        "missing",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page": 0}, "page must"),
        ({"page_size": 0}, "page_size must"),
        ({"sort_by": "unknown"}, "unsupported task sort field"),
        ({"sort_order": "sideways"}, "sort_order must"),
    ],
)
async def test_paginated_listing_rejects_invalid_query_contract(
    tmp_path: Path,
    kwargs: dict,
    message: str,
) -> None:
    service = PersistenceService(output_dir=str(tmp_path))

    with pytest.raises(ValueError, match=message):
        await service.list_tasks_paginated(**kwargs)
