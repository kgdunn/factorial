"""add api cost tracking columns to messages and conversations

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-message cost snapshot (nullable — not all messages come from an
    # API call; user/tool_result rows leave these NULL).
    op.add_column(
        "messages",
        sa.Column("input_rate_usd_per_mtok", sa.Numeric(12, 6), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("output_rate_usd_per_mtok", sa.Numeric(12, 6), nullable=True),
    )
    op.add_column("messages", sa.Column("input_cost_usd", sa.Numeric(14, 10), nullable=True))
    op.add_column("messages", sa.Column("output_cost_usd", sa.Numeric(14, 10), nullable=True))
    op.add_column("messages", sa.Column("markup_rate", sa.Numeric(6, 4), nullable=True))
    op.add_column("messages", sa.Column("markup_cost_usd", sa.Numeric(14, 10), nullable=True))

    # Conversation-level running totals.
    op.add_column(
        "conversations",
        sa.Column("total_cost_usd", sa.Numeric(14, 10), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "total_markup_cost_usd", sa.Numeric(14, 10), server_default="0", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "total_markup_cost_usd")
    op.drop_column("conversations", "total_cost_usd")
    op.drop_column("messages", "markup_cost_usd")
    op.drop_column("messages", "markup_rate")
    op.drop_column("messages", "output_cost_usd")
    op.drop_column("messages", "input_cost_usd")
    op.drop_column("messages", "output_rate_usd_per_mtok")
    op.drop_column("messages", "input_rate_usd_per_mtok")
