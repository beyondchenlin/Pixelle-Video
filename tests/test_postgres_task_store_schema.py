from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql


def test_generation_tasks_migration_contains_source_level_constraints():
    migration = Path(
        "api/tasks/alembic/versions/0001_create_generation_tasks.py"
    ).read_text(encoding="utf-8")

    assert "generation_tasks" in migration
    assert "uq_generation_tasks_active_fingerprint" in migration
    assert "postgresql_where" in migration
    assert "status IN ('pending', 'running')" in migration
    assert "lease_token" in migration
    assert "artifact_status" in migration
    assert "idx_generation_tasks_pending_claim" in migration
    assert "trg_generation_tasks_updated_at" in migration


def test_worker_heartbeat_migration_contains_shared_capability_table():
    migration = Path(
        "api/tasks/alembic/versions/0002_create_worker_heartbeats.py"
    ).read_text(encoding="utf-8")

    assert "worker_heartbeats" in migration
    assert "worker_id" in migration
    assert "supported_task_types" in migration
    assert "heartbeat_at" in migration
    assert "idx_worker_heartbeats_heartbeat_at" in migration


def test_postgres_worker_registry_exposes_shared_heartbeat_methods():
    from api.tasks.postgres import PostgresWorkerRegistry

    assert hasattr(PostgresWorkerRegistry, "heartbeat")
    assert hasattr(PostgresWorkerRegistry, "supports")


def test_postgres_store_exposes_required_methods():
    from api.tasks.postgres import PostgresTaskStore

    for name in [
        "create_task",
        "get_task",
        "find_reusable_by_fingerprint",
        "update_status",
        "update_progress",
        "claim_next_pending",
        "list_tasks",
        "count_tasks",
        "cancel_task",
    ]:
        assert hasattr(PostgresTaskStore, name)


def test_postgres_store_list_tasks_uses_stable_pagination_order():
    source = Path("api/tasks/postgres.py").read_text(encoding="utf-8")

    assert (
        ".order_by(desc(generation_tasks.c.created_at), desc(generation_tasks.c.task_id))"
        in source
    )


@pytest.mark.asyncio
async def test_postgres_store_count_tasks_counts_generation_tasks_with_status_filter():
    from api.tasks.models import TaskStatus
    from api.tasks.postgres import PostgresTaskStore

    class FakeResult:
        def scalar_one(self) -> int:
            return 7

    class FakeSession:
        statement = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def execute(self, statement):
            self.statement = statement
            return FakeResult()

    fake_session = FakeSession()
    store = object.__new__(PostgresTaskStore)
    store.session_factory = lambda: fake_session

    assert await store.count_tasks(status=TaskStatus.RUNNING) == 7

    compiled = fake_session.statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "SELECT count(*) AS count_1" in sql
    assert "FROM generation_tasks" in sql
    assert "WHERE generation_tasks.status =" in sql
    assert compiled.params["status_1"] == TaskStatus.RUNNING.value
