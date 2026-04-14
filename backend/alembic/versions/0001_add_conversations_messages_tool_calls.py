"""add conversations, messages, and tool_calls tables

Revision ID: 0001
Revises:
Create Date: 2026-04-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("model_key", sa.String(100), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("total_input_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("total_output_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("message_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("starred", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, server_default="", nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("tool_use_id", sa.String(100), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_input", sa.JSON, nullable=True),
        sa.Column("is_tool_result", sa.Boolean, server_default="false", nullable=False),
        sa.Column("input_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("stop_reason", sa.String(50), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_use_id", sa.String(100), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_input", sa.JSON, nullable=True),
        sa.Column("tool_output", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), server_default="success", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("agent_turn", sa.Integer, server_default="1", nullable=False),
        sa.Column("call_order", sa.Integer, server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_calls_conversation_id", "tool_calls", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("messages")
    op.drop_table("conversations")
