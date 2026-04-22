"""simulators table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-22

Adds the ``simulators`` table carrying the hidden ``private_state`` for
fake-data simulators created via the ``create_simulator`` agent tool.
Expand-safe per the blue-green rule: new table, ignored by old code.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sim_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("public_summary", postgresql.JSONB(), nullable=True),
        sa.Column("private_state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "reveal_request_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_simulators_sim_id",
        "simulators",
        ["sim_id"],
        unique=True,
    )
    op.create_index("ix_simulators_user_id", "simulators", ["user_id"])
    op.create_index(
        "ix_simulators_conversation_id",
        "simulators",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_simulators_conversation_id", table_name="simulators")
    op.drop_index("ix_simulators_user_id", table_name="simulators")
    op.drop_index("ix_simulators_sim_id", table_name="simulators")
    op.drop_table("simulators")
