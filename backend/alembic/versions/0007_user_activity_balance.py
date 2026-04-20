"""user activity tracking + user_balances table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-19

Adds four nullable columns to ``users`` for sign-in activity and geo
(``last_login_at``, ``last_login_ip``, ``country``, ``timezone``) and
creates the new ``user_balances`` table carrying a prepaid dollar +
token balance per user.

All changes are **expand-safe** per the blue-green rule in CLAUDE.md:
new nullable columns default to NULL, the new table is ignored by old
code, no drops or NULL-tightening. A single-deploy migration is safe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_ip", postgresql.INET(), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(2), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.String(64), nullable=True))

    op.create_table(
        "user_balances",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "balance_usd",
            sa.Numeric(12, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "balance_tokens",
            sa.BigInteger(),
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


def downgrade() -> None:
    op.drop_table("user_balances")
    op.drop_column("users", "timezone")
    op.drop_column("users", "country")
    op.drop_column("users", "last_login_ip")
    op.drop_column("users", "last_login_at")
