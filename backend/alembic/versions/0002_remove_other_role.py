"""remove built-in 'other' role

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25

The signup form has its own hardcoded \"Other (describe below)\" option
that collects a free-text role description. The seeded ``other`` role
rendered as a second \"Other / not listed\" entry in the dropdown and
captured no information, so we drop it. ``users.role_id`` and
``signup_requests.role_id`` both use ``ON DELETE SET NULL``, so any
rows pointing at it are nulled out cleanly.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM roles WHERE name = 'other' AND is_builtin = true"
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (name, description, is_builtin)
        VALUES ('other', 'Other / not listed', true)
        ON CONFLICT (name) DO NOTHING
        """
    )
