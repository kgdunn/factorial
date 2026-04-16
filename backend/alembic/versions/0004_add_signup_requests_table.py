"""add signup_requests table for admin-approved registration

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("use_case", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("invite_token", sa.String(255), nullable=True, unique=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signup_requests_email", "signup_requests", ["email"], unique=True)
    op.create_index("ix_signup_requests_invite_token", "signup_requests", ["invite_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_signup_requests_invite_token", table_name="signup_requests")
    op.drop_index("ix_signup_requests_email", table_name="signup_requests")
    op.drop_table("signup_requests")
