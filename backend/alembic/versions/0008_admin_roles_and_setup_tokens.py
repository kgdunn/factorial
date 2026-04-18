"""admin on users, roles table, setup tokens, signup role fields

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-18

Changes:

- ``roles`` table + seeding with the eight built-in roles
  (previously the ``background`` Literal enum).
- ``setup_tokens`` table for admin bootstrap and password reset.
- ``users.is_admin`` boolean (replaces the ``ADMIN_EMAILS`` env var).
- ``users.role_id`` nullable FK -> ``roles.id`` (backfilled from
  ``users.background`` when the strings match).
- ``signup_requests.requested_role`` (applicant's free text) and
  ``signup_requests.role_id`` (admin-decided role at approval time).

``users.background`` is kept for one release so we don't lose data
in case a rollback is needed; a later migration will drop it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BUILTIN_ROLES: list[tuple[str, str]] = [
    ("chemical_engineer", "Chemical engineer"),
    ("pharmaceutical_scientist", "Pharmaceutical scientist"),
    ("food_scientist", "Food scientist"),
    ("academic_researcher", "Academic researcher"),
    ("quality_engineer", "Quality engineer"),
    ("data_scientist", "Data scientist"),
    ("student", "Student"),
    ("other", "Other / not listed"),
]


def upgrade() -> None:
    # 1. roles
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    # Seed built-in roles.
    roles_table = sa.table(
        "roles",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_builtin", sa.Boolean),
    )
    op.bulk_insert(
        roles_table,
        [{"name": name, "description": desc, "is_builtin": True} for name, desc in _BUILTIN_ROLES],
    )

    # 2. users: is_admin, role_id
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_role_id", "users", ["role_id"])

    # Backfill users.role_id from users.background when the slug matches.
    op.execute(
        """
        UPDATE users u
        SET role_id = r.id
        FROM roles r
        WHERE r.name = u.background
          AND u.background IS NOT NULL
        """
    )

    # 3. setup_tokens
    op.create_table(
        "setup_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_setup_tokens_user_id", "setup_tokens", ["user_id"])
    op.create_index("ix_setup_tokens_token", "setup_tokens", ["token"], unique=True)

    # 4. signup_requests: requested_role, role_id
    op.add_column(
        "signup_requests",
        sa.Column("requested_role", sa.String(255), nullable=True),
    )
    op.add_column(
        "signup_requests",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("signup_requests", "role_id")
    op.drop_column("signup_requests", "requested_role")

    op.drop_index("ix_setup_tokens_token", table_name="setup_tokens")
    op.drop_index("ix_setup_tokens_user_id", table_name="setup_tokens")
    op.drop_table("setup_tokens")

    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_column("users", "role_id")
    op.drop_column("users", "is_admin")

    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
