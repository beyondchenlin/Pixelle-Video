"""create generation tasks

Revision ID: 0001_create_generation_tasks
Revises:
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_create_generation_tasks"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_tasks",
        sa.Column("task_id", sa.Text(), primary_key=True),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("generation_fingerprint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "request_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("lease_token", sa.Text(), nullable=True),
        sa.Column("artifact_status", sa.Text(), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_generation_tasks_status",
        ),
        sa.CheckConstraint(
            "artifact_status IN ('none', 'persisted', 'missing')",
            name="ck_generation_tasks_artifact_status",
        ),
    )
    op.create_index(
        "idx_generation_tasks_status_created_at",
        "generation_tasks",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_generation_tasks_fingerprint_status",
        "generation_tasks",
        ["generation_fingerprint", "status"],
    )
    op.create_index(
        "idx_generation_tasks_fingerprint_completed",
        "generation_tasks",
        ["generation_fingerprint", "completed_at"],
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.create_index(
        "idx_generation_tasks_pending_claim",
        "generation_tasks",
        ["created_at", "task_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_generation_tasks_active_fingerprint",
        "generation_tasks",
        ["task_type", "generation_fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'running') AND generation_fingerprint IS NOT NULL"
        ),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_generation_tasks_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_generation_tasks_updated_at
        BEFORE UPDATE ON generation_tasks
        FOR EACH ROW
        EXECUTE FUNCTION set_generation_tasks_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_generation_tasks_updated_at ON generation_tasks")
    op.execute("DROP FUNCTION IF EXISTS set_generation_tasks_updated_at")
    op.drop_index("uq_generation_tasks_active_fingerprint", table_name="generation_tasks")
    op.drop_index("idx_generation_tasks_pending_claim", table_name="generation_tasks")
    op.drop_index("idx_generation_tasks_fingerprint_completed", table_name="generation_tasks")
    op.drop_index("idx_generation_tasks_fingerprint_status", table_name="generation_tasks")
    op.drop_index("idx_generation_tasks_status_created_at", table_name="generation_tasks")
    op.drop_table("generation_tasks")
