"""user_feedback table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-19

Creates the ``user_feedback`` table backing the in-app "Give feedback"
button. Holds one row per submission with topic, free-text message,
contextual metadata captured at submit time, an optional inline PNG
screenshot of the current tab, and a reply audit trail populated when an
admin answers through the dashboard.

This is a new table — purely **expand-safe** per the blue-green rule in
CLAUDE.md. Old code ignores the table during a cutover; no contract step
is required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("viewport", sa.String(32), nullable=True),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("screenshot_png", sa.LargeBinary(), nullable=True),
        sa.Column("screenshot_mime", sa.String(32), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "replied_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reply_body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_feedback_created_at",
        "user_feedback",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_user_feedback_user_created_at",
        "user_feedback",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_user_feedback_user_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_created_at", table_name="user_feedback")
    op.drop_table("user_feedback")
