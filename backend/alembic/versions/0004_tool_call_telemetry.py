"""tool_calls telemetry columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

Adds per-invocation telemetry columns to ``tool_calls``:

- ``turn_id``       — links tool calls to the ``ChatEvent.turn_id`` of the
                      user message that caused them, so all tools for one
                      user turn can be grouped.
- ``model_key``     — which orchestrating model produced the tool call
                      (needed for per-model A/B comparisons).
- ``rss_bytes``     — resident set size of the backend process at tool
                      finish. Process-wide, not per-tool.
- ``cpu_percent``   — psutil cpu_percent sample at tool finish.
                      Process-wide, not per-tool.
- ``input_bytes`` / ``output_bytes`` — JSON payload size; cheap cost proxy.
- ``output_truncated`` — reserved for a future size-cap policy. Default
                      false; lets us add truncation later without a
                      migration.
- ``tool_version``  — optional version string reported by the tool, so
                      behavioural changes can be correlated with code
                      revisions.

All columns are nullable. This is purely expand-safe: old code ignores
the new columns, new code populates them. No contract step needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tool_calls",
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column("model_key", sa.String(100), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column("rss_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column("cpu_percent", sa.Float(), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column("input_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column("output_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tool_calls",
        sa.Column(
            "output_truncated",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tool_calls",
        sa.Column("tool_version", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_tool_calls_turn_id",
        "tool_calls",
        ["turn_id"],
    )
    op.create_index(
        "ix_tool_calls_conversation_created",
        "tool_calls",
        ["conversation_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_calls_conversation_created", table_name="tool_calls")
    op.drop_index("ix_tool_calls_turn_id", table_name="tool_calls")
    op.drop_column("tool_calls", "tool_version")
    op.drop_column("tool_calls", "output_truncated")
    op.drop_column("tool_calls", "output_bytes")
    op.drop_column("tool_calls", "input_bytes")
    op.drop_column("tool_calls", "cpu_percent")
    op.drop_column("tool_calls", "rss_bytes")
    op.drop_column("tool_calls", "model_key")
    op.drop_column("tool_calls", "turn_id")
