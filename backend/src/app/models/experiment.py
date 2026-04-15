"""SQLAlchemy model for experiment persistence.

An Experiment is auto-created when the agent's ``generate_design`` tool
succeeds.  It stores the full design output (JSONB), factor specs, and
user-entered results so experiments survive browser sessions and support
incremental results entry.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExperimentStatus(enum.StrEnum):
    """Lifecycle status of an experiment."""

    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class Experiment(Base):
    """A persisted DOE experiment with design matrix and results."""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        default="Untitled Experiment",
        server_default="Untitled Experiment",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        server_default="draft",
    )
    design_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Factor specifications (e.g. [{name, type, low, high, units}, ...])
    factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Full generate_design tool output (design_coded, design_actual, run_order, etc.)
    design_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # User-entered results: [{run_index: 0, response_name: value}, ...]
    results_data: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Link to originating conversation (SET NULL on conversation delete)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    conversation = relationship("Conversation")
