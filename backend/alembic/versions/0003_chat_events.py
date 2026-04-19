"""chat_events durable stream log for SSE resume

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19

Creates ``chat_events``: an append-only log of every SSE event emitted
during an agent turn. Each row carries a ``turn_id`` (one per
``run_chat`` invocation) and a monotonic ``sequence`` within the turn so
the frontend can resume a dropped SSE stream by sending the standard
``Last-Event-ID`` header.

Rows for a conversation are deleted via ``ON DELETE CASCADE`` when the
conversation is deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("turn_id", "sequence", name="uq_chat_events_turn_sequence"),
    )
    op.create_index(
        "ix_chat_events_conversation_created",
        "chat_events",
        ["conversation_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_chat_events_turn_sequence",
        "chat_events",
        ["turn_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_events_turn_sequence", table_name="chat_events")
    op.drop_index("ix_chat_events_conversation_created", table_name="chat_events")
    op.drop_table("chat_events")
