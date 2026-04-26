"""BYOK schema (token + DEK + per-session wrap + audit history)

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-26

Adds the BYOK (Bring-Your-Own Anthropic API key) schema:

- ``users``: six new nullable columns + non-null status default ``absent``.
- ``sessions``: two new nullable BYTEA columns for the per-session DEK wrap.
- ``messages``: ``byok_used`` boolean default ``false``.
- ``byok_credentials_history``: append-only audit table.

All changes are **expand-safe** per the blue-green rule in CLAUDE.md:
new nullable columns default to NULL, the new ``status`` column has a
server default so old code paths that don't set it still write valid
rows, the new table is ignored by old code, and the boolean default on
``messages.byok_used`` backfills cleanly without rewriting existing rows.
A single-deploy migration is safe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users: BYOK columns ------------------------------------------------
    op.add_column("users", sa.Column("byok_token_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("byok_dek_wrapped", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("byok_kek_salt", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("byok_kdf_params", postgresql.JSONB(), nullable=True))
    op.add_column(
        "users",
        sa.Column("byok_token_last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "byok_token_status",
            sa.String(20),
            nullable=False,
            server_default="absent",
        ),
    )

    # ---- sessions: per-session DEK wrap -------------------------------------
    op.add_column("sessions", sa.Column("byok_session_key_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column("sessions", sa.Column("byok_dek_session_wrapped", sa.LargeBinary(), nullable=True))

    # ---- messages: BYOK billing flag ----------------------------------------
    op.add_column(
        "messages",
        sa.Column(
            "byok_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ---- byok_credentials_history: append-only audit log -------------------
    op.create_table(
        "byok_credentials_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("status_after", sa.String(20), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_byok_credentials_history_user_id",
        "byok_credentials_history",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_byok_credentials_history_user_id",
        table_name="byok_credentials_history",
    )
    op.drop_table("byok_credentials_history")

    op.drop_column("messages", "byok_used")

    op.drop_column("sessions", "byok_dek_session_wrapped")
    op.drop_column("sessions", "byok_session_key_encrypted")

    op.drop_column("users", "byok_token_status")
    op.drop_column("users", "byok_token_last_verified_at")
    op.drop_column("users", "byok_kdf_params")
    op.drop_column("users", "byok_kek_salt")
    op.drop_column("users", "byok_dek_wrapped")
    op.drop_column("users", "byok_token_ciphertext")
