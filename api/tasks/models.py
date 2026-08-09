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
Task data models
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_serializer


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for persisted task state."""
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """Task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_TASK_STATUSES = frozenset({TaskStatus.PENDING, TaskStatus.RUNNING})
TERMINAL_TASK_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)
TASK_STATUS_TRANSITION_SOURCES: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.PENDING}),
    TaskStatus.RUNNING: frozenset({TaskStatus.PENDING, TaskStatus.RUNNING}),
    TaskStatus.COMPLETED: frozenset({TaskStatus.RUNNING, TaskStatus.COMPLETED}),
    TaskStatus.FAILED: frozenset(
        {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.FAILED}
    ),
    TaskStatus.CANCELLED: frozenset(
        {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.CANCELLED}
    ),
}


class ArtifactStatus(str, Enum):
    """Persisted generation artifact status"""
    NONE = "none"
    PERSISTED = "persisted"
    MISSING = "missing"


class TaskType(str, Enum):
    """Task type"""
    VIDEO_GENERATION = "video_generation"
    FRAME_IMAGE_REGENERATION = "frame_image_regeneration"


class TaskProgress(BaseModel):
    """Task progress information"""
    current: int = 0
    total: int = 0
    percentage: float = 0.0
    message: str = ""
    event_type: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Task model"""
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    
    # Progress tracking
    progress: Optional[TaskProgress] = None
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utc_now)
    
    # Request parameters (for reference)
    request_params: Optional[dict] = None

    # Distributed generation coordination
    generation_fingerprint: Optional[str] = None
    owner_id: Optional[str] = None
    lease_token: Optional[str] = None
    artifact_status: ArtifactStatus = ArtifactStatus.NONE

    @field_serializer("created_at", "started_at", "completed_at", "updated_at", when_used="json")
    def serialize_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None


class ReserveOutcome(BaseModel):
    """Result of reserving or reusing a generation task."""
    task: Task
    created: bool
    reused_reason: Literal["active", "recent_completed"] | None = None


class ExecutionLease(BaseModel):
    """Worker execution lease with a fencing token."""
    task_id: str
    owner_id: str
    lease_token: str
    lease_expires_at: datetime


class ClaimedTask(BaseModel):
    """Task claimed by a worker with an execution lease."""
    task: Task
    lease: ExecutionLease
