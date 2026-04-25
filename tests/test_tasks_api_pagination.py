import pytest

import api.routers.tasks as tasks_router
from api.tasks.models import Task, TaskStatus, TaskType


class FakeTaskManager:
    def __init__(self) -> None:
        self.tasks = [
            Task(task_id=f"task-{index}", task_type=TaskType.VIDEO_GENERATION)
            for index in range(1, 6)
        ]

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        tasks = self.tasks
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return tasks[offset : offset + limit]

    async def count_tasks(self, status: TaskStatus | None = None) -> int:
        if status is None:
            return len(self.tasks)
        return len([task for task in self.tasks if task.status == status])


@pytest.mark.asyncio
async def test_list_tasks_page_returns_paginated_response(monkeypatch):
    monkeypatch.setattr(tasks_router, "task_manager", FakeTaskManager())

    response = await tasks_router.list_tasks_page(status=None, page=2, page_size=2)

    assert response.success is True
    assert response.message == "Success"
    assert response.total == 5
    assert response.page == 2
    assert response.page_size == 2
    assert [task.task_id for task in response.tasks] == ["task-3", "task-4"]


@pytest.mark.asyncio
async def test_list_tasks_still_returns_plain_list(monkeypatch):
    monkeypatch.setattr(tasks_router, "task_manager", FakeTaskManager())

    response = await tasks_router.list_tasks(status=None, limit=2)

    assert isinstance(response, list)
    assert [task.task_id for task in response] == ["task-1", "task-2"]
    assert not hasattr(response, "success")
