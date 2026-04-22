"""SQLAlchemy model for fake-data simulators.

A :class:`Simulator` row is created when the agent's ``create_simulator``
tool succeeds. It stores the hidden ``private_state`` (seed + factor
specs + structural hints) that the agent loop re-injects on every
subsequent ``simulate_process`` or ``reveal_simulator`` call so the LLM
never has to carry the state itself.

``reveal_request_count`` tracks how many times the user has asked to
reveal the underlying model; the agent loop requires at least two
requests (or the ``simulator_reveal_force`` override) before dispatching
the tool with ``confirmed=True``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Simulator(Base):
    """A persisted fake-data simulator."""

    __tablename__ = "simulators"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # The ``sim_id`` returned to the LLM by the ``create_simulator`` tool.
    # Unique per row; used as the lookup key in the agent loop.
    sim_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # LLM-visible summary (factor ranges, output names, noise level, ...).
    public_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Hidden model spec: seed + factor specs + output specs + hints.
    # Never shipped to the LLM except via ``reveal_simulator`` after the
    # double-confirm gate passes.
    private_state: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Counts how many times ``reveal_simulator`` has been attempted for
    # this simulator. The agent loop resets to 0 after a successful
    # confirmed reveal so subsequent reveals also require two asks.
    reveal_request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversation = relationship("Conversation")
