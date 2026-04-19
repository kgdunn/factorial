"""SQLAlchemy model for per-user balance (dollars + tokens)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserBalance(Base):
    """Prepaid balance a user can draw LLM spend against.

    ``balance_usd`` is billable dollars; ``balance_tokens`` is a separate
    quota expressed in raw Anthropic tokens. Admins top these up through
    the admin panel; consumption is not yet wired in (future work).
    """

    __tablename__ = "user_balances"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
        server_default="0",
    )
    balance_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
