"""admin_events operational log

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-19

Creates the ``admin_events`` table: a generic operational log that will
back the future admin dashboard. Designed to hold run records for
long-running jobs (postgres_backup, postgres_restore, restore_drill) as
well as snapshot rows for user counts, token usage, token budgets, and
any other operational events we add later.

The ``event_type`` column is a free string (not a Postgres enum) so
adding a new event kind never forces a migration. Type-specific data
lives in the ``payload`` JSONB column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_admin_events_event_type_created_at",
        "admin_events",
        ["event_type", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_events_status_created_at",
        "admin_events",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_events_created_at",
        "admin_events",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_admin_events_payload_gin",
        "admin_events",
        ["payload"],
        postgresql_using="gin",
        postgresql_ops={"payload": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_admin_events_payload_gin", table_name="admin_events")
    op.drop_index("ix_admin_events_created_at", table_name="admin_events")
    op.drop_index("ix_admin_events_status_created_at", table_name="admin_events")
    op.drop_index("ix_admin_events_event_type_created_at", table_name="admin_events")
    op.drop_table("admin_events")
