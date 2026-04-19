"""signup_requests disclaimer acceptance columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-19

Adds two columns to ``signup_requests`` so the public /register form can
capture disclaimer acceptance at submission time:

- ``accepted_disclaimers`` — BOOLEAN NOT NULL DEFAULT false. The server
                             default lets old-backend INSERTs during a
                             blue-green cutover satisfy NOT NULL with a
                             truthful value (the old form never showed
                             the checkbox).
- ``disclaimers_accepted_at`` — TIMESTAMPTZ NULL. Populated by the new
                             backend when the applicant ticks the box.
                             Stays NULL for pre-migration rows.

Both changes are expand-safe: no contract step required.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signup_requests",
        sa.Column(
            "accepted_disclaimers",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "signup_requests",
        sa.Column(
            "disclaimers_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("signup_requests", "disclaimers_accepted_at")
    op.drop_column("signup_requests", "accepted_disclaimers")
