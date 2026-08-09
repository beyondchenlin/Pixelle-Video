"""PostgreSQL TaskStore implementation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    MetaData,
    Table,
    Text,
    and_,
    asc,
    desc,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from api.tasks.models import (
    TASK_STATUS_TRANSITION_SOURCES,
    TERMINAL_TASK_STATUSES,
    ArtifactStatus,
    Task,
    TaskProgress,
    TaskStatus,
    TaskType,
    utc_now,
)
from api.tasks.store import (
    InvalidTaskTransitionError,
    LostTaskLeaseError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
)
from api.tasks.worker_registry import WorkerHeartbeat

metadata = MetaData()

generation_tasks = Table(
    "generation_tasks",
    metadata,
    Column("task_id", Text, primary_key=True),
    Column("task_type", Text, nullable=False),
    Column("generation_fingerprint", Text),
    Column("status", Text, nullable=False),
    Column("request_params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("progress", JSONB),
    Column("result", JSONB),
    Column("error", Text),
    Column("owner_id", Text),
    Column("lease_token", Text),
    Column("artifact_status", Text, nullable=False, server_default="none"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        name="ck_generation_tasks_status",
    ),
    CheckConstraint(
        "artifact_status IN ('none', 'persisted', 'missing')",
        name="ck_generation_tasks_artifact_status",
    ),
)

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_id", Text, primary_key=True),
    Column("supported_task_types", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

Index(
    "idx_generation_tasks_status_created_at",
    generation_tasks.c.status,
    generation_tasks.c.created_at,
)
Index(
    "idx_generation_tasks_fingerprint_status",
    generation_tasks.c.generation_fingerprint,
    generation_tasks.c.status,
)
Index(
    "idx_generation_tasks_fingerprint_completed",
    generation_tasks.c.generation_fingerprint,
    generation_tasks.c.completed_at,
    postgresql_where=generation_tasks.c.status == TaskStatus.COMPLETED.value,
)
Index(
    "idx_generation_tasks_pending_claim",
    generation_tasks.c.created_at,
    generation_tasks.c.task_id,
    postgresql_where=generation_tasks.c.status == TaskStatus.PENDING.value,
)
Index(
    "uq_generation_tasks_active_fingerprint",
    generation_tasks.c.task_type,
    generation_tasks.c.generation_fingerprint,
    unique=True,
    postgresql_where=and_(
        generation_tasks.c.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value]),
        generation_tasks.c.generation_fingerprint.is_not(None),
    ),
)
Index("idx_worker_heartbeats_heartbeat_at", worker_heartbeats.c.heartbeat_at)


def create_async_engine_from_dsn(dsn: str) -> AsyncEngine:
    return create_async_engine(dsn, pool_pre_ping=True)


class PostgresTaskStore:
    """PostgreSQL-backed implementation of the TaskStore protocol."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_task(self, task: Task) -> Task:
        values = self._task_to_values(task)
        try:
            async with self.session_factory() as session:
                await session.execute(insert(generation_tasks).values(**values))
                await session.commit()
        except IntegrityError as exc:
            raise TaskAlreadyExistsError(task.task_id) from exc

        created = await self.get_task(task.task_id)
        if created is None:
            raise TaskNotFoundError(task.task_id)
        return created

    async def get_task(self, task_id: str) -> Task | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(generation_tasks).where(generation_tasks.c.task_id == task_id)
            )
            row = result.mappings().first()
            return self._row_to_task(row) if row is not None else None

    async def find_reusable_by_fingerprint(
        self,
        *,
        fingerprint: str,
        task_type: TaskType,
        active_statuses: set[TaskStatus],
        completed_after: datetime | None,
    ) -> Task | None:
        async with self.session_factory() as session:
            active_result = await session.execute(
                select(generation_tasks)
                .where(
                    generation_tasks.c.generation_fingerprint == fingerprint,
                    generation_tasks.c.task_type == task_type.value,
                    generation_tasks.c.status.in_([status.value for status in active_statuses]),
                )
                .order_by(desc(generation_tasks.c.created_at))
                .limit(1)
            )
            active = active_result.mappings().first()
            if active is not None:
                return self._row_to_task(active)

            completed_conditions = [
                generation_tasks.c.generation_fingerprint == fingerprint,
                generation_tasks.c.task_type == task_type.value,
                generation_tasks.c.status == TaskStatus.COMPLETED.value,
            ]
            if completed_after is not None:
                completed_conditions.append(generation_tasks.c.completed_at >= completed_after)

            completed_result = await session.execute(
                select(generation_tasks)
                .where(*completed_conditions)
                .order_by(desc(generation_tasks.c.completed_at))
                .limit(1)
            )
            completed = completed_result.mappings().first()
            return self._row_to_task(completed) if completed is not None else None

    async def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        owner_id: str | None = None,
        lease_token: str | None = None,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
        result: dict | None = None,
        artifact_status: ArtifactStatus | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status.value,
            "updated_at": utc_now(),
        }
        if owner_id is not None:
            values["owner_id"] = owner_id
        if lease_token is not None:
            values["lease_token"] = lease_token
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if error is not None:
            values["error"] = error
        if result is not None:
            values["result"] = result
        if artifact_status is not None:
            values["artifact_status"] = artifact_status.value
        if status in TERMINAL_TASK_STATUSES:
            values["lease_token"] = None
            values["completed_at"] = func.coalesce(
                generation_tasks.c.completed_at,
                completed_at or utc_now(),
            )

        await self._execute_update(
            task_id=task_id,
            values=values,
            expected_owner_id=expected_owner_id,
            expected_lease_token=expected_lease_token,
            allowed_current_statuses=TASK_STATUS_TRANSITION_SOURCES[status],
        )

    async def update_progress(
        self,
        *,
        task_id: str,
        progress: TaskProgress,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None:
        await self._execute_update(
            task_id=task_id,
            values={"progress": progress.model_dump(), "updated_at": utc_now()},
            expected_owner_id=expected_owner_id,
            expected_lease_token=expected_lease_token,
            allowed_current_statuses=frozenset({TaskStatus.RUNNING}),
        )

    async def claim_next_pending(
        self,
        *,
        owner_id: str,
        lease_token: str,
        task_types: set[TaskType] | None = None,
    ) -> Task | None:
        async with self.session_factory() as session:
            async with session.begin():
                candidate = (
                    select(generation_tasks)
                    .where(generation_tasks.c.status == TaskStatus.PENDING.value)
                    .order_by(asc(generation_tasks.c.created_at))
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if task_types:
                    candidate = candidate.where(
                        generation_tasks.c.task_type.in_(
                            [task_type.value for task_type in task_types]
                        )
                    )

                result = await session.execute(candidate)
                row = result.mappings().first()
                if row is None:
                    return None

                now = utc_now()
                updated = await session.execute(
                    update(generation_tasks)
                    .where(generation_tasks.c.task_id == row["task_id"])
                    .values(
                        status=TaskStatus.RUNNING.value,
                        owner_id=owner_id,
                        lease_token=lease_token,
                        started_at=row["started_at"] or now,
                        updated_at=now,
                    )
                    .returning(generation_tasks)
                )
                updated_row = updated.mappings().one()
                return self._row_to_task(updated_row)

    async def list_running_tasks(
        self,
        *,
        task_types: set[TaskType] | None = None,
        limit: int = 100,
    ) -> list[Task]:
        async with self.session_factory() as session:
            query = (
                select(generation_tasks)
                .where(generation_tasks.c.status == TaskStatus.RUNNING.value)
                .order_by(asc(generation_tasks.c.updated_at), asc(generation_tasks.c.task_id))
                .limit(limit)
            )
            if task_types:
                query = query.where(
                    generation_tasks.c.task_type.in_([task_type.value for task_type in task_types])
                )
            result = await session.execute(query)
            return [self._row_to_task(row) for row in result.mappings()]

    async def claim_running_task(
        self,
        *,
        task_id: str,
        owner_id: str,
        lease_token: str,
        expected_owner_id: str | None,
        expected_lease_token: str | None,
    ) -> Task | None:
        async with self.session_factory() as session:
            async with session.begin():
                statement = (
                    update(generation_tasks)
                    .where(
                        generation_tasks.c.task_id == task_id,
                        generation_tasks.c.status == TaskStatus.RUNNING.value,
                    )
                    .values(
                        owner_id=owner_id,
                        lease_token=lease_token,
                        updated_at=utc_now(),
                    )
                    .returning(generation_tasks)
                )
                if expected_owner_id is not None:
                    statement = statement.where(generation_tasks.c.owner_id == expected_owner_id)
                if expected_lease_token is not None:
                    statement = statement.where(
                        generation_tasks.c.lease_token == expected_lease_token
                    )

                result = await session.execute(statement)
                row = result.mappings().first()
                return self._row_to_task(row) if row is not None else None

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        async with self.session_factory() as session:
            query = (
                select(generation_tasks)
                .order_by(desc(generation_tasks.c.created_at), desc(generation_tasks.c.task_id))
                .limit(limit)
                .offset(offset)
            )
            if status is not None:
                query = query.where(generation_tasks.c.status == status.value)
            result = await session.execute(query)
            return [self._row_to_task(row) for row in result.mappings()]

    async def count_tasks(self, status: TaskStatus | None = None) -> int:
        async with self.session_factory() as session:
            query = select(func.count()).select_from(generation_tasks)
            if status is not None:
                query = query.where(generation_tasks.c.status == status.value)
            result = await session.execute(query)
            return result.scalar_one()

    async def cancel_task(self, task_id: str) -> bool:
        return await self.cancel_task_if_owned(task_id)

    async def cancel_task_if_owned(
        self,
        task_id: str,
        *,
        expected_owner_id: str | None = None,
        expected_lease_token: str | None = None,
        require_lease_match: bool = False,
    ) -> bool:
        async with self.session_factory() as session:
            statement = (
                update(generation_tasks)
                .where(generation_tasks.c.task_id == task_id)
                .where(
                    generation_tasks.c.status.in_(
                        [TaskStatus.PENDING.value, TaskStatus.RUNNING.value]
                    )
                )
                .values(
                    status=TaskStatus.CANCELLED.value,
                    owner_id=None,
                    lease_token=None,
                    completed_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
            if require_lease_match:
                statement = statement.where(
                    generation_tasks.c.owner_id.is_(None)
                    if expected_owner_id is None
                    else generation_tasks.c.owner_id == expected_owner_id
                ).where(
                    generation_tasks.c.lease_token.is_(None)
                    if expected_lease_token is None
                    else generation_tasks.c.lease_token == expected_lease_token
                )
            result = await session.execute(statement)
            await session.commit()
            return bool(result.rowcount)

    async def _execute_update(
        self,
        *,
        task_id: str,
        values: dict[str, Any],
        expected_owner_id: str | None,
        expected_lease_token: str | None,
        allowed_current_statuses: frozenset[TaskStatus] | None = None,
    ) -> None:
        async with self.session_factory() as session:
            statement = update(generation_tasks).where(generation_tasks.c.task_id == task_id)
            if expected_owner_id is not None:
                statement = statement.where(generation_tasks.c.owner_id == expected_owner_id)
            if expected_lease_token is not None:
                statement = statement.where(generation_tasks.c.lease_token == expected_lease_token)
            if allowed_current_statuses is not None:
                statement = statement.where(
                    generation_tasks.c.status.in_(
                        [status.value for status in allowed_current_statuses]
                    )
                )

            result = await session.execute(statement.values(**values))
            await session.commit()

            if result.rowcount:
                return
            current_result = await session.execute(
                select(
                    generation_tasks.c.owner_id,
                    generation_tasks.c.lease_token,
                    generation_tasks.c.status,
                ).where(generation_tasks.c.task_id == task_id)
            )
            current = current_result.mappings().first()
            if current is None:
                raise TaskNotFoundError(task_id)
            if (expected_owner_id is not None and current["owner_id"] != expected_owner_id) or (
                expected_lease_token is not None and current["lease_token"] != expected_lease_token
            ):
                raise LostTaskLeaseError(task_id)
            if (
                allowed_current_statuses is not None
                and TaskStatus(current["status"]) not in allowed_current_statuses
            ):
                raise InvalidTaskTransitionError(
                    f"task {task_id} cannot change while {current['status']}"
                )
            raise TaskNotFoundError(task_id)

    @staticmethod
    def _task_to_values(task: Task) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "generation_fingerprint": task.generation_fingerprint,
            "status": task.status.value,
            "request_params": task.request_params or {},
            "progress": task.progress.model_dump() if task.progress else None,
            "result": task.result,
            "error": task.error,
            "owner_id": task.owner_id,
            "lease_token": task.lease_token,
            "artifact_status": task.artifact_status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "updated_at": task.updated_at,
        }

    @staticmethod
    def _row_to_task(row) -> Task:
        progress = row["progress"]
        return Task(
            task_id=row["task_id"],
            task_type=TaskType(row["task_type"]),
            generation_fingerprint=row["generation_fingerprint"],
            status=TaskStatus(row["status"]),
            request_params=dict(row["request_params"] or {}),
            progress=TaskProgress(**progress) if progress else None,
            result=row["result"],
            error=row["error"],
            owner_id=row["owner_id"],
            lease_token=row["lease_token"],
            artifact_status=ArtifactStatus(row["artifact_status"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            updated_at=row["updated_at"],
        )


class PostgresWorkerRegistry:
    def __init__(self, engine: AsyncEngine, *, heartbeat_ttl_seconds: int = 60) -> None:
        self.engine = engine
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        values = {
            "worker_id": heartbeat.worker_id,
            "supported_task_types": [
                task_type.value for task_type in heartbeat.supported_task_types
            ],
            "heartbeat_at": heartbeat.heartbeat_at,
            "updated_at": utc_now(),
        }
        statement = pg_insert(worker_heartbeats).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[worker_heartbeats.c.worker_id],
            set_=values,
        )
        async with self.session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def supports(self, task_type: TaskType, *, now: datetime | None = None) -> bool:
        cutoff = (now or utc_now()) - timedelta(seconds=self.heartbeat_ttl_seconds)
        async with self.session_factory() as session:
            result = await session.execute(
                select(worker_heartbeats.c.worker_id)
                .where(worker_heartbeats.c.heartbeat_at >= cutoff)
                .where(worker_heartbeats.c.supported_task_types.contains([task_type.value]))
                .limit(1)
            )
            return result.first() is not None
