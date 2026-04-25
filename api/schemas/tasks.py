from pydantic import BaseModel

from api.tasks.models import Task


class TaskListResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    tasks: list[Task]
    total: int
    page: int
    page_size: int
