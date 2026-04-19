"""initial unified schema

Revision ID: 0001
Revises:
Create Date: 2026-04-18

Creates the full application schema in a single revision: roles, users,
signup_requests, setup_tokens, conversations, messages, tool_calls,
experiments, and experiment_shares. The eight built-in roles are seeded
at the end of ``upgrade``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
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
    # -- roles ----------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    # -- users ----------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role_id", "users", ["role_id"])

    # -- signup_requests ------------------------------------------------------
    op.create_table(
        "signup_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("use_case", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("requested_role", sa.String(255), nullable=True),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("invite_token", sa.String(255), nullable=True, unique=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signup_requests_email", "signup_requests", ["email"], unique=True)
    op.create_index("ix_signup_requests_invite_token", "signup_requests", ["invite_token"], unique=True)

    # -- setup_tokens ---------------------------------------------------------
    op.create_table(
        "setup_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
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

    # -- conversations --------------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("model_key", sa.String(100), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("total_input_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("total_output_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("message_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(14, 10), server_default="0", nullable=False),
        sa.Column("total_markup_cost_usd", sa.Numeric(14, 10), server_default="0", nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("starred", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    # -- messages -------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, server_default="", nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("tool_use_id", sa.String(100), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_input", sa.JSON, nullable=True),
        sa.Column("is_tool_result", sa.Boolean, server_default="false", nullable=False),
        sa.Column("input_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer, server_default="0", nullable=False),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("stop_reason", sa.String(50), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("input_rate_usd_per_mtok", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_rate_usd_per_mtok", sa.Numeric(12, 6), nullable=True),
        sa.Column("input_cost_usd", sa.Numeric(14, 10), nullable=True),
        sa.Column("output_cost_usd", sa.Numeric(14, 10), nullable=True),
        sa.Column("markup_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("markup_cost_usd", sa.Numeric(14, 10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    # -- tool_calls -----------------------------------------------------------
    op.create_table(
        "tool_calls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_use_id", sa.String(100), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_input", sa.JSON, nullable=True),
        sa.Column("tool_output", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), server_default="success", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("agent_turn", sa.Integer, server_default="1", nullable=False),
        sa.Column("call_order", sa.Integer, server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tool_calls_conversation_id", "tool_calls", ["conversation_id"])

    # -- experiments ----------------------------------------------------------
    op.create_table(
        "experiments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), server_default="Untitled Experiment", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("design_type", sa.String(100), nullable=True),
        sa.Column("factors", sa.JSON, nullable=True),
        sa.Column("design_data", sa.JSON, nullable=True),
        sa.Column("results_data", sa.JSON, nullable=True),
        sa.Column("evaluation_data", sa.JSON, nullable=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_experiments_user_id", "experiments", ["user_id"])
    op.create_index("ix_experiments_conversation_id", "experiments", ["conversation_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])

    # -- experiment_shares ----------------------------------------------------
    op.create_table(
        "experiment_shares",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "experiment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("allow_results", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_experiment_shares_experiment_id", "experiment_shares", ["experiment_id"])
    op.create_index("ix_experiment_shares_token", "experiment_shares", ["token"], unique=True)
    op.create_index("ix_experiment_shares_exp_revoked", "experiment_shares", ["experiment_id", "revoked_at"])

    # -- tool_usage -----------------------------------------------------------
    # Per-identity, per-day CPU-time accounting for the tool bridge and the
    # hosted MCP endpoint. ``user_id`` is NOT a foreign key so the synthetic
    # SERVICE_USER_ID (shared X-API-Key identity) can write here.
    op.create_table(
        "tool_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("cpu_seconds_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_tool_usage_user_day"),
    )
    op.create_index("ix_tool_usage_user_id", "tool_usage", ["user_id"])
    op.create_index("ix_tool_usage_day", "tool_usage", ["day"])

    # -- seed built-in roles --------------------------------------------------
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


def downgrade() -> None:
    op.drop_index("ix_tool_usage_day", table_name="tool_usage")
    op.drop_index("ix_tool_usage_user_id", table_name="tool_usage")
    op.drop_table("tool_usage")

    op.drop_index("ix_experiment_shares_exp_revoked", table_name="experiment_shares")
    op.drop_index("ix_experiment_shares_token", table_name="experiment_shares")
    op.drop_index("ix_experiment_shares_experiment_id", table_name="experiment_shares")
    op.drop_table("experiment_shares")

    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_index("ix_experiments_conversation_id", table_name="experiments")
    op.drop_index("ix_experiments_user_id", table_name="experiments")
    op.drop_table("experiments")

    op.drop_index("ix_tool_calls_conversation_id", table_name="tool_calls")
    op.drop_table("tool_calls")

    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_setup_tokens_token", table_name="setup_tokens")
    op.drop_index("ix_setup_tokens_user_id", table_name="setup_tokens")
    op.drop_table("setup_tokens")

    op.drop_index("ix_signup_requests_invite_token", table_name="signup_requests")
    op.drop_index("ix_signup_requests_email", table_name="signup_requests")
    op.drop_table("signup_requests")

    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
