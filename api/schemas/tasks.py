from typing import Any

from pydantic import BaseModel

from api.tasks.models import TaskProgress, TaskStatus, TaskType


class TaskListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    tasks: list["TaskResponse"]
    total: int
    page: int
    page_size: int


class TaskResponse(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus
    progress: TaskProgress | None = None
    result: Any = None
    error: str | None = None
