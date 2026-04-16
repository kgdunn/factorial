"""add experiment_shares table for shareable read-only links

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_shares",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "experiment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "allow_results",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "view_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_experiment_shares_experiment_id",
        "experiment_shares",
        ["experiment_id"],
    )
    op.create_index(
        "ix_experiment_shares_token",
        "experiment_shares",
        ["token"],
        unique=True,
    )
    op.create_index(
        "ix_experiment_shares_exp_revoked",
        "experiment_shares",
        ["experiment_id", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_shares_exp_revoked", table_name="experiment_shares")
    op.drop_index("ix_experiment_shares_token", table_name="experiment_shares")
    op.drop_index("ix_experiment_shares_experiment_id", table_name="experiment_shares")
    op.drop_table("experiment_shares")
