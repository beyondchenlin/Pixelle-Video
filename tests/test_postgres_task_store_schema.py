from pathlib import Path


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
