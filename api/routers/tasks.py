# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Task management endpoints

Endpoints for managing async tasks (checking status, canceling, etc.)
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger

from api.schemas.tasks import TaskListResponse, TaskResponse
from api.tasks import Task, TaskStatus, TaskType, task_manager

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    request: Request = None,
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tasks")
):
    """
    List tasks

    Retrieve list of tasks with optional filtering.

    - **status**: Optional filter by status (pending/running/completed/failed/cancelled)
    - **limit**: Maximum number of tasks to return (default 100)

    Returns list of tasks sorted by creation time (newest first).
    """
    try:
        tasks = await task_manager.list_tasks(status=status, limit=limit)
        return [present_task(task, request=request) for task in tasks]

    except Exception as e:
        logger.error(f"List tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/page", response_model=TaskListResponse)
async def list_tasks_page(
    request: Request = None,
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Tasks per page"),
):
    """
    List tasks with pagination metadata.
    """
    try:
        offset = (page - 1) * page_size
        tasks = await task_manager.list_tasks(status=status, limit=page_size, offset=offset)
        total = await task_manager.count_tasks(status=status)
        return TaskListResponse(
            tasks=[present_task(task, request=request) for task in tasks],
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"List paginated tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request):
    """
    Get task details

    Retrieve detailed information about a specific task.

    - **task_id**: Task ID

    Returns task details including status, progress, and result (if completed).
    """
    try:
        task = await task_manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return present_task(task, request=request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get task error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel task

    Cancel a running or pending task.

    - **task_id**: Task ID

    Returns success status.
    """
    try:
        success = await task_manager.cancel_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return {
            "success": True,
            "message": f"Task {task_id} cancelled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel task error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def task_storage_key_to_url(request: Request | None, storage_key: str) -> str:
    if request is None:
        return f"/api/files/{storage_key.lstrip('/')}"
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/files/{storage_key.lstrip('/')}"


def present_task(task: Task, *, request: Request | None = None) -> TaskResponse:
    result = task.result
    if (
        task.task_type == TaskType.VIDEO_GENERATION
        and isinstance(result, dict)
        and result.get("storage_key")
        and "video_url" not in result
    ):
        result = {
            **result,
            "video_url": task_storage_key_to_url(request, str(result["storage_key"])),
        }
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
        progress=task.progress,
        result=result,
        error=task.error,
    )
